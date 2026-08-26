"""Issue #31 — the publish queue.

Per the issue's acceptance criteria, these tests exercise three things:

  1. A transient failure (e.g. a 429) retries and eventually succeeds.
  2. A failure that never recovers lands the post on status=failed (here:
     Post.current_pipeline_stage == PipelineStage.FAILED, plus the linked
     ContentCalendarEvent's status — see apps/api/models/
     content_calendar_event.py's already-unused PUBLISHED/FAILED values)
     only once retries are exhausted, with the reason recorded on
     Post.publish_error/publish_results — never silently dropped.
  3. Approved posts are picked up without a manual trigger: the
     human-review approve endpoint (#25) resumes the pipeline graph,
     which now runs a real `publisher` node
     (packages/agents/pipeline/graph.py) that hands the post straight to
     this queue.

Most of this exercises apps/api/services/publish_queue.py's functions
directly — no Celery/Redis involved — per the issue's explicit ask that
the service be unit-testable without that machinery running. A couple of
tests at the bottom check apps/api/worker.py's Celery task wrapper: its
retry configuration, and that its on_failure hook is what actually flips
a post to the terminal failed state.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from apps.api.auth.jwt import create_access_token, hash_password
from apps.api.main import app
from apps.api.models import (
    Brand,
    CalendarEventStatus,
    ContentCalendarEvent,
    Organization,
    PipelineStage,
    Post,
    SocialAccount,
    SocialAccountStatus,
    SocialPlatform,
    User,
    UserRole,
)
from apps.api.services import publish_queue
from packages.agents.pipeline.checkpointer import get_postgres_checkpointer
from packages.agents.pipeline.graph import run_pipeline
from packages.integrations.social.base import PublishResult
from packages.integrations.social.encryption import encrypt_token

client = TestClient(app)
uses_test_session = pytest.mark.usefixtures("override_get_db")


def _setup_brand(db_session) -> Brand:
    org = Organization(name="Acme Agency")
    db_session.add(org)
    db_session.flush()
    brand = Brand(organization_id=org.id, name="Acme Widgets")
    db_session.add(brand)
    db_session.flush()
    return brand


def _connect_linkedin(db_session, brand: Brand, status: SocialAccountStatus = SocialAccountStatus.ACTIVE) -> SocialAccount:
    account = SocialAccount(
        brand_id=brand.id,
        platform=SocialPlatform.LINKEDIN,
        access_token_encrypted=encrypt_token("real-access-token"),
        status=status,
    )
    db_session.add(account)
    db_session.flush()
    return account


def _make_post(db_session, brand: Brand, body_text: dict, calendar_event_id: uuid.UUID | None = None) -> Post:
    post = Post(brand_id=brand.id, body_text=body_text, calendar_event_id=calendar_event_id)
    db_session.add(post)
    db_session.flush()
    return post


def _make_calendar_event(db_session, brand: Brand) -> ContentCalendarEvent:
    event = ContentCalendarEvent(
        brand_id=brand.id,
        title="Launch post",
        target_platforms=["linkedin"],
        desired_format="text",
        target_datetime=datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc),
    )
    db_session.add(event)
    db_session.flush()
    return event


# --- publish_post: success ------------------------------------------------


def test_publish_post_success_marks_published(db_session) -> None:
    brand = _setup_brand(db_session)
    _connect_linkedin(db_session, brand)
    event = _make_calendar_event(db_session, brand)
    post = _make_post(db_session, brand, {"linkedin": "Hello world"}, calendar_event_id=event.id)

    publisher = MagicMock()
    publisher.publish.return_value = PublishResult(
        success=True, platform_post_id="123", platform_post_url="https://linkedin.com/p/123"
    )

    with patch.object(publish_queue, "get_social_publisher", return_value=publisher):
        publish_queue.publish_post(db_session, post.id)

    db_session.refresh(post)
    assert post.publish_error is None
    assert post.publish_results["linkedin"]["status"] == "published"
    assert post.publish_results["linkedin"]["platform_post_id"] == "123"

    db_session.refresh(event)
    assert event.status == CalendarEventStatus.PUBLISHED


def test_publish_post_skips_platform_already_published_on_a_prior_attempt(db_session) -> None:
    """Idempotency: a retry must never re-publish a platform that already
    succeeded on an earlier attempt."""
    brand = _setup_brand(db_session)
    _connect_linkedin(db_session, brand)
    post = _make_post(db_session, brand, {"linkedin": "Hello world"})
    post.publish_results = {"linkedin": {"status": "published", "platform_post_id": "already-there"}}
    db_session.flush()

    publisher = MagicMock()
    with patch.object(publish_queue, "get_social_publisher", return_value=publisher):
        publish_queue.publish_post(db_session, post.id)

    publisher.publish.assert_not_called()
    db_session.refresh(post)
    assert post.publish_results["linkedin"]["platform_post_id"] == "already-there"


# --- publish_post: transient failure then success (retry) -----------------


def test_transient_failure_then_retry_succeeds(db_session) -> None:
    brand = _setup_brand(db_session)
    _connect_linkedin(db_session, brand)
    post = _make_post(db_session, brand, {"linkedin": "Hello world"})

    publisher = MagicMock()
    publisher.publish.side_effect = [
        PublishResult(success=False, error="429 Too Many Requests"),
        PublishResult(success=True, platform_post_id="456", platform_post_url="https://linkedin.com/p/456"),
    ]

    with patch.object(publish_queue, "get_social_publisher", return_value=publisher):
        # Attempt 1 — transient failure.
        with pytest.raises(publish_queue.PublishAttemptFailed, match="429"):
            publish_queue.publish_post(db_session, post.id)

        db_session.refresh(post)
        assert post.publish_results["linkedin"]["status"] == "failed"
        assert "429" in post.publish_error
        # Still mid-retry — never prematurely marked as the terminal
        # failed stage.
        assert post.current_pipeline_stage != PipelineStage.FAILED

        # Attempt 2 (what Celery's autoretry_for would trigger) — succeeds.
        publish_queue.publish_post(db_session, post.id)

    db_session.refresh(post)
    assert post.publish_error is None
    assert post.publish_results["linkedin"]["status"] == "published"
    assert publisher.publish.call_count == 2


# --- publish_post: permanent failure across multiple platforms ------------


def test_partial_failure_raises_and_records_both_platform_outcomes(db_session) -> None:
    """linkedin has a connected account and succeeds; x isn't a supported
    SocialAccount platform yet (Issue #10/#25 scope), so it fails — a
    realistic "this post targets a platform with no connected account"
    permanent failure that never recovers on retry."""
    brand = _setup_brand(db_session)
    _connect_linkedin(db_session, brand)
    post = _make_post(db_session, brand, {"linkedin": "Hello world", "x": "Hello world"})

    publisher = MagicMock()
    publisher.publish.return_value = PublishResult(success=True, platform_post_id="789")

    with patch.object(publish_queue, "get_social_publisher", return_value=publisher):
        with pytest.raises(publish_queue.PublishAttemptFailed):
            publish_queue.publish_post(db_session, post.id)

    db_session.refresh(post)
    assert post.publish_results["linkedin"]["status"] == "published"
    assert post.publish_results["x"]["status"] == "failed"
    assert "x" in post.publish_error

    # Retrying again must not re-publish linkedin (already succeeded).
    with patch.object(publish_queue, "get_social_publisher", return_value=publisher):
        with pytest.raises(publish_queue.PublishAttemptFailed):
            publish_queue.publish_post(db_session, post.id)
    assert publisher.publish.call_count == 1  # only ever called for linkedin, once


def test_publish_post_no_connected_account_fails_with_reason(db_session) -> None:
    brand = _setup_brand(db_session)
    post = _make_post(db_session, brand, {"linkedin": "Hello world"})

    with pytest.raises(publish_queue.PublishAttemptFailed):
        publish_queue.publish_post(db_session, post.id)

    db_session.refresh(post)
    assert post.publish_results["linkedin"]["status"] == "failed"
    assert "No active linkedin account" in post.publish_error


def test_publish_post_revoked_account_fails(db_session) -> None:
    brand = _setup_brand(db_session)
    _connect_linkedin(db_session, brand, status=SocialAccountStatus.REVOKED)
    post = _make_post(db_session, brand, {"linkedin": "Hello world"})

    with pytest.raises(publish_queue.PublishAttemptFailed):
        publish_queue.publish_post(db_session, post.id)

    db_session.refresh(post)
    assert post.publish_results["linkedin"]["status"] == "failed"


def test_publish_post_missing_post_raises(db_session) -> None:
    with pytest.raises(publish_queue.PostNotFoundError):
        publish_queue.publish_post(db_session, uuid.uuid4())


# --- mark_post_failed: terminal state after retries exhausted -------------


def test_mark_post_failed_sets_terminal_stage_and_reason(db_session) -> None:
    brand = _setup_brand(db_session)
    event = _make_calendar_event(db_session, brand)
    post = _make_post(db_session, brand, {"linkedin": "Hello world"}, calendar_event_id=event.id)
    post.current_pipeline_stage = PipelineStage.COMPLETED
    db_session.flush()

    publish_queue.mark_post_failed(db_session, post.id, reason="linkedin: 401 invalid token")

    db_session.refresh(post)
    assert post.current_pipeline_stage == PipelineStage.FAILED
    assert post.publish_error == "linkedin: 401 invalid token"

    db_session.refresh(event)
    assert event.status == CalendarEventStatus.FAILED


def test_mark_post_failed_missing_post_raises(db_session) -> None:
    with pytest.raises(publish_queue.PostNotFoundError):
        publish_queue.mark_post_failed(db_session, uuid.uuid4(), reason="whatever")


# --- enqueue_publish --------------------------------------------------------


def test_enqueue_publish_delegates_to_celery_task() -> None:
    post_id = uuid.uuid4()
    with patch("apps.api.worker.publish_post_task") as mock_task:
        publish_queue.enqueue_publish(post_id)
    mock_task.delay.assert_called_once_with(str(post_id))


# --- worker.py: Celery task wiring -----------------------------------------


def test_publish_post_task_retry_configuration() -> None:
    from apps.api import worker

    assert worker.publish_post_task.autoretry_for == (publish_queue.PublishAttemptFailed,)
    assert worker.publish_post_task.max_retries == worker.PUBLISH_MAX_RETRIES
    assert worker.publish_post_task.retry_backoff == worker.PUBLISH_RETRY_BACKOFF_BASE
    assert worker.publish_post_task.retry_backoff_max == worker.PUBLISH_RETRY_BACKOFF_MAX
    assert worker.publish_post_task.retry_jitter is True


def test_on_failure_hook_ignores_calls_with_no_post_id(caplog) -> None:
    from apps.api import worker

    worker.publish_post_task.on_failure(RuntimeError("boom"), "task-id", (), {}, None)
    assert "no post_id" in caplog.text.lower()


def test_publish_post_task_run_success(db_session, monkeypatch) -> None:
    """Runs the task's underlying function body directly (`.run`, not
    `.delay`/`.apply`) so this exercises apps/api/worker.py's own
    db-session/commit handling without needing Celery/Redis machinery."""
    from apps.api import worker

    brand = _setup_brand(db_session)
    _connect_linkedin(db_session, brand)
    post = _make_post(db_session, brand, {"linkedin": "Hello world"})

    monkeypatch.setattr(worker, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)

    publisher = MagicMock()
    publisher.publish.return_value = PublishResult(success=True, platform_post_id="1")
    with patch.object(publish_queue, "get_social_publisher", return_value=publisher):
        worker.publish_post_task.run(str(post.id))

    db_session.refresh(post)
    assert post.publish_results["linkedin"]["status"] == "published"


def test_publish_post_task_run_failure_commits_partial_results_and_reraises(db_session, monkeypatch) -> None:
    from apps.api import worker

    brand = _setup_brand(db_session)
    post = _make_post(db_session, brand, {"linkedin": "Hello world"})

    monkeypatch.setattr(worker, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)

    with pytest.raises(publish_queue.PublishAttemptFailed):
        worker.publish_post_task.run(str(post.id))

    db_session.refresh(post)
    assert post.publish_results["linkedin"]["status"] == "failed"


def test_on_failure_hook_marks_post_failed_once_retries_exhausted(db_session, monkeypatch) -> None:
    """Simulates what Celery does after autoretry_for's retries are
    exhausted: it calls Task.on_failure exactly once, with the exception
    from the final attempt. This is where "status=failed... only after
    retries are exhausted" actually gets set — see apps/api/worker.py's
    _PublishTask docstring."""
    from apps.api import worker

    brand = _setup_brand(db_session)
    post = _make_post(db_session, brand, {"linkedin": "Hello world"})

    # worker.py opens its own SessionLocal() rather than using the test's
    # db_session (same reason apps/api/config/database.py's get_db does) —
    # point it at this test's connection so the assertions below see it.
    monkeypatch.setattr(worker, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)  # keep the test's session alive

    exc = publish_queue.PublishAttemptFailed("linkedin: 401 invalid token, no refresh token")
    worker.publish_post_task.on_failure(exc, "task-id-123", (str(post.id),), {}, None)

    db_session.refresh(post)
    assert post.current_pipeline_stage == PipelineStage.FAILED
    assert post.publish_error == "linkedin: 401 invalid token, no refresh token"


# --- end-to-end: approve picks up publishing without a manual trigger -----


def _post_at_human_review(db_session, brand: Brand, thread_cleanup) -> Post:
    post = Post(brand_id=brand.id)
    db_session.add(post)
    db_session.flush()
    thread_cleanup.append(str(post.id))

    with get_postgres_checkpointer() as checkpointer:
        list(run_pipeline(db_session, post, checkpointer))

    db_session.refresh(post)
    assert post.current_pipeline_stage == PipelineStage.HUMAN_REVIEW
    return post


@pytest.fixture()
def thread_cleanup():
    thread_ids: list[str] = []
    yield thread_ids
    if not thread_ids:
        return
    with get_postgres_checkpointer() as checkpointer:
        for thread_id in thread_ids:
            checkpointer.delete_thread(thread_id)


def _auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(
        user_id=str(user.id), org_id=str(user.organization_id), role=user.role.value
    )
    return {"Authorization": f"Bearer {token}"}


@uses_test_session
def test_approving_a_post_enqueues_it_for_publishing_without_manual_trigger(
    db_session, thread_cleanup
) -> None:
    brand = _setup_brand(db_session)
    user = User(
        organization_id=brand.organization_id,
        email="editor@acme.test",
        password_hash=hash_password("test-password"),
        role=UserRole.EDITOR,
    )
    db_session.add(user)
    db_session.flush()

    post = _post_at_human_review(db_session, brand, thread_cleanup)

    with patch("packages.agents.pipeline.graph.enqueue_publish") as mock_enqueue:
        response = client.post(
            f"/brands/{brand.id}/review-queue/{post.id}/approve",
            json={},
            headers=_auth_headers(user),
        )

    assert response.status_code == 200
    assert response.json()["current_pipeline_stage"] == "completed"
    # No human ever called a publish/admin endpoint directly — the
    # pipeline's publisher node reached this on its own as part of
    # resuming the graph.
    mock_enqueue.assert_called_once_with(post.id)
