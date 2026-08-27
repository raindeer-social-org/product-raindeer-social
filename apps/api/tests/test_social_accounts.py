import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from apps.api.auth.jwt import create_access_token, hash_password
from apps.api.main import app
from apps.api.models import Brand, Organization, SocialAccount, SocialPlatform, User, UserRole
from packages.integrations.social.base import SocialTokens

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
def test_connect_returns_authorize_url_with_signed_state(db_session, monkeypatch) -> None:
    from apps.api.config import get_settings

    monkeypatch.setenv("LINKEDIN_REDIRECT_URI", "http://localhost:8000/oauth/linkedin/callback")
    get_settings.cache_clear()
    brand, user = _setup_brand(db_session)

    response = client.post(
        f"/brands/{brand.id}/social-accounts/linkedin/connect", headers=_auth_headers(user)
    )
    get_settings.cache_clear()

    assert response.status_code == 200
    url = response.json()["authorize_url"]
    assert url.startswith("https://www.linkedin.com/oauth/v2/authorization")
    assert "state=" in url


@uses_test_session
def test_connect_503_when_linkedin_not_configured(db_session, monkeypatch) -> None:
    from apps.api.config import get_settings

    # A real .env may itself have LINKEDIN_REDIRECT_URI set (pydantic-settings
    # falls back to its env_file when the var isn't in the process
    # environment, so delenv alone doesn't reliably force it empty) —
    # setenv("", ...) overrides at the process-env layer, which takes
    # precedence over the .env file either way.
    monkeypatch.setenv("LINKEDIN_REDIRECT_URI", "")
    get_settings.cache_clear()
    brand, user = _setup_brand(db_session)

    response = client.post(
        f"/brands/{brand.id}/social-accounts/linkedin/connect", headers=_auth_headers(user)
    )
    get_settings.cache_clear()

    assert response.status_code == 503


@uses_test_session
def test_viewer_cannot_connect(db_session) -> None:
    brand, viewer = _setup_brand(db_session, UserRole.VIEWER)

    response = client.post(
        f"/brands/{brand.id}/social-accounts/linkedin/connect", headers=_auth_headers(viewer)
    )

    assert response.status_code == 403


@uses_test_session
def test_callback_rejects_invalid_state(db_session) -> None:
    response = client.get(
        "/oauth/linkedin/callback", params={"code": "abc", "state": "not-a-valid-jwt"}
    )

    assert response.status_code == 400


@uses_test_session
def test_callback_stores_tokens_encrypted_not_plaintext(db_session) -> None:
    from apps.api.routers.social_accounts import _create_state

    brand, _user = _setup_brand(db_session)
    state = _create_state(brand.id, "linkedin")

    fake_tokens = SocialTokens(
        access_token="super-secret-access-token",
        refresh_token="super-secret-refresh-token",
        expires_at=datetime.now(timezone.utc) + timedelta(days=60),
        scopes=["openid", "profile", "w_member_social"],
        external_account_id="linkedin-member-123",
    )

    with patch(
        "apps.api.routers.social_accounts.get_social_oauth_provider"
    ) as mock_get_provider:
        mock_get_provider.return_value.exchange_code.return_value = fake_tokens
        response = client.get(
            "/oauth/linkedin/callback", params={"code": "auth-code", "state": state}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["external_account_id"] == "linkedin-member-123"
    assert body["status"] == "active"
    assert "access_token" not in body  # never returned to the client

    # Raw DB row must hold ciphertext, not the plaintext token.
    account = (
        db_session.query(SocialAccount)
        .filter(SocialAccount.brand_id == brand.id, SocialAccount.platform == SocialPlatform.LINKEDIN)
        .one()
    )
    assert account.access_token_encrypted != "super-secret-access-token"
    assert "super-secret-access-token" not in account.access_token_encrypted
    assert account.refresh_token_encrypted != "super-secret-refresh-token"


@uses_test_session
def test_callback_reconnect_upserts_same_row(db_session) -> None:
    from apps.api.routers.social_accounts import _create_state

    brand, _user = _setup_brand(db_session)
    tokens_v1 = SocialTokens(
        access_token="token-v1", refresh_token=None, expires_at=None,
        scopes=["openid"], external_account_id="member-1",
    )
    tokens_v2 = SocialTokens(
        access_token="token-v2", refresh_token=None, expires_at=None,
        scopes=["openid"], external_account_id="member-1",
    )

    with patch("apps.api.routers.social_accounts.get_social_oauth_provider") as mock_provider:
        mock_provider.return_value.exchange_code.return_value = tokens_v1
        client.get("/oauth/linkedin/callback", params={"code": "c1", "state": _create_state(brand.id, "linkedin")})
        mock_provider.return_value.exchange_code.return_value = tokens_v2
        client.get("/oauth/linkedin/callback", params={"code": "c2", "state": _create_state(brand.id, "linkedin")})

    accounts = db_session.query(SocialAccount).filter(SocialAccount.brand_id == brand.id).all()
    assert len(accounts) == 1


@uses_test_session
def test_verify_marks_revoked_when_platform_rejects_token(db_session) -> None:
    brand, user = _setup_brand(db_session)
    account = SocialAccount(
        brand_id=brand.id,
        platform=SocialPlatform.LINKEDIN,
        access_token_encrypted="ciphertext-not-checked-directly",
    )
    db_session.add(account)
    db_session.flush()

    with patch("apps.api.routers.social_accounts.decrypt_token", return_value="whatever"), patch(
        "apps.api.routers.social_accounts.get_social_oauth_provider"
    ) as mock_provider:
        mock_provider.return_value.is_token_valid.return_value = False
        response = client.post(
            f"/brands/{brand.id}/social-accounts/{account.id}/verify", headers=_auth_headers(user)
        )

    assert response.status_code == 200
    assert response.json()["status"] == "revoked"


@uses_test_session
def test_verify_marks_expired_from_local_expiry_without_calling_platform(db_session) -> None:
    brand, user = _setup_brand(db_session)
    account = SocialAccount(
        brand_id=brand.id,
        platform=SocialPlatform.LINKEDIN,
        access_token_encrypted="ciphertext",
        token_expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db_session.add(account)
    db_session.flush()

    with patch("apps.api.routers.social_accounts.get_social_oauth_provider") as mock_provider:
        response = client.post(
            f"/brands/{brand.id}/social-accounts/{account.id}/verify", headers=_auth_headers(user)
        )

    assert response.status_code == 200
    assert response.json()["status"] == "expired"
    mock_provider.return_value.is_token_valid.assert_not_called()


@uses_test_session
def test_disconnect_wipes_tokens_and_marks_revoked(db_session) -> None:
    brand, user = _setup_brand(db_session)
    account = SocialAccount(
        brand_id=brand.id,
        platform=SocialPlatform.LINKEDIN,
        access_token_encrypted="ciphertext",
        refresh_token_encrypted="ciphertext-refresh",
    )
    db_session.add(account)
    db_session.flush()

    response = client.delete(
        f"/brands/{brand.id}/social-accounts/{account.id}", headers=_auth_headers(user)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "revoked"
    db_session.refresh(account)
    assert account.access_token_encrypted is None
    assert account.refresh_token_encrypted is None


@uses_test_session
def test_connect_x_returns_authorize_url_with_signed_state(db_session, monkeypatch) -> None:
    from apps.api.config import get_settings

    monkeypatch.setenv("X_REDIRECT_URI", "http://localhost:8000/oauth/x/callback")
    get_settings.cache_clear()
    brand, user = _setup_brand(db_session)

    response = client.post(
        f"/brands/{brand.id}/social-accounts/x/connect", headers=_auth_headers(user)
    )
    get_settings.cache_clear()

    assert response.status_code == 200
    url = response.json()["authorize_url"]
    assert url.startswith("https://twitter.com/i/oauth2/authorize")
    assert "state=" in url


@uses_test_session
def test_connect_503_when_x_not_configured(db_session, monkeypatch) -> None:
    from apps.api.config import get_settings

    monkeypatch.setenv("X_REDIRECT_URI", "")
    get_settings.cache_clear()
    brand, user = _setup_brand(db_session)

    response = client.post(
        f"/brands/{brand.id}/social-accounts/x/connect", headers=_auth_headers(user)
    )
    get_settings.cache_clear()

    assert response.status_code == 503


@uses_test_session
def test_x_callback_passes_state_as_pkce_code_verifier(db_session) -> None:
    from apps.api.routers.social_accounts import _create_state

    brand, _user = _setup_brand(db_session)
    state = _create_state(brand.id, "x")
    fake_tokens = SocialTokens(
        access_token="token", refresh_token=None, expires_at=None,
        scopes=["tweet.write"], external_account_id="x-user-1",
    )

    with patch("apps.api.routers.social_accounts.get_social_oauth_provider") as mock_provider:
        mock_provider.return_value.exchange_code.return_value = fake_tokens
        response = client.get("/oauth/x/callback", params={"code": "auth-code", "state": state})

        # This is the actual regression this issue was filed for: XProvider's
        # PKCE ("plain") requires code_verifier == the code_challenge sent to
        # authorize_url (state) — exchange_code must receive exactly `state`,
        # not redirect_uri or anything else.
        mock_provider.return_value.exchange_code.assert_called_once_with(
            code="auth-code", redirect_uri="http://localhost:8000/oauth/x/callback", code_verifier=state
        )

    assert response.status_code == 200
    account = (
        db_session.query(SocialAccount)
        .filter(SocialAccount.brand_id == brand.id, SocialAccount.platform == SocialPlatform.X)
        .one()
    )
    assert account.external_account_id == "x-user-1"


@uses_test_session
def test_state_from_one_platform_rejected_by_another_platforms_callback(db_session) -> None:
    from apps.api.routers.social_accounts import _create_state

    brand, _user = _setup_brand(db_session)
    linkedin_state = _create_state(brand.id, "linkedin")

    response = client.get("/oauth/x/callback", params={"code": "auth-code", "state": linkedin_state})

    assert response.status_code == 400


@uses_test_session
def test_cross_org_social_account_access_returns_404(db_session) -> None:
    brand, _owner = _setup_brand(db_session, UserRole.EDITOR, suffix="-1")
    _brand2, other_user = _setup_brand(db_session, UserRole.EDITOR, suffix="-2")
    account = SocialAccount(
        brand_id=brand.id, platform=SocialPlatform.LINKEDIN, access_token_encrypted="ciphertext"
    )
    db_session.add(account)
    db_session.flush()

    response = client.get(
        f"/brands/{brand.id}/social-accounts/{account.id}", headers=_auth_headers(other_user)
    )

    assert response.status_code == 404
