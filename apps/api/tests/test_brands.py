import uuid

import pytest
from fastapi.testclient import TestClient

from apps.api.auth.jwt import create_access_token, hash_password
from apps.api.config.database import SessionLocal
from apps.api.main import app
from apps.api.models import Brand, Organization, User, UserRole

client = TestClient(app)

# Applied per-test rather than as a module-level pytestmark, because
# test_created_brand_actually_persists_across_connections deliberately
# must NOT get this override — see that test for why.
uses_test_session = pytest.mark.usefixtures("override_get_db")


def _create_org_and_user(db_session, role: UserRole, email: str) -> tuple[Organization, User]:
    org = Organization(name=f"Org for {email}")
    db_session.add(org)
    db_session.flush()

    user = User(
        organization_id=org.id,
        email=email,
        password_hash=hash_password("test-password"),
        role=role,
    )
    db_session.add(user)
    db_session.flush()
    return org, user


def _auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(
        user_id=str(user.id), org_id=str(user.organization_id), role=user.role.value
    )
    return {"Authorization": f"Bearer {token}"}


@uses_test_session
def test_editor_can_create_brand(db_session) -> None:
    _org, user = _create_org_and_user(db_session, UserRole.EDITOR, "editor@acme.test")

    response = client.post(
        "/brands", json={"name": "Acme Widgets"}, headers=_auth_headers(user)
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Acme Widgets"
    assert body["organization_id"] == str(user.organization_id)


@uses_test_session
def test_viewer_cannot_create_brand(db_session) -> None:
    _org, user = _create_org_and_user(db_session, UserRole.VIEWER, "viewer@acme.test")

    response = client.post(
        "/brands", json={"name": "Acme Widgets"}, headers=_auth_headers(user)
    )

    assert response.status_code == 403


@uses_test_session
def test_list_brands_only_returns_own_org(db_session) -> None:
    _org_a, user_a = _create_org_and_user(db_session, UserRole.EDITOR, "a@acme.test")
    _org_b, user_b = _create_org_and_user(db_session, UserRole.EDITOR, "b@acme.test")

    client.post("/brands", json={"name": "Org A Brand"}, headers=_auth_headers(user_a))
    client.post("/brands", json={"name": "Org B Brand"}, headers=_auth_headers(user_b))

    response = client.get("/brands", headers=_auth_headers(user_a))

    assert response.status_code == 200
    names = [b["name"] for b in response.json()]
    assert names == ["Org A Brand"]


@uses_test_session
def test_cross_org_brand_access_returns_404_not_403(db_session) -> None:
    _org_a, user_a = _create_org_and_user(db_session, UserRole.EDITOR, "a2@acme.test")
    _org_b, user_b = _create_org_and_user(db_session, UserRole.EDITOR, "b2@acme.test")

    created = client.post(
        "/brands", json={"name": "Org A Brand"}, headers=_auth_headers(user_a)
    ).json()

    response = client.get(f"/brands/{created['id']}", headers=_auth_headers(user_b))

    assert response.status_code == 404


@uses_test_session
def test_editor_can_update_brand(db_session) -> None:
    _org, user = _create_org_and_user(db_session, UserRole.EDITOR, "editor2@acme.test")
    created = client.post(
        "/brands", json={"name": "Old Name"}, headers=_auth_headers(user)
    ).json()

    response = client.patch(
        f"/brands/{created['id']}",
        json={"name": "New Name", "industry": "Consumer goods"},
        headers=_auth_headers(user),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "New Name"
    assert body["industry"] == "Consumer goods"


@uses_test_session
def test_viewer_cannot_update_brand(db_session) -> None:
    _org, user = _create_org_and_user(db_session, UserRole.EDITOR, "editor3@acme.test")
    created = client.post(
        "/brands", json={"name": "Name"}, headers=_auth_headers(user)
    ).json()

    _org2, viewer = _create_org_and_user(db_session, UserRole.VIEWER, "viewer2@acme.test")
    # give the viewer the same org so this tests role, not org-scoping
    viewer.organization_id = user.organization_id
    db_session.flush()
    headers = _auth_headers(viewer)

    response = client.patch(
        f"/brands/{created['id']}", json={"name": "Hacked"}, headers=headers
    )

    assert response.status_code == 403


@uses_test_session
def test_editor_can_delete_brand_then_404s(db_session) -> None:
    _org, user = _create_org_and_user(db_session, UserRole.EDITOR, "editor4@acme.test")
    created = client.post(
        "/brands", json={"name": "To Delete"}, headers=_auth_headers(user)
    ).json()

    delete_response = client.delete(
        f"/brands/{created['id']}", headers=_auth_headers(user)
    )
    assert delete_response.status_code == 204

    get_response = client.get(f"/brands/{created['id']}", headers=_auth_headers(user))
    assert get_response.status_code == 404


@uses_test_session
def test_viewer_cannot_delete_brand(db_session) -> None:
    _org, user = _create_org_and_user(db_session, UserRole.EDITOR, "editor5@acme.test")
    created = client.post(
        "/brands", json={"name": "Name"}, headers=_auth_headers(user)
    ).json()

    _org2, viewer = _create_org_and_user(db_session, UserRole.VIEWER, "viewer3@acme.test")
    viewer.organization_id = user.organization_id
    db_session.flush()

    response = client.delete(
        f"/brands/{created['id']}", headers=_auth_headers(viewer)
    )
    assert response.status_code == 403


def test_created_brand_actually_persists_across_connections() -> None:
    # Deliberately does NOT use override_get_db — this goes through the
    # real Depends(get_db) -> SessionLocal() path, the same one every real
    # request uses in production. This is the regression test for the bug
    # this issue caught: get_db() previously never called db.commit(), so
    # every write would silently vanish once the request's session closed.
    # Proving persistence means querying via a THIRD, completely separate
    # session afterward — not the one the request used.
    #
    # This test writes real, connection-level-committed rows rather than
    # relying on db_session's transaction-rollback isolation, so — unlike
    # every other test in this file — it's responsible for cleaning up
    # after itself; a unique-per-run email keeps repeat local runs from
    # colliding even if cleanup is ever skipped (e.g. the test fails).
    # SQLAlchemy's default expire_on_commit=True expires *every* loaded
    # object in the session on each commit, not just the one just
    # committed — so org's attributes would be expired by user's later
    # commit below. Capture plain values immediately after each refresh
    # rather than touching the ORM objects again after the session closes.
    email = f"persist-{uuid.uuid4().hex[:8]}@acme.test"
    setup_db = SessionLocal()
    try:
        org = Organization(name="Persistence Test Org")
        setup_db.add(org)
        setup_db.commit()
        setup_db.refresh(org)
        org_id = org.id

        user = User(
            organization_id=org_id,
            email=email,
            password_hash=hash_password("test-password"),
            role=UserRole.EDITOR,
        )
        setup_db.add(user)
        setup_db.commit()
        setup_db.refresh(user)
        auth_headers = _auth_headers(user)
    finally:
        setup_db.close()

    brand_id = None
    try:
        response = client.post(
            "/brands", json={"name": "Really Persisted"}, headers=auth_headers
        )
        assert response.status_code == 201
        brand_id = response.json()["id"]

        verify_db = SessionLocal()
        try:
            fetched = verify_db.get(Brand, brand_id)
            assert fetched is not None
            assert fetched.name == "Really Persisted"
        finally:
            verify_db.rollback()
            verify_db.close()
    finally:
        cleanup_db = SessionLocal()
        try:
            if brand_id is not None:
                cleanup_db.query(Brand).filter(Brand.id == brand_id).delete()
            cleanup_db.query(User).filter(User.email == email).delete()
            cleanup_db.query(Organization).filter(Organization.id == org_id).delete()
            cleanup_db.commit()
        finally:
            cleanup_db.close()
