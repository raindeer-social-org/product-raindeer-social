"""Engagement polling — Issue #33.

Per-platform polling jobs that fetch likes/comments/shares/impressions
for published posts and write EngagementSnapshot rows on a schedule — a
true time series (one row appended per poll, never an overwrite of a
previous row; see apps/api/models/engagement_snapshot.py).

Same two-halves split #31's publish queue established
(apps/api/services/publish_queue.py's module docstring):

  * This file — the actual polling logic: find every Post with at least
    one platform successfully published (Post.publish_results, #31),
    resolve each published platform to a connected SocialAccount, call
    #30's SocialPublisher.get_engagement() adapters
    (packages.integrations.registry.get_social_publisher), and append an
    EngagementSnapshot row per successful fetch. Plain functions taking a
    Session, no Celery import anywhere — fully unit-testable without any
    Celery/Redis machinery running.
  * apps/api/worker.py — the thin Celery Beat + task wrapper around
    find_posts_due_for_polling()/poll_post_engagement() below, which is
    what actually gives this its schedule and its rate-limit backoff:
    Celery's own autoretry_for/retry_backoff (built-in, not a hand-rolled
    backoff loop) — the same mechanism, and the same reasoning, #31's
    publish_post_task already uses.

Unlike publish_post() (#31), a poll attempt has no notion of "already
succeeded, don't repeat" to protect: publishing a platform twice would be
a real duplicate post, but polling engagement twice just produces two
data points close together in time, which is exactly what a time series
is for. So poll_post_engagement() makes no attempt to skip platforms a
previous, still-retrying attempt already polled successfully this
round — every platform is (re)polled on every attempt, and every
successful fetch's snapshot row is committed regardless of whether a
sibling platform's fetch on that same attempt failed.

Rate limits: get_engagement() never raises for a rate-limited response
(HTTP 429) — it comes back as EngagementResult(success=False,
rate_limited=True), same "adapter never raises, caller decides" shape
#30's publish() already uses for ordinary failures. This module turns
that (like any other per-platform failure) into EngagementPollFailed,
which apps/api/worker.py's Celery task retries with exponential backoff
via autoretry_for/retry_backoff — so a rate-limited platform is backed
off and retried later, never hammered with immediate retries, and never
crashes the poll for a post's other platforms or for other posts in the
same sweep (find_posts_due_for_polling() fans out one Celery task per
post; one post's task raising/retrying doesn't affect any other post's).
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.orm import Session

from apps.api.models import (
    EngagementSnapshot,
    Post,
    SocialAccount,
    SocialAccountStatus,
    SocialPlatform,
)
from packages.integrations.registry import get_social_publisher
from packages.integrations.social.encryption import decrypt_token

logger = logging.getLogger(__name__)


class PostNotFoundError(Exception):
    """Raised when poll_post_engagement() is asked to act on a post_id
    that doesn't resolve to a Post row — a programming/data error (the
    Celery task was enqueued with a bad id), not a polling failure."""


class EngagementPollFailed(Exception):
    """Raised by poll_post_engagement() when at least one of a post's
    published platforms failed to return engagement data on this attempt
    (including being rate-limited). Callers that want durable retry
    (apps/api/worker.py's Celery task) are expected to retry the call —
    see module docstring for why every platform is simply re-polled on
    retry rather than skipping ones that already succeeded."""


def _published_platforms(post: Post) -> dict[str, str]:
    """Returns {platform: platform_post_id} for every platform this post
    actually succeeded in publishing to, per Post.publish_results (#31) —
    the only platforms there's anything to poll engagement for. A post
    that hasn't published anywhere yet (or only has failed attempts)
    yields an empty dict."""
    results = post.publish_results or {}
    out: dict[str, str] = {}
    for platform, entry in results.items():
        if (
            isinstance(entry, dict)
            and entry.get("status") == "published"
            and entry.get("platform_post_id")
        ):
            out[platform] = entry["platform_post_id"]
    return out


def find_posts_due_for_polling(db: Session) -> list[uuid.UUID]:
    """Every Post with at least one platform successfully published is
    due for a poll on every scheduled sweep. Unlike #29's pipeline
    trigger there's no one-shot "claim" step guarding against
    re-triggering — engagement metrics change continuously for the
    lifetime of a post, so the same post is legitimately, deliberately
    polled again on every sweep, each poll simply appending another
    EngagementSnapshot row."""
    rows = db.query(Post.id, Post.publish_results).filter(Post.publish_results.isnot(None)).all()
    return [
        post_id
        for post_id, publish_results in rows
        if any(
            isinstance(entry, dict) and entry.get("status") == "published"
            for entry in (publish_results or {}).values()
        )
    ]


def poll_post_engagement(db: Session, post_id: uuid.UUID) -> list[EngagementSnapshot]:
    """Makes one polling attempt, across every platform this post has
    successfully published to, appending an EngagementSnapshot row for
    each platform whose fetch succeeds. Raises EngagementPollFailed if
    any platform's fetch failed on this attempt (after committing every
    successful platform's snapshot row so nothing is silently dropped) —
    see module docstring for the full retry model."""
    post = db.get(Post, post_id)
    if post is None:
        raise PostNotFoundError(f"No Post found for post_id={post_id!r}")

    platforms = _published_platforms(post)
    snapshots: list[EngagementSnapshot] = []
    errors: dict[str, str] = {}

    for platform, platform_post_id in platforms.items():
        try:
            social_platform = SocialPlatform(platform)
        except ValueError:
            errors[platform] = f"Unsupported engagement-polling platform {platform!r}"
            continue

        account = (
            db.query(SocialAccount)
            .filter(SocialAccount.brand_id == post.brand_id, SocialAccount.platform == social_platform)
            .first()
        )
        if (
            account is None
            or account.access_token_encrypted is None
            or account.status != SocialAccountStatus.ACTIVE
        ):
            errors[platform] = f"No active {platform} account connected for this brand"
            continue

        publisher = get_social_publisher(platform)
        access_token = decrypt_token(account.access_token_encrypted)

        result = publisher.get_engagement(
            access_token=access_token, platform_post_id=platform_post_id
        )

        if not result.success or result.metrics is None:
            error = result.error or f"{platform} engagement fetch failed with no error detail"
            errors[platform] = error
            continue

        snapshot = EngagementSnapshot(
            post_id=post.id,
            platform=platform,
            likes=result.metrics.likes,
            comments=result.metrics.comments,
            shares=result.metrics.shares,
            impressions=result.metrics.impressions,
        )
        db.add(snapshot)
        db.flush()
        snapshots.append(snapshot)

    if errors:
        raise EngagementPollFailed(
            "; ".join(f"{platform}: {error}" for platform, error in errors.items())
        )

    return snapshots
