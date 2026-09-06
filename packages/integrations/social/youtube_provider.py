import json
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
    """Internal signal that YouTube/Google rejected access_token as
    expired/invalid — distinct from other HTTP failures because it's the
    one case publish() retries after a refresh, rather than surfacing
    immediately."""


class YouTubeProvider(SocialOAuthProvider, SocialPublisher):
    """The only file in this codebase allowed to call Google's OAuth2 and
    the YouTube Data API v3 directly.

    Standard Google OAuth2 authorization-code flow (no PKCE needed — this
    is a confidential/server-side client, same shape as LinkedIn) with
    `access_type=offline` + `prompt=consent` so Google actually returns a
    refresh_token (it otherwise only does so on a user's very first
    consent). Publishing uploads a video via `videos.insert`'s resumable
    upload protocol: an initial POST to get a per-upload session URL, then
    a PUT of the raw bytes to that URL — YouTube has no "post text" concept
    like LinkedIn/X, every publish is a video upload, so `content` here is
    used as the video's title/description rather than post body text.
    """

    AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    UPLOAD_URL = (
        "https://www.googleapis.com/upload/youtube/v3/videos"
        "?uploadType=resumable&part=snippet,status"
    )
    VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
    CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
    TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"

    SCOPES = (
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtube.readonly",
    )

    def __init__(self, client_id: str, client_secret: str, timeout: float = 30.0) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.timeout = timeout

    # -- SocialOAuthProvider ---------------------------------------------

    def authorize_url(self, state: str, redirect_uri: str) -> str:
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "scope": " ".join(self.SCOPES),
            "access_type": "offline",
            "prompt": "consent",
        }
        return f"{self.AUTHORIZE_URL}?{urlencode(params)}"

    def exchange_code(
        self, code: str, redirect_uri: str, code_verifier: str | None = None
    ) -> SocialTokens:
        with track_integration_call("youtube", "oauth_exchange"):
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
        scopes = raw_scope.split(" ") if raw_scope else list(self.SCOPES)

        external_account_id = self._fetch_channel_id(data["access_token"])

        return SocialTokens(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_at=expires_at,
            scopes=scopes,
            external_account_id=external_account_id,
        )

    def is_token_valid(self, access_token: str) -> bool:
        with track_integration_call("youtube", "oauth_status_check"):
            response = httpx.get(
                self.TOKENINFO_URL,
                params={"access_token": access_token},
                timeout=self.timeout,
            )
        return response.status_code == 200

    def _fetch_channel_id(self, access_token: str) -> str | None:
        with track_integration_call("youtube", "oauth_userinfo"):
            response = httpx.get(
                self.CHANNELS_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                params={"part": "id", "mine": "true"},
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
                error="YouTube publish requires a video file — no media_urls provided",
            )
        try:
            return self._attempt_publish(access_token, content, media_urls[0])
        except _TokenExpiredError:
            if not refresh_token:
                return PublishResult(
                    success=False,
                    error="YouTube access token expired/invalid and no refresh token is stored",
                )
            try:
                new_tokens = self._refresh_access_token(refresh_token)
            except Exception as exc:  # noqa: BLE001 - surfaced as PublishResult, not raised
                return PublishResult(success=False, error=f"YouTube token refresh failed: {exc}")

            try:
                result = self._attempt_publish(new_tokens.access_token, content, media_urls[0])
            except Exception as exc:  # noqa: BLE001
                return PublishResult(
                    success=False, error=f"YouTube publish failed after token refresh: {exc}"
                )
            result.refreshed_tokens = new_tokens
            return result
        except Exception as exc:  # noqa: BLE001 - vendor/network errors become failures, not raises
            return PublishResult(success=False, error=str(exc))

    def _attempt_publish(
        self, access_token: str, content: str, video_url: str
    ) -> PublishResult:
        with track_integration_call("youtube", "publish"):
            video_bytes = httpx.get(video_url, timeout=self.timeout).content

            session = httpx.post(
                self.UPLOAD_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json; charset=UTF-8",
                    "X-Upload-Content-Type": "video/*",
                },
                content=json.dumps(
                    {
                        "snippet": {"title": content[:100] or "Untitled", "description": content},
                        "status": {"privacyStatus": "public"},
                    }
                ),
                timeout=self.timeout,
            )
            if session.status_code == 401:
                raise _TokenExpiredError("YouTube rejected the access token")
            session.raise_for_status()
            upload_url = session.headers["Location"]

            response = httpx.put(
                upload_url,
                content=video_bytes,
                headers={"Content-Type": "video/*"},
                timeout=self.timeout,
            )
            if response.status_code == 401:
                raise _TokenExpiredError("YouTube rejected the access token")
            response.raise_for_status()
            data = response.json()

        video_id = data.get("id")
        return PublishResult(
            success=True,
            platform_post_id=video_id,
            platform_post_url=f"https://youtube.com/watch?v={video_id}" if video_id else None,
        )

    # -- SocialPublisher: engagement ---------------------------------------

    def get_engagement(self, access_token: str, platform_post_id: str) -> EngagementResult:
        try:
            with track_integration_call("youtube", "get_engagement"):
                response = httpx.get(
                    self.VIDEOS_URL,
                    headers={"Authorization": f"Bearer {access_token}"},
                    params={"id": platform_post_id, "part": "statistics"},
                    timeout=self.timeout,
                )
                if response.status_code == 429:
                    return EngagementResult(
                        success=False,
                        error="YouTube rate-limited this engagement request",
                        rate_limited=True,
                    )
                response.raise_for_status()
                items = response.json().get("items", [])
                stats = items[0]["statistics"] if items else {}
        except Exception as exc:  # noqa: BLE001 - vendor/network errors become failures, not raises
            return EngagementResult(success=False, error=str(exc))

        return EngagementResult(
            success=True,
            metrics=EngagementMetrics(
                likes=int(stats.get("likeCount", 0)),
                comments=int(stats.get("commentCount", 0)),
                shares=0,  # YouTube Data API exposes no share count.
                impressions=int(stats.get("viewCount", 0)),
            ),
        )

    def _refresh_access_token(self, refresh_token: str) -> SocialTokens:
        with track_integration_call("youtube", "oauth_refresh"):
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
        scopes = raw_scope.split(" ") if raw_scope else list(self.SCOPES)

        return SocialTokens(
            access_token=data["access_token"],
            # Google doesn't reissue a refresh_token on refresh — the
            # original stays valid until revoked, unlike X's rotate-every-
            # use model.
            refresh_token=refresh_token,
            expires_at=expires_at,
            scopes=scopes,
            external_account_id=None,
        )
