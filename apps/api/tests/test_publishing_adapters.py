import ast
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from apps.api.models import IntegrationCall
from packages.integrations.registry import get_social_publisher
from packages.integrations.social.base import PublishResult, SocialPublisher
from packages.integrations.social.facebook_provider import FacebookProvider
from packages.integrations.social.instagram_provider import InstagramProvider
from packages.integrations.social.linkedin_provider import LinkedInProvider
from packages.integrations.social.pinterest_provider import PinterestProvider
from packages.integrations.social.threads_provider import ThreadsProvider
from packages.integrations.social.tiktok_provider import TikTokProvider
from packages.integrations.social.x_provider import XProvider
from packages.integrations.social.youtube_provider import YouTubeProvider

REPO_ROOT = Path(__file__).resolve().parents[3]

# Domains only the matching provider file is allowed to reference —
# everything else must go through SocialPublisher / SocialOAuthProvider
# instead of talking to the vendor directly. Instagram/Facebook share
# facebook.com/graph.facebook.com (same Meta Graph API host), so both
# provider files are listed for that marker.
VENDOR_MARKERS = {
    "linkedin.com": ("linkedin_provider.py",),
    "twitter.com": ("x_provider.py",),
    "facebook.com": ("facebook_provider.py", "instagram_provider.py"),
    "threads.net": ("threads_provider.py",),
    "googleapis.com": ("youtube_provider.py",),
    "tiktok.com": ("tiktok_provider.py",),
    "tiktokapis.com": ("tiktok_provider.py",),
    "pinterest.com": ("pinterest_provider.py",),
}

ALLOWED_FILES = {
    "linkedin_provider.py",
    "x_provider.py",
    "facebook_provider.py",
    "instagram_provider.py",
    "threads_provider.py",
    "youtube_provider.py",
    "tiktok_provider.py",
    "pinterest_provider.py",
}


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


def test_facebook_provider_implements_social_publisher() -> None:
    provider = FacebookProvider(client_id="cid", client_secret="secret")
    assert isinstance(provider, SocialPublisher)


def test_instagram_provider_implements_social_publisher() -> None:
    provider = InstagramProvider(client_id="cid", client_secret="secret")
    assert isinstance(provider, SocialPublisher)


def test_threads_provider_implements_social_publisher() -> None:
    provider = ThreadsProvider(client_id="cid", client_secret="secret")
    assert isinstance(provider, SocialPublisher)


def test_registry_resolves_facebook_publisher() -> None:
    assert isinstance(get_social_publisher("facebook"), FacebookProvider)


def test_registry_resolves_instagram_publisher() -> None:
    assert isinstance(get_social_publisher("instagram"), InstagramProvider)


def test_registry_resolves_threads_publisher() -> None:
    assert isinstance(get_social_publisher("threads"), ThreadsProvider)


def test_youtube_provider_implements_social_publisher() -> None:
    provider = YouTubeProvider(client_id="cid", client_secret="secret")
    assert isinstance(provider, SocialPublisher)


def test_tiktok_provider_implements_social_publisher() -> None:
    provider = TikTokProvider(client_key="key", client_secret="secret")
    assert isinstance(provider, SocialPublisher)


def test_pinterest_provider_implements_social_publisher() -> None:
    provider = PinterestProvider(client_id="cid", client_secret="secret")
    assert isinstance(provider, SocialPublisher)


def test_registry_resolves_youtube_publisher() -> None:
    assert isinstance(get_social_publisher("youtube"), YouTubeProvider)


def test_registry_resolves_tiktok_publisher() -> None:
    assert isinstance(get_social_publisher("tiktok"), TikTokProvider)


def test_registry_resolves_pinterest_publisher() -> None:
    assert isinstance(get_social_publisher("pinterest"), PinterestProvider)


def test_registry_unknown_platform_raises() -> None:
    with pytest.raises(ValueError, match="Unknown social platform"):
        get_social_publisher("snapchat")


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
        for marker in (*VENDOR_MARKERS, "api.x.com", "://x.com"):
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


# ---------------------------------------------------------------------
# Issue #33: get_engagement() — same "never raises, caller decides"
# shape as publish() above, exercised here for the same reason XProvider's
# OAuth/publish methods are: this is the only file allowed to build these
# adapters, so their real HTTP behavior belongs in this test module.
# ---------------------------------------------------------------------


def test_linkedin_get_engagement_success_returns_metrics(db_session) -> None:
    provider = LinkedInProvider(client_id="cid", client_secret="secret")

    with patch(
        "httpx.get",
        return_value=_mock_response({"likes": 10, "comments": 2, "shares": 1, "impressions": 500}),
    ):
        result = provider.get_engagement(access_token="good-token", platform_post_id="123")

    assert result.success is True
    assert result.rate_limited is False
    assert result.metrics.likes == 10
    assert result.metrics.comments == 2
    assert result.metrics.shares == 1
    assert result.metrics.impressions == 500


def test_linkedin_get_engagement_logs_integration_call(db_session) -> None:
    provider = LinkedInProvider(client_id="cid", client_secret="secret")

    with patch(
        "httpx.get", return_value=_mock_response({"likes": 1, "comments": 0, "shares": 0, "impressions": 5})
    ):
        provider.get_engagement(access_token="good-token", platform_post_id="123")

    logged = (
        db_session.query(IntegrationCall)
        .filter_by(provider="linkedin", capability="get_engagement")
        .order_by(IntegrationCall.created_at.desc())
        .first()
    )
    assert logged is not None
    assert logged.success is True


def test_linkedin_get_engagement_rate_limited_returns_flag_not_raise(db_session) -> None:
    provider = LinkedInProvider(client_id="cid", client_secret="secret")

    with patch("httpx.get", return_value=_mock_response(status_code=429)):
        result = provider.get_engagement(access_token="good-token", platform_post_id="123")

    assert result.success is False
    assert result.rate_limited is True
    assert result.metrics is None


def test_linkedin_get_engagement_hard_http_failure_returns_failed_result(db_session) -> None:
    provider = LinkedInProvider(client_id="cid", client_secret="secret")

    with patch("httpx.get", return_value=_mock_response(status_code=500)):
        result = provider.get_engagement(access_token="good-token", platform_post_id="123")

    assert result.success is False
    assert result.rate_limited is False
    assert result.error is not None


def test_x_get_engagement_success_returns_metrics(db_session) -> None:
    provider = XProvider(client_id="cid", client_secret="secret")

    with patch(
        "httpx.get",
        return_value=_mock_response(
            {
                "data": {
                    "id": "999",
                    "public_metrics": {
                        "like_count": 8,
                        "reply_count": 3,
                        "retweet_count": 2,
                        "impression_count": 300,
                    },
                }
            }
        ),
    ):
        result = provider.get_engagement(access_token="good-token", platform_post_id="999")

    assert result.success is True
    assert result.metrics.likes == 8
    assert result.metrics.comments == 3
    assert result.metrics.shares == 2
    assert result.metrics.impressions == 300


def test_x_get_engagement_rate_limited_returns_flag_not_raise(db_session) -> None:
    provider = XProvider(client_id="cid", client_secret="secret")

    with patch("httpx.get", return_value=_mock_response(status_code=429)):
        result = provider.get_engagement(access_token="good-token", platform_post_id="999")

    assert result.success is False
    assert result.rate_limited is True
    assert result.metrics is None


def test_x_get_engagement_logs_integration_call(db_session) -> None:
    provider = XProvider(client_id="cid", client_secret="secret")

    with patch(
        "httpx.get",
        return_value=_mock_response(
            {"data": {"id": "1", "public_metrics": {"like_count": 1, "reply_count": 0, "retweet_count": 0, "impression_count": 1}}}
        ),
    ):
        provider.get_engagement(access_token="good-token", platform_post_id="999")

    logged = (
        db_session.query(IntegrationCall)
        .filter_by(provider="x", capability="get_engagement")
        .order_by(IntegrationCall.created_at.desc())
        .first()
    )
    assert logged is not None
    assert logged.success is True


# ---------------------------------------------------------------------
# Facebook: OAuth-connection interface, same shape as LinkedIn/X's above —
# exercised here for coverage since #110 is what introduces FacebookProvider.
# ---------------------------------------------------------------------


def test_facebook_authorize_url_includes_state_and_scopes() -> None:
    provider = FacebookProvider(client_id="cid", client_secret="secret")
    url = provider.authorize_url(state="signed-state", redirect_uri="https://app.test/callback")

    assert url.startswith(FacebookProvider.AUTHORIZE_URL)
    assert "client_id=cid" in url
    assert "state=signed-state" in url
    assert "pages_manage_posts" in url


def test_facebook_exchange_code_returns_tokens_and_fetches_page_id() -> None:
    provider = FacebookProvider(client_id="cid", client_secret="secret")
    token_response = _mock_response({"access_token": "at-123", "expires_in": 5184000})
    page_response = _mock_response({"id": "page-42", "name": "Acme Page"})

    with patch("httpx.post", return_value=token_response), patch(
        "httpx.get", return_value=page_response
    ):
        tokens = provider.exchange_code(code="auth-code", redirect_uri="https://app.test/callback")

    assert tokens.access_token == "at-123"
    assert tokens.refresh_token is None
    assert tokens.external_account_id == "page-42"
    assert tokens.expires_at is not None


def test_facebook_is_token_valid_true_on_200() -> None:
    provider = FacebookProvider(client_id="cid", client_secret="secret")
    with patch("httpx.get", return_value=_mock_response({"id": "page-42"}, status_code=200)):
        assert provider.is_token_valid("some-token") is True


def test_facebook_is_token_valid_false_when_platform_rejects_it() -> None:
    provider = FacebookProvider(client_id="cid", client_secret="secret")
    with patch("httpx.get", return_value=_mock_response(status_code=401)):
        assert provider.is_token_valid("revoked-token") is False


# ---------------------------------------------------------------------
# Facebook: successful publish
# ---------------------------------------------------------------------


def test_facebook_publish_success_returns_populated_result(db_session) -> None:
    provider = FacebookProvider(client_id="cid", client_secret="secret")
    page_response = _mock_response({"id": "page-42"})
    post_response = _mock_response({"id": "page-42_999"})

    with patch("httpx.get", return_value=page_response), patch(
        "httpx.post", return_value=post_response
    ):
        result = provider.publish(access_token="good-token", content="hello world")

    assert isinstance(result, PublishResult)
    assert result.success is True
    assert result.platform_post_id == "page-42_999"
    assert result.platform_post_url is not None
    assert result.error is None
    assert result.refreshed_tokens is None


def test_facebook_publish_success_logs_integration_call(db_session) -> None:
    provider = FacebookProvider(client_id="cid", client_secret="secret")
    page_response = _mock_response({"id": "page-42"})
    post_response = _mock_response({"id": "page-42_999"})

    with patch("httpx.get", return_value=page_response), patch(
        "httpx.post", return_value=post_response
    ):
        provider.publish(access_token="good-token", content="hello world")

    logged = (
        db_session.query(IntegrationCall)
        .filter_by(provider="facebook", capability="publish")
        .order_by(IntegrationCall.created_at.desc())
        .first()
    )
    assert logged is not None
    assert logged.success is True


def test_facebook_publish_includes_link_when_media_urls_given(db_session) -> None:
    provider = FacebookProvider(client_id="cid", client_secret="secret")
    page_response = _mock_response({"id": "page-42"})
    post_response = _mock_response({"id": "page-42_999"})

    with patch("httpx.get", return_value=page_response), patch(
        "httpx.post", return_value=post_response
    ) as mock_post:
        result = provider.publish(
            access_token="good-token",
            content="hello world",
            media_urls=["https://cdn.test/image.png"],
        )

    assert result.success is True
    assert mock_post.call_args.kwargs["json"]["link"] == "https://cdn.test/image.png"


# ---------------------------------------------------------------------
# Facebook: expired token -> transparent refresh + retry
# ---------------------------------------------------------------------


def test_facebook_publish_refreshes_and_retries_once_on_expired_token(db_session) -> None:
    provider = FacebookProvider(client_id="cid", client_secret="secret")

    expired_page_response = _mock_response(status_code=401)
    refresh_response = _mock_response({"access_token": "new-token", "expires_in": 5184000})
    retry_page_response = _mock_response({"id": "page-42"})
    retry_post_response = _mock_response({"id": "page-42_777"})

    get_calls = [expired_page_response, retry_page_response]
    post_calls = [refresh_response, retry_post_response]

    with patch("httpx.get", side_effect=get_calls) as mock_get, patch(
        "httpx.post", side_effect=post_calls
    ) as mock_post:
        result = provider.publish(
            access_token="stale-token", content="hello world", refresh_token="prior-long-lived-token"
        )

    assert result.success is True
    assert result.platform_post_id == "page-42_777"
    assert result.refreshed_tokens is not None
    assert result.refreshed_tokens.access_token == "new-token"
    assert mock_get.call_count == 2
    assert mock_post.call_count == 2


def test_facebook_publish_expired_token_not_surfaced_as_failure(db_session) -> None:
    provider = FacebookProvider(client_id="cid", client_secret="secret")

    get_calls = [_mock_response(status_code=401), _mock_response({"id": "page-42"})]
    post_calls = [
        _mock_response({"access_token": "new-token"}),
        _mock_response({"id": "id-1"}),
    ]

    with patch("httpx.get", side_effect=get_calls), patch("httpx.post", side_effect=post_calls):
        result = provider.publish(
            access_token="stale-token", content="hello world", refresh_token="prior-token"
        )

    assert result.success is True
    assert result.error is None


def test_facebook_publish_expired_token_without_refresh_token_fails(db_session) -> None:
    provider = FacebookProvider(client_id="cid", client_secret="secret")

    with patch("httpx.get", return_value=_mock_response(status_code=401)):
        result = provider.publish(access_token="stale-token", content="hello world")

    assert result.success is False
    assert result.error is not None
    assert "refresh" in result.error.lower()


def test_facebook_publish_refresh_failure_surfaces_as_real_failure(db_session) -> None:
    provider = FacebookProvider(client_id="cid", client_secret="secret")

    with patch("httpx.get", return_value=_mock_response(status_code=401)), patch(
        "httpx.post", return_value=_mock_response(status_code=400)
    ):
        result = provider.publish(
            access_token="stale-token", content="hello world", refresh_token="bad-token"
        )

    assert result.success is False
    assert result.error is not None


# ---------------------------------------------------------------------
# Facebook: hard (non-token) failures
# ---------------------------------------------------------------------


def test_facebook_publish_hard_http_failure_returns_failed_result(db_session) -> None:
    provider = FacebookProvider(client_id="cid", client_secret="secret")

    with patch("httpx.get", return_value=_mock_response({"id": "page-42"})), patch(
        "httpx.post", return_value=_mock_response(status_code=500)
    ):
        result = provider.publish(access_token="good-token", content="hello world")

    assert result.success is False
    assert result.error is not None


def test_facebook_publish_hard_failure_logged(db_session) -> None:
    provider = FacebookProvider(client_id="cid", client_secret="secret")

    with patch("httpx.get", return_value=_mock_response({"id": "page-42"})), patch(
        "httpx.post", return_value=_mock_response(status_code=500)
    ):
        provider.publish(access_token="good-token", content="hello world")

    logged = (
        db_session.query(IntegrationCall)
        .filter_by(provider="facebook", capability="publish")
        .order_by(IntegrationCall.created_at.desc())
        .first()
    )
    assert logged is not None
    assert logged.success is False
    assert logged.error_message is not None


# ---------------------------------------------------------------------
# Facebook: get_engagement()
# ---------------------------------------------------------------------


def test_facebook_get_engagement_success_returns_metrics(db_session) -> None:
    provider = FacebookProvider(client_id="cid", client_secret="secret")

    with patch(
        "httpx.get",
        return_value=_mock_response(
            {
                "likes": {"summary": {"total_count": 10}},
                "comments": {"summary": {"total_count": 4}},
                "shares": {"count": 2},
            }
        ),
    ):
        result = provider.get_engagement(access_token="good-token", platform_post_id="page-42_999")

    assert result.success is True
    assert result.rate_limited is False
    assert result.metrics.likes == 10
    assert result.metrics.comments == 4
    assert result.metrics.shares == 2
    assert result.metrics.impressions == 0


def test_facebook_get_engagement_rate_limited_returns_flag_not_raise(db_session) -> None:
    provider = FacebookProvider(client_id="cid", client_secret="secret")

    with patch("httpx.get", return_value=_mock_response(status_code=429)):
        result = provider.get_engagement(access_token="good-token", platform_post_id="page-42_999")

    assert result.success is False
    assert result.rate_limited is True
    assert result.metrics is None


def test_facebook_get_engagement_hard_http_failure_returns_failed_result(db_session) -> None:
    provider = FacebookProvider(client_id="cid", client_secret="secret")

    with patch("httpx.get", return_value=_mock_response(status_code=500)):
        result = provider.get_engagement(access_token="good-token", platform_post_id="page-42_999")

    assert result.success is False
    assert result.rate_limited is False
    assert result.error is not None


def test_facebook_get_engagement_logs_integration_call(db_session) -> None:
    provider = FacebookProvider(client_id="cid", client_secret="secret")

    with patch(
        "httpx.get",
        return_value=_mock_response(
            {"likes": {"summary": {"total_count": 1}}, "comments": {"summary": {"total_count": 0}}, "shares": {"count": 0}}
        ),
    ):
        provider.get_engagement(access_token="good-token", platform_post_id="page-42_999")

    logged = (
        db_session.query(IntegrationCall)
        .filter_by(provider="facebook", capability="get_engagement")
        .order_by(IntegrationCall.created_at.desc())
        .first()
    )
    assert logged is not None
    assert logged.success is True


# ---------------------------------------------------------------------
# Instagram: OAuth-connection interface
# ---------------------------------------------------------------------


def test_instagram_authorize_url_includes_state_and_scopes() -> None:
    provider = InstagramProvider(client_id="cid", client_secret="secret")
    url = provider.authorize_url(state="signed-state", redirect_uri="https://app.test/callback")

    assert url.startswith(InstagramProvider.AUTHORIZE_URL)
    assert "client_id=cid" in url
    assert "state=signed-state" in url
    assert "instagram_content_publish" in url


def test_instagram_exchange_code_returns_tokens_and_fetches_ig_user_id() -> None:
    provider = InstagramProvider(client_id="cid", client_secret="secret")
    token_response = _mock_response({"access_token": "at-123", "expires_in": 5184000})
    accounts_response = _mock_response(
        {"data": [{"id": "page-1", "instagram_business_account": {"id": "17841400000000000"}}]}
    )

    with patch("httpx.post", return_value=token_response), patch(
        "httpx.get", return_value=accounts_response
    ):
        tokens = provider.exchange_code(code="auth-code", redirect_uri="https://app.test/callback")

    assert tokens.access_token == "at-123"
    assert tokens.external_account_id == "17841400000000000"


def test_instagram_exchange_code_handles_no_linked_ig_account() -> None:
    provider = InstagramProvider(client_id="cid", client_secret="secret")
    token_response = _mock_response({"access_token": "at-123"})
    accounts_response = _mock_response({"data": [{"id": "page-1"}]})

    with patch("httpx.post", return_value=token_response), patch(
        "httpx.get", return_value=accounts_response
    ):
        tokens = provider.exchange_code(code="auth-code", redirect_uri="https://app.test/callback")

    assert tokens.external_account_id is None


def test_instagram_is_token_valid_true_on_200() -> None:
    provider = InstagramProvider(client_id="cid", client_secret="secret")
    with patch("httpx.get", return_value=_mock_response({"data": []}, status_code=200)):
        assert provider.is_token_valid("some-token") is True


def test_instagram_is_token_valid_false_when_platform_rejects_it() -> None:
    provider = InstagramProvider(client_id="cid", client_secret="secret")
    with patch("httpx.get", return_value=_mock_response(status_code=401)):
        assert provider.is_token_valid("revoked-token") is False


# ---------------------------------------------------------------------
# Instagram: publish requires media
# ---------------------------------------------------------------------


def test_instagram_publish_without_media_fails_without_any_http_call() -> None:
    provider = InstagramProvider(client_id="cid", client_secret="secret")

    with patch("httpx.get") as mock_get, patch("httpx.post") as mock_post:
        result = provider.publish(access_token="good-token", content="hello world")

    assert result.success is False
    assert "media" in result.error.lower()
    mock_get.assert_not_called()
    mock_post.assert_not_called()


# ---------------------------------------------------------------------
# Instagram: successful publish (two-step container -> publish)
# ---------------------------------------------------------------------


def test_instagram_publish_success_returns_populated_result(db_session) -> None:
    provider = InstagramProvider(client_id="cid", client_secret="secret")
    accounts_response = _mock_response(
        {"data": [{"id": "page-1", "instagram_business_account": {"id": "ig-user-1"}}]}
    )
    container_response = _mock_response({"id": "container-1"})
    publish_response = _mock_response({"id": "ig-post-1"})

    with patch("httpx.get", return_value=accounts_response), patch(
        "httpx.post", side_effect=[container_response, publish_response]
    ):
        result = provider.publish(
            access_token="good-token",
            content="hello world",
            media_urls=["https://cdn.test/photo.png"],
        )

    assert isinstance(result, PublishResult)
    assert result.success is True
    assert result.platform_post_id == "ig-post-1"
    assert result.platform_post_url is not None
    assert result.error is None


def test_instagram_publish_success_logs_integration_call(db_session) -> None:
    provider = InstagramProvider(client_id="cid", client_secret="secret")
    accounts_response = _mock_response(
        {"data": [{"id": "page-1", "instagram_business_account": {"id": "ig-user-1"}}]}
    )
    container_response = _mock_response({"id": "container-1"})
    publish_response = _mock_response({"id": "ig-post-1"})

    with patch("httpx.get", return_value=accounts_response), patch(
        "httpx.post", side_effect=[container_response, publish_response]
    ):
        provider.publish(
            access_token="good-token",
            content="hello world",
            media_urls=["https://cdn.test/photo.png"],
        )

    logged = (
        db_session.query(IntegrationCall)
        .filter_by(provider="instagram", capability="publish")
        .order_by(IntegrationCall.created_at.desc())
        .first()
    )
    assert logged is not None
    assert logged.success is True


def test_instagram_publish_fails_when_no_ig_account_linked(db_session) -> None:
    provider = InstagramProvider(client_id="cid", client_secret="secret")
    accounts_response = _mock_response({"data": [{"id": "page-1"}]})

    with patch("httpx.get", return_value=accounts_response), patch("httpx.post") as mock_post:
        result = provider.publish(
            access_token="good-token",
            content="hello world",
            media_urls=["https://cdn.test/photo.png"],
        )

    assert result.success is False
    assert "instagram" in result.error.lower()
    mock_post.assert_not_called()


# ---------------------------------------------------------------------
# Instagram: expired token -> transparent refresh + retry
# ---------------------------------------------------------------------


def test_instagram_publish_refreshes_and_retries_once_on_expired_token(db_session) -> None:
    provider = InstagramProvider(client_id="cid", client_secret="secret")

    expired_accounts_response = _mock_response(status_code=401)
    retry_accounts_response = _mock_response(
        {"data": [{"id": "page-1", "instagram_business_account": {"id": "ig-user-1"}}]}
    )
    refresh_response = _mock_response({"access_token": "new-token", "expires_in": 5184000})
    container_response = _mock_response({"id": "container-1"})
    publish_response = _mock_response({"id": "ig-post-9"})

    get_calls = [expired_accounts_response, retry_accounts_response]
    post_calls = [refresh_response, container_response, publish_response]

    with patch("httpx.get", side_effect=get_calls) as mock_get, patch(
        "httpx.post", side_effect=post_calls
    ) as mock_post:
        result = provider.publish(
            access_token="stale-token",
            content="hello world",
            media_urls=["https://cdn.test/photo.png"],
            refresh_token="prior-long-lived-token",
        )

    assert result.success is True
    assert result.platform_post_id == "ig-post-9"
    assert result.refreshed_tokens is not None
    assert result.refreshed_tokens.access_token == "new-token"
    assert mock_get.call_count == 2
    assert mock_post.call_count == 3


def test_instagram_publish_expired_token_without_refresh_token_fails(db_session) -> None:
    provider = InstagramProvider(client_id="cid", client_secret="secret")

    with patch("httpx.get", return_value=_mock_response(status_code=401)):
        result = provider.publish(
            access_token="stale-token",
            content="hello world",
            media_urls=["https://cdn.test/photo.png"],
        )

    assert result.success is False
    assert "refresh" in result.error.lower()


def test_instagram_publish_refresh_failure_surfaces_as_real_failure(db_session) -> None:
    provider = InstagramProvider(client_id="cid", client_secret="secret")

    with patch("httpx.get", return_value=_mock_response(status_code=401)), patch(
        "httpx.post", return_value=_mock_response(status_code=400)
    ):
        result = provider.publish(
            access_token="stale-token",
            content="hello world",
            media_urls=["https://cdn.test/photo.png"],
            refresh_token="bad-token",
        )

    assert result.success is False
    assert result.error is not None


# ---------------------------------------------------------------------
# Instagram: hard (non-token) failures
# ---------------------------------------------------------------------


def test_instagram_publish_hard_http_failure_returns_failed_result(db_session) -> None:
    provider = InstagramProvider(client_id="cid", client_secret="secret")
    accounts_response = _mock_response(
        {"data": [{"id": "page-1", "instagram_business_account": {"id": "ig-user-1"}}]}
    )

    with patch("httpx.get", return_value=accounts_response), patch(
        "httpx.post", return_value=_mock_response(status_code=500)
    ):
        result = provider.publish(
            access_token="good-token",
            content="hello world",
            media_urls=["https://cdn.test/photo.png"],
        )

    assert result.success is False
    assert result.error is not None


# ---------------------------------------------------------------------
# Instagram: get_engagement()
# ---------------------------------------------------------------------


def test_instagram_get_engagement_success_returns_metrics(db_session) -> None:
    provider = InstagramProvider(client_id="cid", client_secret="secret")

    with patch(
        "httpx.get",
        return_value=_mock_response(
            {
                "data": [
                    {"name": "likes", "values": [{"value": 12}]},
                    {"name": "comments", "values": [{"value": 3}]},
                    {"name": "saved", "values": [{"value": 5}]},
                    {"name": "impressions", "values": [{"value": 400}]},
                ]
            }
        ),
    ):
        result = provider.get_engagement(access_token="good-token", platform_post_id="ig-post-1")

    assert result.success is True
    assert result.metrics.likes == 12
    assert result.metrics.comments == 3
    assert result.metrics.shares == 5
    assert result.metrics.impressions == 400


def test_instagram_get_engagement_rate_limited_returns_flag_not_raise(db_session) -> None:
    provider = InstagramProvider(client_id="cid", client_secret="secret")

    with patch("httpx.get", return_value=_mock_response(status_code=429)):
        result = provider.get_engagement(access_token="good-token", platform_post_id="ig-post-1")

    assert result.success is False
    assert result.rate_limited is True
    assert result.metrics is None


def test_instagram_get_engagement_logs_integration_call(db_session) -> None:
    provider = InstagramProvider(client_id="cid", client_secret="secret")

    with patch(
        "httpx.get",
        return_value=_mock_response({"data": [{"name": "likes", "values": [{"value": 1}]}]}),
    ):
        provider.get_engagement(access_token="good-token", platform_post_id="ig-post-1")

    logged = (
        db_session.query(IntegrationCall)
        .filter_by(provider="instagram", capability="get_engagement")
        .order_by(IntegrationCall.created_at.desc())
        .first()
    )
    assert logged is not None
    assert logged.success is True


# ---------------------------------------------------------------------
# Threads: OAuth-connection interface
# ---------------------------------------------------------------------


def test_threads_authorize_url_includes_state_and_scopes() -> None:
    provider = ThreadsProvider(client_id="cid", client_secret="secret")
    url = provider.authorize_url(state="signed-state", redirect_uri="https://app.test/callback")

    assert url.startswith(ThreadsProvider.AUTHORIZE_URL)
    assert "client_id=cid" in url
    assert "state=signed-state" in url
    assert "threads_content_publish" in url


def test_threads_exchange_code_returns_tokens_from_response_directly() -> None:
    # Unlike LinkedIn/X/Facebook/Instagram, Threads' token-exchange response
    # includes user_id directly — no separate userinfo call is needed.
    provider = ThreadsProvider(client_id="cid", client_secret="secret")
    token_response = _mock_response(
        {"access_token": "at-123", "user_id": 999888777, "expires_in": 3600}
    )

    with patch("httpx.post", return_value=token_response) as mock_post, patch(
        "httpx.get"
    ) as mock_get:
        tokens = provider.exchange_code(code="auth-code", redirect_uri="https://app.test/callback")

    assert tokens.access_token == "at-123"
    assert tokens.external_account_id == "999888777"
    assert tokens.expires_at is not None
    mock_get.assert_not_called()
    mock_post.assert_called_once()


def test_threads_is_token_valid_true_on_200() -> None:
    provider = ThreadsProvider(client_id="cid", client_secret="secret")
    with patch("httpx.get", return_value=_mock_response({"id": "user-1"}, status_code=200)):
        assert provider.is_token_valid("some-token") is True


def test_threads_is_token_valid_false_when_platform_rejects_it() -> None:
    provider = ThreadsProvider(client_id="cid", client_secret="secret")
    with patch("httpx.get", return_value=_mock_response(status_code=401)):
        assert provider.is_token_valid("revoked-token") is False


# ---------------------------------------------------------------------
# Threads: successful publish (two-step container -> publish, text-only ok)
# ---------------------------------------------------------------------


def test_threads_publish_success_returns_populated_result(db_session) -> None:
    provider = ThreadsProvider(client_id="cid", client_secret="secret")
    me_response = _mock_response({"id": "user-1"})
    container_response = _mock_response({"id": "container-1"})
    publish_response = _mock_response({"id": "thread-1"})

    with patch("httpx.get", return_value=me_response), patch(
        "httpx.post", side_effect=[container_response, publish_response]
    ):
        result = provider.publish(access_token="good-token", content="hello world")

    assert isinstance(result, PublishResult)
    assert result.success is True
    assert result.platform_post_id == "thread-1"
    assert result.platform_post_url is not None
    assert result.error is None


def test_threads_publish_success_logs_integration_call(db_session) -> None:
    provider = ThreadsProvider(client_id="cid", client_secret="secret")
    me_response = _mock_response({"id": "user-1"})
    container_response = _mock_response({"id": "container-1"})
    publish_response = _mock_response({"id": "thread-1"})

    with patch("httpx.get", return_value=me_response), patch(
        "httpx.post", side_effect=[container_response, publish_response]
    ):
        provider.publish(access_token="good-token", content="hello world")

    logged = (
        db_session.query(IntegrationCall)
        .filter_by(provider="threads", capability="publish")
        .order_by(IntegrationCall.created_at.desc())
        .first()
    )
    assert logged is not None
    assert logged.success is True


def test_threads_publish_with_media_sets_image_body(db_session) -> None:
    provider = ThreadsProvider(client_id="cid", client_secret="secret")
    me_response = _mock_response({"id": "user-1"})
    container_response = _mock_response({"id": "container-1"})
    publish_response = _mock_response({"id": "thread-1"})

    with patch("httpx.get", return_value=me_response), patch(
        "httpx.post", side_effect=[container_response, publish_response]
    ) as mock_post:
        result = provider.publish(
            access_token="good-token",
            content="hello world",
            media_urls=["https://cdn.test/image.png"],
        )

    assert result.success is True
    first_call_body = mock_post.call_args_list[0].kwargs["json"]
    assert first_call_body["media_type"] == "IMAGE"
    assert first_call_body["image_url"] == "https://cdn.test/image.png"


# ---------------------------------------------------------------------
# Threads: expired token -> transparent refresh + retry
# ---------------------------------------------------------------------


def test_threads_publish_refreshes_and_retries_once_on_expired_token(db_session) -> None:
    provider = ThreadsProvider(client_id="cid", client_secret="secret")

    expired_me_response = _mock_response(status_code=401)
    refresh_response = _mock_response({"access_token": "new-token", "expires_in": 5184000})
    retry_me_response = _mock_response({"id": "user-1"})
    container_response = _mock_response({"id": "container-1"})
    publish_response = _mock_response({"id": "thread-9"})

    get_calls = [expired_me_response, refresh_response, retry_me_response]
    post_calls = [container_response, publish_response]

    with patch("httpx.get", side_effect=get_calls) as mock_get, patch(
        "httpx.post", side_effect=post_calls
    ) as mock_post:
        result = provider.publish(
            access_token="stale-token", content="hello world", refresh_token="prior-token"
        )

    assert result.success is True
    assert result.platform_post_id == "thread-9"
    assert result.refreshed_tokens is not None
    assert result.refreshed_tokens.access_token == "new-token"
    assert mock_get.call_count == 3
    assert mock_post.call_count == 2


def test_threads_publish_expired_token_without_refresh_token_fails(db_session) -> None:
    provider = ThreadsProvider(client_id="cid", client_secret="secret")

    with patch("httpx.get", return_value=_mock_response(status_code=401)):
        result = provider.publish(access_token="stale-token", content="hello world")

    assert result.success is False
    assert "refresh" in result.error.lower()


def test_threads_publish_refresh_failure_surfaces_as_real_failure(db_session) -> None:
    provider = ThreadsProvider(client_id="cid", client_secret="secret")

    get_calls = [_mock_response(status_code=401), _mock_response(status_code=400)]

    with patch("httpx.get", side_effect=get_calls):
        result = provider.publish(
            access_token="stale-token", content="hello world", refresh_token="bad-token"
        )

    assert result.success is False
    assert result.error is not None


# ---------------------------------------------------------------------
# Threads: hard (non-token) failures
# ---------------------------------------------------------------------


def test_threads_publish_hard_http_failure_returns_failed_result(db_session) -> None:
    provider = ThreadsProvider(client_id="cid", client_secret="secret")
    me_response = _mock_response({"id": "user-1"})

    with patch("httpx.get", return_value=me_response), patch(
        "httpx.post", return_value=_mock_response(status_code=500)
    ):
        result = provider.publish(access_token="good-token", content="hello world")

    assert result.success is False
    assert result.error is not None


# ---------------------------------------------------------------------
# Threads: get_engagement()
# ---------------------------------------------------------------------


def test_threads_get_engagement_success_returns_metrics(db_session) -> None:
    provider = ThreadsProvider(client_id="cid", client_secret="secret")

    with patch(
        "httpx.get",
        return_value=_mock_response(
            {
                "data": [
                    {"name": "likes", "values": [{"value": 7}]},
                    {"name": "replies", "values": [{"value": 1}]},
                    {"name": "reposts", "values": [{"value": 2}]},
                    {"name": "views", "values": [{"value": 50}]},
                ]
            }
        ),
    ):
        result = provider.get_engagement(access_token="good-token", platform_post_id="thread-1")

    assert result.success is True
    assert result.metrics.likes == 7
    assert result.metrics.comments == 1
    assert result.metrics.shares == 2
    assert result.metrics.impressions == 50


def test_threads_get_engagement_rate_limited_returns_flag_not_raise(db_session) -> None:
    provider = ThreadsProvider(client_id="cid", client_secret="secret")

    with patch("httpx.get", return_value=_mock_response(status_code=429)):
        result = provider.get_engagement(access_token="good-token", platform_post_id="thread-1")

    assert result.success is False
    assert result.rate_limited is True
    assert result.metrics is None


def test_threads_get_engagement_logs_integration_call(db_session) -> None:
    provider = ThreadsProvider(client_id="cid", client_secret="secret")

    with patch(
        "httpx.get",
        return_value=_mock_response({"data": [{"name": "likes", "values": [{"value": 1}]}]}),
    ):
        provider.get_engagement(access_token="good-token", platform_post_id="thread-1")

    logged = (
        db_session.query(IntegrationCall)
        .filter_by(provider="threads", capability="get_engagement")
        .order_by(IntegrationCall.created_at.desc())
        .first()
    )
    assert logged is not None
    assert logged.success is True


# ---------------------------------------------------------------------
# YouTube: OAuth
# ---------------------------------------------------------------------


def test_youtube_authorize_url_includes_offline_access_and_scopes() -> None:
    provider = YouTubeProvider(client_id="cid", client_secret="secret")

    url = provider.authorize_url(state="state-123", redirect_uri="https://app.test/callback")

    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth")
    assert "access_type=offline" in url
    assert "state=state-123" in url
    assert "youtube.upload" in url


def test_youtube_exchange_code_returns_tokens_and_fetches_channel_id() -> None:
    provider = YouTubeProvider(client_id="cid", client_secret="secret")
    token_response = _mock_response(
        {
            "access_token": "at-123",
            "refresh_token": "rt-123",
            "expires_in": 3600,
            "scope": "https://www.googleapis.com/auth/youtube.upload",
        }
    )
    channels_response = _mock_response({"items": [{"id": "channel-1"}]})

    with patch("httpx.post", return_value=token_response), patch(
        "httpx.get", return_value=channels_response
    ):
        tokens = provider.exchange_code(code="auth-code", redirect_uri="https://app.test/callback")

    assert tokens.access_token == "at-123"
    assert tokens.refresh_token == "rt-123"
    assert tokens.external_account_id == "channel-1"
    assert tokens.expires_at is not None


def test_youtube_is_token_valid_true_on_200() -> None:
    provider = YouTubeProvider(client_id="cid", client_secret="secret")

    with patch("httpx.get", return_value=_mock_response({"expires_in": 100})):
        assert provider.is_token_valid("good-token") is True


def test_youtube_is_token_valid_false_when_platform_rejects_it() -> None:
    provider = YouTubeProvider(client_id="cid", client_secret="secret")

    with patch("httpx.get", return_value=_mock_response(status_code=400)):
        assert provider.is_token_valid("bad-token") is False


# ---------------------------------------------------------------------
# YouTube: publish() / get_engagement()
# ---------------------------------------------------------------------


def test_youtube_publish_without_media_fails_without_any_http_call() -> None:
    provider = YouTubeProvider(client_id="cid", client_secret="secret")

    with patch("httpx.post") as mock_post, patch("httpx.get") as mock_get:
        result = provider.publish(access_token="good-token", content="hello")

    assert result.success is False
    assert "media_urls" in (result.error or "").lower() or "video" in (result.error or "").lower()
    mock_post.assert_not_called()
    mock_get.assert_not_called()


def test_youtube_publish_success_returns_populated_result(db_session) -> None:
    provider = YouTubeProvider(client_id="cid", client_secret="secret")
    session_response = _mock_response(headers={"Location": "https://upload.example/session-1"})
    put_response = _mock_response({"id": "video-1"})

    with patch("httpx.get", return_value=MagicMock(content=b"fake-video-bytes")), patch(
        "httpx.post", return_value=session_response
    ), patch("httpx.put", return_value=put_response):
        result = provider.publish(
            access_token="good-token", content="My video", media_urls=["https://cdn.test/video.mp4"]
        )

    assert result.success is True
    assert result.platform_post_id == "video-1"
    assert result.platform_post_url == "https://youtube.com/watch?v=video-1"


def test_youtube_publish_success_logs_integration_call(db_session) -> None:
    provider = YouTubeProvider(client_id="cid", client_secret="secret")
    session_response = _mock_response(headers={"Location": "https://upload.example/session-1"})
    put_response = _mock_response({"id": "video-1"})

    with patch("httpx.get", return_value=MagicMock(content=b"fake-video-bytes")), patch(
        "httpx.post", return_value=session_response
    ), patch("httpx.put", return_value=put_response):
        provider.publish(
            access_token="good-token", content="My video", media_urls=["https://cdn.test/video.mp4"]
        )

    logged = (
        db_session.query(IntegrationCall)
        .filter_by(provider="youtube", capability="publish")
        .order_by(IntegrationCall.created_at.desc())
        .first()
    )
    assert logged is not None
    assert logged.success is True


def test_youtube_get_engagement_success_returns_metrics(db_session) -> None:
    provider = YouTubeProvider(client_id="cid", client_secret="secret")

    with patch(
        "httpx.get",
        return_value=_mock_response(
            {"items": [{"statistics": {"likeCount": "5", "commentCount": "2", "viewCount": "100"}}]}
        ),
    ):
        result = provider.get_engagement(access_token="good-token", platform_post_id="video-1")

    assert result.success is True
    assert result.metrics.likes == 5
    assert result.metrics.comments == 2
    assert result.metrics.impressions == 100
    assert result.metrics.shares == 0


def test_youtube_get_engagement_rate_limited_returns_flag_not_raise(db_session) -> None:
    provider = YouTubeProvider(client_id="cid", client_secret="secret")

    with patch("httpx.get", return_value=_mock_response(status_code=429)):
        result = provider.get_engagement(access_token="good-token", platform_post_id="video-1")

    assert result.success is False
    assert result.rate_limited is True


# ---------------------------------------------------------------------
# TikTok: OAuth (PKCE)
# ---------------------------------------------------------------------


def test_tiktok_authorize_url_includes_s256_code_challenge() -> None:
    provider = TikTokProvider(client_key="key", client_secret="secret")

    url = provider.authorize_url(state="verifier-state", redirect_uri="https://app.test/callback")

    assert url.startswith("https://www.tiktok.com/v2/auth/authorize/")
    assert "code_challenge_method=S256" in url
    assert "state=verifier-state" in url
    # The challenge must be a deterministic function of the verifier, not
    # the raw verifier itself (unlike XProvider's "plain" shortcut).
    assert "verifier-state" not in url.split("code_challenge=")[1].split("&")[0]


def test_tiktok_exchange_code_requires_code_verifier() -> None:
    provider = TikTokProvider(client_key="key", client_secret="secret")

    with pytest.raises(ValueError, match="code_verifier"):
        provider.exchange_code(code="auth-code", redirect_uri="https://app.test/callback")


def test_tiktok_exchange_code_returns_tokens() -> None:
    provider = TikTokProvider(client_key="key", client_secret="secret")
    token_response = _mock_response(
        {
            "access_token": "at-123",
            "refresh_token": "rt-123",
            "expires_in": 86400,
            "open_id": "tiktok-user-1",
            "scope": "user.info.basic,video.publish",
        }
    )

    with patch("httpx.post", return_value=token_response) as mock_post:
        tokens = provider.exchange_code(
            code="auth-code", redirect_uri="https://app.test/callback", code_verifier="verifier-state"
        )

    assert tokens.access_token == "at-123"
    assert tokens.external_account_id == "tiktok-user-1"
    assert mock_post.call_args.kwargs["data"]["code_verifier"] == "verifier-state"


def test_tiktok_is_token_valid_true_on_200() -> None:
    provider = TikTokProvider(client_key="key", client_secret="secret")

    with patch("httpx.get", return_value=_mock_response({"data": {}})):
        assert provider.is_token_valid("good-token") is True


def test_tiktok_is_token_valid_false_when_platform_rejects_it() -> None:
    provider = TikTokProvider(client_key="key", client_secret="secret")

    with patch("httpx.get", return_value=_mock_response(status_code=401)):
        assert provider.is_token_valid("bad-token") is False


# ---------------------------------------------------------------------
# TikTok: publish() / get_engagement()
# ---------------------------------------------------------------------


def test_tiktok_publish_without_media_fails_without_any_http_call() -> None:
    provider = TikTokProvider(client_key="key", client_secret="secret")

    with patch("httpx.post") as mock_post:
        result = provider.publish(access_token="good-token", content="hello")

    assert result.success is False
    mock_post.assert_not_called()


def test_tiktok_publish_success_returns_populated_result(db_session) -> None:
    provider = TikTokProvider(client_key="key", client_secret="secret")

    with patch("httpx.post", return_value=_mock_response({"data": {"publish_id": "pub-1"}})):
        result = provider.publish(
            access_token="good-token", content="caption", media_urls=["https://cdn.test/video.mp4"]
        )

    assert result.success is True
    assert result.platform_post_id == "pub-1"


def test_tiktok_publish_success_logs_integration_call(db_session) -> None:
    provider = TikTokProvider(client_key="key", client_secret="secret")

    with patch("httpx.post", return_value=_mock_response({"data": {"publish_id": "pub-1"}})):
        provider.publish(
            access_token="good-token", content="caption", media_urls=["https://cdn.test/video.mp4"]
        )

    logged = (
        db_session.query(IntegrationCall)
        .filter_by(provider="tiktok", capability="publish")
        .order_by(IntegrationCall.created_at.desc())
        .first()
    )
    assert logged is not None
    assert logged.success is True


def test_tiktok_get_engagement_success_returns_metrics(db_session) -> None:
    provider = TikTokProvider(client_key="key", client_secret="secret")

    with patch(
        "httpx.post",
        return_value=_mock_response(
            {
                "data": {
                    "videos": [
                        {"like_count": 10, "comment_count": 3, "share_count": 4, "view_count": 200}
                    ]
                }
            }
        ),
    ):
        result = provider.get_engagement(access_token="good-token", platform_post_id="pub-1")

    assert result.success is True
    assert result.metrics.likes == 10
    assert result.metrics.shares == 4
    assert result.metrics.impressions == 200


def test_tiktok_get_engagement_rate_limited_returns_flag_not_raise(db_session) -> None:
    provider = TikTokProvider(client_key="key", client_secret="secret")

    with patch("httpx.post", return_value=_mock_response(status_code=429)):
        result = provider.get_engagement(access_token="good-token", platform_post_id="pub-1")

    assert result.success is False
    assert result.rate_limited is True


# ---------------------------------------------------------------------
# Pinterest: OAuth
# ---------------------------------------------------------------------


def test_pinterest_authorize_url_includes_state_and_scopes() -> None:
    provider = PinterestProvider(client_id="cid", client_secret="secret")

    url = provider.authorize_url(state="state-123", redirect_uri="https://app.test/callback")

    assert url.startswith("https://www.pinterest.com/oauth/")
    assert "state=state-123" in url
    assert "pins%3Awrite" in url or "pins:write" in url


def test_pinterest_exchange_code_returns_tokens_and_fetches_username() -> None:
    provider = PinterestProvider(client_id="cid", client_secret="secret")
    token_response = _mock_response(
        {"access_token": "at-123", "refresh_token": "rt-123", "expires_in": 2592000, "scope": "pins:write"}
    )
    account_response = _mock_response({"username": "acme"})

    with patch("httpx.post", return_value=token_response), patch(
        "httpx.get", return_value=account_response
    ):
        tokens = provider.exchange_code(code="auth-code", redirect_uri="https://app.test/callback")

    assert tokens.access_token == "at-123"
    assert tokens.external_account_id == "acme"


def test_pinterest_is_token_valid_true_on_200() -> None:
    provider = PinterestProvider(client_id="cid", client_secret="secret")

    with patch("httpx.get", return_value=_mock_response({"username": "acme"})):
        assert provider.is_token_valid("good-token") is True


def test_pinterest_is_token_valid_false_when_platform_rejects_it() -> None:
    provider = PinterestProvider(client_id="cid", client_secret="secret")

    with patch("httpx.get", return_value=_mock_response(status_code=401)):
        assert provider.is_token_valid("bad-token") is False


# ---------------------------------------------------------------------
# Pinterest: publish() / get_engagement()
# ---------------------------------------------------------------------


def test_pinterest_publish_without_media_fails_without_any_http_call() -> None:
    provider = PinterestProvider(client_id="cid", client_secret="secret")

    with patch("httpx.post") as mock_post, patch("httpx.get") as mock_get:
        result = provider.publish(access_token="good-token", content="hello")

    assert result.success is False
    mock_post.assert_not_called()
    mock_get.assert_not_called()


def test_pinterest_publish_success_returns_populated_result(db_session) -> None:
    provider = PinterestProvider(client_id="cid", client_secret="secret")

    with patch("httpx.get", return_value=_mock_response({"items": [{"id": "board-1"}]})), patch(
        "httpx.post", return_value=_mock_response({"id": "pin-1"})
    ):
        result = provider.publish(
            access_token="good-token", content="caption", media_urls=["https://cdn.test/image.png"]
        )

    assert result.success is True
    assert result.platform_post_id == "pin-1"
    assert result.platform_post_url == "https://pinterest.com/pin/pin-1"


def test_pinterest_publish_success_logs_integration_call(db_session) -> None:
    provider = PinterestProvider(client_id="cid", client_secret="secret")

    with patch("httpx.get", return_value=_mock_response({"items": [{"id": "board-1"}]})), patch(
        "httpx.post", return_value=_mock_response({"id": "pin-1"})
    ):
        provider.publish(
            access_token="good-token", content="caption", media_urls=["https://cdn.test/image.png"]
        )

    logged = (
        db_session.query(IntegrationCall)
        .filter_by(provider="pinterest", capability="publish")
        .order_by(IntegrationCall.created_at.desc())
        .first()
    )
    assert logged is not None
    assert logged.success is True


def test_pinterest_get_engagement_success_returns_metrics(db_session) -> None:
    provider = PinterestProvider(client_id="cid", client_secret="secret")

    with patch(
        "httpx.get",
        return_value=_mock_response(
            {"all": {"summary_metrics": {"IMPRESSION": 100, "SAVE": 8, "OUTBOUND_CLICK": 3}}}
        ),
    ):
        result = provider.get_engagement(access_token="good-token", platform_post_id="pin-1")

    assert result.success is True
    assert result.metrics.likes == 8
    assert result.metrics.shares == 3
    assert result.metrics.impressions == 100


def test_pinterest_get_engagement_rate_limited_returns_flag_not_raise(db_session) -> None:
    provider = PinterestProvider(client_id="cid", client_secret="secret")

    with patch("httpx.get", return_value=_mock_response(status_code=429)):
        result = provider.get_engagement(access_token="good-token", platform_post_id="pin-1")

    assert result.success is False
    assert result.rate_limited is True
