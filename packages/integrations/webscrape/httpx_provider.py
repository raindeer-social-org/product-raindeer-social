import io
import logging
import re
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from PIL import Image

from packages.integrations.observability import track_integration_call
from packages.integrations.webscrape.base import ScrapeResult, WebScrapeProvider

logger = logging.getLogger(__name__)

FETCH_TIMEOUT = 10.0
MAX_TEXT_CHARS = 8000
MAX_COLORS = 5
_USER_AGENT = "RaindeerSocial-Aarav/1.0 (+onboarding brand scan; respects robots via a single fetch)"

# Recognized social platforms for link detection, keyed by the domain
# fragment to match against an <a href>, valued by the canonical platform
# name used elsewhere in this repo (matches packages/integrations/social's
# provider names where one exists, e.g. "linkedin"/"x"/"instagram", plus a
# few this repo doesn't have a publishing adapter for yet — still useful
# as a brand-identity signal even without one).
_SOCIAL_DOMAINS = {
    "linkedin.com": "linkedin",
    "instagram.com": "instagram",
    "threads.net": "threads",
    "facebook.com": "facebook",
    "youtube.com": "youtube",
    "tiktok.com": "tiktok",
    "pinterest.com": "pinterest",
    "twitter.com": "x",
    "x.com": "x",
}


class HttpxWebScrapeProvider(WebScrapeProvider):
    """Free, dependency-light website scraper — plain httpx + BeautifulSoup
    + Pillow, no third-party scraping API/key. The only file allowed to
    fetch a brand's own site directly; every other module reaches it only
    through WebScrapeProvider, resolved via
    packages.integrations.registry.get_webscrape_provider()."""

    def scrape(self, url: str) -> ScrapeResult:
        with track_integration_call("httpx_webscrape", "scrape"):
            response = httpx.get(
                url,
                timeout=FETCH_TIMEOUT,
                follow_redirects=True,
                headers={"User-Agent": _USER_AGENT},
            )
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        final_url = str(response.url)

        title = _tag_text(soup.title)
        description = _meta_content(soup, "description") or _meta_content(soup, "og:description")
        logo_url = _resolve(_meta_content(soup, "og:image"), final_url) or _favicon_url(soup, final_url)
        text = _visible_text(soup)[:MAX_TEXT_CHARS]

        logo_bytes: bytes | None = None
        logo_content_type: str | None = None
        colors: list[str] = []
        if logo_url:
            logo_bytes, logo_content_type = _fetch_image_safely(logo_url)
            if logo_bytes:
                colors = _extract_palette(logo_bytes)

        social_links = _find_social_links(soup, final_url)

        return ScrapeResult(
            url=final_url,
            title=title,
            description=description,
            text=text,
            logo_url=logo_url if logo_bytes else None,
            logo_bytes=logo_bytes,
            logo_content_type=logo_content_type,
            colors=colors,
            social_links=social_links,
        )


def _tag_text(tag) -> str | None:
    if tag and tag.string:
        return tag.string.strip() or None
    return None


def _meta_content(soup: BeautifulSoup, name: str) -> str | None:
    tag = soup.find("meta", attrs={"name": name}) or soup.find("meta", attrs={"property": name})
    content = tag.get("content") if tag else None
    return content.strip() if content else None


def _resolve(maybe_url: str | None, base_url: str) -> str | None:
    if not maybe_url:
        return None
    return urljoin(base_url, maybe_url)


def _favicon_url(soup: BeautifulSoup, base_url: str) -> str | None:
    for rel in ("icon", "shortcut icon", "apple-touch-icon"):
        tag = soup.find("link", rel=rel)
        href = tag.get("href") if tag else None
        if href:
            return urljoin(base_url, href)
    # Last-resort convention every site is expected to (but may not)
    # serve — a 404 here is caught by _fetch_image_safely, not here.
    parsed = urlparse(base_url)
    return f"{parsed.scheme}://{parsed.netloc}/favicon.ico"


def _find_social_links(soup: BeautifulSoup, base_url: str) -> dict[str, str]:
    """Scans every <a href> on the page for a known social-platform domain
    (header/footer icon links, "follow us" sections, etc.) — the first
    match per platform wins. Deliberately does not follow or scrape these
    links (most social platforms require auth or actively block
    unauthenticated scraping); this is just honest surfacing of what the
    brand's own site already links to."""
    found: dict[str, str] = {}
    own_netloc = urlparse(base_url).netloc.lower()
    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        if not href or href.startswith("#"):
            continue
        resolved = urljoin(base_url, href)
        netloc = urlparse(resolved).netloc.lower().removeprefix("www.")
        if netloc == own_netloc:
            continue
        for domain, platform in _SOCIAL_DOMAINS.items():
            if platform in found:
                continue
            if netloc == domain or netloc.endswith(f".{domain}"):
                found[platform] = resolved
                break
    return found


def _visible_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript", "svg", "header", "footer", "nav"]):
        tag.decompose()
    return re.sub(r"\s+", " ", soup.get_text(separator=" ")).strip()


def _fetch_image_safely(image_url: str) -> tuple[bytes | None, str | None]:
    try:
        response = httpx.get(
            image_url, timeout=FETCH_TIMEOUT, follow_redirects=True, headers={"User-Agent": _USER_AGENT}
        )
        response.raise_for_status()
        content_type = response.headers.get("content-type", "image/png").split(";")[0].strip()
        return response.content, content_type
    except Exception:
        logger.info("Web scrape: logo candidate %r unreachable, skipping", image_url, exc_info=True)
        return None, None


def _extract_palette(image_bytes: bytes) -> list[str]:
    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        image.thumbnail((64, 64))
        quantized = image.quantize(colors=MAX_COLORS, method=Image.MEDIANCUT)
        palette = quantized.getpalette() or []
        counts = sorted(quantized.getcolors() or [], reverse=True)
        hex_colors = []
        for _, index in counts[:MAX_COLORS]:
            r, g, b = palette[index * 3 : index * 3 + 3]
            hex_colors.append(f"#{r:02x}{g:02x}{b:02x}")
        return hex_colors
    except Exception:
        logger.info("Web scrape: color extraction failed", exc_info=True)
        return []
