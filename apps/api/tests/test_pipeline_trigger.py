"""Tests for the Issue #29 pipeline trigger.

Exercises packages/agents/pipeline/trigger.py directly (not the Celery
task wrapper in apps/api/worker.py — that's a thin, untested-here wrapper
by design, see this repo's other Celery task docstrings) against a real
Postgres-backed pipeline run, same pattern as
packages/agents/tests/test_pipeline_graph.py. Covers the issue's three
acceptance criteria:

  1. An event with a near-future target_datetime is picked up and its
     status flips to PIPELINE_RUNNING (and, once the run reaches the
     human_review interrupt, on to READY_FOR_REVIEW).
  2. An event far in the future is not picked up.
  3. An event already PIPELINE_RUNNING is not re-triggered even if it's
     still within the lead-time window — including when a second,
     duplicate/"concurrent" poll call races the first.
"""

from datetime import datetime, timedelta, timezone

import pytest

from apps.api.models import (
    Brand,
    CalendarEventStatus,
    ContentCalendarEvent,
    Organization,
    PipelineStage,
    Post,
)
from packages.agents.pipeline.checkpointer import get_postgres_checkpointer
from packages.agents.pipeline.trigger import (
    DEFAULT_LEAD_TIME_MINUTES,
    _claim_due_events,
    trigger_due_pipelines,
)

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


@pytest.fixture()
def thread_cleanup():
    """Pipeline checkpoint rows live in Postgres on a connection totally
    separate from db_session's rolled-back transaction (see
    test_pipeline_graph.py), so they need explicit teardown."""
    thread_ids: list[str] = []
    yield thread_ids
    if not thread_ids:
        return
    with get_postgres_checkpointer() as checkpointer:
        for thread_id in thread_ids:
            checkpointer.delete_thread(thread_id)


def _setup_brand(db_session) -> Brand:
    org = Organization(name="Acme Agency")
    db_session.add(org)
    db_session.flush()

    brand = Brand(organization_id=org.id, name="Acme Widgets")
    db_session.add(brand)
    db_session.flush()
    return brand


def _make_event(
    db_session,
    brand: Brand,
    *,
    target_datetime: datetime,
    status: CalendarEventStatus = CalendarEventStatus.SCHEDULED,
) -> ContentCalendarEvent:
    event = ContentCalendarEvent(
        brand_id=brand.id,
        title="Launch announcement",
        description="Announce the new widget line",
        target_platforms=["linkedin"],
        desired_format="single-image",
        target_datetime=target_datetime,
        status=status,
    )
    db_session.add(event)
    db_session.flush()
    return event


def test_near_future_event_is_claimed_and_flips_to_pipeline_running(db_session) -> None:
    brand = _setup_brand(db_session)
    event = _make_event(db_session, brand, target_datetime=NOW + timedelta(minutes=30))

    claimed = _claim_due_events(db_session, lead_time_minutes=60, now=NOW)

    assert [e.id for e in claimed] == [event.id]
    db_session.refresh(event)
    assert event.status == CalendarEventStatus.PIPELINE_RUNNING


def test_far_future_event_is_not_picked_up(db_session) -> None:
    brand = _setup_brand(db_session)
    event = _make_event(db_session, brand, target_datetime=NOW + timedelta(days=5))

    claimed = _claim_due_events(db_session, lead_time_minutes=60, now=NOW)

    assert claimed == []
    db_session.refresh(event)
    assert event.status == CalendarEventStatus.SCHEDULED


def test_event_exactly_at_lead_time_horizon_is_picked_up(db_session) -> None:
    brand = _setup_brand(db_session)
    event = _make_event(db_session, brand, target_datetime=NOW + timedelta(minutes=60))

    claimed = _claim_due_events(db_session, lead_time_minutes=60, now=NOW)

    assert [e.id for e in claimed] == [event.id]


def test_already_pipeline_running_event_is_not_reclaimed(db_session) -> None:
    brand = _setup_brand(db_session)
    event = _make_event(
        db_session,
        brand,
        target_datetime=NOW + timedelta(minutes=10),
        status=CalendarEventStatus.PIPELINE_RUNNING,
    )

    claimed = _claim_due_events(db_session, lead_time_minutes=60, now=NOW)

    assert claimed == []
    db_session.refresh(event)
    assert event.status == CalendarEventStatus.PIPELINE_RUNNING


def test_duplicate_poll_call_only_triggers_once(db_session, thread_cleanup, monkeypatch) -> None:
    """Simulates a concurrent/duplicate poll: trigger_due_pipelines is
    called twice in a row for the same due event. The atomic claim means
    the second call must find nothing left to claim, so the pipeline is
    only ever started once."""
    brand = _setup_brand(db_session)
    event = _make_event(db_session, brand, target_datetime=NOW + timedelta(minutes=15))

    run_calls: list[str] = []
    from packages.agents.pipeline import trigger as trigger_module

    original_run_pipeline = trigger_module.run_pipeline

    def _counting_run_pipeline(db, post, checkpointer, **kwargs):
        run_calls.append(str(post.id))
        return original_run_pipeline(db, post, checkpointer, **kwargs)

    monkeypatch.setattr(trigger_module, "run_pipeline", _counting_run_pipeline)

    first_started = trigger_due_pipelines(db_session, lead_time_minutes=60, now=NOW)
    assert len(first_started) == 1
    thread_cleanup.append(str(first_started[0].id))

    second_started = trigger_due_pipelines(db_session, lead_time_minutes=60, now=NOW)

    assert second_started == []
    assert run_calls == [str(first_started[0].id)]

    db_session.refresh(event)
    assert event.status != CalendarEventStatus.SCHEDULED

    # Only one Post was ever created for this event, not two.
    posts = db_session.query(Post).filter(Post.calendar_event_id == event.id).all()
    assert len(posts) == 1


def test_trigger_creates_post_runs_pipeline_and_syncs_status_to_ready_for_review(
    db_session, thread_cleanup
) -> None:
    brand = _setup_brand(db_session)
    event = _make_event(db_session, brand, target_datetime=NOW + timedelta(minutes=5))

    started = trigger_due_pipelines(db_session, lead_time_minutes=60, now=NOW)

    assert len(started) == 1
    post = started[0]
    thread_cleanup.append(str(post.id))

    assert post.brand_id == brand.id
    assert post.calendar_event_id == event.id

    # The stub pipeline (research/creative/generation/reviewer all run,
    # then interrupts at human_review) reaches HUMAN_REVIEW synchronously
    # within this call, so the event's status is already synced past
    # PIPELINE_RUNNING to READY_FOR_REVIEW — reusing Post.
    # current_pipeline_stage (#18) as the source of truth rather than a
    # second, independently-tracked progress field.
    assert post.current_pipeline_stage == PipelineStage.HUMAN_REVIEW
    db_session.refresh(event)
    assert event.status == CalendarEventStatus.READY_FOR_REVIEW


def test_trigger_reuses_existing_post_for_event_instead_of_creating_a_second_one(
    db_session, thread_cleanup
) -> None:
    """Covers the case where a Post already exists for a calendar event
    (e.g. a previous run got partway through before this poll fired) —
    the trigger must resume that Post's pipeline thread, not fork a new,
    disconnected one."""
    brand = _setup_brand(db_session)
    event = _make_event(db_session, brand, target_datetime=NOW + timedelta(minutes=5))

    existing_post = Post(brand_id=brand.id, calendar_event_id=event.id)
    db_session.add(existing_post)
    db_session.flush()
    thread_cleanup.append(str(existing_post.id))

    started = trigger_due_pipelines(db_session, lead_time_minutes=60, now=NOW)

    assert len(started) == 1
    assert started[0].id == existing_post.id

    posts = db_session.query(Post).filter(Post.calendar_event_id == event.id).all()
    assert len(posts) == 1


def test_default_lead_time_constant_matches_settings_default() -> None:
    from apps.api.config import Settings

    assert DEFAULT_LEAD_TIME_MINUTES == Settings().pipeline_trigger_lead_minutes
