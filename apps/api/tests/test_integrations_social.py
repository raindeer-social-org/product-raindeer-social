from unittest.mock import MagicMock, patch

from apps.api.models import IntegrationCall
from packages.integrations.social.encryption import decrypt_token, encrypt_token
from packages.integrations.social.linkedin_provider import LinkedInProvider


def test_encrypt_token_round_trips() -> None:
    ciphertext = encrypt_token("plaintext-access-token")
    assert ciphertext != "plaintext-access-token"
    assert decrypt_token(ciphertext) == "plaintext-access-token"


def test_encrypt_token_is_not_deterministic() -> None:
    # Fernet includes a random nonce/IV — same plaintext, different
    # ciphertext each time, which is what makes it safe to store.
    a = encrypt_token("same-token")
    b = encrypt_token("same-token")
    assert a != b
    assert decrypt_token(a) == decrypt_token(b) == "same-token"


def _mock_response(json_data: dict, status_code: int = 200) -> MagicMock:
    response = MagicMock()
    response.json.return_value = json_data
    response.status_code = status_code
    response.raise_for_status.return_value = None
    return response


def test_authorize_url_includes_state_and_scopes() -> None:
    provider = LinkedInProvider(client_id="cid", client_secret="secret")
    url = provider.authorize_url(state="signed-state", redirect_uri="https://app.test/callback")

    assert url.startswith(LinkedInProvider.AUTHORIZE_URL)
    assert "client_id=cid" in url
    assert "state=signed-state" in url
    assert "w_member_social" in url


def test_exchange_code_returns_tokens_and_fetches_member_id() -> None:
    provider = LinkedInProvider(client_id="cid", client_secret="secret")
    token_response = _mock_response(
        {"access_token": "at-123", "refresh_token": "rt-123", "expires_in": 5184000, "scope": "openid,profile"}
    )
    userinfo_response = _mock_response({"sub": "linkedin-member-42"})

    with patch("httpx.post", return_value=token_response), patch(
        "httpx.get", return_value=userinfo_response
    ):
        tokens = provider.exchange_code(code="auth-code", redirect_uri="https://app.test/callback")

    assert tokens.access_token == "at-123"
    assert tokens.refresh_token == "rt-123"
    assert tokens.external_account_id == "linkedin-member-42"
    assert tokens.expires_at is not None
    assert tokens.scopes == ["openid", "profile"]


def test_exchange_code_logs_integration_call(db_session) -> None:
    provider = LinkedInProvider(client_id="cid", client_secret="secret")
    token_response = _mock_response({"access_token": "at-123", "scope": ""})
    userinfo_response = _mock_response({"sub": "member-1"})

    with patch("httpx.post", return_value=token_response), patch(
        "httpx.get", return_value=userinfo_response
    ):
        provider.exchange_code(code="auth-code", redirect_uri="https://app.test/callback")

    logged = (
        db_session.query(IntegrationCall)
        .filter_by(provider="linkedin", capability="oauth_exchange")
        .order_by(IntegrationCall.created_at.desc())
        .first()
    )
    assert logged is not None
    assert logged.success is True


def test_is_token_valid_true_on_200() -> None:
    provider = LinkedInProvider(client_id="cid", client_secret="secret")
    with patch("httpx.get", return_value=_mock_response({"sub": "member-1"}, status_code=200)):
        assert provider.is_token_valid("some-token") is True


def test_is_token_valid_false_when_platform_rejects_it() -> None:
    provider = LinkedInProvider(client_id="cid", client_secret="secret")
    with patch("httpx.get", return_value=_mock_response({}, status_code=401)):
        assert provider.is_token_valid("revoked-token") is False
