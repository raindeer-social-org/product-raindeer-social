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
    """Internal signal that the platform rejected access_token as
    expired/invalid — distinct from other HTTP failures because it's the
    one case publish() retries after a refresh, rather than surfacing
    immediately."""


class LinkedInProvider(SocialOAuthProvider, SocialPublisher):
    """The only file in this codebase allowed to call LinkedIn's OAuth and
    publishing endpoints directly."""

    AUTHORIZE_URL = "https://www.linkedin.com/oauth/v2/authorization"
    TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
    USERINFO_URL = "https://api.linkedin.com/v2/userinfo"
    UGC_POSTS_URL = "https://api.linkedin.com/v2/ugcPosts"
    SOCIAL_METRICS_URL = "https://api.linkedin.com/v2/socialMetrics"

    SCOPES = ("openid", "profile", "w_member_social")

    def __init__(self, client_id: str, client_secret: str, timeout: float = 15.0) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.timeout = timeout

    def authorize_url(self, state: str, redirect_uri: str) -> str:
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "scope": " ".join(self.SCOPES),
        }
        return f"{self.AUTHORIZE_URL}?{urlencode(params)}"

    def exchange_code(
        self, code: str, redirect_uri: str, code_verifier: str | None = None
    ) -> SocialTokens:
        # LinkedIn's authorization-code flow doesn't use PKCE — code_verifier
        # is part of the shared SocialOAuthProvider interface (XProvider
        # needs it), unused here.
        with track_integration_call("linkedin", "oauth_exchange"):
            response = httpx.post(
                self.TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
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

        external_account_id = self._fetch_member_id(data["access_token"])

        return SocialTokens(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_at=expires_at,
            scopes=scopes,
            external_account_id=external_account_id,
        )

    def is_token_valid(self, access_token: str) -> bool:
        with track_integration_call("linkedin", "oauth_status_check"):
            response = httpx.get(
                self.USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=self.timeout,
            )
        return response.status_code == 200

    def _fetch_member_id(self, access_token: str) -> str | None:
        with track_integration_call("linkedin", "oauth_userinfo"):
            response = httpx.get(
                self.USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json().get("sub")

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
                    error="LinkedIn access token expired/invalid and no refresh token is stored",
                )
            try:
                new_tokens = self._refresh_access_token(refresh_token)
            except Exception as exc:  # noqa: BLE001 - surfaced as PublishResult, not raised
                return PublishResult(success=False, error=f"LinkedIn token refresh failed: {exc}")

            try:
                result = self._attempt_publish(new_tokens.access_token, content, media_urls)
            except Exception as exc:  # noqa: BLE001
                return PublishResult(
                    success=False,
                    error=f"LinkedIn publish failed after token refresh: {exc}",
                )
            result.refreshed_tokens = new_tokens
            return result
        except Exception as exc:  # noqa: BLE001 - vendor/network errors become failures, not raises
            return PublishResult(success=False, error=str(exc))

    def _attempt_publish(
        self, access_token: str, content: str, media_urls: list[str] | None
    ) -> PublishResult:
        with track_integration_call("linkedin", "publish"):
            member_response = httpx.get(
                self.USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=self.timeout,
            )
            if member_response.status_code == 401:
                raise _TokenExpiredError("LinkedIn rejected the access token")
            member_response.raise_for_status()
            author_urn = f"urn:li:person:{member_response.json()['sub']}"

            share_content: dict[str, object] = {
                "shareCommentary": {"text": content},
                "shareMediaCategory": "IMAGE" if media_urls else "NONE",
            }
            if media_urls:
                share_content["media"] = [
                    {"status": "READY", "originalUrl": url} for url in media_urls
                ]

            response = httpx.post(
                self.UGC_POSTS_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                    "X-Restli-Protocol-Version": "2.0.0",
                },
                json={
                    "author": author_urn,
                    "lifecycleState": "PUBLISHED",
                    "specificContent": {"com.linkedin.ugc.ShareContent": share_content},
                    "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
                },
                timeout=self.timeout,
            )
            if response.status_code == 401:
                raise _TokenExpiredError("LinkedIn rejected the access token")
            response.raise_for_status()
            post_id = response.headers.get("x-restli-id") or response.json().get("id")

        return PublishResult(
            success=True,
            platform_post_id=post_id,
            platform_post_url=(
                f"https://www.linkedin.com/feed/update/{post_id}/" if post_id else None
            ),
        )

    # -- SocialPublisher: engagement -------------------------------------

    def get_engagement(self, access_token: str, platform_post_id: str) -> EngagementResult:
        try:
            with track_integration_call("linkedin", "get_engagement"):
                response = httpx.get(
                    f"{self.SOCIAL_METRICS_URL}/{platform_post_id}",
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=self.timeout,
                )
                if response.status_code == 429:
                    return EngagementResult(
                        success=False,
                        error="LinkedIn rate-limited this engagement request",
                        rate_limited=True,
                    )
                response.raise_for_status()
                data = response.json()
        except Exception as exc:  # noqa: BLE001 - vendor/network errors become failures, not raises
            return EngagementResult(success=False, error=str(exc))

        return EngagementResult(
            success=True,
            metrics=EngagementMetrics(
                likes=data.get("likes", 0),
                comments=data.get("comments", 0),
                shares=data.get("shares", 0),
                impressions=data.get("impressions", 0),
            ),
        )

    def _refresh_access_token(self, refresh_token: str) -> SocialTokens:
        with track_integration_call("linkedin", "oauth_refresh"):
            response = httpx.post(
                self.TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
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
            # LinkedIn's refresh response doesn't always include a new
            # refresh_token — the old one stays valid until it's rotated.
            refresh_token=data.get("refresh_token", refresh_token),
            expires_at=expires_at,
            scopes=scopes,
            external_account_id=None,
        )
