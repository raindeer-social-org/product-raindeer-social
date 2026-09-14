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
    """Internal signal that Instagram (Meta Graph API) rejected
    access_token as expired/invalid — distinct from other HTTP failures
    because it's the one case publish() retries after a refresh, rather
    than surfacing immediately."""


class _NoInstagramAccountError(Exception):
    """Raised when the Facebook Page behind this token has no linked
    Instagram professional account — a real, expected state (not every
    Page has one converted), not a transport failure, so it's a distinct
    class from _TokenExpiredError even though both fall back to the same
    generic PublishResult(success=False, ...) in publish()."""


class InstagramProvider(SocialOAuthProvider, SocialPublisher):
    """The only file in this codebase allowed to call the Instagram Graph
    API's OAuth and content-publishing endpoints directly.

    Instagram's Content Publishing API rides on Facebook Login and the same
    graph.facebook.com host FacebookProvider uses (same Meta developer app,
    same reason META_APP_ID/META_APP_SECRET are shared config) — an IG
    professional account is only reachable through the Facebook Page it's
    linked to, never directly. `access_token` is a Page-scoped user access
    token; `_fetch_ig_user_id` resolves the linked IG business account id
    fresh on every call (via /me/accounts) rather than accepting it as a
    parameter, the same "ask the token, don't thread an extra id through
    the interface" choice LinkedInProvider/XProvider make for their own
    account ids.

    Instagram has no text-only post — every publish() call requires at
    least one media URL; a caller that omits media_urls gets a normal
    PublishResult(success=False, ...) rather than a raised error, same as
    any other rejected-content failure.

    Like FacebookProvider, Meta has no standalone refresh_token — see that
    class's docstring for how _refresh_access_token models re-exchange
    instead.
    """

    GRAPH_VERSION = "v21.0"
    AUTHORIZE_URL = f"https://www.facebook.com/{GRAPH_VERSION}/dialog/oauth"
    TOKEN_URL = f"https://graph.facebook.com/{GRAPH_VERSION}/oauth/access_token"
    ACCOUNTS_URL = f"https://graph.facebook.com/{GRAPH_VERSION}/me/accounts"

    SCOPES = (
        "instagram_basic",
        "instagram_content_publish",
        "pages_show_list",
        "pages_read_engagement",
    )

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
        with track_integration_call("instagram", "oauth_exchange"):
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

        try:
            external_account_id = self._fetch_ig_user_id(data["access_token"])
        except _NoInstagramAccountError:
            external_account_id = None

        return SocialTokens(
            access_token=data["access_token"],
            refresh_token=None,
            expires_at=expires_at,
            scopes=list(self.SCOPES),
            external_account_id=external_account_id,
        )

    def is_token_valid(self, access_token: str) -> bool:
        with track_integration_call("instagram", "oauth_status_check"):
            response = httpx.get(
                self.ACCOUNTS_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=self.timeout,
            )
        return response.status_code == 200

    def _fetch_ig_user_id(self, access_token: str) -> str:
        with track_integration_call("instagram", "oauth_userinfo"):
            response = httpx.get(
                self.ACCOUNTS_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                params={"fields": "instagram_business_account"},
                timeout=self.timeout,
            )
            if response.status_code == 401:
                raise _TokenExpiredError("Instagram rejected the access token")
            response.raise_for_status()
            pages = response.json().get("data", [])

        for page in pages:
            ig_account = page.get("instagram_business_account")
            if ig_account and ig_account.get("id"):
                return ig_account["id"]
        raise _NoInstagramAccountError(
            "No Instagram professional account is linked to this Facebook Page"
        )

    # -- SocialPublisher -----------------------------------------------

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
                error="Instagram requires at least one media URL to publish a post",
            )
        try:
            return self._attempt_publish(access_token, content, media_urls)
        except _TokenExpiredError:
            if not refresh_token:
                return PublishResult(
                    success=False,
                    error="Instagram access token expired/invalid and no refresh token is stored",
                )
            try:
                new_tokens = self._refresh_access_token(refresh_token)
            except Exception as exc:  # noqa: BLE001 - surfaced as PublishResult, not raised
                return PublishResult(success=False, error=f"Instagram token refresh failed: {exc}")

            try:
                result = self._attempt_publish(new_tokens.access_token, content, media_urls)
            except Exception as exc:  # noqa: BLE001
                return PublishResult(
                    success=False,
                    error=f"Instagram publish failed after token refresh: {exc}",
                )
            result.refreshed_tokens = new_tokens
            return result
        except Exception as exc:  # noqa: BLE001 - vendor/network errors become failures, not raises
            return PublishResult(success=False, error=str(exc))

    def _attempt_publish(
        self, access_token: str, content: str, media_urls: list[str]
    ) -> PublishResult:
        with track_integration_call("instagram", "publish"):
            ig_user_id = self._fetch_ig_user_id(access_token)

            container_response = httpx.post(
                f"https://graph.facebook.com/{self.GRAPH_VERSION}/{ig_user_id}/media",
                headers={"Authorization": f"Bearer {access_token}"},
                json={"image_url": media_urls[0], "caption": content},
                timeout=self.timeout,
            )
            if container_response.status_code == 401:
                raise _TokenExpiredError("Instagram rejected the access token")
            container_response.raise_for_status()
            creation_id = container_response.json()["id"]

            publish_response = httpx.post(
                f"https://graph.facebook.com/{self.GRAPH_VERSION}/{ig_user_id}/media_publish",
                headers={"Authorization": f"Bearer {access_token}"},
                json={"creation_id": creation_id},
                timeout=self.timeout,
            )
            if publish_response.status_code == 401:
                raise _TokenExpiredError("Instagram rejected the access token")
            publish_response.raise_for_status()
            post_id = publish_response.json().get("id")

        return PublishResult(
            success=True,
            platform_post_id=post_id,
            platform_post_url=f"https://www.instagram.com/p/{post_id}/" if post_id else None,
        )

    # -- SocialPublisher: engagement -------------------------------------

    def get_engagement(self, access_token: str, platform_post_id: str) -> EngagementResult:
        try:
            with track_integration_call("instagram", "get_engagement"):
                response = httpx.get(
                    f"https://graph.facebook.com/{self.GRAPH_VERSION}/{platform_post_id}/insights",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params={"metric": "impressions,reach,likes,comments,saved"},
                    timeout=self.timeout,
                )
                if response.status_code == 429:
                    return EngagementResult(
                        success=False,
                        error="Instagram rate-limited this engagement request",
                        rate_limited=True,
                    )
                response.raise_for_status()
                metric_rows = response.json().get("data", [])
        except Exception as exc:  # noqa: BLE001 - vendor/network errors become failures, not raises
            return EngagementResult(success=False, error=str(exc))

        values = {
            row["name"]: row.get("values", [{}])[0].get("value", 0)
            for row in metric_rows
            if row.get("name")
        }
        return EngagementResult(
            success=True,
            metrics=EngagementMetrics(
                likes=values.get("likes", 0),
                comments=values.get("comments", 0),
                # Instagram has no public "share" count — "saved" is the
                # closest amplification-style signal it exposes.
                shares=values.get("saved", 0),
                impressions=values.get("impressions", 0),
            ),
        )

    def _refresh_access_token(self, refresh_token: str) -> SocialTokens:
        with track_integration_call("instagram", "oauth_refresh"):
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
            refresh_token=data.get("access_token"),
            expires_at=expires_at,
            scopes=list(self.SCOPES),
            external_account_id=None,
        )
