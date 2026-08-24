"""Issue #25 — the acceptance criteria is explicit that this must exercise
the *real* resume mechanism, not just check for an HTTP 200: approve must
actually resume the checkpointed graph (Issue #18) past `scheduler`, and
reject must actually halt it before `publisher`. So these tests drive a
real post through packages.agents.pipeline.graph.run_pipeline to the
human_review interrupt (same pattern as
packages/agents/tests/test_pipeline_graph.py) before calling the API,
then assert on Post.current_pipeline_stage / AgentRun rows afterward —
not just the response body.
"""

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from apps.api.auth.jwt import create_access_token, hash_password
from apps.api.main import app
from apps.api.models import (
    AgentRun,
    Brand,
    ContentCalendarEvent,
    Organization,
    PipelineStage,
    Post,
    ReviewFeedback,
    ReviewSource,
    ReviewVerdict,
    User,
    UserRole,
)
from packages.agents.pipeline.checkpointer import get_postgres_checkpointer
from packages.agents.pipeline.graph import run_pipeline

client = TestClient(app)
uses_test_session = pytest.mark.usefixtures("override_get_db")


@pytest.fixture()
def thread_cleanup():
    """Pipeline checkpoint rows live in Postgres on a connection totally
    separate from db_session's rolled-back transaction (same reasoning as
    test_pipeline_graph.py's fixture of the same name), so they need
    explicit teardown."""
    thread_ids: list[str] = []
    yield thread_ids
    if not thread_ids:
        return
    with get_postgres_checkpointer() as checkpointer:
        for thread_id in thread_ids:
            checkpointer.delete_thread(thread_id)


def _setup_brand(db_session, role: UserRole = UserRole.EDITOR, suffix: str = "") -> tuple[Brand, User]:
    org = Organization(name="Acme Agency")
    db_session.add(org)
    db_session.flush()

    user = User(
        organization_id=org.id,
        email=f"{role.value}{suffix}@acme.test",
        password_hash=hash_password("test-password"),
        role=role,
    )
    brand = Brand(organization_id=org.id, name="Acme Widgets")
    db_session.add_all([user, brand])
    db_session.flush()
    return brand, user


def _auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(
        user_id=str(user.id), org_id=str(user.organization_id), role=user.role.value
    )
    return {"Authorization": f"Bearer {token}"}


def _post_at_human_review(
    db_session, brand: Brand, thread_cleanup, calendar_event_id: uuid.UUID | None = None
) -> Post:
    """Runs a real Post through the pipeline graph up to (and pausing at)
    the human_review interrupt — the same durable-Postgres-checkpoint
    mechanism run_pipeline uses in production, not a shortcut that just
    sets current_pipeline_stage directly."""
    post = Post(brand_id=brand.id, calendar_event_id=calendar_event_id)
    db_session.add(post)
    db_session.flush()
    thread_cleanup.append(str(post.id))

    with get_postgres_checkpointer() as checkpointer:
        list(run_pipeline(db_session, post, checkpointer))

    db_session.refresh(post)
    assert post.current_pipeline_stage == PipelineStage.HUMAN_REVIEW
    return post


# --- list ---------------------------------------------------------------


@uses_test_session
def test_list_review_queue_scoped_to_brand(db_session, thread_cleanup) -> None:
    brand, user = _setup_brand(db_session)
    post = _post_at_human_review(db_session, brand, thread_cleanup)

    response = client.get(f"/brands/{brand.id}/review-queue", headers=_auth_headers(user))

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == str(post.id)
    # The Reviewer Engine's (#24) AI review is attached alongside whatever
    # human review history exists — here, none yet.
    sources = [f["source"] for f in body[0]["review_feedback"]]
    assert sources == ["ai_reviewer"]


@uses_test_session
def test_list_review_queue_excludes_posts_not_paused(db_session, thread_cleanup) -> None:
    brand, user = _setup_brand(db_session)
    Post(brand_id=brand.id)  # never persisted through the pipeline
    fresh_post = Post(brand_id=brand.id)
    db_session.add(fresh_post)
    db_session.flush()
    assert fresh_post.current_pipeline_stage == PipelineStage.RESEARCH

    response = client.get(f"/brands/{brand.id}/review-queue", headers=_auth_headers(user))

    assert response.status_code == 200
    assert response.json() == []


# --- approve --------------------------------------------------------------


@uses_test_session
def test_approve_resumes_graph_toward_scheduler(db_session, thread_cleanup) -> None:
    brand, user = _setup_brand(db_session)
    post = _post_at_human_review(db_session, brand, thread_cleanup)

    response = client.post(
        f"/brands/{brand.id}/review-queue/{post.id}/approve",
        json={"comments": "Looks great"},
        headers=_auth_headers(user),
    )

    assert response.status_code == 200
    assert response.json()["current_pipeline_stage"] == "completed"

    db_session.refresh(post)
    assert post.current_pipeline_stage == PipelineStage.COMPLETED

    # Proof the graph actually advanced past human_review — not just a
    # 200 response — by checking the AgentRun rows the downstream stub
    # stages log (packages/agents/pipeline/graph.py::run_pipeline).
    agent_stages = {
        run.agent_type.value
        for run in db_session.query(AgentRun).filter(AgentRun.post_id == post.id).all()
    }
    assert {"human_review", "scheduler", "publisher", "analytics_collector"} <= agent_stages

    human_feedback = (
        db_session.query(ReviewFeedback)
        .filter(ReviewFeedback.post_id == post.id, ReviewFeedback.source == ReviewSource.HUMAN)
        .all()
    )
    assert len(human_feedback) == 1
    assert human_feedback[0].verdict == ReviewVerdict.APPROVE
    assert human_feedback[0].comments == {"comments": "Looks great"}


@uses_test_session
def test_approve_a_post_not_at_human_review_is_409(db_session, thread_cleanup) -> None:
    brand, user = _setup_brand(db_session)
    post = Post(brand_id=brand.id)
    db_session.add(post)
    db_session.flush()

    response = client.post(
        f"/brands/{brand.id}/review-queue/{post.id}/approve",
        json={},
        headers=_auth_headers(user),
    )

    assert response.status_code == 409


@uses_test_session
def test_viewer_cannot_approve(db_session, thread_cleanup) -> None:
    brand, viewer = _setup_brand(db_session, UserRole.VIEWER)
    post = _post_at_human_review(db_session, brand, thread_cleanup)

    response = client.post(
        f"/brands/{brand.id}/review-queue/{post.id}/approve",
        json={},
        headers=_auth_headers(viewer),
    )

    assert response.status_code == 403


# --- reject -----------------------------------------------------------------


@uses_test_session
def test_reject_halts_graph_before_publisher(db_session, thread_cleanup) -> None:
    brand, user = _setup_brand(db_session)
    post = _post_at_human_review(db_session, brand, thread_cleanup)

    response = client.post(
        f"/brands/{brand.id}/review-queue/{post.id}/reject",
        json={"comments": "Off-brand"},
        headers=_auth_headers(user),
    )

    assert response.status_code == 200
    assert response.json()["current_pipeline_stage"] == "rejected"

    db_session.refresh(post)
    assert post.current_pipeline_stage == PipelineStage.REJECTED

    agent_stages = {
        run.agent_type.value
        for run in db_session.query(AgentRun).filter(AgentRun.post_id == post.id).all()
    }
    assert "scheduler" not in agent_stages
    assert "publisher" not in agent_stages
    assert "analytics_collector" not in agent_stages

    human_feedback = (
        db_session.query(ReviewFeedback)
        .filter(ReviewFeedback.post_id == post.id, ReviewFeedback.source == ReviewSource.HUMAN)
        .all()
    )
    assert len(human_feedback) == 1
    assert human_feedback[0].verdict == ReviewVerdict.REJECT
    assert human_feedback[0].comments == {"comments": "Off-brand"}


# --- edit ---------------------------------------------------------------


@uses_test_session
def test_edit_updates_body_text_without_resuming(db_session, thread_cleanup) -> None:
    brand, user = _setup_brand(db_session)
    post = _post_at_human_review(db_session, brand, thread_cleanup)

    response = client.post(
        f"/brands/{brand.id}/review-queue/{post.id}/edit",
        json={"body_text": {"linkedin": "A hand-edited draft."}},
        headers=_auth_headers(user),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["body_text"] == {"linkedin": "A hand-edited draft."}
    assert body["current_pipeline_stage"] == "human_review"

    db_session.refresh(post)
    assert post.body_text == {"linkedin": "A hand-edited draft."}
    # Editing must not touch the checkpointed graph — still paused.
    assert post.current_pipeline_stage == PipelineStage.HUMAN_REVIEW


# --- reschedule -----------------------------------------------------------


@uses_test_session
def test_reschedule_updates_linked_calendar_event(db_session, thread_cleanup) -> None:
    brand, user = _setup_brand(db_session)
    event = ContentCalendarEvent(
        brand_id=brand.id,
        title="Launch",
        target_platforms=["linkedin"],
        desired_format="image",
        target_datetime=datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc),
    )
    db_session.add(event)
    db_session.flush()

    post = _post_at_human_review(db_session, brand, thread_cleanup, calendar_event_id=event.id)

    response = client.post(
        f"/brands/{brand.id}/review-queue/{post.id}/reschedule",
        json={"target_datetime": "2026-09-05T15:30:00Z"},
        headers=_auth_headers(user),
    )

    assert response.status_code == 200
    expected = datetime(2026, 9, 5, 15, 30, tzinfo=timezone.utc)
    assert datetime.fromisoformat(response.json()["target_datetime"]) == expected

    db_session.refresh(event)
    assert event.target_datetime == expected

    # Reschedule must not touch the checkpointed graph either.
    db_session.refresh(post)
    assert post.current_pipeline_stage == PipelineStage.HUMAN_REVIEW


@uses_test_session
def test_reschedule_without_calendar_event_is_400(db_session, thread_cleanup) -> None:
    brand, user = _setup_brand(db_session)
    post = _post_at_human_review(db_session, brand, thread_cleanup)

    response = client.post(
        f"/brands/{brand.id}/review-queue/{post.id}/reschedule",
        json={"target_datetime": "2026-09-05T15:30:00Z"},
        headers=_auth_headers(user),
    )

    assert response.status_code == 400


# --- scoping / isolation ----------------------------------------------------


@uses_test_session
def test_cross_org_post_access_returns_404(db_session, thread_cleanup) -> None:
    brand, _owner = _setup_brand(db_session, UserRole.EDITOR, suffix="-1")
    _brand2, other_user = _setup_brand(db_session, UserRole.EDITOR, suffix="-2")
    post = _post_at_human_review(db_session, brand, thread_cleanup)

    response = client.post(
        f"/brands/{brand.id}/review-queue/{post.id}/approve",
        json={},
        headers=_auth_headers(other_user),
    )

    assert response.status_code == 404
