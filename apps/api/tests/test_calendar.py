import pytest
from fastapi.testclient import TestClient

from apps.api.auth.jwt import create_access_token, hash_password
from apps.api.main import app
from apps.api.models import (
    AgentRun,
    AgentType,
    Brand,
    Organization,
    Post,
    ReviewFeedback,
    ReviewSource,
    ReviewVerdict,
    User,
    UserRole,
)

client = TestClient(app)
uses_test_session = pytest.mark.usefixtures("override_get_db")


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


def _payload(**overrides: object) -> dict:
    base = {
        "title": "Launch announcement",
        "description": "Announce the new widget line",
        "target_platforms": ["linkedin"],
        "desired_format": "single-image",
        "target_datetime": "2026-09-01T12:00:00Z",
    }
    base.update(overrides)
    return base


@uses_test_session
def test_create_event(db_session) -> None:
    brand, user = _setup_brand(db_session)

    response = client.post(
        f"/brands/{brand.id}/calendar-events", json=_payload(), headers=_auth_headers(user)
    )

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Launch announcement"
    assert body["status"] == "scheduled"
    assert body["target_platforms"] == ["linkedin"]


@uses_test_session
def test_create_event_rejects_unsupported_platform(db_session) -> None:
    brand, user = _setup_brand(db_session)

    response = client.post(
        f"/brands/{brand.id}/calendar-events",
        json=_payload(target_platforms=["tiktok"]),
        headers=_auth_headers(user),
    )

    assert response.status_code == 422


@uses_test_session
def test_viewer_cannot_create_event(db_session) -> None:
    brand, viewer = _setup_brand(db_session, UserRole.VIEWER)

    response = client.post(
        f"/brands/{brand.id}/calendar-events", json=_payload(), headers=_auth_headers(viewer)
    )

    assert response.status_code == 403


@uses_test_session
def test_list_events_scoped_to_brand(db_session) -> None:
    brand, user = _setup_brand(db_session)
    headers = _auth_headers(user)
    client.post(f"/brands/{brand.id}/calendar-events", json=_payload(), headers=headers)
    client.post(
        f"/brands/{brand.id}/calendar-events",
        json=_payload(title="Second post"),
        headers=headers,
    )

    response = client.get(f"/brands/{brand.id}/calendar-events", headers=headers)

    assert response.status_code == 200
    assert len(response.json()) == 2


@uses_test_session
def test_get_event_404_for_unknown_id(db_session) -> None:
    brand, user = _setup_brand(db_session)
    import uuid

    response = client.get(
        f"/brands/{brand.id}/calendar-events/{uuid.uuid4()}", headers=_auth_headers(user)
    )

    assert response.status_code == 404


@uses_test_session
def test_update_event_status(db_session) -> None:
    brand, user = _setup_brand(db_session)
    headers = _auth_headers(user)
    created = client.post(
        f"/brands/{brand.id}/calendar-events", json=_payload(), headers=headers
    ).json()

    response = client.patch(
        f"/brands/{brand.id}/calendar-events/{created['id']}",
        json={"status": "approved"},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "approved"


@uses_test_session
def test_delete_event(db_session) -> None:
    brand, user = _setup_brand(db_session)
    headers = _auth_headers(user)
    created = client.post(
        f"/brands/{brand.id}/calendar-events", json=_payload(), headers=headers
    ).json()

    delete_response = client.delete(
        f"/brands/{brand.id}/calendar-events/{created['id']}", headers=headers
    )
    get_response = client.get(
        f"/brands/{brand.id}/calendar-events/{created['id']}", headers=headers
    )

    assert delete_response.status_code == 204
    assert get_response.status_code == 404


@uses_test_session
def test_cross_org_event_access_returns_404(db_session) -> None:
    brand, owner = _setup_brand(db_session, UserRole.EDITOR, suffix="-1")
    _brand2, other_user = _setup_brand(db_session, UserRole.EDITOR, suffix="-2")
    headers = _auth_headers(owner)
    created = client.post(
        f"/brands/{brand.id}/calendar-events", json=_payload(), headers=headers
    ).json()

    response = client.get(
        f"/brands/{brand.id}/calendar-events/{created['id']}",
        headers=_auth_headers(other_user),
    )

    assert response.status_code == 404


@uses_test_session
def test_get_event_post_returns_null_when_pipeline_hasnt_run_yet(db_session) -> None:
    """A SCHEDULED event the pipeline trigger hasn't claimed yet has no
    Post row — the endpoint should say so with a 200/null, not a 404, so
    the calendar's post preview modal can render a "not reviewed yet"
    state rather than treating this as an error."""
    brand, user = _setup_brand(db_session)
    headers = _auth_headers(user)
    created = client.post(
        f"/brands/{brand.id}/calendar-events", json=_payload(), headers=headers
    ).json()

    response = client.get(
        f"/brands/{brand.id}/calendar-events/{created['id']}/post", headers=headers
    )

    assert response.status_code == 200
    assert response.json() is None


@uses_test_session
def test_get_event_post_404_for_unknown_event(db_session) -> None:
    brand, user = _setup_brand(db_session)
    import uuid

    response = client.get(
        f"/brands/{brand.id}/calendar-events/{uuid.uuid4()}/post", headers=_auth_headers(user)
    )

    assert response.status_code == 404


@uses_test_session
def test_get_event_post_returns_post_review_feedback_and_agent_runs(db_session) -> None:
    brand, user = _setup_brand(db_session)
    headers = _auth_headers(user)
    created = client.post(
        f"/brands/{brand.id}/calendar-events", json=_payload(), headers=headers
    ).json()
    event_id = created["id"]

    post = Post(
        brand_id=brand.id,
        calendar_event_id=event_id,
        body_text={"linkedin": "Draft copy"},
    )
    db_session.add(post)
    db_session.flush()

    feedback = ReviewFeedback(
        post_id=post.id,
        source=ReviewSource.AI_REVIEWER,
        score=82.0,
        verdict=ReviewVerdict.APPROVE,
        comments={
            "platforms": {"linkedin": {"score": 82.0, "verdict": "approve", "issues": [], "suggested_edits": "n/a"}},
            "model": "test-model",
        },
    )
    db_session.add(feedback)

    research_run = AgentRun(
        post_id=post.id,
        agent_type=AgentType.RESEARCH,
        input={"post_id": str(post.id)},
        output={"completed_stages": ["research"]},
    )
    reviewer_run = AgentRun(
        post_id=post.id,
        agent_type=AgentType.REVIEWER,
        input={"post_id": str(post.id)},
        output={"completed_stages": ["research", "creative", "generation", "reviewer"]},
    )
    db_session.add_all([research_run, reviewer_run])
    db_session.flush()

    response = client.get(f"/brands/{brand.id}/calendar-events/{event_id}/post", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(post.id)
    assert body["calendar_event_id"] == event_id
    assert body["body_text"] == {"linkedin": "Draft copy"}
    assert len(body["review_feedback"]) == 1
    assert body["review_feedback"][0]["score"] == 82.0
    assert [run["agent_type"] for run in body["agent_runs"]] == ["research", "reviewer"]


@uses_test_session
def test_get_event_post_cross_org_returns_404(db_session) -> None:
    brand, owner = _setup_brand(db_session, UserRole.EDITOR, suffix="-1")
    _brand2, other_user = _setup_brand(db_session, UserRole.EDITOR, suffix="-2")
    headers = _auth_headers(owner)
    created = client.post(
        f"/brands/{brand.id}/calendar-events", json=_payload(), headers=headers
    ).json()

    response = client.get(
        f"/brands/{brand.id}/calendar-events/{created['id']}/post",
        headers=_auth_headers(other_user),
    )

    assert response.status_code == 404
