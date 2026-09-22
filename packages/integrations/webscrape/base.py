from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ScrapeResult:
    url: str
    title: str | None = None
    description: str | None = None
    text: str = ""
    logo_url: str | None = None
    # Raw bytes of whatever image logo_url pointed at, when the adapter
    # already had to fetch it (e.g. to extract colors) — lets a caller
    # re-host it via StorageProvider without a second fetch. None when no
    # logo candidate was found, or the fetch failed.
    logo_bytes: bytes | None = None
    logo_content_type: str | None = None
    colors: list[str] = field(default_factory=list)
    # Social profile links found on the page (e.g. footer/header icons
    # linking to instagram.com/x.com/linkedin.com/...), deduplicated by
    # platform, first match wins. This repo doesn't attempt to scrape
    # *those* pages directly (most require auth or actively block
    # unauthenticated scraping) — surfacing the links themselves is real,
    # honest signal Aarav can reference and the brand can later connect
    # for real via the existing OAuth flows (packages/integrations/social).
    social_links: dict[str, str] = field(default_factory=dict)


class WebScrapeProvider(ABC):
    """Interface every website-scraping adapter implements. Business/agent
    code must only ever depend on this interface — never fetch a brand's
    website directly outside the adapter that implements it, same
    contract as every other package under packages/integrations/."""

    @abstractmethod
    def scrape(self, url: str) -> ScrapeResult:
        """Fetches `url` and extracts title/description/visible text plus
        a logo candidate and a small dominant-color palette.

        Same raise/catch split as every other adapter in this repo (e.g.
        FalImageProvider.generate()): raises if the primary page fetch
        itself fails (unreachable site, non-2xx) — the caller (see
        packages/agents/onboarding/research_step.py's
        run_website_scrape()) is responsible for catching that and
        degrading gracefully, same as _search_safely there already does
        for Tavily. A failed *secondary* step — no logo found, the logo
        image failing to fetch/decode — does NOT raise; it just leaves
        logo_url/logo_bytes/colors empty on an otherwise-successful
        result, since a missing logo shouldn't sink an otherwise-good
        scrape of the page's text."""
        ...
