"""Tests for Issue #126's GET /brands/{brand_id}/posts — the general,
read-only Post listing the Create Post page's "Recent runs" list needs
(no existing endpoint returns Posts across every pipeline stage; see
apps/api/routers/posts.py's module docstring)."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from apps.api.auth.jwt import create_access_token, hash_password
from apps.api.main import app
from apps.api.models import Brand, Organization, PipelineStage, Post, User, UserRole

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


@uses_test_session
def test_list_posts_returns_every_stage_newest_first(db_session) -> None:
    brand, user = _setup_brand(db_session)

    base = datetime.now(timezone.utc)
    rejected = Post(
        brand_id=brand.id, current_pipeline_stage=PipelineStage.REJECTED, created_at=base
    )
    research = Post(
        brand_id=brand.id,
        current_pipeline_stage=PipelineStage.RESEARCH,
        created_at=base + timedelta(seconds=1),
    )
    completed = Post(
        brand_id=brand.id,
        current_pipeline_stage=PipelineStage.COMPLETED,
        created_at=base + timedelta(seconds=2),
    )
    db_session.add_all([rejected, research, completed])
    db_session.flush()

    response = client.get(f"/brands/{brand.id}/posts", headers=_auth_headers(user))

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 3
    stages = {p["current_pipeline_stage"] for p in body}
    assert stages == {"rejected", "research", "completed"}
    # Newest first.
    assert body[0]["id"] == str(completed.id)


@uses_test_session
def test_list_posts_scoped_to_brand_and_org(db_session) -> None:
    brand, user = _setup_brand(db_session)
    other_brand, _ = _setup_brand(db_session, suffix="-2")

    db_session.add(Post(brand_id=other_brand.id))
    db_session.flush()

    response = client.get(f"/brands/{brand.id}/posts", headers=_auth_headers(user))
    assert response.status_code == 200
    assert response.json() == []


@uses_test_session
def test_list_posts_404s_for_unknown_brand(db_session) -> None:
    _, user = _setup_brand(db_session)

    response = client.get(f"/brands/{uuid.uuid4()}/posts", headers=_auth_headers(user))
    assert response.status_code == 404
