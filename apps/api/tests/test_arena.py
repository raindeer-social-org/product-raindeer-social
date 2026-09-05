"""Issue #124 — the Content Arena canvas's read-only run-composition
endpoint (apps/api/routers/arena.py). Like test_review.py, this drives a
real Post through packages.agents.pipeline.graph.run_pipeline (rather than
hand-setting Post.current_pipeline_stage) so the AgentRun rows returned are
the same ones the real pipeline logs, not a shortcut.
"""

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from apps.api.auth.jwt import create_access_token, hash_password
from apps.api.main import app
from apps.api.models import (
    AgentRun,
    AgentType,
    Brand,
    ContentCalendarEvent,
    Organization,
    Post,
    User,
    UserRole,
)
from packages.agents.pipeline.checkpointer import get_postgres_checkpointer
from packages.agents.pipeline.graph import run_pipeline

client = TestClient(app)
uses_test_session = pytest.mark.usefixtures("override_get_db")


@pytest.fixture()
def thread_cleanup():
    """Same reasoning as test_review.py's fixture of the same name:
    pipeline checkpoint rows live in Postgres on a connection separate
    from db_session's rolled-back transaction, so they need explicit
    teardown."""
    thread_ids: list[str] = []
    yield thread_ids
    if not thread_ids:
        return
    with get_postgres_checkpointer() as checkpointer:
        for thread_id in thread_ids:
            checkpointer.delete_thread(thread_id)


def _setup_brand(db_session, suffix: str = "") -> tuple[Brand, User]:
    org = Organization(name="Acme Agency")
    db_session.add(org)
    db_session.flush()

    user = User(
        organization_id=org.id,
        email=f"editor{suffix}@acme.test",
        password_hash=hash_password("test-password"),
        role=UserRole.EDITOR,
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


def _post_at_human_review(db_session, brand: Brand, thread_cleanup, calendar_event_id=None) -> Post:
    """Runs a real Post through the pipeline graph up to (and pausing at)
    the human_review interrupt, logging real AgentRun rows for research,
    creative, generation and reviewer along the way — same mechanism
    test_review.py uses."""
    post = Post(brand_id=brand.id, calendar_event_id=calendar_event_id)
    db_session.add(post)
    db_session.flush()
    thread_cleanup.append(str(post.id))

    with get_postgres_checkpointer() as checkpointer:
        list(run_pipeline(db_session, post, checkpointer))

    db_session.refresh(post)
    return post


# --- by-event -------------------------------------------------------------


@uses_test_session
def test_get_run_for_event_returns_agent_runs_in_order(db_session, thread_cleanup) -> None:
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

    response = client.get(
        f"/brands/{brand.id}/arena/by-event/{event.id}", headers=_auth_headers(user)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["calendar_event_id"] == str(event.id)
    assert body["post"]["id"] == str(post.id)
    assert body["post"]["current_pipeline_stage"] == "human_review"

    stages = [run["agent_type"] for run in body["agent_runs"]]
    assert stages == ["research", "creative", "generation", "reviewer"]
    # Ordered oldest-first (pipeline execution order), not reversed.
    timestamps = [run["created_at"] for run in body["agent_runs"]]
    assert timestamps == sorted(timestamps)

    # The AI reviewer's pass (Issue #24) is attached as review history.
    sources = [f["source"] for f in body["review_feedback"]]
    assert sources == ["ai_reviewer"]

    # `input` is never exposed — see schemas/arena.py's docstring.
    assert "input" not in body["agent_runs"][0]


@uses_test_session
def test_get_run_for_event_without_a_post_yet(db_session) -> None:
    brand, user = _setup_brand(db_session)
    event = ContentCalendarEvent(
        brand_id=brand.id,
        title="Not triggered yet",
        target_platforms=["linkedin"],
        desired_format="image",
        target_datetime=datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc),
    )
    db_session.add(event)
    db_session.flush()

    response = client.get(
        f"/brands/{brand.id}/arena/by-event/{event.id}", headers=_auth_headers(user)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["calendar_event_id"] == str(event.id)
    assert body["post"] is None
    assert body["agent_runs"] == []
    assert body["review_feedback"] == []


@uses_test_session
def test_get_run_for_unknown_event_is_404(db_session) -> None:
    brand, user = _setup_brand(db_session)

    response = client.get(
        f"/brands/{brand.id}/arena/by-event/{uuid.uuid4()}", headers=_auth_headers(user)
    )

    assert response.status_code == 404


@uses_test_session
def test_cross_org_event_access_returns_404(db_session) -> None:
    brand, _owner = _setup_brand(db_session, suffix="-1")
    _brand2, other_user = _setup_brand(db_session, suffix="-2")
    event = ContentCalendarEvent(
        brand_id=brand.id,
        title="Launch",
        target_platforms=["linkedin"],
        desired_format="image",
        target_datetime=datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc),
    )
    db_session.add(event)
    db_session.flush()

    response = client.get(
        f"/brands/{brand.id}/arena/by-event/{event.id}", headers=_auth_headers(other_user)
    )

    assert response.status_code == 404


# --- latest -----------------------------------------------------------------


@uses_test_session
def test_get_latest_run_returns_most_recently_created_post(db_session, thread_cleanup) -> None:
    brand, user = _setup_brand(db_session)
    older = Post(brand_id=brand.id)
    db_session.add(older)
    db_session.flush()
    # Postgres's now() is constant for the whole transaction, so both Posts
    # would otherwise get an identical server-generated created_at within
    # this one test transaction — force `older` to genuinely predate
    # `newer` so the ORDER BY created_at DESC this endpoint relies on has
    # something real to sort by.
    older.created_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
    db_session.flush()

    newer = _post_at_human_review(db_session, brand, thread_cleanup)

    response = client.get(f"/brands/{brand.id}/arena/latest", headers=_auth_headers(user))

    assert response.status_code == 200
    body = response.json()
    assert body["post"]["id"] == str(newer.id)
    assert older.id != newer.id


@uses_test_session
def test_get_latest_run_with_no_posts_yet(db_session) -> None:
    brand, user = _setup_brand(db_session)

    response = client.get(f"/brands/{brand.id}/arena/latest", headers=_auth_headers(user))

    assert response.status_code == 200
    body = response.json()
    assert body["post"] is None
    assert body["calendar_event_id"] is None
    assert body["agent_runs"] == []


@uses_test_session
def test_get_latest_run_unknown_brand_is_404(db_session, thread_cleanup) -> None:
    brand, user = _setup_brand(db_session)
    _post_at_human_review(db_session, brand, thread_cleanup)

    response = client.get(f"/brands/{uuid.uuid4()}/arena/latest", headers=_auth_headers(user))

    assert response.status_code == 404


@uses_test_session
def test_agent_runs_expose_real_cost_and_token_data(db_session) -> None:
    """Confirms the endpoint passes through AgentRun's real
    model/tokens/cost/latency columns rather than only the stage name —
    the Arena inspector panel (Issue #124) needs these for real stats."""
    brand, user = _setup_brand(db_session)
    post = Post(brand_id=brand.id)
    db_session.add(post)
    db_session.flush()

    db_session.add(
        AgentRun(
            post_id=post.id,
            agent_type=AgentType.GENERATION,
            input={"post_id": str(post.id)},
            output={"generation_output": {"model": "sonnet", "tokens": 512, "cost": 0.12}},
            model="sonnet",
            tokens=512,
            cost=0.12,
            latency_ms=845.5,
        )
    )
    db_session.flush()

    response = client.get(f"/brands/{brand.id}/arena/latest", headers=_auth_headers(user))

    assert response.status_code == 200
    run = response.json()["agent_runs"][0]
    assert run["model"] == "sonnet"
    assert run["tokens"] == 512
    assert run["cost"] == 0.12
    assert run["latency_ms"] == 845.5
    assert run["output"]["generation_output"]["model"] == "sonnet"
