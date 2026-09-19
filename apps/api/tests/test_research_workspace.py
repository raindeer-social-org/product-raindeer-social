"""Tests for Issue #126's standalone Research workspace page:
  1. packages/agents/pipeline/nodes/research_engine.py::run_standalone_research
     reuses _research_brief exactly (same shape, same degrade-on-failure
     behavior) for an ad hoc Post.
  2. apps/api/routers/research.py's POST .../research/run creates the ad
     hoc Post, runs the brief, and logs an AgentRun(agent_type=research).
  3. GET .../research/latest returns the most recent one without
     triggering a new run, and 404s when none exists yet.
"""

import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from apps.api.auth.jwt import create_access_token, hash_password
from apps.api.main import app
from apps.api.models import AgentRun, AgentType, Brand, Organization, Post, User, UserRole
from packages.agents.pipeline.nodes.research_engine import run_standalone_research
from packages.integrations.search.base import SearchResult

client = TestClient(app)
uses_test_session = pytest.mark.usefixtures("override_get_db")

SEARCH_PATCH_TARGET = "packages.agents.pipeline.nodes.research_engine.get_search_provider"
EMBED_PATCH_TARGET = "apps.api.services.brand_retrieval.get_embedding_provider"


def _setup_brand(db_session, role: UserRole = UserRole.EDITOR) -> tuple[Brand, User]:
    org = Organization(name="Acme Agency")
    db_session.add(org)
    db_session.flush()

    user = User(
        organization_id=org.id,
        email=f"{role.value}@acme.test",
        password_hash=hash_password("test-password"),
        role=role,
    )
    brand = Brand(organization_id=org.id, name="Acme Widgets", industry="Outdoor gear")
    db_session.add_all([user, brand])
    db_session.flush()
    return brand, user


def _auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(
        user_id=str(user.id), org_id=str(user.organization_id), role=user.role.value
    )
    return {"Authorization": f"Bearer {token}"}


def _mock_search_provider():
    provider = type(
        "StubSearch",
        (),
        {"search": lambda self, query, max_results=5: [SearchResult(title=f"Result for {query}", url="https://example.com", content="c")]},
    )()
    return provider


# --- engine wrapper ---------------------------------------------------


def test_run_standalone_research_reuses_research_brief_shape(db_session) -> None:
    brand, _ = _setup_brand(db_session)
    post = Post(brand_id=brand.id)
    db_session.add(post)
    db_session.flush()

    with patch(SEARCH_PATCH_TARGET, return_value=_mock_search_provider()), patch(
        EMBED_PATCH_TARGET, side_effect=Exception("no embedding provider configured")
    ):
        brief = run_standalone_research(db_session, post)

    assert brief["post_id"] == str(post.id)
    assert "platform_trends" in brief
    assert "industry_trends" in brief
    assert "timing_signal" in brief


# --- router: POST /run -------------------------------------------------


@uses_test_session
def test_run_research_endpoint_creates_ad_hoc_post_and_agent_run(db_session) -> None:
    brand, user = _setup_brand(db_session)

    with patch(SEARCH_PATCH_TARGET, return_value=_mock_search_provider()), patch(
        EMBED_PATCH_TARGET, side_effect=Exception("no embedding provider configured")
    ):
        response = client.post(
            f"/brands/{brand.id}/research/run", headers=_auth_headers(user)
        )

    assert response.status_code == 201
    body = response.json()
    assert body["brand_id"] == str(brand.id)
    assert "platform_trends" in body["brief"]

    post = db_session.query(Post).filter(Post.id == uuid.UUID(body["post_id"])).first()
    assert post is not None
    assert post.brand_id == brand.id
    assert post.calendar_event_id is None

    run = db_session.query(AgentRun).filter(AgentRun.post_id == post.id).first()
    assert run is not None
    assert run.agent_type == AgentType.RESEARCH
    assert run.output == body["brief"]


@uses_test_session
def test_run_research_endpoint_rejects_viewer_role(db_session) -> None:
    brand, _ = _setup_brand(db_session, role=UserRole.EDITOR)
    _, viewer = _setup_brand(db_session, role=UserRole.VIEWER)

    response = client.post(f"/brands/{brand.id}/research/run", headers=_auth_headers(viewer))
    assert response.status_code == 403


# --- router: GET /latest ------------------------------------------------


@uses_test_session
def test_latest_research_returns_404_when_none_exists(db_session) -> None:
    brand, user = _setup_brand(db_session)

    response = client.get(f"/brands/{brand.id}/research/latest", headers=_auth_headers(user))
    assert response.status_code == 404


@uses_test_session
def test_latest_research_returns_most_recent_run(db_session) -> None:
    brand, user = _setup_brand(db_session)

    with patch(SEARCH_PATCH_TARGET, return_value=_mock_search_provider()), patch(
        EMBED_PATCH_TARGET, side_effect=Exception("no embedding provider configured")
    ):
        run_response = client.post(f"/brands/{brand.id}/research/run", headers=_auth_headers(user))
    assert run_response.status_code == 201

    latest_response = client.get(f"/brands/{brand.id}/research/latest", headers=_auth_headers(user))
    assert latest_response.status_code == 200
    assert latest_response.json()["post_id"] == run_response.json()["post_id"]
