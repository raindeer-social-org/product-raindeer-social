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


class SocialPublisher(ABC):
    """Interface #30's publishing adapters implement. Declared here (not
    implemented until #30) so the SocialAccount storage this issue builds
    has a stable contract to be read through from day one — #30 doesn't
    have to touch this table's shape at all, only add adapters against it.
    Takes primitive types (not the SocialAccount ORM model) so this
    package never depends on apps.api."""

    @abstractmethod
    def publish(
        self, access_token: str, content: str, media_urls: list[str] | None = None
    ) -> str:
        """Publish content, returning the platform's post id/URL."""
        ...
