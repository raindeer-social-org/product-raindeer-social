"""Issue #33 — engagement-metrics polling jobs.

Per the issue's acceptance criteria, these tests exercise three things:

  1. A poll for a published post writes a new EngagementSnapshot row with
     accurate metrics (mocking the platform adapter, same shape #31's
     test_publish_queue.py already uses for SocialPublisher.publish).
  2. Calling poll_post_engagement multiple times over "time" produces
     multiple rows — a true time series, not an overwrite. Assertions
     check row *count* growing, never that the latest row's values just
     changed in place.
  3. A rate-limited (429) response from the platform is backed off rather
     than hammered or crashing the job: get_engagement() comes back
     rate_limited=True (never raises), poll_post_engagement() turns that
     into EngagementPollFailed, and apps/api/worker.py's Celery task is
     configured with autoretry_for/retry_backoff on exactly that
     exception — mirroring #31's publish_post_task retry-configuration
     test below.

Most of this exercises apps/api/services/engagement_polling.py's
functions directly — no Celery/Redis involved — per the same
unit-testable-without-that-machinery goal #31's publish queue has. A
couple of tests at the bottom check apps/api/worker.py's Celery task
wrappers: their retry configuration, and the beat-sweep fan-out.
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest

from apps.api.models import (
    Brand,
    Organization,
    Post,
    SocialAccount,
    SocialAccountStatus,
    SocialPlatform,
)
from apps.api.services import engagement_polling
from packages.integrations.social.base import EngagementMetrics, EngagementResult
from packages.integrations.social.encryption import encrypt_token


def _setup_brand(db_session) -> Brand:
    org = Organization(name="Acme Agency")
    db_session.add(org)
    db_session.flush()
    brand = Brand(organization_id=org.id, name="Acme Widgets")
    db_session.add(brand)
    db_session.flush()
    return brand


def _connect_linkedin(
    db_session, brand: Brand, status: SocialAccountStatus = SocialAccountStatus.ACTIVE
) -> SocialAccount:
    account = SocialAccount(
        brand_id=brand.id,
        platform=SocialPlatform.LINKEDIN,
        access_token_encrypted=encrypt_token("real-access-token"),
        status=status,
    )
    db_session.add(account)
    db_session.flush()
    return account


def _make_published_post(db_session, brand: Brand, platform_post_id: str = "123") -> Post:
    post = Post(
        brand_id=brand.id,
        body_text={"linkedin": "Hello world"},
        publish_results={
            "linkedin": {
                "status": "published",
                "platform_post_id": platform_post_id,
                "platform_post_url": f"https://linkedin.com/p/{platform_post_id}",
            }
        },
    )
    db_session.add(post)
    db_session.flush()
    return post


# --- poll_post_engagement: writes an accurate snapshot ---------------------


def test_poll_writes_snapshot_with_accurate_metrics(db_session) -> None:
    brand = _setup_brand(db_session)
    _connect_linkedin(db_session, brand)
    post = _make_published_post(db_session, brand)

    publisher = MagicMock()
    publisher.get_engagement.return_value = EngagementResult(
        success=True,
        metrics=EngagementMetrics(likes=10, comments=2, shares=1, impressions=500),
    )

    with patch.object(engagement_polling, "get_social_publisher", return_value=publisher):
        snapshots = engagement_polling.poll_post_engagement(db_session, post.id)

    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot.post_id == post.id
    assert snapshot.platform == "linkedin"
    assert snapshot.likes == 10
    assert snapshot.comments == 2
    assert snapshot.shares == 1
    assert snapshot.impressions == 500
    assert snapshot.polled_at is not None

    publisher.get_engagement.assert_called_once_with(
        access_token="real-access-token", platform_post_id="123"
    )


def test_poll_only_covers_platforms_actually_published(db_session) -> None:
    """A platform present in Post.publish_results but not marked
    "published" (e.g. it failed) has nothing to poll — only the platforms
    that actually succeeded a publish attempt are engagement-pollable."""
    brand = _setup_brand(db_session)
    _connect_linkedin(db_session, brand)
    post = Post(
        brand_id=brand.id,
        body_text={"linkedin": "Hello world", "x": "Hello world"},
        publish_results={
            "linkedin": {"status": "published", "platform_post_id": "123"},
            "x": {"status": "failed", "error": "Unsupported publishing platform 'x'"},
        },
    )
    db_session.add(post)
    db_session.flush()

    publisher = MagicMock()
    publisher.get_engagement.return_value = EngagementResult(
        success=True,
        metrics=EngagementMetrics(likes=1, comments=0, shares=0, impressions=10),
    )

    with patch.object(engagement_polling, "get_social_publisher", return_value=publisher):
        snapshots = engagement_polling.poll_post_engagement(db_session, post.id)

    assert len(snapshots) == 1
    assert snapshots[0].platform == "linkedin"
    publisher.get_engagement.assert_called_once()


def test_poll_missing_post_raises(db_session) -> None:
    with pytest.raises(engagement_polling.PostNotFoundError):
        engagement_polling.poll_post_engagement(db_session, uuid.uuid4())


def test_poll_no_connected_account_raises_and_writes_nothing(db_session) -> None:
    brand = _setup_brand(db_session)
    post = _make_published_post(db_session, brand)

    with pytest.raises(engagement_polling.EngagementPollFailed, match="No active linkedin account"):
        engagement_polling.poll_post_engagement(db_session, post.id)

    rows = engagement_polling.find_posts_due_for_polling(db_session)
    assert post.id in rows  # still due — nothing was recorded for it


# --- true time series: repeated polls append, never overwrite --------------


def test_repeated_polls_append_rows_not_overwrite(db_session) -> None:
    """Calling poll_post_engagement multiple times over "time" must grow
    the row count each time — never just update a single row's values in
    place."""
    brand = _setup_brand(db_session)
    _connect_linkedin(db_session, brand)
    post = _make_published_post(db_session, brand)

    publisher = MagicMock()
    publisher.get_engagement.side_effect = [
        EngagementResult(
            success=True, metrics=EngagementMetrics(likes=5, comments=1, shares=0, impressions=100)
        ),
        EngagementResult(
            success=True, metrics=EngagementMetrics(likes=12, comments=3, shares=1, impressions=250)
        ),
        EngagementResult(
            success=True, metrics=EngagementMetrics(likes=20, comments=4, shares=2, impressions=400)
        ),
    ]

    with patch.object(engagement_polling, "get_social_publisher", return_value=publisher):
        engagement_polling.poll_post_engagement(db_session, post.id)
        engagement_polling.poll_post_engagement(db_session, post.id)
        engagement_polling.poll_post_engagement(db_session, post.id)

    from apps.api.models import EngagementSnapshot

    rows = (
        db_session.query(EngagementSnapshot)
        .filter(EngagementSnapshot.post_id == post.id)
        .order_by(EngagementSnapshot.likes)
        .all()
    )
    assert len(rows) == 3
    assert [row.likes for row in rows] == [5, 12, 20]
    # Every row is a distinct id — genuinely separate rows, not one row
    # mutated three times.
    assert len({row.id for row in rows}) == 3


# --- rate limiting: backed off, not hammered or crashed ---------------------


def test_rate_limited_response_backs_off_without_crashing(db_session) -> None:
    brand = _setup_brand(db_session)
    _connect_linkedin(db_session, brand)
    post = _make_published_post(db_session, brand)

    publisher = MagicMock()
    publisher.get_engagement.return_value = EngagementResult(
        success=False, error="LinkedIn rate-limited this engagement request", rate_limited=True
    )

    with patch.object(engagement_polling, "get_social_publisher", return_value=publisher):
        with pytest.raises(engagement_polling.EngagementPollFailed, match="rate"):
            engagement_polling.poll_post_engagement(db_session, post.id)

    # A single rate-limited call, not hammered with immediate retries
    # inside poll_post_engagement itself — durable retry is Celery's job
    # (apps/api/worker.py's autoretry_for/retry_backoff), exercised below.
    publisher.get_engagement.assert_called_once()

    from apps.api.models import EngagementSnapshot

    assert (
        db_session.query(EngagementSnapshot).filter(EngagementSnapshot.post_id == post.id).count()
        == 0
    )


def test_rate_limited_then_recovers_writes_snapshot_on_retry(db_session) -> None:
    brand = _setup_brand(db_session)
    _connect_linkedin(db_session, brand)
    post = _make_published_post(db_session, brand)

    publisher = MagicMock()
    publisher.get_engagement.side_effect = [
        EngagementResult(success=False, error="429 Too Many Requests", rate_limited=True),
        EngagementResult(
            success=True, metrics=EngagementMetrics(likes=3, comments=0, shares=0, impressions=50)
        ),
    ]

    with patch.object(engagement_polling, "get_social_publisher", return_value=publisher):
        with pytest.raises(engagement_polling.EngagementPollFailed):
            engagement_polling.poll_post_engagement(db_session, post.id)

        # Attempt 2 — what Celery's autoretry_for would trigger after
        # backing off — succeeds.
        snapshots = engagement_polling.poll_post_engagement(db_session, post.id)

    assert len(snapshots) == 1
    assert snapshots[0].likes == 3
    assert publisher.get_engagement.call_count == 2


# --- find_posts_due_for_polling ---------------------------------------------


def test_find_posts_due_for_polling_only_returns_published_posts(db_session) -> None:
    brand = _setup_brand(db_session)
    published = _make_published_post(db_session, brand, platform_post_id="pub-1")

    never_published = Post(brand_id=brand.id, body_text={"linkedin": "Draft"})
    db_session.add(never_published)

    failed_only = Post(
        brand_id=brand.id,
        body_text={"linkedin": "Failed"},
        publish_results={"linkedin": {"status": "failed", "error": "boom"}},
    )
    db_session.add(failed_only)
    db_session.flush()

    due = engagement_polling.find_posts_due_for_polling(db_session)

    assert published.id in due
    assert never_published.id not in due
    assert failed_only.id not in due


# --- worker.py: Celery task wiring -----------------------------------------


def test_poll_post_engagement_task_retry_configuration() -> None:
    from apps.api import worker

    assert worker.poll_post_engagement_task.autoretry_for == (
        engagement_polling.EngagementPollFailed,
    )
    assert worker.poll_post_engagement_task.max_retries == worker.ENGAGEMENT_MAX_RETRIES
    assert worker.poll_post_engagement_task.retry_backoff == worker.ENGAGEMENT_RETRY_BACKOFF_BASE
    assert worker.poll_post_engagement_task.retry_backoff_max == worker.ENGAGEMENT_RETRY_BACKOFF_MAX
    assert worker.poll_post_engagement_task.retry_jitter is True


def test_beat_schedule_registers_poll_engagement() -> None:
    from apps.api import worker

    entry = worker.celery_app.conf.beat_schedule["poll-engagement"]
    assert entry["task"] == "worker.poll_engagement"
    assert entry["schedule"] == worker.ENGAGEMENT_POLL_INTERVAL_SECONDS


def test_poll_engagement_task_fans_out_one_task_per_due_post(db_session, monkeypatch) -> None:
    from apps.api import worker

    brand = _setup_brand(db_session)
    post = _make_published_post(db_session, brand)

    monkeypatch.setattr(worker, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)

    with patch.object(worker, "poll_post_engagement_task") as mock_task:
        result = worker.poll_engagement_task.run()

    assert result == 1
    mock_task.delay.assert_called_once_with(str(post.id))


def test_poll_post_engagement_task_run_success(db_session, monkeypatch) -> None:
    """Runs the task's underlying function body directly (`.run`, not
    `.delay`/`.apply`) so this exercises apps/api/worker.py's own
    db-session/commit handling without needing Celery/Redis machinery."""
    from apps.api import worker

    brand = _setup_brand(db_session)
    _connect_linkedin(db_session, brand)
    post = _make_published_post(db_session, brand)

    monkeypatch.setattr(worker, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)

    publisher = MagicMock()
    publisher.get_engagement.return_value = EngagementResult(
        success=True, metrics=EngagementMetrics(likes=7, comments=1, shares=0, impressions=99)
    )
    with patch.object(engagement_polling, "get_social_publisher", return_value=publisher):
        worker.poll_post_engagement_task.run(str(post.id))

    from apps.api.models import EngagementSnapshot

    rows = (
        db_session.query(EngagementSnapshot).filter(EngagementSnapshot.post_id == post.id).all()
    )
    assert len(rows) == 1
    assert rows[0].likes == 7


def test_poll_post_engagement_task_run_failure_reraises_for_celery_retry(
    db_session, monkeypatch
) -> None:
    from apps.api import worker

    brand = _setup_brand(db_session)
    post = _make_published_post(db_session, brand)  # no connected account

    monkeypatch.setattr(worker, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)

    with pytest.raises(engagement_polling.EngagementPollFailed):
        worker.poll_post_engagement_task.run(str(post.id))
