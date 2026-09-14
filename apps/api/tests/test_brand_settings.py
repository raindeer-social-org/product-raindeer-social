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
def test_get_settings_auto_provisions_defaults(db_session) -> None:
    brand, user = _setup_brand(db_session)

    response = client.get(f"/brands/{brand.id}/settings", headers=_auth_headers(user))

    assert response.status_code == 200
    body = response.json()
    assert body["brand_id"] == str(brand.id)
    assert body["auto_approve_enabled"] is False
    assert body["auto_approve_threshold"] == 90
    assert body["show_agent_reasoning"] is True
    assert body["email_review_digest_enabled"] is True
    assert body["auto_shift_posting_times"] is True


@uses_test_session
def test_get_settings_is_idempotent_and_does_not_duplicate_rows(db_session) -> None:
    brand, user = _setup_brand(db_session)
    headers = _auth_headers(user)

    first = client.get(f"/brands/{brand.id}/settings", headers=headers).json()
    second = client.get(f"/brands/{brand.id}/settings", headers=headers).json()

    assert first["id"] == second["id"]


@uses_test_session
def test_update_settings_persists_partial_changes(db_session) -> None:
    brand, user = _setup_brand(db_session)
    headers = _auth_headers(user)

    response = client.put(
        f"/brands/{brand.id}/settings",
        json={"auto_approve_enabled": True, "auto_approve_threshold": 75},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["auto_approve_enabled"] is True
    assert body["auto_approve_threshold"] == 75
    # Untouched fields keep their defaults.
    assert body["show_agent_reasoning"] is True


@uses_test_session
def test_update_settings_round_trips_across_reads(db_session) -> None:
    brand, user = _setup_brand(db_session)
    headers = _auth_headers(user)

    client.put(
        f"/brands/{brand.id}/settings",
        json={"show_agent_reasoning": False, "auto_shift_posting_times": False},
        headers=headers,
    )

    response = client.get(f"/brands/{brand.id}/settings", headers=headers)

    body = response.json()
    assert body["show_agent_reasoning"] is False
    assert body["auto_shift_posting_times"] is False


@uses_test_session
def test_update_rejects_out_of_range_threshold(db_session) -> None:
    brand, user = _setup_brand(db_session)

    response = client.put(
        f"/brands/{brand.id}/settings",
        json={"auto_approve_threshold": 150},
        headers=_auth_headers(user),
    )

    assert response.status_code == 422


@uses_test_session
def test_viewer_cannot_update_settings(db_session) -> None:
    brand, editor = _setup_brand(db_session, UserRole.EDITOR)
    _brand2, viewer = _setup_brand(db_session, UserRole.VIEWER, suffix="2")
    viewer.organization_id = editor.organization_id
    db_session.flush()

    response = client.put(
        f"/brands/{brand.id}/settings",
        json={"show_agent_reasoning": False},
        headers=_auth_headers(viewer),
    )

    assert response.status_code == 403


@uses_test_session
def test_viewer_can_read_settings(db_session) -> None:
    brand, editor = _setup_brand(db_session, UserRole.EDITOR)
    _brand2, viewer = _setup_brand(db_session, UserRole.VIEWER, suffix="2")
    viewer.organization_id = editor.organization_id
    db_session.flush()

    response = client.get(f"/brands/{brand.id}/settings", headers=_auth_headers(viewer))

    assert response.status_code == 200


@uses_test_session
def test_settings_404_for_brand_in_another_org(db_session) -> None:
    brand, _user = _setup_brand(db_session)
    _other_brand, other_user = _setup_brand(db_session, suffix="2")

    response = client.get(f"/brands/{brand.id}/settings", headers=_auth_headers(other_user))

    assert response.status_code == 404
