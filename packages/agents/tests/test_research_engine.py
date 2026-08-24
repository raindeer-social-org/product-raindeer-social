"""Tests for the Issue #19 Research Engine node.

Per the issue's acceptance criteria:
  1. The node calls SearchProvider only through its interface — never a
     direct HTTP call or vendor SDK.
  2. The output includes a timing/trend signal usable by #28 (auto-
     scheduling), not just topic research.
  3. An AgentRun row is logged with agent_type=research.

Most of these are exercised directly against build_research_node() (fast,
no checkpointer needed — mirrors how
packages/agents/onboarding/research_step.py's tests call
run_onboarding_research() directly). The AgentRun-logging criterion is
exercised through the real pipeline (run_pipeline + a Postgres-backed
checkpointer, like packages/agents/tests/test_pipeline_graph.py), since
that's the code that actually writes AgentRun rows — the node itself just
returns a dict for run_pipeline to log.
"""

import hashlib
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from apps.api.models import (
    AgentRun,
    AgentType,
    Brand,
    ContentCalendarEvent,
    Organization,
    Post,
)
from packages.agents.onboarding.embedding import embed_brand_report
from packages.agents.pipeline.checkpointer import get_postgres_checkpointer
from packages.agents.pipeline.graph import run_pipeline
from packages.agents.pipeline.nodes.research_engine import (
    ResearchEngineError,
    build_research_node,
)
from packages.integrations.search.base import SearchResult

SEARCH_PATCH_TARGET = "packages.agents.pipeline.nodes.research_engine.get_search_provider"
EMBED_PATCH_TARGET = "apps.api.services.brand_retrieval.get_embedding_provider"


def _setup_brand(db_session, industry: str | None = None) -> Brand:
    org = Organization(name="Acme Agency")
    db_session.add(org)
    db_session.flush()

    brand = Brand(organization_id=org.id, name="Acme Widgets", industry=industry)
    db_session.add(brand)
    db_session.flush()
    return brand


def _setup_post(
    db_session, brand: Brand | None = None, calendar_event: ContentCalendarEvent | None = None
) -> Post:
    if brand is None:
        brand = _setup_brand(db_session)
    post = Post(
        brand_id=brand.id,
        calendar_event_id=calendar_event.id if calendar_event else None,
    )
    db_session.add(post)
    db_session.flush()
    return post


def _fake_embed(text: str) -> list[float]:
    vec = [0.0] * 1536
    idx = int(hashlib.sha256(text.encode()).hexdigest(), 16) % 1536
    vec[idx] = 1.0
    return vec


def _run_node(db_session, post: Post) -> dict:
    node = build_research_node(db_session)
    return node({"post_id": str(post.id), "completed_stages": []})


@pytest.fixture()
def thread_cleanup():
    """Same teardown as test_pipeline_graph.py's fixture — pipeline
    checkpoint rows live in Postgres on a connection separate from
    db_session's rolled-back transaction, so they need explicit cleanup."""
    thread_ids: list[str] = []
    yield thread_ids
    if not thread_ids:
        return
    with get_postgres_checkpointer() as checkpointer:
        for thread_id in thread_ids:
            checkpointer.delete_thread(thread_id)


# --- SearchProvider used only through its interface -------------------------


def test_research_node_calls_search_provider_only_through_interface(db_session) -> None:
    post = _setup_post(db_session)

    with patch(SEARCH_PATCH_TARGET) as mock_search, patch(EMBED_PATCH_TARGET) as mock_embed:
        mock_search.return_value.search.return_value = []
        mock_embed.return_value.embed.return_value = _fake_embed("query")

        _run_node(db_session, post)

    mock_search.assert_called()
    mock_search.return_value.search.assert_called()


def test_research_node_never_makes_a_direct_http_call(db_session) -> None:
    """No direct HTTP/vendor SDK usage: TavilyProvider is the only file
    allowed to call httpx — the node must go through get_search_provider()
    exclusively, never touch httpx (or any vendor SDK) itself."""
    post = _setup_post(db_session)

    with (
        patch(SEARCH_PATCH_TARGET) as mock_search,
        patch(EMBED_PATCH_TARGET) as mock_embed,
        patch("httpx.post") as mock_httpx_post,
    ):
        mock_search.return_value.search.return_value = []
        mock_embed.return_value.embed.return_value = _fake_embed("query")

        _run_node(db_session, post)

    mock_httpx_post.assert_not_called()


def test_research_node_degrades_gracefully_on_search_provider_failure(db_session) -> None:
    post = _setup_post(db_session)

    with patch(SEARCH_PATCH_TARGET) as mock_search, patch(EMBED_PATCH_TARGET) as mock_embed:
        mock_search.return_value.search.side_effect = Exception("Tavily timed out")
        mock_embed.return_value.embed.return_value = _fake_embed("query")

        result = _run_node(db_session, post)

    brief = result["research_brief"]
    assert brief["industry_trends"] == []
    assert all(results == [] for results in brief["platform_trends"].values())
    assert brief["timing_signal"]["trending_topics"] == []


# --- timing/trend signal ------------------------------------------------


def test_research_brief_includes_timing_trend_signal(db_session) -> None:
    brand = _setup_brand(db_session, industry="Outdoor gear")
    post = _setup_post(db_session, brand=brand)

    trend_results = [
        SearchResult(
            title="Trending: sustainable camping gear",
            url="https://x.test/a",
            content="...",
        )
    ]

    with patch(SEARCH_PATCH_TARGET) as mock_search, patch(EMBED_PATCH_TARGET) as mock_embed:
        mock_search.return_value.search.return_value = trend_results
        mock_embed.return_value.embed.return_value = _fake_embed("query")

        result = _run_node(db_session, post)

    brief = result["research_brief"]
    assert "timing_signal" in brief
    signal = brief["timing_signal"]
    assert set(signal.keys()) == {"researched_at", "platforms", "trending_topics", "target_datetime"}
    assert signal["platforms"] == ["linkedin", "x"]  # SUPPORTED_PLATFORMS fallback
    assert "Trending: sustainable camping gear" in signal["trending_topics"]
    assert signal["target_datetime"] is None
    # researched_at is a real, parseable ISO-8601 timestamp, not a placeholder.
    datetime.fromisoformat(signal["researched_at"])


def test_timing_signal_uses_calendar_event_platforms_and_target_datetime(db_session) -> None:
    brand = _setup_brand(db_session)
    target_dt = datetime(2026, 9, 1, 14, 0, tzinfo=timezone.utc)
    event = ContentCalendarEvent(
        brand_id=brand.id,
        title="Launch post",
        target_platforms=["linkedin"],
        desired_format="image",
        target_datetime=target_dt,
    )
    db_session.add(event)
    db_session.flush()
    post = _setup_post(db_session, brand=brand, calendar_event=event)

    with patch(SEARCH_PATCH_TARGET) as mock_search, patch(EMBED_PATCH_TARGET) as mock_embed:
        mock_search.return_value.search.return_value = []
        mock_embed.return_value.embed.return_value = _fake_embed("query")

        result = _run_node(db_session, post)

    signal = result["research_brief"]["timing_signal"]
    assert signal["platforms"] == ["linkedin"]
    assert signal["target_datetime"] == target_dt.isoformat()
    # platform_trends is keyed by the scheduled platform only, not every
    # supported platform generically.
    assert set(result["research_brief"]["platform_trends"].keys()) == {"linkedin"}


# --- brand context via #16's retrieval helper (reused, not reinvented) -----


def test_research_brief_reuses_brand_context_retrieval_helper(db_session) -> None:
    brand = _setup_brand(db_session)
    brand.brand_report = {"audience": "Eco-conscious millennials"}
    db_session.flush()

    with patch("packages.agents.onboarding.embedding.get_embedding_provider") as mock_embed_onboard:
        mock_embed_onboard.return_value.embed.side_effect = _fake_embed
        embed_brand_report(db_session, brand)

    post = _setup_post(db_session, brand=brand)

    with patch(SEARCH_PATCH_TARGET) as mock_search, patch(EMBED_PATCH_TARGET) as mock_embed:
        mock_search.return_value.search.return_value = []
        mock_embed.return_value.embed.side_effect = _fake_embed

        result = _run_node(db_session, post)

    assert result["research_brief"]["brand_context"] == [
        {"section": "audience", "content": "Eco-conscious millennials"}
    ]


def test_research_node_degrades_gracefully_on_brand_context_retrieval_failure(db_session) -> None:
    """A broken embedding provider (e.g. no API key configured) must not
    take the whole node down — mirrors the search-provider degrade path."""
    post = _setup_post(db_session)

    with patch(SEARCH_PATCH_TARGET) as mock_search, patch(EMBED_PATCH_TARGET) as mock_embed:
        mock_search.return_value.search.return_value = []
        mock_embed.return_value.embed.side_effect = Exception("embeddings API unreachable")

        result = _run_node(db_session, post)

    assert result["research_brief"]["brand_context"] == []


def test_research_brief_brand_context_empty_when_no_brand_report(db_session) -> None:
    post = _setup_post(db_session)  # brand has no brand_report / no chunks

    with patch(SEARCH_PATCH_TARGET) as mock_search, patch(EMBED_PATCH_TARGET) as mock_embed:
        mock_search.return_value.search.return_value = []
        mock_embed.return_value.embed.return_value = _fake_embed("query")

        result = _run_node(db_session, post)

    assert result["research_brief"]["brand_context"] == []


# --- error handling -----------------------------------------------------


def test_build_research_node_requires_a_db_session_to_actually_run() -> None:
    node = build_research_node(None)
    with pytest.raises(RuntimeError):
        node({"post_id": "irrelevant", "completed_stages": []})


def test_research_node_raises_when_post_not_found(db_session) -> None:
    node = build_research_node(db_session)
    with pytest.raises(ResearchEngineError):
        node({"post_id": str(uuid.uuid4()), "completed_stages": []})


# --- completed_stages bookkeeping (same shape as the other node stubs) -----


def test_research_node_appends_to_completed_stages(db_session) -> None:
    post = _setup_post(db_session)

    with patch(SEARCH_PATCH_TARGET) as mock_search, patch(EMBED_PATCH_TARGET) as mock_embed:
        mock_search.return_value.search.return_value = []
        mock_embed.return_value.embed.return_value = _fake_embed("query")

        node = build_research_node(db_session)
        result = node({"post_id": str(post.id), "completed_stages": ["upstream_stage"]})

    assert result["completed_stages"] == ["upstream_stage", "research"]


# --- AgentRun logged with agent_type=research, via the real pipeline -------


def test_pipeline_logs_agent_run_with_agent_type_research(db_session, thread_cleanup) -> None:
    post = _setup_post(db_session)
    thread_cleanup.append(str(post.id))

    trend_results = [SearchResult(title="AI content trends 2026", url="https://x.test/a", content="...")]

    with patch(SEARCH_PATCH_TARGET) as mock_search, patch(EMBED_PATCH_TARGET) as mock_embed:
        mock_search.return_value.search.return_value = trend_results
        mock_embed.return_value.embed.return_value = _fake_embed("query")

        with get_postgres_checkpointer() as checkpointer:
            list(run_pipeline(db_session, post, checkpointer))

    run = (
        db_session.query(AgentRun)
        .filter(AgentRun.post_id == post.id, AgentRun.agent_type == AgentType.RESEARCH)
        .order_by(AgentRun.created_at.desc())
        .first()
    )
    assert run is not None
    assert run.output is not None

    brief = run.output["research_brief"]
    assert brief["post_id"] == str(post.id)
    assert "timing_signal" in brief
    assert brief["timing_signal"]["trending_topics"] == ["AI content trends 2026"]
