"""Publish queue — Issue #31.

The pipeline's `publisher` stage (packages/agents/pipeline/graph.py) used
to be a stub: a post approved via Issue #25's human-review flow would
sail straight through it to COMPLETED without anything actually being
posted to LinkedIn/X. This module is where that gap gets closed.

Two halves, deliberately kept apart:

  * This file (`publish_queue.py`) — the actual publish logic: resolve
    each of a Post's target platforms to a connected SocialAccount, call
    #30's SocialPublisher adapters (packages.integrations.registry.
    get_social_publisher), and record the outcome. Plain functions taking
    a Session, no Celery import anywhere — so it's fully unit-testable
    (mock the adapter, call publish_post(), assert on the Post/
    ContentCalendarEvent rows) without any Celery/Redis machinery
    running. Same separation apps/api/services/scheduling_suggestion.py
    already established for #28.
  * apps/api/worker.py — the thin Celery task wrapper around
    publish_post()/mark_post_failed() below, which is what actually gives
    this durability and retry-with-backoff: Celery's own
    autoretry_for/retry_backoff (built-in, not a hand-rolled backoff
    loop), backed by the Redis broker this repo already runs.

Retry/failure model:
  * publish_post() makes exactly ONE attempt across every target
    platform that hasn't already succeeded on an earlier attempt (see
    `_already_published`, keyed off Post.publish_results — makes retries
    idempotent: a platform that published fine on attempt 1 is never
    re-published just because a sibling platform failed and the whole
    post gets retried).
  * If every platform succeeds (or there are none), it returns normally.
  * If ANY platform's attempt fails — for any reason: a genuinely
    transient error (rate limit, network blip) or one that will never
    succeed (revoked token, no connected account) — it records that
    platform's error and raises PublishAttemptFailed. Callers (the
    Celery task) are expected to retry this exact call with backoff.
    There is no upfront transient/permanent classification: #30's
    SocialPublisher.publish() only ever returns a plain error string
    (see packages/integrations/social/base.py's PublishResult
    docstring), not a structured status code, so there's nothing
    reliable to classify on. A failure that's genuinely permanent just
    keeps failing on every retry and ends up in mark_post_failed() once
    attempts are exhausted — functionally identical to "retried until
    the cap, then given up", which is exactly what the issue asks for.
  * mark_post_failed() is called once — by apps/api/worker.py's
    Task.on_failure, itself called by Celery exactly once, after the
    final failed attempt (whether that's because retries were exhausted
    or a non-retryable exception) — to set the terminal FAILED state.
    Nothing about *that* state is inferred mid-retry; every attempt's
    error is already visible on Post.publish_results/publish_error as it
    happens (see module-level "not silently dropped" requirement in the
    issue), this just flips the terminal marker once retrying is over.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.orm import Session

from apps.api.models import (
    CalendarEventStatus,
    ContentCalendarEvent,
    PipelineStage,
    Post,
    SocialAccount,
    SocialAccountStatus,
    SocialPlatform,
)
from packages.integrations.registry import get_social_publisher
from packages.integrations.social.encryption import decrypt_token, encrypt_token

logger = logging.getLogger(__name__)


class PostNotFoundError(Exception):
    """Raised when publish_post()/mark_post_failed() is asked to act on a
    post_id that doesn't resolve to a Post row — a programming/data error
    (the Celery task was enqueued with a bad id), not a publish failure."""


class PublishAttemptFailed(Exception):
    """Raised by publish_post() when at least one of a post's target
    platforms failed on this attempt. Callers that want durable retry
    (apps/api/worker.py's Celery task) are expected to retry the call —
    see module docstring for why this doesn't try to distinguish
    transient from permanent failures upfront."""


def _target_platforms(post: Post) -> list[str]:
    """A Post carries no explicit `target_platforms` column of its own —
    Post.body_text (written by the Generation Engine, Issue #21) is
    already keyed by exactly the platforms its creative_brief targeted,
    so that's the single source of truth here too, for both
    calendar-scheduled and ad-hoc posts."""
    if not post.body_text:
        return []
    return list(post.body_text.keys())


def _already_published(post: Post, platform: str) -> bool:
    results = post.publish_results or {}
    entry = results.get(platform)
    return isinstance(entry, dict) and entry.get("status") == "published"


def _mark_calendar_event(db: Session, post: Post, status: CalendarEventStatus) -> None:
    """Keeps the linked ContentCalendarEvent (Issue #26/#27) — which
    already has PUBLISHED/FAILED terminal states of its own, unused until
    now — in sync with the outcome of this post's publish. A no-op for an
    ad-hoc post with no calendar_event_id."""
    if post.calendar_event_id is None:
        return
    event = db.get(ContentCalendarEvent, post.calendar_event_id)
    if event is None:
        return
    event.status = status


def publish_post(db: Session, post_id: uuid.UUID) -> None:
    """Makes one publish attempt, across every target platform that
    hasn't already succeeded, for the given post. Raises
    PublishAttemptFailed if any platform failed on this attempt (after
    persisting every attempt's per-platform result/error so nothing is
    silently dropped) — see module docstring for the full retry model.
    """
    post = db.get(Post, post_id)
    if post is None:
        raise PostNotFoundError(f"No Post found for post_id={post_id!r}")

    platforms = _target_platforms(post)
    results: dict[str, dict] = dict(post.publish_results or {})
    errors: dict[str, str] = {}

    for platform in platforms:
        if _already_published(post, platform):
            continue

        content = post.body_text.get(platform) if post.body_text else None
        if not content:
            error = f"No generated copy for platform {platform!r}"
            errors[platform] = error
            results[platform] = {"status": "failed", "error": error}
            continue

        try:
            social_platform = SocialPlatform(platform)
        except ValueError:
            error = f"Unsupported publishing platform {platform!r}"
            errors[platform] = error
            results[platform] = {"status": "failed", "error": error}
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
            error = f"No active {platform} account connected for this brand"
            errors[platform] = error
            results[platform] = {"status": "failed", "error": error}
            continue

        publisher = get_social_publisher(platform)
        access_token = decrypt_token(account.access_token_encrypted)
        refresh_token = (
            decrypt_token(account.refresh_token_encrypted)
            if account.refresh_token_encrypted
            else None
        )

        result = publisher.publish(
            access_token=access_token, content=content, refresh_token=refresh_token
        )

        if result.refreshed_tokens is not None:
            # publish() transparently refreshed an expired token to
            # succeed (or to retry after failing once) — persist the new
            # one so the *next* attempt (this platform or any future
            # publish) doesn't have to refresh again.
            account.access_token_encrypted = encrypt_token(result.refreshed_tokens.access_token)
            if result.refreshed_tokens.refresh_token:
                account.refresh_token_encrypted = encrypt_token(
                    result.refreshed_tokens.refresh_token
                )
            account.token_expires_at = result.refreshed_tokens.expires_at

        if result.success:
            results[platform] = {
                "status": "published",
                "platform_post_id": result.platform_post_id,
                "platform_post_url": result.platform_post_url,
            }
        else:
            error = result.error or f"{platform} publish failed with no error detail"
            errors[platform] = error
            results[platform] = {"status": "failed", "error": error}

    post.publish_results = results
    db.flush()

    if errors:
        post.publish_error = "; ".join(f"{platform}: {error}" for platform, error in errors.items())
        db.flush()
        raise PublishAttemptFailed(post.publish_error)

    # Every target platform is now published (possibly across several
    # attempts) — clear any stale error from an earlier, since-recovered
    # attempt and mark the linked calendar event (if any) published.
    post.publish_error = None
    _mark_calendar_event(db, post, CalendarEventStatus.PUBLISHED)
    db.flush()


def mark_post_failed(db: Session, post_id: uuid.UUID, reason: str) -> None:
    """Sets the terminal FAILED state once retries are genuinely
    exhausted (see module docstring) — called from apps/api/worker.py's
    Task.on_failure, not from publish_post() itself, so a post that's
    still mid-retry never shows this terminal state prematurely."""
    post = db.get(Post, post_id)
    if post is None:
        raise PostNotFoundError(f"No Post found for post_id={post_id!r}")

    post.current_pipeline_stage = PipelineStage.FAILED
    post.publish_error = reason
    _mark_calendar_event(db, post, CalendarEventStatus.FAILED)
    db.flush()


def enqueue_publish(post_id: uuid.UUID) -> None:
    """Hands an approved post off to the durable, Redis-backed publish
    queue (apps/api/worker.py's Celery task). The pipeline's `publisher`
    node (packages/agents/pipeline/graph.py) calls this — its one job is
    making sure the handoff genuinely happens, not doing the publish
    itself or waiting for it to finish.

    Imports apps.api.worker locally rather than at module level: worker.py
    imports this module (to call publish_post/mark_post_failed from
    inside its Celery task), so a top-level import here would be a
    circular import.
    """
    from apps.api.worker import publish_post_task

    publish_post_task.delay(str(post_id))
