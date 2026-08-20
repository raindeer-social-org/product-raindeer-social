import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient

from apps.api.auth.dependencies import CurrentUser, get_current_user
from apps.api.auth.jwt import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from apps.api.main import app
from apps.api.middleware.rbac import require_role
from apps.api.models import Organization, User, UserRole

client = TestClient(app)
pytestmark = pytest.mark.usefixtures("override_get_db")


def test_hash_and_verify_password_round_trip() -> None:
    hashed = hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"
    assert verify_password("correct horse battery staple", hashed)
    assert not verify_password("wrong password", hashed)


def test_create_and_decode_access_token_round_trip() -> None:
    token = create_access_token(user_id="u1", org_id="o1", role="editor")
    payload = decode_access_token(token)
    assert payload["sub"] == "u1"
    assert payload["org_id"] == "o1"
    assert payload["role"] == "editor"


def test_decode_expired_token_raises() -> None:
    token = create_access_token(
        user_id="u1", org_id="o1", role="editor", expires_minutes=-1
    )
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)


def _create_user(db_session, role: UserRole, email: str) -> User:
    org = Organization(name="Acme Agency")
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
    return user


def test_login_with_valid_credentials_returns_token(db_session) -> None:
    _create_user(db_session, UserRole.OWNER, "owner@acme.test")

    response = client.post(
        "/auth/login", json={"email": "owner@acme.test", "password": "test-password"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert decode_access_token(body["access_token"])["role"] == "owner"


def test_login_with_wrong_password_returns_401(db_session) -> None:
    _create_user(db_session, UserRole.OWNER, "owner2@acme.test")

    response = client.post(
        "/auth/login", json={"email": "owner2@acme.test", "password": "wrong"}
    )

    assert response.status_code == 401


def test_login_with_unknown_email_returns_401(db_session) -> None:
    response = client.post(
        "/auth/login", json={"email": "nobody@acme.test", "password": "whatever"}
    )

    assert response.status_code == 401


def test_me_with_valid_token_returns_200(db_session) -> None:
    user = _create_user(db_session, UserRole.VIEWER, "viewer@acme.test")
    token = create_access_token(
        user_id=str(user.id), org_id=str(user.organization_id), role="viewer"
    )

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["role"] == "viewer"


def test_me_without_token_returns_401() -> None:
    response = client.get("/auth/me")
    assert response.status_code == 401


def test_me_with_garbage_token_returns_401() -> None:
    response = client.get("/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401


@pytest.mark.parametrize(
    ("role", "expect_allowed"),
    [
        (UserRole.OWNER, True),
        (UserRole.ADMIN, True),
        (UserRole.EDITOR, True),
        (UserRole.VIEWER, False),
    ],
)
def test_require_role_gates_write_access_per_role(role, expect_allowed) -> None:
    # Simulates exactly what a write endpoint (e.g. Brand CRUD's POST/PATCH/
    # DELETE, landing in Issue #9) will use: Depends(require_role(...)).
    # No write endpoint exists yet in this codebase to test through the full
    # HTTP stack, so this exercises the same dependency directly instead of
    # a throwaway route invented just for this test.
    write_gate = require_role(UserRole.OWNER, UserRole.ADMIN, UserRole.EDITOR)
    current_user = CurrentUser(user_id="u1", org_id="o1", role=role)

    if expect_allowed:
        assert write_gate(current_user=current_user) is current_user
    else:
        with pytest.raises(HTTPException) as exc_info:
            write_gate(current_user=current_user)
        assert exc_info.value.status_code == 403


def test_get_current_user_rejects_role_not_in_token() -> None:
    token = create_access_token(user_id="u1", org_id="o1", role="not-a-real-role")
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(
            credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        )
    assert exc_info.value.status_code == 401
