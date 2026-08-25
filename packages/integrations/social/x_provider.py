import base64
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx

from packages.integrations.observability import track_integration_call
from packages.integrations.social.base import (
    EngagementMetrics,
    EngagementResult,
    PublishResult,
    SocialOAuthProvider,
    SocialPublisher,
    SocialTokens,
)


class _TokenExpiredError(Exception):
    """Internal signal that X rejected access_token as expired/invalid —
    distinct from other HTTP failures because it's the one case publish()
    retries after a refresh, rather than surfacing immediately."""


class XProvider(SocialOAuthProvider, SocialPublisher):
    """The only file in this codebase allowed to call X's (Twitter's)
    OAuth and publishing endpoints directly.

    X's OAuth 2.0 authorization-code flow requires PKCE. Rather than widen
    SocialOAuthProvider's shared signature (authorize_url/exchange_code
    take no PKCE params, since LinkedIn doesn't need any), this uses the
    "plain" code_challenge_method with `state` doubling as the code
    verifier — state is already unique per request, single-use, and
    round-trips unmodified through the redirect, so it satisfies PKCE's
    requirements without adding a param the interface's other adapters
    would never use.
    """

    AUTHORIZE_URL = "https://twitter.com/i/oauth2/authorize"
    TOKEN_URL = "https://api.twitter.com/2/oauth2/token"
    USERINFO_URL = "https://api.twitter.com/2/users/me"
    TWEETS_URL = "https://api.twitter.com/2/tweets"

    SCOPES = ("tweet.read", "tweet.write", "users.read", "offline.access")

    def __init__(self, client_id: str, client_secret: str, timeout: float = 15.0) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.timeout = timeout

    def _basic_auth_header(self) -> str:
        raw = f"{self.client_id}:{self.client_secret}".encode()
        return f"Basic {base64.b64encode(raw).decode()}"

    # -- SocialOAuthProvider ---------------------------------------------

    def authorize_url(self, state: str, redirect_uri: str) -> str:
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "scope": " ".join(self.SCOPES),
            "code_challenge": state,
            "code_challenge_method": "plain",
        }
        return f"{self.AUTHORIZE_URL}?{urlencode(params)}"

    def exchange_code(self, code: str, redirect_uri: str) -> SocialTokens:
        with track_integration_call("x", "oauth_exchange"):
            response = httpx.post(
                self.TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": self.client_id,
                    "code_verifier": redirect_uri,
                },
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Authorization": self._basic_auth_header(),
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()

        expires_in = data.get("expires_in")
        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            if expires_in is not None
            else None
        )
        raw_scope = data.get("scope")
        scopes = raw_scope.split(" ") if raw_scope else list(self.SCOPES)

        external_account_id = self._fetch_user_id(data["access_token"])

        return SocialTokens(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_at=expires_at,
            scopes=scopes,
            external_account_id=external_account_id,
        )

    def is_token_valid(self, access_token: str) -> bool:
        with track_integration_call("x", "oauth_status_check"):
            response = httpx.get(
                self.USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=self.timeout,
            )
        return response.status_code == 200

    def _fetch_user_id(self, access_token: str) -> str | None:
        with track_integration_call("x", "oauth_userinfo"):
            response = httpx.get(
                self.USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json().get("data", {}).get("id")

    # -- SocialPublisher ---------------------------------------------------

    def publish(
        self,
        access_token: str,
        content: str,
        media_urls: list[str] | None = None,
        refresh_token: str | None = None,
    ) -> PublishResult:
        try:
            return self._attempt_publish(access_token, content, media_urls)
        except _TokenExpiredError:
            if not refresh_token:
                return PublishResult(
                    success=False,
                    error="X access token expired/invalid and no refresh token is stored",
                )
            try:
                new_tokens = self._refresh_access_token(refresh_token)
            except Exception as exc:  # noqa: BLE001 - surfaced as PublishResult, not raised
                return PublishResult(success=False, error=f"X token refresh failed: {exc}")

            try:
                result = self._attempt_publish(new_tokens.access_token, content, media_urls)
            except Exception as exc:  # noqa: BLE001
                return PublishResult(
                    success=False, error=f"X publish failed after token refresh: {exc}"
                )
            result.refreshed_tokens = new_tokens
            return result
        except Exception as exc:  # noqa: BLE001 - vendor/network errors become failures, not raises
            return PublishResult(success=False, error=str(exc))

    def _attempt_publish(
        self, access_token: str, content: str, media_urls: list[str] | None
    ) -> PublishResult:
        # media_urls isn't wired through here: X requires media to be
        # pre-uploaded via the separate v1.1 media/upload endpoint (which
        # needs OAuth 1.0a user-context signing, not the OAuth2 bearer
        # token used everywhere else in this adapter) and referenced by
        # the resulting media_id — no adapter/consumer in this codebase
        # produces uploaded X media ids yet.
        with track_integration_call("x", "publish"):
            response = httpx.post(
                self.TWEETS_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json={"text": content},
                timeout=self.timeout,
            )
            if response.status_code == 401:
                raise _TokenExpiredError("X rejected the access token")
            response.raise_for_status()
            data = response.json().get("data", {})

        post_id = data.get("id")
        return PublishResult(
            success=True,
            platform_post_id=post_id,
            platform_post_url=f"https://x.com/i/web/status/{post_id}" if post_id else None,
        )

    # -- SocialPublisher: engagement ---------------------------------------

    def get_engagement(self, access_token: str, platform_post_id: str) -> EngagementResult:
        try:
            with track_integration_call("x", "get_engagement"):
                response = httpx.get(
                    f"{self.TWEETS_URL}/{platform_post_id}",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params={"tweet.fields": "public_metrics"},
                    timeout=self.timeout,
                )
                if response.status_code == 429:
                    return EngagementResult(
                        success=False,
                        error="X rate-limited this engagement request",
                        rate_limited=True,
                    )
                response.raise_for_status()
                metrics = response.json().get("data", {}).get("public_metrics", {})
        except Exception as exc:  # noqa: BLE001 - vendor/network errors become failures, not raises
            return EngagementResult(success=False, error=str(exc))

        return EngagementResult(
            success=True,
            metrics=EngagementMetrics(
                likes=metrics.get("like_count", 0),
                comments=metrics.get("reply_count", 0),
                shares=metrics.get("retweet_count", 0),
                impressions=metrics.get("impression_count", 0),
            ),
        )

    def _refresh_access_token(self, refresh_token: str) -> SocialTokens:
        with track_integration_call("x", "oauth_refresh"):
            response = httpx.post(
                self.TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": self.client_id,
                },
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Authorization": self._basic_auth_header(),
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()

        expires_in = data.get("expires_in")
        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            if expires_in is not None
            else None
        )
        raw_scope = data.get("scope")
        scopes = raw_scope.split(" ") if raw_scope else list(self.SCOPES)

        return SocialTokens(
            access_token=data["access_token"],
            # X rotates refresh tokens on every use — unlike LinkedIn,
            # the old one is invalidated, so fall back only if the
            # response is missing one for some reason.
            refresh_token=data.get("refresh_token", refresh_token),
            expires_at=expires_at,
            scopes=scopes,
            external_account_id=None,
        )
