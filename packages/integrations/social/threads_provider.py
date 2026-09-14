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
    """Internal signal that Threads rejected access_token as
    expired/invalid — distinct from other HTTP failures because it's the
    one case publish() retries after a refresh, rather than surfacing
    immediately."""


class ThreadsProvider(SocialOAuthProvider, SocialPublisher):
    """The only file in this codebase allowed to call the Threads API's
    OAuth and publishing endpoints directly.

    Threads is a separate Meta product from the Facebook Graph API proper —
    its own OAuth dialog (threads.net) and its own API host
    (graph.threads.net) — but still registered under the same Meta
    developer app as Facebook/Instagram, hence sharing META_APP_ID/
    META_APP_SECRET with FacebookProvider/InstagramProvider even though the
    endpoints themselves differ.

    The authorization-code exchange response includes the Threads user id
    directly (`user_id`), so unlike LinkedIn/X/Facebook/Instagram this
    adapter doesn't need a separate userinfo call during exchange_code —
    only publish()/is_token_valid(), which don't have that response handy,
    re-fetch it from `/me`.

    Threads publishing is two-step like Instagram's (create a media
    container, then publish it) and supports text-only posts, unlike
    Instagram.

    Meta has no standalone refresh_token here either — see
    FacebookProvider's docstring for the same "re-exchange the token
    itself" shape, using Threads' own `th_refresh_token` grant.
    """

    AUTHORIZE_URL = "https://threads.net/oauth/authorize"
    TOKEN_URL = "https://graph.threads.net/oauth/access_token"
    REFRESH_URL = "https://graph.threads.net/refresh_access_token"
    ME_URL = "https://graph.threads.net/v1.0/me"

    SCOPES = ("threads_basic", "threads_content_publish")

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
        with track_integration_call("threads", "oauth_exchange"):
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

        return SocialTokens(
            access_token=data["access_token"],
            refresh_token=None,
            expires_at=expires_at,
            scopes=list(self.SCOPES),
            external_account_id=str(data["user_id"]) if data.get("user_id") is not None else None,
        )

    def is_token_valid(self, access_token: str) -> bool:
        with track_integration_call("threads", "oauth_status_check"):
            response = httpx.get(
                self.ME_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=self.timeout,
            )
        return response.status_code == 200

    def _fetch_user_id(self, access_token: str) -> str:
        with track_integration_call("threads", "oauth_userinfo"):
            response = httpx.get(
                self.ME_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=self.timeout,
            )
            if response.status_code == 401:
                raise _TokenExpiredError("Threads rejected the access token")
            response.raise_for_status()
            return response.json()["id"]

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
                    error="Threads access token expired/invalid and no refresh token is stored",
                )
            try:
                new_tokens = self._refresh_access_token(refresh_token)
            except Exception as exc:  # noqa: BLE001 - surfaced as PublishResult, not raised
                return PublishResult(success=False, error=f"Threads token refresh failed: {exc}")

            try:
                result = self._attempt_publish(new_tokens.access_token, content, media_urls)
            except Exception as exc:  # noqa: BLE001
                return PublishResult(
                    success=False,
                    error=f"Threads publish failed after token refresh: {exc}",
                )
            result.refreshed_tokens = new_tokens
            return result
        except Exception as exc:  # noqa: BLE001 - vendor/network errors become failures, not raises
            return PublishResult(success=False, error=str(exc))

    def _attempt_publish(
        self, access_token: str, content: str, media_urls: list[str] | None
    ) -> PublishResult:
        with track_integration_call("threads", "publish"):
            threads_user_id = self._fetch_user_id(access_token)

            body: dict[str, object] = {"text": content}
            if media_urls:
                body["media_type"] = "IMAGE"
                body["image_url"] = media_urls[0]
            else:
                body["media_type"] = "TEXT"

            container_response = httpx.post(
                f"https://graph.threads.net/v1.0/{threads_user_id}/threads",
                headers={"Authorization": f"Bearer {access_token}"},
                json=body,
                timeout=self.timeout,
            )
            if container_response.status_code == 401:
                raise _TokenExpiredError("Threads rejected the access token")
            container_response.raise_for_status()
            creation_id = container_response.json()["id"]

            publish_response = httpx.post(
                f"https://graph.threads.net/v1.0/{threads_user_id}/threads_publish",
                headers={"Authorization": f"Bearer {access_token}"},
                json={"creation_id": creation_id},
                timeout=self.timeout,
            )
            if publish_response.status_code == 401:
                raise _TokenExpiredError("Threads rejected the access token")
            publish_response.raise_for_status()
            post_id = publish_response.json().get("id")

        return PublishResult(
            success=True,
            platform_post_id=post_id,
            platform_post_url=f"https://www.threads.net/t/{post_id}" if post_id else None,
        )

    # -- SocialPublisher: engagement -------------------------------------

    def get_engagement(self, access_token: str, platform_post_id: str) -> EngagementResult:
        try:
            with track_integration_call("threads", "get_engagement"):
                response = httpx.get(
                    f"https://graph.threads.net/v1.0/{platform_post_id}/insights",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params={"metric": "likes,replies,reposts,views"},
                    timeout=self.timeout,
                )
                if response.status_code == 429:
                    return EngagementResult(
                        success=False,
                        error="Threads rate-limited this engagement request",
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
                comments=values.get("replies", 0),
                shares=values.get("reposts", 0),
                impressions=values.get("views", 0),
            ),
        )

    def _refresh_access_token(self, refresh_token: str) -> SocialTokens:
        with track_integration_call("threads", "oauth_refresh"):
            response = httpx.get(
                self.REFRESH_URL,
                params={
                    "grant_type": "th_refresh_token",
                    "access_token": refresh_token,
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
