"""Tests for Issue #126's standalone Creative workspace page:
  1. packages/agents/pipeline/nodes/creative_engine.py::generate_creative_angles
     calls LLMProvider only through its interface and returns exactly
     `count` distinct angle cards.
  2. It degrades to the fixed fallback angles (not an error) when the LLM
     call/parse fails — same contract as _generate_platform_briefs.
  3. apps/api/routers/creative.py's POST .../creative/angles logs an
     AgentRun(agent_type=creative, post_id=None).
"""

import json
import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from apps.api.auth.jwt import create_access_token, hash_password
from apps.api.main import app
from apps.api.models import AgentRun, AgentType, Brand, Organization, User, UserRole
from packages.agents.pipeline.nodes.creative_engine import (
    ANGLE_COUNT,
    REQUIRED_ANGLE_KEYS,
    generate_creative_angles,
)
from packages.integrations.llm.base import LLMResponse

client = TestClient(app)
uses_test_session = pytest.mark.usefixtures("override_get_db")

LLM_PATCH_TARGET = "packages.agents.pipeline.nodes.creative_engine.get_llm_provider"


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


def _angle(i: int) -> dict:
    return {
        "format": f"format-{i}",
        "angle": f"angle-{i}",
        "hook": f"hook-{i}",
        "why": f"why-{i}",
        "cta": f"cta-{i}",
        "score": 90 - i,
    }


def _llm_angles_response(count: int) -> LLMResponse:
    return LLMResponse(
        text=json.dumps([_angle(i) for i in range(count)]),
        model="openrouter/free",
        input_tokens=100,
        output_tokens=50,
    )


# --- engine ---------------------------------------------------------


def test_generate_creative_angles_returns_six_distinct_cards() -> None:
    brand = Brand(organization_id=uuid.uuid4(), name="Acme", industry="Outdoor gear")
    with patch(LLM_PATCH_TARGET) as mock_llm:
        mock_llm.return_value.complete.return_value = _llm_angles_response(ANGLE_COUNT)
        angles = generate_creative_angles(brand, "Post about our new product launch")

    assert len(angles) == ANGLE_COUNT
    for angle in angles:
        assert all(key in angle for key in REQUIRED_ANGLE_KEYS)
    formats = {a["format"] for a in angles}
    assert len(formats) == ANGLE_COUNT


def test_generate_creative_angles_falls_back_on_llm_failure() -> None:
    brand = Brand(organization_id=uuid.uuid4(), name="Acme", industry="Outdoor gear")
    with patch(LLM_PATCH_TARGET, side_effect=Exception("LLM unreachable")):
        angles = generate_creative_angles(brand, "Post about our new product launch")

    assert len(angles) == ANGLE_COUNT
    for angle in angles:
        assert all(key in angle for key in REQUIRED_ANGLE_KEYS)


# --- router -----------------------------------------------------------


@uses_test_session
def test_generate_angles_endpoint_logs_agent_run(db_session) -> None:
    brand, user = _setup_brand(db_session)

    with patch(LLM_PATCH_TARGET) as mock_llm:
        mock_llm.return_value.complete.return_value = _llm_angles_response(ANGLE_COUNT)
        response = client.post(
            f"/brands/{brand.id}/creative/angles",
            headers=_auth_headers(user),
            json={"brief": "Launch our new contract-review turnaround feature"},
        )

    assert response.status_code == 201
    body = response.json()
    assert len(body["angles"]) == ANGLE_COUNT

    run = (
        db_session.query(AgentRun)
        .filter(AgentRun.agent_type == AgentType.CREATIVE, AgentRun.post_id.is_(None))
        .order_by(AgentRun.created_at.desc())
        .first()
    )
    assert run is not None
    assert run.input["brand_id"] == str(brand.id)
    assert len(run.output["angles"]) == ANGLE_COUNT


@uses_test_session
def test_generate_angles_endpoint_rejects_viewer_role(db_session) -> None:
    brand, _ = _setup_brand(db_session, role=UserRole.EDITOR)
    _, viewer = _setup_brand(db_session, role=UserRole.VIEWER)

    response = client.post(
        f"/brands/{brand.id}/creative/angles",
        headers=_auth_headers(viewer),
        json={"brief": "Launch our new feature"},
    )
    assert response.status_code == 403
