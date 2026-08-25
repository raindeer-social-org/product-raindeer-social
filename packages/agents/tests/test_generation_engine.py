"""Tests for the Issue #21 Generation Engine node.

Per the issue's acceptance criteria:
  1. Copy generation uses LLMProvider exclusively — no direct OpenAI/
     OpenRouter SDK/httpx calls.
  2. Output is written to Post.body_text, with version history preserved
     (a second generation call must not overwrite/lose the first
     version — PostVersion keeps both).
  3. The image/video generation hook is actually invoked (even though
     it's a stub) when a platform's brief calls for image/video/carousel,
     and NOT invoked for a plain text format.
  4. An AgentRun row is logged with agent_type=generation, including
     token/cost fields.

Mirrors test_creative_engine.py's structure: most cases exercised
directly against build_generation_node() (fast, no checkpointer needed),
with LLMProvider mocked through
packages.agents.pipeline.nodes.generation_engine.get_llm_provider — never
a direct vendor SDK call. The AgentRun-logging criterion is exercised
through the real pipeline (run_pipeline + a Postgres-backed
checkpointer), since that's the code that actually writes AgentRun rows.
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
    PostVersion,
)
from packages.agents.pipeline.checkpointer import get_postgres_checkpointer
from packages.agents.pipeline.graph import run_pipeline
from packages.agents.pipeline.nodes.generation_engine import (
    GenerationEngineError,
    build_generation_node,
)
from packages.integrations.llm.base import LLMResponse

LLM_PATCH_TARGET = "packages.agents.pipeline.nodes.generation_engine.get_llm_provider"
MEDIA_PATCH_TARGET = "packages.agents.pipeline.nodes.generation_engine.generate_media_stub"
SEARCH_PATCH_TARGET = "packages.agents.pipeline.nodes.research_engine.get_search_provider"
EMBED_PATCH_TARGET = "apps.api.services.brand_retrieval.get_embedding_provider"
CREATIVE_LLM_PATCH_TARGET = "packages.agents.pipeline.nodes.creative_engine.get_llm_provider"


def _setup_brand(db_session) -> Brand:
    org = Organization(name="Acme Agency")
    db_session.add(org)
    db_session.flush()

    brand = Brand(organization_id=org.id, name="Acme Widgets", industry="Outdoor gear")
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
        input_tokens=120,
        output_tokens=80,
    )


def _creative_brief(*, linkedin_format: str = "text_post", x_format: str = "short_thread") -> dict:
    return {
        "platforms": {
            "linkedin": {
                "format": linkedin_format,
                "angle": "thought_leadership",
                "hook": "Most brands get sustainability messaging backwards.",
                "cta": "What's your take? Share below.",
                "tone": "professional, authoritative",
            },
            "x": {
                "format": x_format,
                "angle": "hot_take",
                "hook": "unpopular opinion: your camping gear is overengineered",
                "cta": "reply if you agree (or don't)",
                "tone": "casual, punchy",
            },
        }
    }


def _copy_payload() -> dict:
    return {
        "linkedin": "Most brands get sustainability messaging backwards. Here's why...\n\nWhat's your take? Share below.",
        "x": "unpopular opinion: your camping gear is overengineered\n\nreply if you agree (or don't)",
    }


def _run_node(db_session, post: Post, creative_brief: dict | None = None) -> dict:
    node = build_generation_node(db_session)
    return node(
        {
            "post_id": str(post.id),
            "completed_stages": [],
            "creative_brief": creative_brief if creative_brief is not None else {},
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


# --- LLMProvider used exclusively, never a direct SDK/httpx call -----------


def test_generation_engine_calls_llm_provider_only_through_interface(db_session) -> None:
    post = _setup_post(db_session)

    with patch(LLM_PATCH_TARGET) as mock_llm, patch("httpx.post") as mock_httpx_post:
        mock_llm.return_value.complete.return_value = _llm_response(_copy_payload())
        _run_node(db_session, post, _creative_brief())

    mock_llm.return_value.complete.assert_called_once()
    mock_httpx_post.assert_not_called()


def test_generation_engine_reads_model_from_settings_not_hardcoded(db_session) -> None:
    post = _setup_post(db_session)

    with (
        patch(LLM_PATCH_TARGET) as mock_llm,
        patch(
            "packages.agents.pipeline.nodes.generation_engine.get_settings"
        ) as mock_settings,
    ):
        mock_settings.return_value.llm_default_model = "some/custom-model"
        mock_llm.return_value.complete.return_value = _llm_response(_copy_payload())
        _run_node(db_session, post, _creative_brief())

    _, kwargs = mock_llm.return_value.complete.call_args
    assert kwargs["model"] == "some/custom-model"


# --- Post.body_text written, version history preserved ---------------------


def test_generation_writes_post_body_text(db_session) -> None:
    post = _setup_post(db_session)

    with patch(LLM_PATCH_TARGET) as mock_llm:
        mock_llm.return_value.complete.return_value = _llm_response(_copy_payload())
        result = _run_node(db_session, post, _creative_brief())

    db_session.refresh(post)
    assert post.body_text == _copy_payload()
    assert result["generation_output"]["platforms"]["linkedin"]["body_text"] == _copy_payload()["linkedin"]
    assert result["generation_output"]["platforms"]["x"]["body_text"] == _copy_payload()["x"]


def test_generation_creates_a_post_version_row(db_session) -> None:
    post = _setup_post(db_session)

    with patch(LLM_PATCH_TARGET) as mock_llm:
        mock_llm.return_value.complete.return_value = _llm_response(_copy_payload())
        _run_node(db_session, post, _creative_brief())

    versions = db_session.query(PostVersion).filter(PostVersion.post_id == post.id).all()
    assert len(versions) == 1
    assert versions[0].body_text == _copy_payload()
    assert versions[0].model == "openrouter/free"
    assert versions[0].tokens == 200
    assert versions[0].cost is not None


def test_second_generation_preserves_first_version_instead_of_losing_it(db_session) -> None:
    post = _setup_post(db_session)

    first_payload = _copy_payload()
    second_payload = {
        "linkedin": "A completely different second draft for linkedin.",
        "x": "A completely different second draft for x.",
    }

    with patch(LLM_PATCH_TARGET) as mock_llm:
        mock_llm.return_value.complete.return_value = _llm_response(first_payload)
        _run_node(db_session, post, _creative_brief())

        mock_llm.return_value.complete.return_value = _llm_response(second_payload)
        _run_node(db_session, post, _creative_brief())

    db_session.refresh(post)
    # Post.body_text reflects the latest generation only.
    assert post.body_text == second_payload

    # But both versions still exist in history, oldest first.
    versions = (
        db_session.query(PostVersion)
        .filter(PostVersion.post_id == post.id)
        .order_by(PostVersion.created_at.asc())
        .all()
    )
    assert len(versions) == 2
    assert versions[0].body_text == first_payload
    assert versions[1].body_text == second_payload


# --- image/video generation hook --------------------------------------------


def test_media_hook_invoked_for_image_format(db_session) -> None:
    post = _setup_post(db_session)
    brief = _creative_brief(linkedin_format="image", x_format="short_thread")

    with patch(LLM_PATCH_TARGET) as mock_llm, patch(MEDIA_PATCH_TARGET) as mock_media:
        mock_llm.return_value.complete.return_value = _llm_response(_copy_payload())
        mock_media.return_value = {"status": "stubbed"}
        result = _run_node(db_session, post, brief)

    mock_media.assert_called_once()
    args, _ = mock_media.call_args
    assert args[1] == "linkedin"
    assert result["generation_output"]["platforms"]["linkedin"]["media"] == {"status": "stubbed"}
    # x stayed plain text — no media call for it.
    assert result["generation_output"]["platforms"]["x"]["media"] is None


def test_media_hook_invoked_for_video_and_carousel_formats(db_session) -> None:
    post = _setup_post(db_session)
    brief = _creative_brief(linkedin_format="short_video", x_format="carousel")

    with patch(LLM_PATCH_TARGET) as mock_llm, patch(MEDIA_PATCH_TARGET) as mock_media:
        mock_llm.return_value.complete.return_value = _llm_response(_copy_payload())
        mock_media.return_value = {"status": "stubbed"}
        _run_node(db_session, post, brief)

    assert mock_media.call_count == 2
    called_platforms = {call.args[1] for call in mock_media.call_args_list}
    assert called_platforms == {"linkedin", "x"}


def test_media_hook_not_invoked_for_plain_text_formats(db_session) -> None:
    post = _setup_post(db_session)
    brief = _creative_brief(linkedin_format="text_post", x_format="short_thread")

    with patch(LLM_PATCH_TARGET) as mock_llm, patch(MEDIA_PATCH_TARGET) as mock_media:
        mock_llm.return_value.complete.return_value = _llm_response(_copy_payload())
        result = _run_node(db_session, post, brief)

    mock_media.assert_not_called()
    assert result["generation_output"]["platforms"]["linkedin"]["media"] is None
    assert result["generation_output"]["platforms"]["x"]["media"] is None


# --- degrade-on-failure ------------------------------------------------


def test_generation_falls_back_to_hook_and_cta_on_llm_failure(db_session) -> None:
    post = _setup_post(db_session)
    brief = _creative_brief()

    with patch(LLM_PATCH_TARGET) as mock_llm:
        mock_llm.return_value.complete.side_effect = Exception("LLM provider unreachable")
        result = _run_node(db_session, post, brief)

    platforms = result["generation_output"]["platforms"]
    assert "Most brands get sustainability messaging backwards." in platforms["linkedin"]["body_text"]
    assert "What's your take? Share below." in platforms["linkedin"]["body_text"]
    db_session.refresh(post)
    assert post.body_text is not None


def test_generation_degrades_gracefully_on_unparseable_llm_output(db_session) -> None:
    post = _setup_post(db_session)
    brief = _creative_brief()

    with patch(LLM_PATCH_TARGET) as mock_llm:
        mock_llm.return_value.complete.return_value = LLMResponse(
            text="not valid json at all",
            model="openrouter/free",
            input_tokens=1,
            output_tokens=1,
        )
        result = _run_node(db_session, post, brief)

    platforms = result["generation_output"]["platforms"]
    assert set(platforms.keys()) == {"linkedin", "x"}


# --- error handling -----------------------------------------------------


def test_build_generation_node_requires_a_db_session_to_actually_run() -> None:
    node = build_generation_node(None)
    with pytest.raises(RuntimeError):
        node({"post_id": "irrelevant", "completed_stages": [], "creative_brief": {}})


def test_generation_node_raises_when_post_not_found(db_session) -> None:
    node = build_generation_node(db_session)
    with pytest.raises(GenerationEngineError):
        node({"post_id": str(uuid.uuid4()), "completed_stages": [], "creative_brief": {}})


# --- completed_stages bookkeeping (same shape as the other node stubs) -----


def test_generation_node_appends_to_completed_stages(db_session) -> None:
    post = _setup_post(db_session)

    with patch(LLM_PATCH_TARGET) as mock_llm:
        mock_llm.return_value.complete.return_value = _llm_response(_copy_payload())
        node = build_generation_node(db_session)
        result = node(
            {
                "post_id": str(post.id),
                "completed_stages": ["research", "creative"],
                "creative_brief": _creative_brief(),
            }
        )

    assert result["completed_stages"] == ["research", "creative", "generation"]


# --- AgentRun logged with agent_type=generation, including token/cost ------


def test_pipeline_logs_agent_run_with_agent_type_generation_including_token_and_cost(
    db_session, thread_cleanup
) -> None:
    post = _setup_post(db_session)
    thread_cleanup.append(str(post.id))

    with (
        patch(SEARCH_PATCH_TARGET) as mock_search,
        patch(EMBED_PATCH_TARGET) as mock_embed,
        patch(CREATIVE_LLM_PATCH_TARGET) as mock_creative_llm,
        patch(LLM_PATCH_TARGET) as mock_generation_llm,
    ):
        mock_search.return_value.search.return_value = []
        mock_embed.return_value.embed.return_value = [0.0] * 1536
        mock_creative_llm.return_value.complete.return_value = _llm_response(
            {
                "linkedin": _creative_brief()["platforms"]["linkedin"],
                "x": _creative_brief()["platforms"]["x"],
            }
        )
        mock_generation_llm.return_value.complete.return_value = _llm_response(_copy_payload())

        with get_postgres_checkpointer() as checkpointer:
            list(run_pipeline(db_session, post, checkpointer))

    run = (
        db_session.query(AgentRun)
        .filter(AgentRun.post_id == post.id, AgentRun.agent_type == AgentType.GENERATION)
        .order_by(AgentRun.created_at.desc())
        .first()
    )
    assert run is not None
    assert run.output is not None
    assert run.model == "openrouter/free"
    assert run.tokens == 200
    assert run.cost is not None
    assert run.cost > 0

    db_session.refresh(post)
    assert post.body_text == _copy_payload()
