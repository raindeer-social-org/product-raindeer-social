import ast
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from apps.api.models import IntegrationCall
from packages.integrations.registry import get_social_publisher
from packages.integrations.social.base import PublishResult, SocialPublisher
from packages.integrations.social.linkedin_provider import LinkedInProvider
from packages.integrations.social.x_provider import XProvider

REPO_ROOT = Path(__file__).resolve().parents[3]

# Domains only linkedin_provider.py / x_provider.py are allowed to
# reference — everything else must go through SocialPublisher /
# SocialOAuthProvider instead of talking to the vendor directly.
VENDOR_MARKERS = {
    "linkedin.com": "linkedin_provider.py",
    "twitter.com": "x_provider.py",
}

ALLOWED_FILES = {"linkedin_provider.py", "x_provider.py"}


def _mock_response(json_data: dict | None = None, status_code: int = 200, headers=None) -> MagicMock:
    response = MagicMock()
    response.json.return_value = json_data if json_data is not None else {}
    response.status_code = status_code
    response.headers = headers or {}
    if status_code >= 400:
        import httpx

        def _raise(*args, **kwargs):
            raise httpx.HTTPStatusError("error", request=MagicMock(), response=response)

        response.raise_for_status.side_effect = _raise
    else:
        response.raise_for_status.return_value = None
    return response


# ---------------------------------------------------------------------
# Interface conformance
# ---------------------------------------------------------------------


def test_linkedin_provider_implements_social_publisher() -> None:
    provider = LinkedInProvider(client_id="cid", client_secret="secret")
    assert isinstance(provider, SocialPublisher)


def test_x_provider_implements_social_publisher() -> None:
    provider = XProvider(client_id="cid", client_secret="secret")
    assert isinstance(provider, SocialPublisher)


def test_registry_resolves_linkedin_publisher() -> None:
    assert isinstance(get_social_publisher("linkedin"), LinkedInProvider)


def test_registry_resolves_x_publisher() -> None:
    assert isinstance(get_social_publisher("x"), XProvider)


def test_registry_unknown_platform_raises() -> None:
    with pytest.raises(ValueError, match="Unknown social platform"):
        get_social_publisher("tiktok")


def test_no_other_file_references_linkedin_or_x_vendor_urls() -> None:
    """LinkedInProvider/XProvider must be the only files that know the
    vendor's domains — everything else (routers, agents, the future
    publish queue) is expected to depend only on SocialPublisher /
    SocialOAuthProvider."""
    offenders = []
    for py_file in REPO_ROOT.rglob("*.py"):
        parts = py_file.parts
        if any(part in {".venv", "venv", "node_modules", ".git", "tests"} for part in parts):
            continue
        if py_file.name in ALLOWED_FILES:
            continue
        try:
            text = py_file.read_text()
        except (UnicodeDecodeError, OSError):
            continue
        for marker in ("linkedin.com", "twitter.com", "api.x.com", "://x.com"):
            if marker in text:
                offenders.append(f"{py_file.relative_to(REPO_ROOT)} references {marker!r}")
    assert offenders == [], "\n".join(offenders)


def test_no_vendor_sdk_imports_outside_adapters() -> None:
    """Nothing besides the two adapter modules should import a
    LinkedIn/X-specific SDK package (there isn't one used in this repo —
    everything goes through httpx — but this guards against one creeping
    in through a side door)."""
    banned_modules = {"linkedin_api", "linkedin", "tweepy", "twitter"}
    offenders = []
    for py_file in REPO_ROOT.rglob("*.py"):
        if any(part in {".venv", "venv", "node_modules", ".git"} for part in py_file.parts):
            continue
        if py_file.name in ALLOWED_FILES:
            continue
        try:
            tree = ast.parse(py_file.read_text())
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in banned_modules:
                        offenders.append(f"{py_file.relative_to(REPO_ROOT)} imports {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.module.split(".")[0] in banned_modules:
                    offenders.append(f"{py_file.relative_to(REPO_ROOT)} imports from {node.module}")
    assert offenders == [], "\n".join(offenders)


# ---------------------------------------------------------------------
# LinkedIn: successful publish
# ---------------------------------------------------------------------


def test_linkedin_publish_success_returns_populated_result(db_session) -> None:
    provider = LinkedInProvider(client_id="cid", client_secret="secret")
    member_response = _mock_response({"sub": "member-1"})
    post_response = _mock_response({"id": "urn:li:share:123"}, headers={"x-restli-id": "urn:li:share:123"})

    with patch("httpx.get", return_value=member_response), patch(
        "httpx.post", return_value=post_response
    ):
        result = provider.publish(access_token="good-token", content="hello world")

    assert isinstance(result, PublishResult)
    assert result.success is True
    assert result.platform_post_id == "urn:li:share:123"
    assert result.platform_post_url is not None
    assert result.error is None
    assert result.refreshed_tokens is None


def test_linkedin_publish_success_logs_integration_call(db_session) -> None:
    provider = LinkedInProvider(client_id="cid", client_secret="secret")
    member_response = _mock_response({"sub": "member-1"})
    post_response = _mock_response({"id": "urn:li:share:123"}, headers={"x-restli-id": "urn:li:share:123"})

    with patch("httpx.get", return_value=member_response), patch(
        "httpx.post", return_value=post_response
    ):
        provider.publish(access_token="good-token", content="hello world")

    logged = (
        db_session.query(IntegrationCall)
        .filter_by(provider="linkedin", capability="publish")
        .order_by(IntegrationCall.created_at.desc())
        .first()
    )
    assert logged is not None
    assert logged.success is True


# ---------------------------------------------------------------------
# LinkedIn: expired token -> transparent refresh + retry
# ---------------------------------------------------------------------


def test_linkedin_publish_refreshes_and_retries_once_on_expired_token(db_session) -> None:
    provider = LinkedInProvider(client_id="cid", client_secret="secret")

    expired_member_response = _mock_response(status_code=401)
    refresh_response = _mock_response({"access_token": "new-token", "expires_in": 5184000})
    retry_member_response = _mock_response({"sub": "member-1"})
    retry_post_response = _mock_response(
        {"id": "urn:li:share:999"}, headers={"x-restli-id": "urn:li:share:999"}
    )

    get_calls = [expired_member_response, retry_member_response]
    post_calls = [refresh_response, retry_post_response]

    with patch("httpx.get", side_effect=get_calls) as mock_get, patch(
        "httpx.post", side_effect=post_calls
    ) as mock_post:
        result = provider.publish(
            access_token="stale-token", content="hello world", refresh_token="refresh-me"
        )

    assert result.success is True
    assert result.platform_post_id == "urn:li:share:999"
    assert result.refreshed_tokens is not None
    assert result.refreshed_tokens.access_token == "new-token"

    # Exactly one refresh + one retry: one call to httpx.get for the first
    # (failed) member lookup, one refresh POST, one retry member lookup,
    # one retry publish POST.
    assert mock_get.call_count == 2
    assert mock_post.call_count == 2


def test_linkedin_publish_expired_token_not_surfaced_as_failure(db_session) -> None:
    provider = LinkedInProvider(client_id="cid", client_secret="secret")

    get_calls = [_mock_response(status_code=401), _mock_response({"sub": "member-1"})]
    post_calls = [
        _mock_response({"access_token": "new-token"}),
        _mock_response({"id": "id-1"}, headers={"x-restli-id": "id-1"}),
    ]

    with patch("httpx.get", side_effect=get_calls), patch("httpx.post", side_effect=post_calls):
        result = provider.publish(
            access_token="stale-token", content="hello world", refresh_token="refresh-me"
        )

    assert result.success is True
    assert result.error is None


def test_linkedin_publish_logs_both_attempts_on_refresh_flow(db_session) -> None:
    provider = LinkedInProvider(client_id="cid", client_secret="secret")

    get_calls = [_mock_response(status_code=401), _mock_response({"sub": "member-1"})]
    post_calls = [
        _mock_response({"access_token": "new-token"}),
        _mock_response({"id": "id-1"}, headers={"x-restli-id": "id-1"}),
    ]

    with patch("httpx.get", side_effect=get_calls), patch("httpx.post", side_effect=post_calls):
        provider.publish(access_token="stale-token", content="hello world", refresh_token="refresh-me")

    # IntegrationCall rows are committed on a separate connection
    # (track_integration_call opens its own SessionLocal()), so other
    # tests' rows are visible too — take just this test's most recent 2
    # "publish" attempts (in chronological order) rather than assuming
    # the table only has this test's rows in it.
    publish_logs = list(
        reversed(
            db_session.query(IntegrationCall)
            .filter_by(provider="linkedin", capability="publish")
            .order_by(IntegrationCall.created_at.desc())
            .limit(2)
            .all()
        )
    )
    assert len(publish_logs) == 2
    assert publish_logs[0].success is False
    assert publish_logs[1].success is True

    refresh_log = (
        db_session.query(IntegrationCall)
        .filter_by(provider="linkedin", capability="oauth_refresh")
        .order_by(IntegrationCall.created_at.desc())
        .first()
    )
    assert refresh_log is not None
    assert refresh_log.success is True


def test_linkedin_publish_expired_token_without_refresh_token_fails(db_session) -> None:
    provider = LinkedInProvider(client_id="cid", client_secret="secret")

    with patch("httpx.get", return_value=_mock_response(status_code=401)):
        result = provider.publish(access_token="stale-token", content="hello world")

    assert result.success is False
    assert result.error is not None
    assert "refresh" in result.error.lower()


def test_linkedin_publish_refresh_failure_surfaces_as_real_failure(db_session) -> None:
    provider = LinkedInProvider(client_id="cid", client_secret="secret")

    with patch("httpx.get", return_value=_mock_response(status_code=401)), patch(
        "httpx.post", return_value=_mock_response(status_code=400)
    ):
        result = provider.publish(
            access_token="stale-token", content="hello world", refresh_token="bad-refresh"
        )

    assert result.success is False
    assert result.error is not None


def test_linkedin_publish_refresh_failure_logged(db_session) -> None:
    provider = LinkedInProvider(client_id="cid", client_secret="secret")

    with patch("httpx.get", return_value=_mock_response(status_code=401)), patch(
        "httpx.post", return_value=_mock_response(status_code=400)
    ):
        provider.publish(access_token="stale-token", content="hello world", refresh_token="bad-refresh")

    refresh_logs = (
        db_session.query(IntegrationCall)
        .filter_by(provider="linkedin", capability="oauth_refresh")
        .order_by(IntegrationCall.created_at.desc())
        .all()
    )
    assert len(refresh_logs) >= 1
    assert refresh_logs[0].success is False


def test_linkedin_publish_retry_failure_after_successful_refresh_is_a_failure(db_session) -> None:
    provider = LinkedInProvider(client_id="cid", client_secret="secret")

    get_calls = [_mock_response(status_code=401), _mock_response(status_code=401)]
    post_calls = [_mock_response({"access_token": "new-token"})]

    with patch("httpx.get", side_effect=get_calls), patch("httpx.post", side_effect=post_calls):
        result = provider.publish(
            access_token="stale-token", content="hello world", refresh_token="refresh-me"
        )

    assert result.success is False
    assert result.error is not None


# ---------------------------------------------------------------------
# LinkedIn: hard (non-token) failures
# ---------------------------------------------------------------------


def test_linkedin_publish_hard_http_failure_returns_failed_result(db_session) -> None:
    provider = LinkedInProvider(client_id="cid", client_secret="secret")

    with patch("httpx.get", return_value=_mock_response({"sub": "member-1"})), patch(
        "httpx.post", return_value=_mock_response(status_code=500)
    ):
        result = provider.publish(access_token="good-token", content="hello world")

    assert result.success is False
    assert result.error is not None


def test_linkedin_publish_hard_failure_logged(db_session) -> None:
    provider = LinkedInProvider(client_id="cid", client_secret="secret")

    with patch("httpx.get", return_value=_mock_response({"sub": "member-1"})), patch(
        "httpx.post", return_value=_mock_response(status_code=500)
    ):
        provider.publish(access_token="good-token", content="hello world")

    logged = (
        db_session.query(IntegrationCall)
        .filter_by(provider="linkedin", capability="publish")
        .order_by(IntegrationCall.created_at.desc())
        .first()
    )
    assert logged is not None
    assert logged.success is False
    assert logged.error_message is not None


# ---------------------------------------------------------------------
# X: OAuth-connection interface (SocialOAuthProvider), same shape as
# LinkedInProvider's from #10 — exercised here for coverage since #30
# is what introduces XProvider.
# ---------------------------------------------------------------------


def test_x_authorize_url_includes_state_and_scopes() -> None:
    provider = XProvider(client_id="cid", client_secret="secret")
    url = provider.authorize_url(state="signed-state", redirect_uri="https://app.test/callback")

    assert url.startswith(XProvider.AUTHORIZE_URL)
    assert "client_id=cid" in url
    assert "state=signed-state" in url
    assert "tweet.write" in url


def test_x_exchange_code_returns_tokens_and_fetches_user_id(db_session) -> None:
    provider = XProvider(client_id="cid", client_secret="secret")
    token_response = _mock_response(
        {"access_token": "at-123", "refresh_token": "rt-123", "expires_in": 7200, "scope": "tweet.read tweet.write"}
    )
    userinfo_response = _mock_response({"data": {"id": "x-user-42"}})

    with patch("httpx.post", return_value=token_response), patch(
        "httpx.get", return_value=userinfo_response
    ):
        tokens = provider.exchange_code(code="auth-code", redirect_uri="https://app.test/callback")

    assert tokens.access_token == "at-123"
    assert tokens.refresh_token == "rt-123"
    assert tokens.external_account_id == "x-user-42"
    assert tokens.expires_at is not None
    assert tokens.scopes == ["tweet.read", "tweet.write"]


def test_x_is_token_valid_true_on_200() -> None:
    provider = XProvider(client_id="cid", client_secret="secret")
    with patch("httpx.get", return_value=_mock_response({"data": {"id": "x-user-42"}})):
        assert provider.is_token_valid("some-token") is True


def test_x_is_token_valid_false_when_platform_rejects_it() -> None:
    provider = XProvider(client_id="cid", client_secret="secret")
    with patch("httpx.get", return_value=_mock_response(status_code=401)):
        assert provider.is_token_valid("revoked-token") is False


# ---------------------------------------------------------------------
# X: successful publish
# ---------------------------------------------------------------------


def test_x_publish_success_returns_populated_result(db_session) -> None:
    provider = XProvider(client_id="cid", client_secret="secret")
    tweet_response = _mock_response({"data": {"id": "tweet-123", "text": "hello"}})

    with patch("httpx.post", return_value=tweet_response):
        result = provider.publish(access_token="good-token", content="hello world")

    assert isinstance(result, PublishResult)
    assert result.success is True
    assert result.platform_post_id == "tweet-123"
    assert result.platform_post_url is not None
    assert result.error is None


def test_x_publish_success_logs_integration_call(db_session) -> None:
    provider = XProvider(client_id="cid", client_secret="secret")
    tweet_response = _mock_response({"data": {"id": "tweet-123"}})

    with patch("httpx.post", return_value=tweet_response):
        provider.publish(access_token="good-token", content="hello world")

    logged = (
        db_session.query(IntegrationCall)
        .filter_by(provider="x", capability="publish")
        .order_by(IntegrationCall.created_at.desc())
        .first()
    )
    assert logged is not None
    assert logged.success is True


# ---------------------------------------------------------------------
# X: expired token -> transparent refresh + retry
# ---------------------------------------------------------------------


def test_x_publish_refreshes_and_retries_once_on_expired_token(db_session) -> None:
    provider = XProvider(client_id="cid", client_secret="secret")

    post_calls = [
        _mock_response(status_code=401),
        _mock_response({"access_token": "new-token", "refresh_token": "new-refresh"}),
        _mock_response({"data": {"id": "tweet-999"}}),
    ]

    with patch("httpx.post", side_effect=post_calls) as mock_post:
        result = provider.publish(
            access_token="stale-token", content="hello world", refresh_token="refresh-me"
        )

    assert result.success is True
    assert result.platform_post_id == "tweet-999"
    assert result.refreshed_tokens is not None
    assert result.refreshed_tokens.access_token == "new-token"
    assert mock_post.call_count == 3


def test_x_publish_expired_token_not_surfaced_as_failure(db_session) -> None:
    provider = XProvider(client_id="cid", client_secret="secret")

    post_calls = [
        _mock_response(status_code=401),
        _mock_response({"access_token": "new-token"}),
        _mock_response({"data": {"id": "tweet-1"}}),
    ]

    with patch("httpx.post", side_effect=post_calls):
        result = provider.publish(
            access_token="stale-token", content="hello world", refresh_token="refresh-me"
        )

    assert result.success is True
    assert result.error is None


def test_x_publish_logs_both_attempts_on_refresh_flow(db_session) -> None:
    provider = XProvider(client_id="cid", client_secret="secret")

    post_calls = [
        _mock_response(status_code=401),
        _mock_response({"access_token": "new-token"}),
        _mock_response({"data": {"id": "tweet-1"}}),
    ]

    with patch("httpx.post", side_effect=post_calls):
        provider.publish(access_token="stale-token", content="hello world", refresh_token="refresh-me")

    publish_logs = list(
        reversed(
            db_session.query(IntegrationCall)
            .filter_by(provider="x", capability="publish")
            .order_by(IntegrationCall.created_at.desc())
            .limit(2)
            .all()
        )
    )
    assert len(publish_logs) == 2
    assert publish_logs[0].success is False
    assert publish_logs[1].success is True


def test_x_publish_expired_token_without_refresh_token_fails(db_session) -> None:
    provider = XProvider(client_id="cid", client_secret="secret")

    with patch("httpx.post", return_value=_mock_response(status_code=401)):
        result = provider.publish(access_token="stale-token", content="hello world")

    assert result.success is False
    assert result.error is not None


def test_x_publish_refresh_failure_surfaces_as_real_failure(db_session) -> None:
    provider = XProvider(client_id="cid", client_secret="secret")

    post_calls = [_mock_response(status_code=401), _mock_response(status_code=400)]

    with patch("httpx.post", side_effect=post_calls):
        result = provider.publish(
            access_token="stale-token", content="hello world", refresh_token="bad-refresh"
        )

    assert result.success is False
    assert result.error is not None


def test_x_publish_refresh_failure_logged(db_session) -> None:
    provider = XProvider(client_id="cid", client_secret="secret")

    post_calls = [_mock_response(status_code=401), _mock_response(status_code=400)]

    with patch("httpx.post", side_effect=post_calls):
        provider.publish(access_token="stale-token", content="hello world", refresh_token="bad-refresh")

    refresh_logs = (
        db_session.query(IntegrationCall)
        .filter_by(provider="x", capability="oauth_refresh")
        .order_by(IntegrationCall.created_at.desc())
        .all()
    )
    assert len(refresh_logs) >= 1
    assert refresh_logs[0].success is False


# ---------------------------------------------------------------------
# X: hard (non-token) failures
# ---------------------------------------------------------------------


def test_x_publish_hard_http_failure_returns_failed_result(db_session) -> None:
    provider = XProvider(client_id="cid", client_secret="secret")

    with patch("httpx.post", return_value=_mock_response(status_code=500)):
        result = provider.publish(access_token="good-token", content="hello world")

    assert result.success is False
    assert result.error is not None


def test_x_publish_hard_failure_logged(db_session) -> None:
    provider = XProvider(client_id="cid", client_secret="secret")

    with patch("httpx.post", return_value=_mock_response(status_code=500)):
        provider.publish(access_token="good-token", content="hello world")

    logged = (
        db_session.query(IntegrationCall)
        .filter_by(provider="x", capability="publish")
        .order_by(IntegrationCall.created_at.desc())
        .first()
    )
    assert logged is not None
    assert logged.success is False
    assert logged.error_message is not None
