import pytest
from fastapi.testclient import TestClient

from apps.api.auth.jwt import create_access_token, hash_password
from apps.api.main import app
from apps.api.models import Brand, Organization, User, UserRole

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
def test_get_onboarding_404_before_anything_saved(db_session) -> None:
    brand, user = _setup_brand(db_session)

    response = client.get(f"/brands/{brand.id}/onboarding", headers=_auth_headers(user))

    assert response.status_code == 404


@uses_test_session
def test_partial_upsert_leaves_incomplete(db_session) -> None:
    brand, user = _setup_brand(db_session)

    response = client.put(
        f"/brands/{brand.id}/onboarding",
        json={"voice": "Playful and direct"},
        headers=_auth_headers(user),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["voice"] == "Playful and direct"
    assert body["is_complete"] is False


@uses_test_session
def test_upsert_merges_across_calls(db_session) -> None:
    brand, user = _setup_brand(db_session)
    headers = _auth_headers(user)

    client.put(f"/brands/{brand.id}/onboarding", json={"voice": "Playful"}, headers=headers)
    response = client.put(
        f"/brands/{brand.id}/onboarding", json={"audience": "Gen Z"}, headers=headers
    )

    body = response.json()
    assert body["voice"] == "Playful"
    assert body["audience"] == "Gen Z"


@uses_test_session
def test_viewer_cannot_upsert_onboarding(db_session) -> None:
    brand, editor = _setup_brand(db_session, UserRole.EDITOR)
    _brand2, viewer = _setup_brand(db_session, UserRole.VIEWER)
    viewer.organization_id = editor.organization_id
    db_session.flush()

    response = client.put(
        f"/brands/{brand.id}/onboarding",
        json={"voice": "Playful"},
        headers=_auth_headers(viewer),
    )

    assert response.status_code == 403


@uses_test_session
def test_complete_fails_with_missing_fields_listed(db_session) -> None:
    brand, user = _setup_brand(db_session)
    client.put(
        f"/brands/{brand.id}/onboarding",
        json={"voice": "Playful", "audience": "Gen Z"},
        headers=_auth_headers(user),
    )

    response = client.post(f"/brands/{brand.id}/onboarding/complete", headers=_auth_headers(user))

    assert response.status_code == 400
    detail = response.json()["message"]
    assert "product_catalog" in detail
    assert "competitors" in detail
    assert "goals" in detail
    assert "voice" not in detail  # already filled, shouldn't be listed as missing


@uses_test_session
def test_complete_succeeds_once_all_required_fields_present(db_session) -> None:
    brand, user = _setup_brand(db_session)
    headers = _auth_headers(user)
    client.put(
        f"/brands/{brand.id}/onboarding",
        json={
            "voice": "Playful and direct",
            "audience": "Gen Z consumers",
            "product_catalog": {"items": ["Widget A", "Widget B"]},
            "competitors": ["Acme Corp", "Widgetron"],
            "goals": ["Increase awareness", "Drive signups"],
        },
        headers=headers,
    )

    response = client.post(f"/brands/{brand.id}/onboarding/complete", headers=headers)

    assert response.status_code == 200
    assert response.json()["is_complete"] is True


@uses_test_session
def test_cannot_edit_after_complete(db_session) -> None:
    brand, user = _setup_brand(db_session)
    headers = _auth_headers(user)
    full_payload = {
        "voice": "Playful",
        "audience": "Gen Z",
        "product_catalog": {"items": ["A"]},
        "competitors": ["X"],
        "goals": ["Grow"],
    }
    client.put(f"/brands/{brand.id}/onboarding", json=full_payload, headers=headers)
    client.post(f"/brands/{brand.id}/onboarding/complete", headers=headers)

    response = client.put(
        f"/brands/{brand.id}/onboarding", json={"voice": "Changed"}, headers=headers
    )

    assert response.status_code == 409


@uses_test_session
def test_cross_org_onboarding_access_returns_404(db_session) -> None:
    brand, _owner = _setup_brand(db_session, UserRole.EDITOR, suffix="-1")
    _brand2, other_user = _setup_brand(db_session, UserRole.EDITOR, suffix="-2")

    response = client.get(
        f"/brands/{brand.id}/onboarding", headers=_auth_headers(other_user)
    )

    assert response.status_code == 404
