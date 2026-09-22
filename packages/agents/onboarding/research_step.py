import logging
import uuid

from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.models.brand import Brand
from apps.api.models.onboarding_research import OnboardingResearch
from apps.api.models.onboarding_response import OnboardingResponse
from packages.integrations.registry import (
    get_llm_provider,
    get_search_provider,
    get_storage_provider,
    get_webscrape_provider,
)
from packages.integrations.search.base import SearchResult
from packages.integrations.webscrape.base import ScrapeResult

logger = logging.getLogger(__name__)

MAX_COMPETITORS = 3
MAX_RESULTS_PER_QUERY = 5
# Distilled summaries are meant to be a few sentences of concrete brand
# knowledge, not a second copy of the scraped page — this is a hard upper
# bound in case the LLM ignores the prompt's length guidance.
MAX_SUMMARY_CHARS = 1200


def _search_safely(query: str) -> list[SearchResult]:
    try:
        return get_search_provider().search(query, max_results=MAX_RESULTS_PER_QUERY)
    except Exception:
        # A slow/broken search provider must never take onboarding down
        # with it — log and continue with whatever queries did succeed
        # (possibly none), so #15 still has questionnaire-only data to
        # synthesize a brand_report from.
        logger.warning("Onboarding research query failed: %r", query, exc_info=True)
        return []


def _get_or_create_research(db: Session, brand_id: uuid.UUID) -> OnboardingResearch:
    research = db.query(OnboardingResearch).filter(OnboardingResearch.brand_id == brand_id).first()
    if research is None:
        research = OnboardingResearch(brand_id=brand_id)
        db.add(research)
        db.flush()
    return research


def _summarize_scrape(brand_name: str, scrape: ScrapeResult) -> str:
    """Distills the raw scraped page text into a few sentences of concrete
    brand knowledge via LLMProvider — the raw scrape.text is never itself
    the stored artifact (per Issue #152: "don't just directly store the
    scraped website, summarize it"). Falls back to the page's own meta
    description (still real signal, just not LLM-distilled) if the LLM
    call fails or the page had no usable text at all — never raises, same
    degrade-gracefully contract as _search_safely above."""
    if not scrape.text and not scrape.description:
        return ""
    prompt = f"""You are a brand researcher reading {brand_name}'s own website to
learn concrete, specific facts about the business — not to write marketing
copy. Respond with 2-4 sentences of plain prose, no markdown, no headers,
no bullet points.

## Page title
{scrape.title or "(none found)"}

## Page description
{scrape.description or "(none found)"}

## Visible page text (truncated)
{scrape.text[:4000] or "(none found)"}

## Task
Summarize what this business actually does, who it's for, and anything
distinctive it says about itself — concrete specifics (products, claims,
numbers, phrasing the brand itself uses) over generic marketing-speak.
If the page text doesn't have enough signal, say so plainly rather than
inventing detail. Respond with ONLY the 2-4 sentences — no preamble."""

    try:
        response = get_llm_provider().complete(
            prompt=prompt, model=get_settings().llm_default_model, temperature=0.3
        )
        summary = response.text.strip()
        return summary[:MAX_SUMMARY_CHARS] if summary else (scrape.description or "")
    except Exception:
        logger.warning("Onboarding website-scrape summarization failed", exc_info=True)
        return scrape.description or ""


def _rehost_logo(brand_id: uuid.UUID, scrape: ScrapeResult) -> str | None:
    """Re-uploads whatever logo/favicon bytes the scrape already fetched
    (for color extraction) through StorageProvider, so onboarding offers a
    durably-hosted URL rather than linking the brand's own site directly —
    a page can change or take its image down after a user has already
    accepted it as their logo. Never raises: a storage failure here just
    means no logo suggestion, not a broken scrape."""
    if not scrape.logo_bytes:
        return None
    try:
        content_type = scrape.logo_content_type or "image/png"
        extension = content_type.split("/")[-1].split(";")[0] or "png"
        path = f"onboarding/{brand_id}/scraped-logo/{uuid.uuid4().hex}.{extension}"
        return get_storage_provider().upload(path, scrape.logo_bytes, content_type)
    except Exception:
        logger.warning("Onboarding website-scrape logo re-hosting failed", exc_info=True)
        return None


def run_website_scrape(db: Session, brand: Brand, url: str | None = None) -> OnboardingResearch:
    """Issue #152 — the real counterpart to search_brand_overview's Tavily
    *search* above: actually fetches the brand's own site
    (WebScrapeProvider, resolved via
    packages.integrations.registry.get_webscrape_provider() — never a
    direct HTTP call here) and distills what it finds. `url` defaults to
    brand.product_catalog["website"] (the field the onboarding interview's
    "confirm your website" step already displays) when not given
    explicitly. Same "never take onboarding down with it" contract as
    every other function in this module: an unreachable/erroring site
    leaves OnboardingResearch's website_* fields as whatever they already
    were (None on a first run) rather than raising, and a caller with no
    website on file at all is a no-op, not an error.

    Upserts, same as run_onboarding_research — re-running the scrape for
    the same brand replaces the prior website_* fields rather than
    accumulating stale rows."""
    research = _get_or_create_research(db, brand.id)

    target_url = url or (brand.product_catalog or {}).get("website")
    if not target_url:
        return research

    try:
        scrape = get_webscrape_provider().scrape(target_url)
    except Exception:
        logger.warning("Onboarding website scrape failed for brand=%s url=%r", brand.id, target_url, exc_info=True)
        return research

    summary = _summarize_scrape(brand.name, scrape)
    if scrape.social_links:
        # Appended deterministically rather than fed into the LLM prompt —
        # this is a plain fact (a link either exists on the page or it
        # doesn't), not something worth risking the summarization call
        # inventing or dropping.
        platforms = ", ".join(sorted(scrape.social_links))
        social_note = f"Also links to {platforms} from its own site."
        summary = f"{summary} {social_note}".strip() if summary else social_note

    research.website_summary = summary
    research.website_logo_url = _rehost_logo(brand.id, scrape)
    research.website_colors = scrape.colors or None
    research.website_social_links = scrape.social_links or None
    db.flush()
    db.refresh(research)
    return research


def _serialize(results: list[SearchResult]) -> list[dict]:
    return [{"title": r.title, "url": r.url, "content": r.content} for r in results]


def search_brand_overview(brand_name: str) -> list[SearchResult]:
    """Public wrapper around the same safe-search path run_onboarding_research
    uses for "{brand} company overview" below. Added for Issue #123's Aarav
    onboarding interview, which previews real web-research signals for a
    brand (via a live progress stream) before the full questionnaire —
    and thus the full run_onboarding_research/run_agent chain, which
    requires onboarding to already be marked complete — can run. Kept as a
    thin named export rather than having callers reach for the
    underscore-prefixed helper directly."""
    return _search_safely(f"{brand_name} company overview")


def run_onboarding_research(
    db: Session, brand: Brand, onboarding_response: OnboardingResponse
) -> OnboardingResearch:
    """Calls SearchProvider exclusively through its interface (never a
    direct Tavily import) to build the structured web-research context
    #15's brand_report synthesis reads. Upserts — re-running onboarding
    research for the same brand replaces the prior results rather than
    accumulating stale rows."""
    overview = _serialize(_search_safely(f"{brand.name} company overview"))

    competitors = (onboarding_response.competitors or [])[:MAX_COMPETITORS]
    competitor_positioning = {
        competitor: _serialize(_search_safely(f"{brand.name} vs {competitor}"))
        for competitor in competitors
    }

    research = _get_or_create_research(db, brand.id)

    research.brand_overview = overview
    research.competitor_positioning = competitor_positioning
    db.flush()
    db.refresh(research)
    return research
