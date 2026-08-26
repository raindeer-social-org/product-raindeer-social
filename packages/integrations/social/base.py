from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass
class SocialTokens:
    access_token: str
    refresh_token: str | None
    expires_at: datetime | None
    scopes: list[str]
    external_account_id: str | None = None


class SocialOAuthProvider(ABC):
    """Interface every social OAuth adapter implements. Business/router
    code must only ever depend on this interface — never import a vendor
    SDK directly outside the adapter that implements it."""

    @abstractmethod
    def authorize_url(self, state: str, redirect_uri: str) -> str:
        ...

    @abstractmethod
    def exchange_code(self, code: str, redirect_uri: str) -> SocialTokens:
        ...

    @abstractmethod
    def is_token_valid(self, access_token: str) -> bool:
        """Calls the platform to check whether access_token is still
        accepted — the only reliable way to detect a token the user
        revoked on the platform's side, since revocation isn't pushed
        to us."""
        ...


@dataclass
class EngagementMetrics:
    """Cumulative engagement counts for a single published post, as
    reported by the platform at the moment of the call — not deltas
    since a previous poll. Deliberately a plain dataclass, same reasoning
    as SocialTokens/PublishResult above: this package never depends on
    apps.api, so the caller (#33's engagement_polling.py) is responsible
    for turning this into an EngagementSnapshot row."""

    likes: int
    comments: int
    shares: int
    impressions: int


@dataclass
class EngagementResult:
    """Returned by SocialPublisher.get_engagement()."""

    success: bool
    metrics: EngagementMetrics | None = None
    error: str | None = None
    # True when the failure was specifically the platform rate-limiting
    # this call (e.g. HTTP 429) — lets the caller (engagement_polling.py)
    # back off rather than hammer the platform, same "respect rate
    # limits" acceptance criterion #31's publish queue already has to
    # satisfy, without the caller having to string-match `error`.
    rate_limited: bool = False


@dataclass
class PublishResult:
    """Returned by SocialPublisher.publish(). Like SocialTokens above,
    deliberately a plain dataclass (not tied to any ORM model) so this
    package never depends on apps.api — the caller (the publish queue in
    #31) is responsible for turning this into whatever it writes back onto
    Post/SocialAccount."""

    success: bool
    platform_post_id: str | None = None
    platform_post_url: str | None = None
    error: str | None = None
    # Populated only when publish() had to transparently refresh an
    # expired access token to succeed — lets the caller persist the new
    # token onto SocialAccount rather than the adapter reaching into that
    # table itself.
    refreshed_tokens: SocialTokens | None = None


class SocialPublisher(ABC):
    """Interface every publishing adapter implements. Business/router code
    (and the #31 publish queue) must only ever depend on this interface —
    never import a vendor SDK or call a vendor URL directly outside the
    adapter that implements it. Takes primitive types (not the
    SocialAccount ORM model) so this package never depends on apps.api."""

    @abstractmethod
    def publish(
        self,
        access_token: str,
        content: str,
        media_urls: list[str] | None = None,
        refresh_token: str | None = None,
    ) -> PublishResult:
        """Publish content. If the platform reports access_token as
        expired/invalid and refresh_token is provided, refreshes it and
        retries exactly once before giving up — that retry (success or
        failure) is what's returned, never surfaced as a separate error to
        the caller. Never raises for an ordinary publish failure (bad
        token, rejected content, network/HTTP error, a failed refresh) —
        those come back as PublishResult(success=False, error=...) so the
        caller doesn't need a try/except around every call site."""
        ...

    @abstractmethod
    def get_engagement(self, access_token: str, platform_post_id: str) -> EngagementResult:
        """Fetch current likes/comments/shares/impressions for a post this
        adapter previously published (platform_post_id is exactly
        PublishResult.platform_post_id from that publish() call). Like
        publish(), never raises for an ordinary failure (bad token,
        not-found post, network/HTTP error, rate limiting) — those come
        back as EngagementResult(success=False, error=..., rate_limited=
        ...) so the caller doesn't need a try/except around every call
        site. Does not itself sleep/retry on a rate limit — see
        EngagementResult.rate_limited's docstring for why that's the
        caller's job."""
        ...
