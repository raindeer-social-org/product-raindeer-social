"""Tests for the Issue #152 website-scraping adapter
(packages/integrations/webscrape/) — the real counterpart to onboarding's
Tavily-search-only "research" step. Per this repo's interface-only
convention (see test_image_gen.py's docstring for the same pattern):

  1. HttpxWebScrapeProvider implements WebScrapeProvider and is reached
     only through that interface elsewhere in the codebase.
  2. It extracts title/description/text/logo/colors from a real page,
     with only the outbound HTTP layer mocked.
  3. A failed primary fetch raises (same raise/catch split as every other
     adapter); a failed secondary step (no logo, bad image bytes) degrades
     within the result instead.
"""

from unittest.mock import MagicMock, patch

import pytest

from apps.api.config import get_settings
from packages.integrations.registry import get_webscrape_provider
from packages.integrations.webscrape.base import ScrapeResult, WebScrapeProvider
from packages.integrations.webscrape.httpx_provider import HttpxWebScrapeProvider

_HTML = """
<html>
  <head>
    <title>Acme Widgets</title>
    <meta name="description" content="We make widgets for makers.">
    <meta property="og:image" content="/static/logo.png">
  </head>
  <body>
    <nav>Nav junk that shouldn't appear</nav>
    <main><p>Acme Widgets builds durable, hand-finished widgets for professional makers.</p></main>
    <footer>Footer junk that shouldn't appear</footer>
  </body>
</html>
"""


def _page_response(html: str = _HTML, url: str = "https://acme.test/") -> MagicMock:
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.text = html
    response.url = url
    return response


def _image_response(content: bytes = b"fake-png-bytes", content_type: str = "image/png") -> MagicMock:
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.content = content
    response.headers = {"content-type": content_type}
    return response


def test_provider_implements_interface() -> None:
    assert isinstance(HttpxWebScrapeProvider(), WebScrapeProvider)


def test_scrape_extracts_title_description_and_text() -> None:
    with patch("httpx.get", return_value=_page_response()):
        result = HttpxWebScrapeProvider().scrape("https://acme.test/")

    assert isinstance(result, ScrapeResult)
    assert result.title == "Acme Widgets"
    assert result.description == "We make widgets for makers."
    assert "hand-finished widgets" in result.text
    assert "Nav junk" not in result.text
    assert "Footer junk" not in result.text


def test_scrape_resolves_relative_og_image_and_fetches_it_for_colors() -> None:
    page = _page_response()
    image = _image_response()

    with patch("httpx.get", side_effect=[page, image]):
        result = HttpxWebScrapeProvider().scrape("https://acme.test/")

    assert result.logo_url == "https://acme.test/static/logo.png"
    assert result.logo_bytes == b"fake-png-bytes"
    # PIL can't decode fake bytes into a real image, so color extraction
    # degrades to an empty palette rather than raising — see the next test
    # for a real image decode.
    assert result.colors == []


def test_scrape_extracts_a_color_palette_from_a_real_image() -> None:
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (10, 10), color=(27, 77, 255)).save(buf, format="PNG")
    real_png_bytes = buf.getvalue()

    page = _page_response()
    image = _image_response(content=real_png_bytes)

    with patch("httpx.get", side_effect=[page, image]):
        result = HttpxWebScrapeProvider().scrape("https://acme.test/")

    assert result.colors == ["#1b4dff"]


def test_scrape_degrades_when_logo_fetch_fails() -> None:
    page = _page_response()

    with patch("httpx.get", side_effect=[page, Exception("logo unreachable")]):
        result = HttpxWebScrapeProvider().scrape("https://acme.test/")

    assert result.logo_url is None
    assert result.logo_bytes is None
    assert result.colors == []
    # The primary page content is still there — a bad logo doesn't sink
    # an otherwise-good scrape.
    assert result.title == "Acme Widgets"


def test_scrape_falls_back_to_favicon_when_no_og_image() -> None:
    html = _HTML.replace('<meta property="og:image" content="/static/logo.png">', "")
    page = _page_response(html)
    image = _image_response()

    with patch("httpx.get", side_effect=[page, image]):
        result = HttpxWebScrapeProvider().scrape("https://acme.test/")

    assert result.logo_url == "https://acme.test/favicon.ico"


def test_scrape_raises_when_primary_fetch_fails() -> None:
    with patch("httpx.get", side_effect=Exception("site unreachable")):
        with pytest.raises(Exception, match="site unreachable"):
            HttpxWebScrapeProvider().scrape("https://acme.test/")


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_get_webscrape_provider_defaults_to_httpx() -> None:
    assert isinstance(get_webscrape_provider(), HttpxWebScrapeProvider)


def test_unknown_webscrape_provider_raises(monkeypatch) -> None:
    monkeypatch.setenv("WEBSCRAPE_PROVIDER", "firecrawl")
    with pytest.raises(ValueError, match="Unknown WEBSCRAPE_PROVIDER"):
        get_webscrape_provider()
