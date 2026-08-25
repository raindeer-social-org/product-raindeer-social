"""Status notifications — Issue #32.

Two triggers, both consumers of state changes owned by earlier issues
rather than anything this module produces itself:

  * A post's publish permanently failing (Issue #31 — the terminal FAILED
    state apps/api/worker.py's `_PublishTask.on_failure` hook sets once
    retries are exhausted). Wired in from there, not from
    apps/api/services/publish_queue.py's `publish_post`/`mark_post_failed`
    themselves, so a transient failure that's still mid-retry never fires
    a notification — only the genuinely terminal one does.
  * A post reaching the `human_review` interrupt (Issue #25 /
    packages/agents/pipeline/graph.py's `human_review` node) — i.e. the
    moment `Post.current_pipeline_stage` (and, once Issue #29's trigger
    lands, `ContentCalendarEvent.status`) becomes ready_for_review. Wired
    in from `run_pipeline()` in graph.py, at the one place that already
    computes "the run just settled on human_review" from the
    checkpointer's authoritative view (see that function's tail).

Two adapters, one small interface (`NotificationAdapter`) — same
provider-abstraction shape as packages/integrations/llm/base.py's
`LLMProvider` and packages/integrations/social/base.py's
`SocialPublisher`: business code (the two `notify_*` functions below)
only ever depends on the interface, and every adapter routes its one
outbound call through `track_integration_call`
(packages.integrations.observability), exactly like every other external
call in this codebase.

  * `EmailAdapter` — plain SMTP (stdlib `smtplib`), not a vendor SDK.
    Portable and trivially mockable in tests without adding a dependency;
    swapping in a real transactional provider (Resend/SendGrid/etc.)
    later is a matter of adding a second adapter class behind the same
    interface, not touching any caller.
  * `SlackWebhookAdapter` — a bare `httpx.post` to an incoming webhook
    URL. No Slack SDK needed for a single fire-and-forget message.

Both adapters, and `NotificationService.send()` itself, treat a send
failure (bad webhook URL, SMTP timeout/auth failure, DNS failure, ...) as
something to log and swallow, never raise — see `NotificationService.send`.
That is what satisfies the issue's "notification failures must not crash
the triggering job" acceptance criterion: apps/api/worker.py's on_failure
hook and packages/agents/pipeline/graph.py's run_pipeline() can both call
straight into `notify_publish_failure`/`notify_ready_for_review` with no
try/except of their own and be guaranteed neither ever raises.
"""

from __future__ import annotations

import logging
import smtplib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from email.message import EmailMessage

import httpx
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.models import Brand, Post, User, UserRole
from packages.integrations.observability import track_integration_call

logger = logging.getLogger(__name__)

# Brand "owners/admins" — who publish failures go to. Narrower than
# REVIEWER_ROLES below: a publish failure is an operational/account
# problem (revoked token, rate limit, ...) that only someone who can
# manage the brand's connected accounts can act on, not every writer.
PUBLISH_FAILURE_ROLES: tuple[UserRole, ...] = (UserRole.OWNER, UserRole.ADMIN)

# Who counts as "a reviewer" for a brand: the same WRITE_ROLES
# apps/api/routers/review.py already gates the approve/reject/edit/
# reschedule endpoints behind (anyone who can actually act on a post
# awaiting review), deliberately excluding VIEWER — the issue's explicit
# "notify the relevant reviewer(s), not the whole org" acceptance
# criterion.
REVIEWER_ROLES: tuple[UserRole, ...] = (UserRole.OWNER, UserRole.ADMIN, UserRole.EDITOR)


@dataclass
class Notification:
    """A single notification to send, already rendered to plain text —
    adapters format/deliver it, they don't decide *what* it says."""

    subject: str
    body: str
    # Email addresses of the resolved recipients. SlackWebhookAdapter
    # ignores this list (a webhook posts to whatever channel it's
    # configured for, not to individual users) but ties into the same
    # Notification so both adapters share one call.
    recipients: list[str] = field(default_factory=list)


class NotificationAdapter(ABC):
    """Interface every notification channel implements. Callers
    (NotificationService.send) must only ever depend on this interface —
    never reach into smtplib/httpx directly outside the adapter that
    implements it, same convention as every other integrations
    adapter in this codebase."""

    @abstractmethod
    def send(self, notification: Notification) -> None:
        ...


class EmailAdapter(NotificationAdapter):
    """Generic SMTP sender — works with any transactional-email provider
    that exposes SMTP credentials (which is effectively all of them:
    SES, SendGrid, Postmark, Resend, ...), so this stays swappable
    without a vendor SDK dependency. If SMTP isn't configured
    (smtp_host unset — the common case for local dev without a real
    mail server) send() logs and no-ops rather than attempting a
    connection that can only fail."""

    def __init__(
        self,
        host: str | None,
        port: int,
        username: str | None,
        password: str | None,
        from_email: str | None,
        timeout: float = 10.0,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.from_email = from_email
        self.timeout = timeout

    def send(self, notification: Notification) -> None:
        if not self.host or not self.from_email:
            logger.info(
                "Email notification skipped (SMTP not configured): %s", notification.subject
            )
            return
        if not notification.recipients:
            logger.info(
                "Email notification skipped (no recipients resolved): %s", notification.subject
            )
            return

        message = EmailMessage()
        message["Subject"] = notification.subject
        message["From"] = self.from_email
        message["To"] = ", ".join(notification.recipients)
        message.set_content(notification.body)

        with track_integration_call("email", "send"):
            with smtplib.SMTP(self.host, self.port, timeout=self.timeout) as smtp:
                if self.username and self.password:
                    smtp.starttls()
                    smtp.login(self.username, self.password)
                smtp.send_message(message)


class SlackWebhookAdapter(NotificationAdapter):
    """Posts a plain-text message to a Slack incoming webhook URL. No
    Slack SDK — a webhook is just an HTTP POST of `{"text": ...}`. If no
    webhook URL is configured, send() logs and no-ops."""

    def __init__(self, webhook_url: str | None, timeout: float = 10.0) -> None:
        self.webhook_url = webhook_url
        self.timeout = timeout

    def send(self, notification: Notification) -> None:
        if not self.webhook_url:
            logger.info(
                "Slack notification skipped (no webhook configured): %s", notification.subject
            )
            return

        text = f"*{notification.subject}*\n{notification.body}"
        with track_integration_call("slack", "webhook_post"):
            response = httpx.post(self.webhook_url, json={"text": text}, timeout=self.timeout)
            response.raise_for_status()


class NotificationService:
    """Fans a single Notification out to every configured adapter,
    catching and logging each adapter's own failures so one bad channel
    (or all of them) never propagates back to the caller — see module
    docstring for why that's a hard requirement here, not just a nicety.
    """

    def __init__(self, adapters: list[NotificationAdapter]) -> None:
        self.adapters = adapters

    def send(self, notification: Notification) -> None:
        for adapter in self.adapters:
            try:
                adapter.send(notification)
            except Exception:
                # Exactly the failure mode the issue calls out (a bad
                # webhook URL, an SMTP timeout): logged, never re-raised,
                # so a single flaky channel can't take down whatever
                # triggered this notification (publish-queue on_failure,
                # the pipeline's run_pipeline) nor block the other
                # adapter from still getting a chance to send.
                logger.exception(
                    "Notification adapter %s failed to send %r",
                    type(adapter).__name__,
                    notification.subject,
                )


def _build_default_service() -> NotificationService:
    settings = get_settings()
    return NotificationService(
        adapters=[
            EmailAdapter(
                host=settings.smtp_host,
                port=settings.smtp_port,
                username=settings.smtp_user,
                password=settings.smtp_password,
                from_email=settings.notification_from_email,
            ),
            SlackWebhookAdapter(webhook_url=settings.slack_webhook_url),
        ]
    )


def _recipients_for_roles(db: Session, brand: Brand, roles: tuple[UserRole, ...]) -> list[str]:
    """Every User in the brand's organization holding one of `roles`.
    Roles are org-wide, not per-brand (apps/api/models/user.py — a User
    carries a single organization_id/role, there's no separate
    brand-membership table), so "who can act on this brand" reduces to
    "who's in its org with the right role", the same resolution
    apps/api/routers/review.py's `_get_org_brand` + `require_role`
    already rely on for authorizing the review-queue endpoints."""
    users = (
        db.query(User)
        .filter(User.organization_id == brand.organization_id, User.role.in_(roles))
        .all()
    )
    return [user.email for user in users]


def notify_publish_failure(db: Session, post: Post) -> None:
    """Issue #32 trigger 1: a post's publish permanently failed (Issue
    #31's terminal FAILED state — see apps/api/worker.py's
    `_PublishTask.on_failure`, the sole caller). Notifies the brand's
    owners/admins with the post/brand identifying info and the actual
    failure reason (`post.publish_error`, written by
    apps/api/services/publish_queue.py on every failed attempt).

    Deliberately wrapped in a broad try/except of its own, on top of
    NotificationService.send's own per-adapter catch — recipient
    resolution itself (the DB queries below) must never be able to crash
    the publish-queue job that calls this, any more than an adapter
    failure can. See module docstring.
    """
    try:
        brand = db.get(Brand, post.brand_id)
        if brand is None:
            logger.warning(
                "Skipping publish-failure notification for post_id=%s: brand %s not found",
                post.id,
                post.brand_id,
            )
            return

        recipients = _recipients_for_roles(db, brand, PUBLISH_FAILURE_ROLES)
        notification = Notification(
            subject=f"[Raindeer] Publish failed — {brand.name}",
            body=(
                f"A post for {brand.name} failed to publish and retries have been "
                f"exhausted.\n\n"
                f"Post ID: {post.id}\n"
                f"Brand: {brand.name}\n"
                f"Reason: {post.publish_error or 'Unknown error'}\n"
            ),
            recipients=recipients,
        )
        _build_default_service().send(notification)
    except Exception:
        logger.exception("notify_publish_failure failed for post_id=%s", post.id)


def notify_ready_for_review(db: Session, post: Post) -> None:
    """Issue #32 trigger 2: a post reached the `human_review` interrupt
    (Issue #25) — sole caller is
    packages/agents/pipeline/graph.py's run_pipeline(), at the point it
    settles Post.current_pipeline_stage on HUMAN_REVIEW. Notifies only
    the brand's reviewers (REVIEWER_ROLES — owner/admin/editor, i.e.
    anyone with write access), never the whole org, per the issue's
    explicit acceptance criterion.

    Same broad try/except as notify_publish_failure, for the same
    reason — must never crash run_pipeline()'s caller.
    """
    try:
        brand = db.get(Brand, post.brand_id)
        if brand is None:
            logger.warning(
                "Skipping ready-for-review notification for post_id=%s: brand %s not found",
                post.id,
                post.brand_id,
            )
            return

        recipients = _recipients_for_roles(db, brand, REVIEWER_ROLES)
        notification = Notification(
            subject=f"[Raindeer] Post ready for review — {brand.name}",
            body=(
                f"A post for {brand.name} has finished the automated pipeline and is "
                f"waiting on human review.\n\n"
                f"Post ID: {post.id}\n"
                f"Brand: {brand.name}\n"
            ),
            recipients=recipients,
        )
        _build_default_service().send(notification)
    except Exception:
        logger.exception("notify_ready_for_review failed for post_id=%s", post.id)
