"""Pipeline trigger — Issue #29.

The seam between the content calendar (#26/#28) and the agent pipeline
(#18): polls `ContentCalendarEvent` rows approaching their
`target_datetime`, atomically claims each one so a concurrent/overlapping
poll can never re-trigger it, creates or locates the calendar event's
`Post` row, and starts (or resumes) the #18 pipeline graph
(`packages/agents/pipeline/graph.py`'s `run_pipeline()`) for it.

Kept separate from `apps/api/worker.py`'s Celery task wrapper — which only
supplies a DB session, the configured lead time, and a schedule — so this
module is fully unit-testable without any Celery machinery. See
`apps/api/tests/test_pipeline_trigger.py`.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from apps.api.models.content_calendar_event import CalendarEventStatus, ContentCalendarEvent
from apps.api.models.post import PipelineStage, Post
from packages.agents.pipeline.checkpointer import get_postgres_checkpointer
from packages.agents.pipeline.graph import run_pipeline

logger = logging.getLogger(__name__)

# Default lead time ahead of target_datetime the trigger starts a pipeline
# run — overridable per call, and, via apps/api/worker.py's Celery Beat
# task, by Settings.pipeline_trigger_lead_minutes (an env var), which is
# what makes this "configurable" per the issue's acceptance criteria.
DEFAULT_LEAD_TIME_MINUTES = 60

# ContentCalendarEvent.status is a distinct field from
# Post.current_pipeline_stage (the #18 mechanism) rather than the same
# enum wearing two names — an event can exist with no Post at all
# (SCHEDULED), and even once a Post exists, "ready for a human to review"
# is a calendar-facing concept while "which of the eight pipeline stages
# just ran" is a pipeline-internals concept. They're kept in sync here
# rather than picked arbitrarily: once a run reaches one of these
# pipeline stages, the event's status is advanced to match.
_STAGE_TO_EVENT_STATUS: dict[PipelineStage, CalendarEventStatus] = {
    PipelineStage.HUMAN_REVIEW: CalendarEventStatus.READY_FOR_REVIEW,
    PipelineStage.COMPLETED: CalendarEventStatus.PUBLISHED,
}


def _claim_due_events(
    db: Session, *, lead_time_minutes: int, now: datetime
) -> list[ContentCalendarEvent]:
    """Atomically claims every SCHEDULED event whose target_datetime is at
    or before ``now + lead_time_minutes``, flipping each straight to
    PIPELINE_RUNNING as part of the same statement.

    This is a single ``UPDATE ... WHERE status = 'scheduled' ... RETURNING``
    rather than a check-then-act SELECT followed by an UPDATE — the race
    the issue calls out. Postgres takes the row locks an UPDATE needs as
    part of evaluating it, so a second, overlapping UPDATE hitting the
    same rows blocks until the first commits and then re-evaluates its
    WHERE clause against the now-committed data — at which point
    ``status = 'scheduled'`` no longer matches (the first caller already
    moved it to PIPELINE_RUNNING), so the second claims zero rows for
    that event. Two overlapping pollers can therefore never both claim
    the same event, without needing a separate
    ``SELECT ... FOR UPDATE SKIP LOCKED`` step.
    """
    horizon = now + timedelta(minutes=lead_time_minutes)

    claimed_ids = (
        db.execute(
            update(ContentCalendarEvent)
            .where(
                ContentCalendarEvent.status == CalendarEventStatus.SCHEDULED,
                ContentCalendarEvent.target_datetime <= horizon,
            )
            .values(status=CalendarEventStatus.PIPELINE_RUNNING)
            .returning(ContentCalendarEvent.id)
        )
        .scalars()
        .all()
    )
    db.flush()

    if not claimed_ids:
        return []

    events = (
        db.execute(
            select(ContentCalendarEvent)
            .where(ContentCalendarEvent.id.in_(claimed_ids))
            .order_by(ContentCalendarEvent.target_datetime)
        )
        .scalars()
        .all()
    )
    for event in events:
        db.refresh(event)
    return list(events)


def _get_or_create_post(db: Session, event: ContentCalendarEvent) -> Post:
    """A calendar event may already have a Post — e.g. a previous trigger
    started the run and it's now paused at the human_review interrupt, or
    a prior attempt failed partway through. Reuse that Post (and hence its
    pipeline checkpoint thread, keyed on Post.id) rather than starting a
    second, disconnected run for the same event."""
    existing = db.query(Post).filter(Post.calendar_event_id == event.id).first()
    if existing is not None:
        return existing

    post = Post(brand_id=event.brand_id, calendar_event_id=event.id)
    db.add(post)
    db.flush()
    db.refresh(post)
    return post


def _sync_event_status(event: ContentCalendarEvent, post: Post) -> None:
    new_status = _STAGE_TO_EVENT_STATUS.get(post.current_pipeline_stage)
    if new_status is not None:
        event.status = new_status


def trigger_due_pipelines(
    db: Session,
    *,
    lead_time_minutes: int = DEFAULT_LEAD_TIME_MINUTES,
    now: datetime | None = None,
) -> list[Post]:
    """Finds every ContentCalendarEvent within `lead_time_minutes` of its
    target_datetime, claims it (SCHEDULED -> PIPELINE_RUNNING, guarding
    against duplicate triggering), starts or resumes its pipeline run via
    `run_pipeline`, and syncs the event's status to match the run's real
    progress. Returns the Posts whose pipeline this call started or
    advanced — an empty list when nothing was due (including when every
    otherwise-due event was already claimed by an earlier/concurrent
    call).
    """
    now = now or datetime.now(timezone.utc)
    events = _claim_due_events(db, lead_time_minutes=lead_time_minutes, now=now)

    started: list[Post] = []
    for event in events:
        post = _get_or_create_post(db, event)
        try:
            with get_postgres_checkpointer() as checkpointer:
                list(run_pipeline(db, post, checkpointer))
        except Exception:
            logger.exception(
                "Pipeline run failed for calendar event %s (post %s)", event.id, post.id
            )
            event.status = CalendarEventStatus.FAILED
            db.flush()
            continue

        _sync_event_status(event, post)
        db.flush()
        started.append(post)

    return started
