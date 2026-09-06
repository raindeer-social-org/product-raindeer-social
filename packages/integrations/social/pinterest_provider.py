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
    """Internal signal that Pinterest rejected access_token as expired/
    invalid — distinct from other HTTP failures because it's the one case
    publish() retries after a refresh, rather than surfacing immediately."""


class PinterestProvider(SocialOAuthProvider, SocialPublisher):
    """The only file in this codebase allowed to call the Pinterest API v5
    directly. Standard OAuth2 authorization-code flow, HTTP Basic
    client-credential auth on the token endpoint — same shape as
    XProvider's _basic_auth_header, no PKCE required. Publishing creates a
    Pin (Pinterest's only content unit) on the account's default board;
    `content` is used as the Pin's description and `media_urls[0]` as its
    image source.
    """

    AUTHORIZE_URL = "https://www.pinterest.com/oauth/"
    TOKEN_URL = "https://api.pinterest.com/v5/oauth/token"
    USER_ACCOUNT_URL = "https://api.pinterest.com/v5/user_account"
    PINS_URL = "https://api.pinterest.com/v5/pins"
    BOARDS_URL = "https://api.pinterest.com/v5/boards"

    SCOPES = ("boards:read", "pins:read", "pins:write", "user_accounts:read")

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
            "scope": ",".join(self.SCOPES),
            "state": state,
        }
        return f"{self.AUTHORIZE_URL}?{urlencode(params)}"

    def exchange_code(
        self, code: str, redirect_uri: str, code_verifier: str | None = None
    ) -> SocialTokens:
        with track_integration_call("pinterest", "oauth_exchange"):
            response = httpx.post(
                self.TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
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
        scopes = raw_scope.split(",") if raw_scope else list(self.SCOPES)

        external_account_id = self._fetch_username(data["access_token"])

        return SocialTokens(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_at=expires_at,
            scopes=scopes,
            external_account_id=external_account_id,
        )

    def is_token_valid(self, access_token: str) -> bool:
        with track_integration_call("pinterest", "oauth_status_check"):
            response = httpx.get(
                self.USER_ACCOUNT_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=self.timeout,
            )
        return response.status_code == 200

    def _fetch_username(self, access_token: str) -> str | None:
        with track_integration_call("pinterest", "oauth_userinfo"):
            response = httpx.get(
                self.USER_ACCOUNT_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json().get("username")

    def _fetch_default_board_id(self, access_token: str) -> str | None:
        with track_integration_call("pinterest", "list_boards"):
            response = httpx.get(
                self.BOARDS_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                params={"page_size": 1},
                timeout=self.timeout,
            )
            response.raise_for_status()
            items = response.json().get("items", [])
            return items[0]["id"] if items else None

    # -- SocialPublisher ---------------------------------------------------

    def publish(
        self,
        access_token: str,
        content: str,
        media_urls: list[str] | None = None,
        refresh_token: str | None = None,
    ) -> PublishResult:
        if not media_urls:
            return PublishResult(
                success=False,
                error="Pinterest publish requires an image — no media_urls provided",
            )
        try:
            return self._attempt_publish(access_token, content, media_urls[0])
        except _TokenExpiredError:
            if not refresh_token:
                return PublishResult(
                    success=False,
                    error="Pinterest access token expired/invalid and no refresh token is stored",
                )
            try:
                new_tokens = self._refresh_access_token(refresh_token)
            except Exception as exc:  # noqa: BLE001 - surfaced as PublishResult, not raised
                return PublishResult(success=False, error=f"Pinterest token refresh failed: {exc}")

            try:
                result = self._attempt_publish(new_tokens.access_token, content, media_urls[0])
            except Exception as exc:  # noqa: BLE001
                return PublishResult(
                    success=False, error=f"Pinterest publish failed after token refresh: {exc}"
                )
            result.refreshed_tokens = new_tokens
            return result
        except Exception as exc:  # noqa: BLE001 - vendor/network errors become failures, not raises
            return PublishResult(success=False, error=str(exc))

    def _attempt_publish(
        self, access_token: str, content: str, image_url: str
    ) -> PublishResult:
        with track_integration_call("pinterest", "publish"):
            board_id = self._fetch_default_board_id(access_token)
            if board_id is None:
                return PublishResult(
                    success=False, error="Pinterest account has no board to pin to"
                )

            response = httpx.post(
                self.PINS_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json={
                    "board_id": board_id,
                    "description": content,
                    "media_source": {"source_type": "image_url", "url": image_url},
                },
                timeout=self.timeout,
            )
            if response.status_code == 401:
                raise _TokenExpiredError("Pinterest rejected the access token")
            response.raise_for_status()
            data = response.json()

        pin_id = data.get("id")
        return PublishResult(
            success=True,
            platform_post_id=pin_id,
            platform_post_url=f"https://pinterest.com/pin/{pin_id}" if pin_id else None,
        )

    # -- SocialPublisher: engagement ---------------------------------------

    def get_engagement(self, access_token: str, platform_post_id: str) -> EngagementResult:
        try:
            with track_integration_call("pinterest", "get_engagement"):
                response = httpx.get(
                    f"{self.PINS_URL}/{platform_post_id}/analytics",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params={"metric_types": "IMPRESSION,SAVE,PIN_CLICK,OUTBOUND_CLICK"},
                    timeout=self.timeout,
                )
                if response.status_code == 429:
                    return EngagementResult(
                        success=False,
                        error="Pinterest rate-limited this engagement request",
                        rate_limited=True,
                    )
                response.raise_for_status()
                totals = response.json().get("all", {}).get("summary_metrics", {})
        except Exception as exc:  # noqa: BLE001 - vendor/network errors become failures, not raises
            return EngagementResult(success=False, error=str(exc))

        return EngagementResult(
            success=True,
            metrics=EngagementMetrics(
                likes=int(totals.get("SAVE", 0)),
                comments=0,  # Pinterest's Pin analytics expose no comment count.
                shares=int(totals.get("OUTBOUND_CLICK", 0)),
                impressions=int(totals.get("IMPRESSION", 0)),
            ),
        )

    def _refresh_access_token(self, refresh_token: str) -> SocialTokens:
        with track_integration_call("pinterest", "oauth_refresh"):
            response = httpx.post(
                self.TOKEN_URL,
                data={"grant_type": "refresh_token", "refresh_token": refresh_token},
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
        scopes = raw_scope.split(",") if raw_scope else list(self.SCOPES)

        return SocialTokens(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", refresh_token),
            expires_at=expires_at,
            scopes=scopes,
            external_account_id=None,
        )
