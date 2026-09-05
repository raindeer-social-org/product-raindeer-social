"""Research Engine — Issue #19, the first real (non-stub) stage in the
per-post pipeline graph built in #18 (packages/agents/pipeline/graph.py).

Gathers the raw material #20 (Creative Engine) needs to write an on-brand,
on-trend post:

  * Platform + industry trend research, via SearchProvider (#7) — called
    only through its interface (packages/integrations/search/base.py),
    never a direct Tavily import. Mirrors the degrade-gracefully-on-
    failure pattern already established in
    packages/agents/onboarding/research_step.py: a slow/broken search
    provider must never take the pipeline down with it.
  * The brand's actual voice/audience/positioning, via #16's pgvector
    retrieval helper (apps.api.services.brand_retrieval.
    get_relevant_brand_context) — reused as-is rather than re-querying
    Brand.brand_report's raw JSONB directly.

The output is a structured "research brief" dict, including a
`timing_signal` field: not full auto-scheduling logic (that is #28's job,
not this issue's), but the trend/timing material #28 will eventually read
— what topics are trending right now, which platforms were researched,
when this research ran, and the post's already-known target_datetime if
it was scheduled onto the content calendar ahead of time.

Node functions elsewhere in this graph take only `state` (see graph.py's
_make_stub_node) — none of the other seven stages need a database
session. Research is the first stage that does, to resolve
Post -> Brand (and, optionally, Post -> ContentCalendarEvent). So this
module exposes a *factory*, build_research_node(db), that closes over a
caller-supplied Session and returns the actual LangGraph node function.
graph.py's build_pipeline_graph() calls this factory for the "research"
stage only — the other stages, and the graph's overall wiring/interrupt
logic, are untouched.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from apps.api.models.brand import Brand
from apps.api.models.content_calendar_event import ContentCalendarEvent, SUPPORTED_PLATFORMS
from apps.api.models.post import Post
from apps.api.services.brand_retrieval import get_relevant_brand_context
from packages.integrations.registry import get_search_provider
from packages.integrations.search.base import SearchResult

logger = logging.getLogger(__name__)

MAX_RESULTS_PER_QUERY = 5
MAX_TRENDING_TOPICS = 5
BRAND_CONTEXT_TOP_K = 3


class ResearchEngineError(Exception):
    """Raised when the research node can't resolve the Post/Brand it was
    asked to research — a programming/data error (missing row), not a
    transient provider failure, so unlike search failures this is not
    swallowed."""


def _search_safely(query: str) -> list[SearchResult]:
    """Calls SearchProvider exclusively through its interface (never a
    direct Tavily import) — same degrade-on-failure contract as
    onboarding/research_step.py: a broken search provider must never take
    the pipeline down with it, just leave this query's results empty."""
    try:
        return get_search_provider().search(query, max_results=MAX_RESULTS_PER_QUERY)
    except Exception:
        logger.warning("Research Engine query failed: %r", query, exc_info=True)
        return []


def _serialize(results: list[SearchResult]) -> list[dict]:
    return [{"title": r.title, "url": r.url, "content": r.content} for r in results]


def _brand_context_safely(db: Session, brand_id: Any, query: str) -> list[dict]:
    """Same degrade-on-failure contract as _search_safely: a broken
    embedding provider (missing/invalid API key, network issue, etc.)
    must not take the whole Research Engine node — and therefore the
    whole pipeline run — down with it. #16's retrieval helper is still
    called exactly as built; this only adds a safety net around it."""
    try:
        return get_relevant_brand_context(db, brand_id, query=query, top_k=BRAND_CONTEXT_TOP_K)
    except Exception:
        logger.warning("Research Engine brand context retrieval failed", exc_info=True)
        return []


def _calendar_event_for(post: Post, db: Session) -> ContentCalendarEvent | None:
    if post.calendar_event_id is None:
        return None
    return db.get(ContentCalendarEvent, post.calendar_event_id)


def _platforms_for(post: Post, db: Session) -> list[str]:
    """Prefers the platforms this post is actually scheduled for (via its
    ContentCalendarEvent, if it has one) over researching every supported
    platform generically."""
    event = _calendar_event_for(post, db)
    if event is not None and event.target_platforms:
        return list(event.target_platforms)
    return list(SUPPORTED_PLATFORMS)


def _build_timing_signal(
    platforms: list[str],
    trend_results: list[SearchResult],
    target_datetime: datetime | None,
) -> dict[str, Any]:
    """The field #28 (auto-scheduling) will eventually consume. Not full
    scheduling logic — just the trend/timing material it needs: what
    topics are trending right now (a proxy for "this is a good moment to
    post about X"), which platforms were researched, when this research
    ran, and the post's already-known target_datetime, if any."""
    trending_topics: list[str] = []
    for result in trend_results:
        if result.title not in trending_topics:
            trending_topics.append(result.title)
        if len(trending_topics) >= MAX_TRENDING_TOPICS:
            break
    return {
        "researched_at": datetime.now(timezone.utc).isoformat(),
        "platforms": platforms,
        "trending_topics": trending_topics,
        "target_datetime": target_datetime.isoformat() if target_datetime else None,
    }


def _research_brief(db: Session, post: Post) -> dict[str, Any]:
    brand = db.get(Brand, post.brand_id)
    if brand is None:
        raise ResearchEngineError(f"Research Engine: no Brand found for post {post.id}")

    platforms = _platforms_for(post, db)
    industry = brand.industry or brand.name

    platform_trend_results = {
        platform: _search_safely(f"{platform} content trends for {industry} brands")
        for platform in platforms
    }
    industry_trend_results = _search_safely(f"{industry} industry trends")

    all_trend_results = [
        result for results in platform_trend_results.values() for result in results
    ] + industry_trend_results

    calendar_event = _calendar_event_for(post, db)
    brand_context = _brand_context_safely(
        db, brand.id, query=f"{brand.name} brand voice, audience, and positioning"
    )

    return {
        "post_id": str(post.id),
        "brand_context": brand_context,
        "platform_trends": {
            platform: _serialize(results) for platform, results in platform_trend_results.items()
        },
        "industry_trends": _serialize(industry_trend_results),
        "timing_signal": _build_timing_signal(
            platforms,
            all_trend_results,
            calendar_event.target_datetime if calendar_event else None,
        ),
    }


def run_standalone_research(db: Session, post: Post) -> dict[str, Any]:
    """Issue #126 — the Research workspace page's "Run new research"
    action. Runs exactly the same research brief the pipeline node above
    produces, but for a standalone Post created ad hoc (no calendar event,
    no downstream Creative/Generation stages) rather than one advancing
    through the full pipeline graph — so a brand can see fresh trend
    results without paying for the other four stages just to view them.

    A thin wrapper around _research_brief rather than a second
    implementation: same search/brand-context logic, same degrade-on-
    failure behavior, same output shape. The caller (apps/api/routers/
    research.py) is responsible for creating the ad hoc Post and logging
    the AgentRun row — this function only produces the brief, same
    division of responsibility build_research_node's node function has
    with run_pipeline's AgentRun-logging (see graph.py).
    """
    return _research_brief(db, post)


def build_research_node(db: Session | None):
    """Builds the real "research" stage node function, closing over `db`.
    Mirrors graph.py's _make_stub_node factory shape/conventions, but for
    the one stage (so far) that needs a database session to do real work.

    `db` is accepted as possibly None so build_pipeline_graph(checkpointer)
    — with no `db` argument — still works for callers that only inspect
    the compiled graph's structure (nodes/edges) without ever streaming or
    invoking it; the resulting node just isn't runnable, and raises
    clearly if it ever is.
    """

    def _node(state: dict) -> dict:
        if db is None:
            raise RuntimeError(
                "Research Engine node has no database session — "
                "build_pipeline_graph() must be called with db=<Session> "
                "to execute (not just inspect) the pipeline graph."
            )

        post = db.get(Post, uuid.UUID(state["post_id"]))
        if post is None:
            raise ResearchEngineError(
                f"Research Engine: no Post found for post_id={state['post_id']!r}"
            )

        brief = _research_brief(db, post)
        return {
            "completed_stages": [*state.get("completed_stages", []), "research"],
            "research_brief": brief,
        }

    _node.__name__ = "research_node"
    return _node
