"""Tests for Issue #126's Content AI workspace page (the image-first fast
path):
  1. packages/agents/pipeline/nodes/generation_engine.py::generate_standalone_images
     calls ImageProvider + StorageProvider only through their interfaces —
     the same real fal.ai-backed adapter (Issue #22) the per-post pipeline
     uses — and returns `count` variants.
  2. A failed variant degrades to {"status": "failed"} without aborting
     the rest of the batch.
  3. apps/api/routers/content_ai.py's POST .../content-ai/generate folds
     aspect-ratio/style/brand-lock into the prompt and logs an
     AgentRun(agent_type=generation, post_id=None).
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from apps.api.auth.jwt import create_access_token, hash_password
from apps.api.main import app
from apps.api.models import AgentRun, AgentType, Brand, Organization, User, UserRole
from packages.agents.pipeline.nodes.generation_engine import generate_standalone_images
from packages.integrations.image_gen.base import ImageResult

client = TestClient(app)
uses_test_session = pytest.mark.usefixtures("override_get_db")

IMAGE_PATCH_TARGET = "packages.agents.pipeline.nodes.generation_engine.get_image_provider"
STORAGE_PATCH_TARGET = "packages.agents.pipeline.nodes.generation_engine.get_storage_provider"


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
    brand = Brand(
        organization_id=org.id, name="Acme Widgets", industry="Outdoor gear", colors=["#1B4DFF", "#0A1633"]
    )
    db_session.add_all([user, brand])
    db_session.flush()
    return brand, user


def _auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(
        user_id=str(user.id), org_id=str(user.organization_id), role=user.role.value
    )
    return {"Authorization": f"Bearer {token}"}


def _mock_image_provider() -> MagicMock:
    provider = MagicMock()
    provider.generate.return_value = ImageResult(url="https://fal.media/files/generated-abc.png")
    return provider


def _mock_download():
    return (b"fake-bytes", "image/png")


# --- engine -------------------------------------------------------------


def test_generate_standalone_images_returns_requested_count() -> None:
    with patch(IMAGE_PATCH_TARGET, return_value=_mock_image_provider()), patch(
        STORAGE_PATCH_TARGET
    ) as mock_storage, patch(
        "packages.agents.pipeline.nodes.generation_engine._download_image_bytes",
        return_value=_mock_download(),
    ):
        mock_storage.return_value.upload.return_value = "https://storage.example/img.png"
        results = generate_standalone_images("editorial navy card", count=4)

    assert len(results) == 4
    assert all(r["status"] == "generated" for r in results)
    assert all(r["url"] == "https://storage.example/img.png" for r in results)


def test_generate_standalone_images_degrades_a_failed_variant() -> None:
    with patch(IMAGE_PATCH_TARGET, side_effect=Exception("fal.ai unreachable")):
        results = generate_standalone_images("editorial navy card", count=2)

    assert len(results) == 2
    assert all(r == {"status": "failed", "url": None} for r in results)


# --- router --------------------------------------------------------------


@uses_test_session
def test_generate_images_endpoint_logs_agent_run(db_session) -> None:
    brand, user = _setup_brand(db_session)

    with patch(IMAGE_PATCH_TARGET, return_value=_mock_image_provider()), patch(
        STORAGE_PATCH_TARGET
    ) as mock_storage, patch(
        "packages.agents.pipeline.nodes.generation_engine._download_image_bytes",
        return_value=_mock_download(),
    ):
        mock_storage.return_value.upload.return_value = "https://storage.example/img.png"
        response = client.post(
            f"/brands/{brand.id}/content-ai/generate",
            headers=_auth_headers(user),
            json={
                "prompt": "Editorial typographic card, deep navy",
                "aspect_ratio": "1:1",
                "style": "editorial",
                "lock_brand_colors": True,
                "count": 4,
            },
        )

    assert response.status_code == 201
    body = response.json()
    assert len(body["variants"]) == 4
    assert all(v["status"] == "generated" for v in body["variants"])

    run = (
        db_session.query(AgentRun)
        .filter(AgentRun.agent_type == AgentType.GENERATION, AgentRun.post_id.is_(None))
        .order_by(AgentRun.created_at.desc())
        .first()
    )
    assert run is not None
    assert run.input["brand_id"] == str(brand.id)
    assert run.input["aspect_ratio"] == "1:1"
    assert len(run.output["variants"]) == 4


@uses_test_session
def test_generate_images_endpoint_rejects_viewer_role(db_session) -> None:
    brand, _ = _setup_brand(db_session, role=UserRole.EDITOR)
    _, viewer = _setup_brand(db_session, role=UserRole.VIEWER)

    response = client.post(
        f"/brands/{brand.id}/content-ai/generate",
        headers=_auth_headers(viewer),
        json={"prompt": "A mountain at sunrise"},
    )
    assert response.status_code == 403
