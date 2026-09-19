from unittest.mock import patch

from apps.api.models import Brand, OnboardingResearch, Organization
from packages.agents.onboarding.research_step import run_website_scrape
from packages.integrations.llm.base import LLMResponse
from packages.integrations.webscrape.base import ScrapeResult

SCRAPE_PATCH_TARGET = "packages.agents.onboarding.research_step.get_webscrape_provider"
LLM_PATCH_TARGET = "packages.agents.onboarding.research_step.get_llm_provider"
STORAGE_PATCH_TARGET = "packages.agents.onboarding.research_step.get_storage_provider"


def _setup_brand(db_session, website: str | None = "https://acme.test") -> Brand:
    org = Organization(name="Acme Agency")
    db_session.add(org)
    db_session.flush()

    brand = Brand(
        organization_id=org.id,
        name="Acme Widgets",
        product_catalog={"website": website} if website else None,
    )
    db_session.add(brand)
    db_session.flush()
    return brand


def _scrape_result(**overrides) -> ScrapeResult:
    defaults = dict(
        url="https://acme.test/",
        title="Acme Widgets",
        description="We make widgets.",
        text="Acme Widgets builds durable widgets for professional makers.",
        logo_url="https://acme.test/logo.png",
        logo_bytes=b"fake-bytes",
        logo_content_type="image/png",
        colors=["#1b4dff", "#0a1633"],
    )
    defaults.update(overrides)
    return ScrapeResult(**defaults)


def _llm_summary_response(text: str = "Acme Widgets makes durable widgets for professional makers.") -> LLMResponse:
    return LLMResponse(text=text, model="openrouter/free", input_tokens=100, output_tokens=30)


def test_scrape_summarizes_and_rehosts_logo_and_stores_colors(db_session) -> None:
    brand = _setup_brand(db_session)

    with (
        patch(SCRAPE_PATCH_TARGET) as mock_scrape,
        patch(LLM_PATCH_TARGET) as mock_llm,
        patch(STORAGE_PATCH_TARGET) as mock_storage,
    ):
        mock_scrape.return_value.scrape.return_value = _scrape_result()
        mock_llm.return_value.complete.return_value = _llm_summary_response()
        mock_storage.return_value.upload.return_value = "https://storage.test/scraped-logo.png"

        research = run_website_scrape(db_session, brand)

    assert research.website_summary == "Acme Widgets makes durable widgets for professional makers."
    assert research.website_logo_url == "https://storage.test/scraped-logo.png"
    assert research.website_colors == ["#1b4dff", "#0a1633"]
    # The summarization LLM call is what's actually stored — never the raw
    # scrape.text itself — verified by asserting the mocked LLM was reached.
    mock_llm.return_value.complete.assert_called_once()
    upload_args = mock_storage.return_value.upload.call_args.args
    assert upload_args[1] == b"fake-bytes"
    assert upload_args[2] == "image/png"


def test_scrape_is_a_noop_when_brand_has_no_website(db_session) -> None:
    brand = _setup_brand(db_session, website=None)

    with patch(SCRAPE_PATCH_TARGET) as mock_scrape:
        research = run_website_scrape(db_session, brand)

    mock_scrape.assert_not_called()
    assert research.website_summary is None
    assert research.website_logo_url is None


def test_scrape_degrades_gracefully_when_provider_raises(db_session) -> None:
    brand = _setup_brand(db_session)

    with patch(SCRAPE_PATCH_TARGET) as mock_scrape:
        mock_scrape.return_value.scrape.side_effect = Exception("site unreachable")
        research = run_website_scrape(db_session, brand)

    assert research.website_summary is None
    assert research.website_logo_url is None


def test_summarization_falls_back_to_description_on_llm_failure(db_session) -> None:
    brand = _setup_brand(db_session)

    with (
        patch(SCRAPE_PATCH_TARGET) as mock_scrape,
        patch(LLM_PATCH_TARGET) as mock_llm,
        patch(STORAGE_PATCH_TARGET) as mock_storage,
    ):
        mock_scrape.return_value.scrape.return_value = _scrape_result()
        mock_llm.return_value.complete.side_effect = Exception("openrouter timed out")
        mock_storage.return_value.upload.return_value = "https://storage.test/scraped-logo.png"

        research = run_website_scrape(db_session, brand)

    assert research.website_summary == "We make widgets."


def test_logo_rehosting_failure_does_not_block_summary(db_session) -> None:
    brand = _setup_brand(db_session)

    with (
        patch(SCRAPE_PATCH_TARGET) as mock_scrape,
        patch(LLM_PATCH_TARGET) as mock_llm,
        patch(STORAGE_PATCH_TARGET) as mock_storage,
    ):
        mock_scrape.return_value.scrape.return_value = _scrape_result()
        mock_llm.return_value.complete.return_value = _llm_summary_response()
        mock_storage.return_value.upload.side_effect = Exception("storage unreachable")

        research = run_website_scrape(db_session, brand)

    assert research.website_summary == "Acme Widgets makes durable widgets for professional makers."
    assert research.website_logo_url is None


def test_scrape_upserts_on_rerun(db_session) -> None:
    brand = _setup_brand(db_session)

    with (
        patch(SCRAPE_PATCH_TARGET) as mock_scrape,
        patch(LLM_PATCH_TARGET) as mock_llm,
        patch(STORAGE_PATCH_TARGET) as mock_storage,
    ):
        mock_scrape.return_value.scrape.return_value = _scrape_result()
        mock_llm.return_value.complete.return_value = _llm_summary_response()
        mock_storage.return_value.upload.return_value = "https://storage.test/scraped-logo.png"

        run_website_scrape(db_session, brand)
        run_website_scrape(db_session, brand)

    rows = db_session.query(OnboardingResearch).filter(OnboardingResearch.brand_id == brand.id).all()
    assert len(rows) == 1


def test_explicit_url_overrides_brand_product_catalog(db_session) -> None:
    brand = _setup_brand(db_session, website="https://old.test")

    with (
        patch(SCRAPE_PATCH_TARGET) as mock_scrape,
        patch(LLM_PATCH_TARGET) as mock_llm,
        patch(STORAGE_PATCH_TARGET) as mock_storage,
    ):
        mock_scrape.return_value.scrape.return_value = _scrape_result()
        mock_llm.return_value.complete.return_value = _llm_summary_response()
        mock_storage.return_value.upload.return_value = "https://storage.test/scraped-logo.png"

        run_website_scrape(db_session, brand, url="https://new.test")

    mock_scrape.return_value.scrape.assert_called_once_with("https://new.test")
