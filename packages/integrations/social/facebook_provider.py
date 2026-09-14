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
    """Internal signal that Facebook rejected access_token as
    expired/invalid — distinct from other HTTP failures because it's the
    one case publish() retries after a refresh, rather than surfacing
    immediately."""


class FacebookProvider(SocialOAuthProvider, SocialPublisher):
    """The only file in this codebase allowed to call Facebook Graph API's
    OAuth and Page-publishing endpoints directly.

    Publishes to a Facebook Page, not a personal profile — the Graph API
    has no endpoint for posting to a personal profile at all. `access_token`
    throughout this adapter is therefore expected to be a Page access token
    (not the user access token OAuth first hands back): `_fetch_page_id`
    resolves which Page it belongs to by calling `/me` — called with a Page
    token, `/me` identifies the Page itself, the same "ask the token who it
    belongs to" trick LinkedInProvider._fetch_member_id uses.

    Meta has no `refresh_token` concept like LinkedIn/X's OAuth2 refresh
    grant — a long-lived token is "refreshed" by re-exchanging *itself*
    (grant_type=fb_exchange_token) while still valid, not via a separate
    refresh credential, and that re-exchange stops working the moment the
    token is actually expired/revoked. `_refresh_access_token` models that:
    it treats whatever is passed as `refresh_token` as the prior long-lived
    access token to re-exchange, and the resulting SocialTokens.refresh_token
    is the new access_token itself (so a caller can chain another refresh
    later, same shape LinkedIn/X give their refresh_token).
    """

    GRAPH_VERSION = "v21.0"
    AUTHORIZE_URL = f"https://www.facebook.com/{GRAPH_VERSION}/dialog/oauth"
    TOKEN_URL = f"https://graph.facebook.com/{GRAPH_VERSION}/oauth/access_token"
    ME_URL = f"https://graph.facebook.com/{GRAPH_VERSION}/me"

    SCOPES = ("pages_show_list", "pages_read_engagement", "pages_manage_posts")

    def __init__(self, client_id: str, client_secret: str, timeout: float = 15.0) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.timeout = timeout

    # -- SocialOAuthProvider -----------------------------------------------

    def authorize_url(self, state: str, redirect_uri: str) -> str:
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "scope": ",".join(self.SCOPES),
        }
        return f"{self.AUTHORIZE_URL}?{urlencode(params)}"

    def exchange_code(self, code: str, redirect_uri: str) -> SocialTokens:
        with track_integration_call("facebook", "oauth_exchange"):
            response = httpx.post(
                self.TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
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
        external_account_id = self._fetch_page_id(data["access_token"])

        return SocialTokens(
            access_token=data["access_token"],
            # No standalone refresh_token — see class docstring.
            refresh_token=None,
            expires_at=expires_at,
            scopes=list(self.SCOPES),
            external_account_id=external_account_id,
        )

    def is_token_valid(self, access_token: str) -> bool:
        with track_integration_call("facebook", "oauth_status_check"):
            response = httpx.get(
                self.ME_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=self.timeout,
            )
        return response.status_code == 200

    def _fetch_page_id(self, access_token: str) -> str | None:
        with track_integration_call("facebook", "oauth_userinfo"):
            response = httpx.get(
                self.ME_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json().get("id")

    # -- SocialPublisher -----------------------------------------------

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
                    error="Facebook access token expired/invalid and no refresh token is stored",
                )
            try:
                new_tokens = self._refresh_access_token(refresh_token)
            except Exception as exc:  # noqa: BLE001 - surfaced as PublishResult, not raised
                return PublishResult(success=False, error=f"Facebook token refresh failed: {exc}")

            try:
                result = self._attempt_publish(new_tokens.access_token, content, media_urls)
            except Exception as exc:  # noqa: BLE001
                return PublishResult(
                    success=False,
                    error=f"Facebook publish failed after token refresh: {exc}",
                )
            result.refreshed_tokens = new_tokens
            return result
        except Exception as exc:  # noqa: BLE001 - vendor/network errors become failures, not raises
            return PublishResult(success=False, error=str(exc))

    def _attempt_publish(
        self, access_token: str, content: str, media_urls: list[str] | None
    ) -> PublishResult:
        with track_integration_call("facebook", "publish"):
            page_response = httpx.get(
                self.ME_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=self.timeout,
            )
            if page_response.status_code == 401:
                raise _TokenExpiredError("Facebook rejected the access token")
            page_response.raise_for_status()
            page_id = page_response.json()["id"]

            body: dict[str, object] = {"message": content}
            if media_urls:
                # A single link attachment — a multi-photo post needs the
                # separate /{page-id}/photos endpoint (attach_to_object_id
                # workflow), which no caller in this codebase produces yet.
                body["link"] = media_urls[0]

            response = httpx.post(
                f"https://graph.facebook.com/{self.GRAPH_VERSION}/{page_id}/feed",
                headers={"Authorization": f"Bearer {access_token}"},
                json=body,
                timeout=self.timeout,
            )
            if response.status_code == 401:
                raise _TokenExpiredError("Facebook rejected the access token")
            response.raise_for_status()
            post_id = response.json().get("id")

        return PublishResult(
            success=True,
            platform_post_id=post_id,
            platform_post_url=f"https://www.facebook.com/{post_id}" if post_id else None,
        )

    # -- SocialPublisher: engagement -------------------------------------

    def get_engagement(self, access_token: str, platform_post_id: str) -> EngagementResult:
        try:
            with track_integration_call("facebook", "get_engagement"):
                response = httpx.get(
                    f"https://graph.facebook.com/{self.GRAPH_VERSION}/{platform_post_id}",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params={"fields": "likes.summary(true),comments.summary(true),shares"},
                    timeout=self.timeout,
                )
                if response.status_code == 429:
                    return EngagementResult(
                        success=False,
                        error="Facebook rate-limited this engagement request",
                        rate_limited=True,
                    )
                response.raise_for_status()
                data = response.json()
        except Exception as exc:  # noqa: BLE001 - vendor/network errors become failures, not raises
            return EngagementResult(success=False, error=str(exc))

        # Post-level impressions require the separate Page Insights API
        # (a different permission this adapter doesn't request today) —
        # left at 0 rather than raised as a failure, same "unsupported
        # metric reads 0, not unknown" convention EngagementSnapshot's
        # model docstring establishes.
        return EngagementResult(
            success=True,
            metrics=EngagementMetrics(
                likes=data.get("likes", {}).get("summary", {}).get("total_count", 0),
                comments=data.get("comments", {}).get("summary", {}).get("total_count", 0),
                shares=data.get("shares", {}).get("count", 0),
                impressions=0,
            ),
        )

    def _refresh_access_token(self, refresh_token: str) -> SocialTokens:
        with track_integration_call("facebook", "oauth_refresh"):
            response = httpx.post(
                self.TOKEN_URL,
                data={
                    "grant_type": "fb_exchange_token",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "fb_exchange_token": refresh_token,
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

        return SocialTokens(
            access_token=data["access_token"],
            # See class docstring: Meta "refresh" re-exchanges the token
            # itself, so the new access_token doubles as the next
            # refresh_token a caller would pass in.
            refresh_token=data.get("access_token"),
            expires_at=expires_at,
            scopes=list(self.SCOPES),
            external_account_id=None,
        )
