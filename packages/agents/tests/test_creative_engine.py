"""Tests for the Issue #20 Creative Engine node.

Per the issue's acceptance criteria:
  1. Output is a structured brief (not free text) with format/angle/hook/
     CTA fields.
  2. Tone/format genuinely adapts per target platform — verified across at
     least 2 platforms by asserting on actual content differences, not
     just that two calls happened.
  3. An AgentRun row is logged with agent_type=creative.

Mirrors test_research_engine.py's structure: most cases exercised
directly against build_creative_node() (fast, no checkpointer needed),
with LLMProvider mocked through packages.integrations.registry
.get_llm_provider — never a direct vendor SDK call. The AgentRun-logging
criterion is exercised through the real pipeline (run_pipeline + a
Postgres-backed checkpointer), since that's the code that actually writes
AgentRun rows — the node itself just returns a dict for run_pipeline to
log.
"""

import json
import uuid
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
from packages.agents.pipeline.checkpointer import get_postgres_checkpointer
from packages.agents.pipeline.graph import run_pipeline
from packages.agents.pipeline.nodes.creative_engine import (
    REQUIRED_BRIEF_KEYS,
    CreativeEngineError,
    build_creative_node,
)
from packages.integrations.llm.base import LLMResponse

LLM_PATCH_TARGET = "packages.agents.pipeline.nodes.creative_engine.get_llm_provider"
SEARCH_PATCH_TARGET = "packages.agents.pipeline.nodes.research_engine.get_search_provider"
EMBED_PATCH_TARGET = "apps.api.services.brand_retrieval.get_embedding_provider"


def _setup_brand(db_session, industry: str | None = "Outdoor gear") -> Brand:
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


def _llm_response(payload: dict) -> LLMResponse:
    return LLMResponse(
        text=json.dumps(payload),
        model="openrouter/free",
        input_tokens=100,
        output_tokens=50,
    )


def _distinct_platform_payload() -> dict:
    """Genuinely different content per platform — not the same brief with
    the platform name swapped in."""
    return {
        "linkedin": {
            "format": "text_post",
            "angle": "thought_leadership",
            "hook": "Most brands get sustainability messaging backwards.",
            "cta": "What's your take? Share below.",
            "tone": "professional, authoritative",
        },
        "x": {
            "format": "short_thread",
            "angle": "hot_take",
            "hook": "unpopular opinion: your camping gear is overengineered",
            "cta": "reply if you agree (or don't)",
            "tone": "casual, punchy",
        },
    }


def _run_node(db_session, post: Post, research_brief: dict | None = None) -> dict:
    node = build_creative_node(db_session)
    return node(
        {
            "post_id": str(post.id),
            "completed_stages": [],
            "research_brief": research_brief or {},
        }
    )


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


# --- structured brief with format/angle/hook/CTA fields ---------------------


def test_creative_brief_is_structured_with_required_fields(db_session) -> None:
    brand = _setup_brand(db_session)
    post = _setup_post(db_session, brand=brand)
    research_brief = {
        "post_id": str(post.id),
        "brand_context": [],
        "platform_trends": {"linkedin": [], "x": []},
        "industry_trends": [],
        "timing_signal": {},
    }

    with patch(LLM_PATCH_TARGET) as mock_llm:
        mock_llm.return_value.complete.return_value = _llm_response(_distinct_platform_payload())
        result = _run_node(db_session, post, research_brief)

    brief = result["creative_brief"]
    assert isinstance(brief, dict)
    assert brief["post_id"] == str(post.id)
    assert set(brief["platforms"].keys()) == {"linkedin", "x"}
    for platform_brief in brief["platforms"].values():
        assert set(REQUIRED_BRIEF_KEYS) <= set(platform_brief.keys())
        for key in REQUIRED_BRIEF_KEYS:
            assert isinstance(platform_brief[key], str)
            assert platform_brief[key]  # not free-text-empty / not blank


def test_creative_engine_calls_llm_provider_only_through_interface(db_session) -> None:
    post = _setup_post(db_session)

    with patch(LLM_PATCH_TARGET) as mock_llm, patch("httpx.post") as mock_httpx_post:
        mock_llm.return_value.complete.return_value = _llm_response(_distinct_platform_payload())
        _run_node(db_session, post)

    mock_llm.return_value.complete.assert_called_once()
    mock_httpx_post.assert_not_called()


def test_creative_engine_reads_model_from_settings_not_hardcoded(db_session) -> None:
    post = _setup_post(db_session)

    with (
        patch(LLM_PATCH_TARGET) as mock_llm,
        patch(
            "packages.agents.pipeline.nodes.creative_engine.get_settings"
        ) as mock_settings,
    ):
        mock_settings.return_value.llm_default_model = "some/custom-model"
        mock_llm.return_value.complete.return_value = _llm_response(_distinct_platform_payload())
        _run_node(db_session, post)

    _, kwargs = mock_llm.return_value.complete.call_args
    assert kwargs["model"] == "some/custom-model"


# --- tone/format genuinely differs across at least 2 platforms --------------


def test_creative_brief_content_genuinely_differs_across_platforms(db_session) -> None:
    post = _setup_post(db_session)
    research_brief = {
        "platform_trends": {"linkedin": [], "x": []},
        "brand_context": [],
        "industry_trends": [],
        "timing_signal": {},
    }

    with patch(LLM_PATCH_TARGET) as mock_llm:
        mock_llm.return_value.complete.return_value = _llm_response(_distinct_platform_payload())
        result = _run_node(db_session, post, research_brief)

    platforms = result["creative_brief"]["platforms"]
    linkedin_brief = platforms["linkedin"]
    x_brief = platforms["x"]

    # Not just "two calls happened" — the actual content differs field by
    # field, proving this isn't the same brief with the platform name
    # swapped in.
    assert linkedin_brief["tone"] != x_brief["tone"]
    assert linkedin_brief["hook"] != x_brief["hook"]
    assert linkedin_brief["angle"] != x_brief["angle"]
    assert linkedin_brief["cta"] != x_brief["cta"]


def test_creative_brief_prompt_asks_for_distinct_platform_adaptation(db_session) -> None:
    """The prompt itself must instruct the LLM to adapt per platform (not
    just list platform names identically) — otherwise identical output
    across platforms would be an unsurprising, undetected failure mode."""
    post = _setup_post(db_session)
    research_brief = {"platform_trends": {"linkedin": [], "x": []}}

    with patch(LLM_PATCH_TARGET) as mock_llm:
        mock_llm.return_value.complete.return_value = _llm_response(_distinct_platform_payload())
        _run_node(db_session, post, research_brief)

    prompt = mock_llm.return_value.complete.call_args.kwargs["prompt"]
    assert "linkedin" in prompt
    assert "x" in prompt
    assert "distinct" in prompt.lower() or "adapted" in prompt.lower()


def test_fallback_briefs_still_differ_by_platform_on_llm_failure(db_session) -> None:
    """Degrade-on-failure contract: a broken/unconfigured LLM provider must
    not take the pipeline down, and the fallback still has to be usable —
    i.e. still platform-differentiated, not one generic brief copy-pasted
    for every platform."""
    post = _setup_post(db_session)
    research_brief = {"platform_trends": {"linkedin": [], "x": []}}

    with patch(LLM_PATCH_TARGET) as mock_llm:
        mock_llm.return_value.complete.side_effect = Exception("LLM provider unreachable")
        result = _run_node(db_session, post, research_brief)

    platforms = result["creative_brief"]["platforms"]
    assert set(platforms.keys()) == {"linkedin", "x"}
    for platform_brief in platforms.values():
        assert set(REQUIRED_BRIEF_KEYS) <= set(platform_brief.keys())
    assert platforms["linkedin"]["tone"] != platforms["x"]["tone"]


def test_creative_engine_degrades_gracefully_on_unparseable_llm_output(db_session) -> None:
    post = _setup_post(db_session)
    research_brief = {"platform_trends": {"linkedin": [], "x": []}}

    with patch(LLM_PATCH_TARGET) as mock_llm:
        mock_llm.return_value.complete.return_value = LLMResponse(
            text="not valid json at all",
            model="openrouter/free",
            input_tokens=1,
            output_tokens=1,
        )
        result = _run_node(db_session, post, research_brief)

    platforms = result["creative_brief"]["platforms"]
    assert set(platforms.keys()) == {"linkedin", "x"}


# --- platform resolution -----------------------------------------------


def test_creative_engine_uses_research_brief_platforms_when_present(db_session) -> None:
    post = _setup_post(db_session)
    research_brief = {"platform_trends": {"linkedin": []}}  # only linkedin

    with patch(LLM_PATCH_TARGET) as mock_llm:
        mock_llm.return_value.complete.return_value = _llm_response(
            {"linkedin": _distinct_platform_payload()["linkedin"]}
        )
        result = _run_node(db_session, post, research_brief)

    assert set(result["creative_brief"]["platforms"].keys()) == {"linkedin"}


def test_creative_engine_falls_back_to_calendar_event_platforms(db_session) -> None:
    """No research_brief platform_trends available (e.g. node invoked
    directly) — falls back to the same Post -> ContentCalendarEvent
    resolution research_engine.py uses."""
    from datetime import datetime, timezone

    brand = _setup_brand(db_session)
    event = ContentCalendarEvent(
        brand_id=brand.id,
        title="Launch post",
        target_platforms=["x"],
        desired_format="image",
        target_datetime=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    db_session.add(event)
    db_session.flush()
    post = _setup_post(db_session, brand=brand, calendar_event=event)

    with patch(LLM_PATCH_TARGET) as mock_llm:
        mock_llm.return_value.complete.return_value = _llm_response(
            {"x": _distinct_platform_payload()["x"]}
        )
        result = _run_node(db_session, post, research_brief={})

    assert set(result["creative_brief"]["platforms"].keys()) == {"x"}


# --- error handling -----------------------------------------------------


def test_build_creative_node_requires_a_db_session_to_actually_run() -> None:
    node = build_creative_node(None)
    with pytest.raises(RuntimeError):
        node({"post_id": "irrelevant", "completed_stages": [], "research_brief": {}})


def test_creative_node_raises_when_post_not_found(db_session) -> None:
    node = build_creative_node(db_session)
    with pytest.raises(CreativeEngineError):
        node({"post_id": str(uuid.uuid4()), "completed_stages": [], "research_brief": {}})


# --- completed_stages bookkeeping (same shape as the other node stubs) -----


def test_creative_node_appends_to_completed_stages(db_session) -> None:
    post = _setup_post(db_session)

    with patch(LLM_PATCH_TARGET) as mock_llm:
        mock_llm.return_value.complete.return_value = _llm_response(_distinct_platform_payload())
        node = build_creative_node(db_session)
        result = node(
            {
                "post_id": str(post.id),
                "completed_stages": ["research"],
                "research_brief": {"platform_trends": {"linkedin": [], "x": []}},
            }
        )

    assert result["completed_stages"] == ["research", "creative"]


# --- AgentRun logged with agent_type=creative, via the real pipeline -------


def test_pipeline_logs_agent_run_with_agent_type_creative(db_session, thread_cleanup) -> None:
    from datetime import datetime, timezone

    # Issues #108/#109/#110 grew SUPPORTED_PLATFORMS beyond ("linkedin",
    # "x") — pin target_platforms explicitly via a calendar event so
    # Research/Creative Engine's "no calendar event" -> "all
    # SUPPORTED_PLATFORMS" fallback doesn't pull in platforms this test's
    # LLM mock doesn't cover.
    brand = _setup_brand(db_session)
    event = ContentCalendarEvent(
        brand_id=brand.id,
        title="Test event",
        target_platforms=["linkedin", "x"],
        desired_format="text_post",
        target_datetime=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    db_session.add(event)
    db_session.flush()
    post = _setup_post(db_session, brand=brand, calendar_event=event)
    thread_cleanup.append(str(post.id))

    with (
        patch(SEARCH_PATCH_TARGET) as mock_search,
        patch(EMBED_PATCH_TARGET) as mock_embed,
        patch(LLM_PATCH_TARGET) as mock_llm,
    ):
        mock_search.return_value.search.return_value = []
        mock_embed.return_value.embed.return_value = [0.0] * 1536
        mock_llm.return_value.complete.return_value = _llm_response(_distinct_platform_payload())

        with get_postgres_checkpointer() as checkpointer:
            list(run_pipeline(db_session, post, checkpointer))

    run = (
        db_session.query(AgentRun)
        .filter(AgentRun.post_id == post.id, AgentRun.agent_type == AgentType.CREATIVE)
        .order_by(AgentRun.created_at.desc())
        .first()
    )
    assert run is not None
    assert run.output is not None

    brief = run.output["creative_brief"]
    assert brief["post_id"] == str(post.id)
    assert set(brief["platforms"].keys()) == {"linkedin", "x"}
    assert brief["platforms"]["linkedin"]["tone"] != brief["platforms"]["x"]["tone"]
