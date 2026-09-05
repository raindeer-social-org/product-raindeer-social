import logging

from sqlalchemy.orm import Session

from apps.api.models.brand import Brand
from apps.api.models.onboarding_research import OnboardingResearch
from apps.api.models.onboarding_response import OnboardingResponse
from packages.integrations.registry import get_search_provider
from packages.integrations.search.base import SearchResult

logger = logging.getLogger(__name__)

MAX_COMPETITORS = 3
MAX_RESULTS_PER_QUERY = 5


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

    research = (
        db.query(OnboardingResearch).filter(OnboardingResearch.brand_id == brand.id).first()
    )
    if research is None:
        research = OnboardingResearch(brand_id=brand.id)
        db.add(research)

    research.brand_overview = overview
    research.competitor_positioning = competitor_positioning
    db.flush()
    db.refresh(research)
    return research
