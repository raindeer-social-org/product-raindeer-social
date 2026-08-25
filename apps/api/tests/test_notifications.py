"""Issue #32 — status notifications (email/Slack).

Per the issue's acceptance criteria and "How to test locally" section,
these exercise:

  1. A publish failure triggers a notification with accurate content
     (brand/post identifying info, the actual failure reason) to the
     right recipients (brand owners/admins, not every role) —
     `notify_publish_failure`.
  2. A post reaching ready_for_review notifies only the relevant
     reviewer(s) (owner/admin/editor — apps/api/routers/review.py's
     WRITE_ROLES), never the whole org (an org with owner/admin/editor/
     viewer users is used so a viewer leaking into the recipient list
     would actually be caught) — `notify_ready_for_review`.
  3. A broken webhook/SMTP failure is caught and never propagates out of
     the two `notify_*` entry points, nor out of the two real trigger
     points that call them: apps/api/worker.py's `_PublishTask.on_failure`
     (Issue #31) and packages/agents/pipeline/graph.py's `run_pipeline`
     (Issue #25's human_review interrupt).

Recipient resolution is exercised directly against `notify_publish_failure`/
`notify_ready_for_review` rather than by driving a real SMTP server/Slack
webhook — same "swap the adapter, not the caller" boundary the module
docstring describes. The two adapters (EmailAdapter/SlackWebhookAdapter)
get their own focused tests for the actual wire format.
"""

import uuid
from unittest.mock import MagicMock, patch

import httpx
import pytest

from apps.api.auth.jwt import hash_password
from apps.api.models import (
    Brand,
    Organization,
    PipelineStage,
    Post,
    User,
    UserRole,
)
from apps.api.services import notifications

# --- fixtures ---------------------------------------------------------------


def _setup_org_with_all_roles(db_session) -> tuple[Brand, dict[UserRole, User]]:
    """One org, one brand, and one user per role — exactly the shape the
    issue's acceptance criteria asks tests to use ("an org that has
    multiple users of different roles") so a notification that
    accidentally reaches the whole org (e.g. a viewer) is actually
    caught, not just theoretically possible."""
    org = Organization(name="Acme Agency")
    db_session.add(org)
    db_session.flush()

    brand = Brand(organization_id=org.id, name="Acme Widgets")
    db_session.add(brand)
    db_session.flush()

    users: dict[UserRole, User] = {}
    for role in UserRole:
        user = User(
            organization_id=org.id,
            email=f"{role.value}@acme.test",
            password_hash=hash_password("test-password"),
            role=role,
        )
        db_session.add(user)
        users[role] = user
    db_session.flush()

    return brand, users


def _make_post(db_session, brand: Brand, **kwargs) -> Post:
    post = Post(brand_id=brand.id, **kwargs)
    db_session.add(post)
    db_session.flush()
    return post


def _install_capturing_service(monkeypatch) -> list[notifications.Notification]:
    """Swaps notifications._build_default_service() for one whose only
    adapter records every Notification it's asked to send, instead of
    hitting real SMTP/Slack — lets tests assert on exactly what would
    have gone out without needing a mail server or webhook endpoint."""
    captured: list[notifications.Notification] = []
    capturing_adapter = MagicMock(spec=notifications.NotificationAdapter)
    capturing_adapter.send.side_effect = captured.append
    monkeypatch.setattr(
        notifications,
        "_build_default_service",
        lambda: notifications.NotificationService(adapters=[capturing_adapter]),
    )
    return captured


# --- notify_publish_failure: recipients + content ---------------------------


def test_publish_failure_notifies_owners_and_admins_only(db_session, monkeypatch) -> None:
    brand, users = _setup_org_with_all_roles(db_session)
    post = _make_post(
        db_session,
        brand,
        body_text={"linkedin": "Hello world"},
        publish_error="linkedin: 401 invalid token, no refresh token",
    )

    captured = _install_capturing_service(monkeypatch)
    notifications.notify_publish_failure(db_session, post)

    assert len(captured) == 1
    notification = captured[0]
    assert sorted(notification.recipients) == sorted(
        [users[UserRole.OWNER].email, users[UserRole.ADMIN].email]
    )
    # Not the whole org.
    assert users[UserRole.EDITOR].email not in notification.recipients
    assert users[UserRole.VIEWER].email not in notification.recipients


def test_publish_failure_notification_content_is_accurate(db_session, monkeypatch) -> None:
    brand, _users = _setup_org_with_all_roles(db_session)
    post = _make_post(
        db_session,
        brand,
        body_text={"linkedin": "Hello world"},
        publish_error="linkedin: 401 invalid token, no refresh token",
    )

    captured = _install_capturing_service(monkeypatch)
    notifications.notify_publish_failure(db_session, post)

    notification = captured[0]
    assert brand.name in notification.subject
    assert brand.name in notification.body
    assert str(post.id) in notification.body
    # The actual failure reason, not a generic "something went wrong".
    assert "401 invalid token, no refresh token" in notification.body


def test_publish_failure_notification_skipped_when_brand_missing(db_session, monkeypatch) -> None:
    """post.brand_id pointing at nothing (shouldn't happen, but must not
    crash the caller) is handled the same defensive way as everything
    else in this module. Deliberately never persisted — Post.brand_id
    has a real FK to brands, so a dangling id can only be exercised on an
    in-memory (never db.add'ed) instance, which is fine here since
    notify_publish_failure only ever reads post.brand_id/post.id, never
    re-queries the Post row itself."""
    post = Post(id=uuid.uuid4(), brand_id=uuid.uuid4(), publish_error="boom")

    captured = _install_capturing_service(monkeypatch)
    notifications.notify_publish_failure(db_session, post)

    assert captured == []


# --- notify_ready_for_review: recipients + content ---------------------------


def test_ready_for_review_notifies_reviewers_not_whole_org(db_session, monkeypatch) -> None:
    brand, users = _setup_org_with_all_roles(db_session)
    post = _make_post(db_session, brand, current_pipeline_stage=PipelineStage.HUMAN_REVIEW)

    captured = _install_capturing_service(monkeypatch)
    notifications.notify_ready_for_review(db_session, post)

    assert len(captured) == 1
    notification = captured[0]
    assert sorted(notification.recipients) == sorted(
        [
            users[UserRole.OWNER].email,
            users[UserRole.ADMIN].email,
            users[UserRole.EDITOR].email,
        ]
    )
    # The explicit acceptance criterion: not the whole org — a viewer
    # must never be in this list.
    assert users[UserRole.VIEWER].email not in notification.recipients


def test_ready_for_review_notification_content_is_accurate(db_session, monkeypatch) -> None:
    brand, _users = _setup_org_with_all_roles(db_session)
    post = _make_post(db_session, brand, current_pipeline_stage=PipelineStage.HUMAN_REVIEW)

    captured = _install_capturing_service(monkeypatch)
    notifications.notify_ready_for_review(db_session, post)

    notification = captured[0]
    assert brand.name in notification.subject
    assert brand.name in notification.body
    assert str(post.id) in notification.body


# --- notification failures must not crash the triggering job ---------------


def test_notify_publish_failure_swallows_adapter_exception(db_session, monkeypatch) -> None:
    brand, _users = _setup_org_with_all_roles(db_session)
    post = _make_post(db_session, brand, publish_error="boom")

    broken_adapter = MagicMock(spec=notifications.NotificationAdapter)
    broken_adapter.send.side_effect = RuntimeError("SMTP connection timed out")
    monkeypatch.setattr(
        notifications,
        "_build_default_service",
        lambda: notifications.NotificationService(adapters=[broken_adapter]),
    )

    # Must not raise — this is the whole point of the acceptance
    # criterion.
    notifications.notify_publish_failure(db_session, post)
    broken_adapter.send.assert_called_once()


def test_notify_ready_for_review_swallows_adapter_exception(db_session, monkeypatch) -> None:
    brand, _users = _setup_org_with_all_roles(db_session)
    post = _make_post(db_session, brand, current_pipeline_stage=PipelineStage.HUMAN_REVIEW)

    broken_adapter = MagicMock(spec=notifications.NotificationAdapter)
    broken_adapter.send.side_effect = httpx.ConnectError("connection refused")
    monkeypatch.setattr(
        notifications,
        "_build_default_service",
        lambda: notifications.NotificationService(adapters=[broken_adapter]),
    )

    notifications.notify_ready_for_review(db_session, post)
    broken_adapter.send.assert_called_once()


def test_notify_publish_failure_survives_recipient_resolution_blowing_up(
    db_session, monkeypatch
) -> None:
    """Even a bug in recipient resolution itself (not just the adapter)
    must not propagate — notify_publish_failure wraps its whole body, not
    just the adapter dispatch."""
    brand, _users = _setup_org_with_all_roles(db_session)
    post = _make_post(db_session, brand, publish_error="boom")

    monkeypatch.setattr(
        notifications,
        "_build_default_service",
        MagicMock(side_effect=RuntimeError("unexpected")),
    )

    notifications.notify_publish_failure(db_session, post)  # must not raise


def test_notification_service_send_continues_past_a_failing_adapter(db_session) -> None:
    """A failure in one adapter must not stop a second, working adapter
    from still getting its chance."""
    broken = MagicMock(spec=notifications.NotificationAdapter)
    broken.send.side_effect = RuntimeError("bad webhook URL")
    working = MagicMock(spec=notifications.NotificationAdapter)

    service = notifications.NotificationService(adapters=[broken, working])
    notification = notifications.Notification(subject="s", body="b", recipients=["a@b.com"])

    service.send(notification)  # must not raise

    broken.send.assert_called_once_with(notification)
    working.send.assert_called_once_with(notification)


# --- EmailAdapter -------------------------------------------------------------


def test_email_adapter_noops_when_smtp_not_configured() -> None:
    adapter = notifications.EmailAdapter(
        host=None, port=587, username=None, password=None, from_email=None
    )
    notification = notifications.Notification(subject="s", body="b", recipients=["a@b.com"])

    with patch("smtplib.SMTP") as mock_smtp:
        adapter.send(notification)
    mock_smtp.assert_not_called()


def test_email_adapter_noops_with_no_recipients() -> None:
    adapter = notifications.EmailAdapter(
        host="smtp.example.com",
        port=587,
        username=None,
        password=None,
        from_email="notify@raindeer.social",
    )
    notification = notifications.Notification(subject="s", body="b", recipients=[])

    with patch("smtplib.SMTP") as mock_smtp:
        adapter.send(notification)
    mock_smtp.assert_not_called()


def test_email_adapter_sends_via_smtp_when_configured() -> None:
    adapter = notifications.EmailAdapter(
        host="smtp.example.com",
        port=587,
        username="user",
        password="pass",
        from_email="notify@raindeer.social",
    )
    notification = notifications.Notification(
        subject="Publish failed", body="details here", recipients=["owner@acme.test"]
    )

    mock_conn = MagicMock()
    with patch("smtplib.SMTP") as mock_smtp:
        mock_smtp.return_value.__enter__.return_value = mock_conn
        adapter.send(notification)

    mock_conn.starttls.assert_called_once()
    mock_conn.login.assert_called_once_with("user", "pass")
    mock_conn.send_message.assert_called_once()
    sent_message = mock_conn.send_message.call_args[0][0]
    assert sent_message["Subject"] == "Publish failed"
    assert sent_message["To"] == "owner@acme.test"
    assert sent_message["From"] == "notify@raindeer.social"


def test_email_adapter_smtp_failure_propagates_to_caller_not_swallowed_here() -> None:
    """The adapter itself doesn't swallow failures — NotificationService
    is what's responsible for catching them (tested above), keeping this
    adapter simple and consistent with every other integrations
    adapter in this codebase (they raise; callers decide what to do)."""
    adapter = notifications.EmailAdapter(
        host="smtp.example.com",
        port=587,
        username=None,
        password=None,
        from_email="notify@raindeer.social",
    )
    notification = notifications.Notification(subject="s", body="b", recipients=["a@b.com"])

    with patch("smtplib.SMTP", side_effect=OSError("connection refused")):
        with pytest.raises(OSError):
            adapter.send(notification)


# --- SlackWebhookAdapter -------------------------------------------------------


def test_slack_adapter_noops_when_webhook_not_configured() -> None:
    adapter = notifications.SlackWebhookAdapter(webhook_url=None)
    notification = notifications.Notification(subject="s", body="b")

    with patch("httpx.post") as mock_post:
        adapter.send(notification)
    mock_post.assert_not_called()


def test_slack_adapter_posts_to_webhook_when_configured() -> None:
    adapter = notifications.SlackWebhookAdapter(webhook_url="https://hooks.slack.test/xyz")
    notification = notifications.Notification(subject="Publish failed", body="details here")

    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    with patch("httpx.post", return_value=mock_response) as mock_post:
        adapter.send(notification)

    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0] == "https://hooks.slack.test/xyz"
    assert "Publish failed" in kwargs["json"]["text"]
    assert "details here" in kwargs["json"]["text"]


def test_slack_adapter_bad_webhook_propagates_to_caller_not_swallowed_here() -> None:
    adapter = notifications.SlackWebhookAdapter(webhook_url="https://hooks.slack.test/broken")
    notification = notifications.Notification(subject="s", body="b")

    with patch("httpx.post", side_effect=httpx.ConnectError("connection refused")):
        with pytest.raises(httpx.ConnectError):
            adapter.send(notification)


# --- wiring: apps/api/worker.py's on_failure hook (Issue #31 trigger) ------


def test_on_failure_hook_fires_publish_failure_notification(db_session, monkeypatch) -> None:
    from apps.api import worker

    brand, _users = _setup_org_with_all_roles(db_session)
    post = _make_post(db_session, brand, body_text={"linkedin": "Hello world"})

    monkeypatch.setattr(worker, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)

    with patch.object(worker.notifications, "notify_publish_failure") as mock_notify:
        worker.publish_post_task.on_failure(
            RuntimeError("linkedin: 401 invalid token"), "task-id", (str(post.id),), {}, None
        )

    db_session.refresh(post)
    assert post.current_pipeline_stage == PipelineStage.FAILED
    mock_notify.assert_called_once()
    called_db, called_post = mock_notify.call_args[0]
    assert called_post.id == post.id


def test_on_failure_hook_completes_normally_when_notify_send_fails(
    db_session, monkeypatch
) -> None:
    """End-to-end version of the "must not crash the triggering job"
    acceptance criterion at the real worker.py trigger point: a broken
    adapter (not a mock of notify_publish_failure itself) must not stop
    on_failure from completing and leaving the post correctly FAILED."""
    from apps.api import worker

    brand, _users = _setup_org_with_all_roles(db_session)
    post = _make_post(db_session, brand, body_text={"linkedin": "Hello world"})

    monkeypatch.setattr(worker, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)

    broken_adapter = MagicMock(spec=notifications.NotificationAdapter)
    broken_adapter.send.side_effect = RuntimeError("SMTP connection timed out")
    monkeypatch.setattr(
        notifications,
        "_build_default_service",
        lambda: notifications.NotificationService(adapters=[broken_adapter]),
    )

    # Must not raise.
    worker.publish_post_task.on_failure(
        RuntimeError("linkedin: 401 invalid token"), "task-id", (str(post.id),), {}, None
    )

    db_session.refresh(post)
    assert post.current_pipeline_stage == PipelineStage.FAILED
    assert post.publish_error == "linkedin: 401 invalid token"
    broken_adapter.send.assert_called_once()


# --- wiring: run_pipeline reaching human_review (Issue #25 trigger) --------


@pytest.fixture()
def thread_cleanup():
    """Pipeline checkpoint rows live in Postgres on a connection totally
    separate from db_session's rolled-back transaction (same pattern as
    packages/agents/tests/test_pipeline_graph.py's fixture of the same
    name), so they need explicit teardown."""
    from packages.agents.pipeline.checkpointer import get_postgres_checkpointer

    thread_ids: list[str] = []
    yield thread_ids
    if not thread_ids:
        return
    with get_postgres_checkpointer() as checkpointer:
        for thread_id in thread_ids:
            checkpointer.delete_thread(thread_id)


def test_run_pipeline_fires_ready_for_review_notification_once(
    db_session, thread_cleanup
) -> None:
    from packages.agents.pipeline.checkpointer import get_postgres_checkpointer
    from packages.agents.pipeline.graph import run_pipeline

    org = Organization(name="Acme Agency")
    db_session.add(org)
    db_session.flush()
    brand = Brand(organization_id=org.id, name="Acme Widgets")
    db_session.add(brand)
    db_session.flush()

    post = Post(brand_id=brand.id)
    db_session.add(post)
    db_session.flush()
    thread_cleanup.append(str(post.id))

    with patch("packages.agents.pipeline.graph.notify_ready_for_review") as mock_notify:
        with get_postgres_checkpointer() as checkpointer:
            list(run_pipeline(db_session, post, checkpointer))

            db_session.refresh(post)
            assert post.current_pipeline_stage == PipelineStage.HUMAN_REVIEW
            mock_notify.assert_called_once_with(db_session, post)

            # Resuming past human_review (approve) must not re-fire it.
            list(run_pipeline(db_session, post, checkpointer, resume="approved"))

    mock_notify.assert_called_once()
