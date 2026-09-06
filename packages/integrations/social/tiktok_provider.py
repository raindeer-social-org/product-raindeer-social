import base64
import hashlib
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
    """Internal signal that TikTok rejected access_token as expired/
    invalid — distinct from other HTTP failures because it's the one case
    publish() retries after a refresh, rather than surfacing immediately."""


def _code_challenge_s256(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


class TikTokProvider(SocialOAuthProvider, SocialPublisher):
    """The only file in this codebase allowed to call TikTok for
    Developers' OAuth2 and Content Posting API directly.

    Unlike XProvider's "plain" PKCE shortcut (code_challenge == the raw
    verifier), TikTok's API requires the S256 method — this derives a real
    code_challenge = base64url(sha256(code_verifier)) at authorize_url
    time. Same "state doubles as the verifier" trick as XProvider (it's
    already unique per request, single-use, and round-trips unmodified
    through the redirect) — router code passes `state` back in as
    `code_verifier` at exchange_code time, same as it does for X.
    """

    AUTHORIZE_URL = "https://www.tiktok.com/v2/auth/authorize/"
    TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
    USERINFO_URL = "https://open.tiktokapis.com/v2/user/info/"
    PUBLISH_INIT_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
    VIDEO_QUERY_URL = "https://open.tiktokapis.com/v2/video/query/"

    SCOPES = ("user.info.basic", "video.publish", "video.list")

    def __init__(self, client_key: str, client_secret: str, timeout: float = 30.0) -> None:
        self.client_key = client_key
        self.client_secret = client_secret
        self.timeout = timeout

    # -- SocialOAuthProvider ---------------------------------------------

    def authorize_url(self, state: str, redirect_uri: str) -> str:
        params = {
            "client_key": self.client_key,
            "response_type": "code",
            "scope": ",".join(self.SCOPES),
            "redirect_uri": redirect_uri,
            "state": state,
            "code_challenge": _code_challenge_s256(state),
            "code_challenge_method": "S256",
        }
        return f"{self.AUTHORIZE_URL}?{urlencode(params)}"

    def exchange_code(
        self, code: str, redirect_uri: str, code_verifier: str | None = None
    ) -> SocialTokens:
        if not code_verifier:
            raise ValueError("TikTokProvider.exchange_code requires code_verifier (PKCE)")

        with track_integration_call("tiktok", "oauth_exchange"):
            response = httpx.post(
                self.TOKEN_URL,
                data={
                    "client_key": self.client_key,
                    "client_secret": self.client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri,
                    "code_verifier": code_verifier,
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
            refresh_token=data.get("refresh_token"),
            expires_at=expires_at,
            scopes=scopes,
            external_account_id=data.get("open_id"),
        )

    def is_token_valid(self, access_token: str) -> bool:
        with track_integration_call("tiktok", "oauth_status_check"):
            response = httpx.get(
                self.USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                params={"fields": "open_id"},
                timeout=self.timeout,
            )
        return response.status_code == 200

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
                error="TikTok publish requires a video file — no media_urls provided",
            )
        try:
            return self._attempt_publish(access_token, content, media_urls[0])
        except _TokenExpiredError:
            if not refresh_token:
                return PublishResult(
                    success=False,
                    error="TikTok access token expired/invalid and no refresh token is stored",
                )
            try:
                new_tokens = self._refresh_access_token(refresh_token)
            except Exception as exc:  # noqa: BLE001 - surfaced as PublishResult, not raised
                return PublishResult(success=False, error=f"TikTok token refresh failed: {exc}")

            try:
                result = self._attempt_publish(new_tokens.access_token, content, media_urls[0])
            except Exception as exc:  # noqa: BLE001
                return PublishResult(
                    success=False, error=f"TikTok publish failed after token refresh: {exc}"
                )
            result.refreshed_tokens = new_tokens
            return result
        except Exception as exc:  # noqa: BLE001 - vendor/network errors become failures, not raises
            return PublishResult(success=False, error=str(exc))

    def _attempt_publish(
        self, access_token: str, content: str, video_url: str
    ) -> PublishResult:
        # Content Posting API's PULL_FROM_URL source lets TikTok fetch the
        # video itself from our already-durable StorageProvider URL, rather
        # than this adapter re-uploading the bytes through a chunked PUT —
        # simplest integration against a public HTTPS video_url, which is
        # exactly what Generation Engine's stored media URLs already are.
        with track_integration_call("tiktok", "publish"):
            response = httpx.post(
                self.PUBLISH_INIT_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json={
                    "post_info": {"title": content, "privacy_level": "PUBLIC_TO_EVERYONE"},
                    "source_info": {
                        "source": "PULL_FROM_URL",
                        "video_url": video_url,
                    },
                },
                timeout=self.timeout,
            )
            if response.status_code == 401:
                raise _TokenExpiredError("TikTok rejected the access token")
            response.raise_for_status()
            data = response.json().get("data", {})

        publish_id = data.get("publish_id")
        return PublishResult(success=True, platform_post_id=publish_id, platform_post_url=None)

    # -- SocialPublisher: engagement ---------------------------------------

    def get_engagement(self, access_token: str, platform_post_id: str) -> EngagementResult:
        try:
            with track_integration_call("tiktok", "get_engagement"):
                response = httpx.post(
                    self.VIDEO_QUERY_URL,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                    },
                    params={"fields": "id,like_count,comment_count,share_count,view_count"},
                    json={"filters": {"video_ids": [platform_post_id]}},
                    timeout=self.timeout,
                )
                if response.status_code == 429:
                    return EngagementResult(
                        success=False,
                        error="TikTok rate-limited this engagement request",
                        rate_limited=True,
                    )
                response.raise_for_status()
                videos = response.json().get("data", {}).get("videos", [])
                stats = videos[0] if videos else {}
        except Exception as exc:  # noqa: BLE001 - vendor/network errors become failures, not raises
            return EngagementResult(success=False, error=str(exc))

        return EngagementResult(
            success=True,
            metrics=EngagementMetrics(
                likes=int(stats.get("like_count", 0)),
                comments=int(stats.get("comment_count", 0)),
                shares=int(stats.get("share_count", 0)),
                impressions=int(stats.get("view_count", 0)),
            ),
        )

    def _refresh_access_token(self, refresh_token: str) -> SocialTokens:
        with track_integration_call("tiktok", "oauth_refresh"):
            response = httpx.post(
                self.TOKEN_URL,
                data={
                    "client_key": self.client_key,
                    "client_secret": self.client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
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
            # TikTok rotates refresh tokens on every use, same as X.
            refresh_token=data.get("refresh_token", refresh_token),
            expires_at=expires_at,
            scopes=scopes,
            external_account_id=data.get("open_id"),
        )
