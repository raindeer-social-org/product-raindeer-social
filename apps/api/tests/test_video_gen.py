"""Tests for Issue #23's video/carousel-generation adapter.

Per the issue's acceptance criteria:
  1. RunwayProvider implements VideoProvider, and is called only through
     that interface — generation_engine.py never imports Runway's SDK/URL
     directly (only packages/integrations/video_gen/runway_provider.py
     may).
  2. A generated video/carousel is stored via the storage adapter (#11)
     and referenced on Post.media.
  3. A video-gen (or storage) failure is caught, logged (to
     integration_calls, via the same track_integration_call every other
     adapter uses), and degrades gracefully — it must not crash
     run_pipeline.

Structured in three parts, mirroring test_storage.py / test_integrations_
llm.py / test_generation_engine.py's conventions:
  * RunwayProvider unit tests — httpx mocked, nothing else.
  * registry.get_video_provider() tests — same shape as
    test_integrations_registry.py's other provider-selection tests.
  * generation_engine.py integration tests — exercised directly against
    build_generation_node() (fast, no checkpointer), with
    get_video_provider/get_storage_provider mocked through
    packages.agents.pipeline.nodes.generation_engine's imports (never a
    direct vendor SDK/httpx call), plus one full run_pipeline() test
    proving a video-gen failure doesn't crash the pipeline run.
"""

import pathlib
import uuid
from unittest.mock import MagicMock, patch

import pytest

from apps.api.config import get_settings
from apps.api.models import (
    AgentRun,
    AgentType,
    Brand,
    IntegrationCall,
    Organization,
    Post,
)
from packages.agents.pipeline.checkpointer import get_postgres_checkpointer
from packages.agents.pipeline.graph import run_pipeline
from packages.agents.pipeline.nodes.generation_engine import (
    build_generation_node,
    generate_media_stub,
)
from packages.integrations.llm.base import LLMResponse
from packages.integrations.registry import get_video_provider
from packages.integrations.video_gen.base import VideoProvider, VideoResult
from packages.integrations.video_gen.runway_provider import RunwayProvider

LLM_PATCH_TARGET = "packages.agents.pipeline.nodes.generation_engine.get_llm_provider"
VIDEO_PATCH_TARGET = "packages.agents.pipeline.nodes.generation_engine.get_video_provider"
STORAGE_PATCH_TARGET = "packages.agents.pipeline.nodes.generation_engine.get_storage_provider"
CREATIVE_LLM_PATCH_TARGET = "packages.agents.pipeline.nodes.creative_engine.get_llm_provider"
SEARCH_PATCH_TARGET = "packages.agents.pipeline.nodes.research_engine.get_search_provider"
EMBED_PATCH_TARGET = "apps.api.services.brand_retrieval.get_embedding_provider"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _provider(**kwargs) -> RunwayProvider:
    return RunwayProvider(api_key="test-key", **kwargs)


def _create_task_response(task_id: str = "task-123") -> MagicMock:
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"id": task_id, "status": "PENDING"}
    return response


def _poll_response(status: str, output: list[str] | None = None, failure: str | None = None) -> MagicMock:
    response = MagicMock()
    response.raise_for_status.return_value = None
    data = {"status": status}
    if output is not None:
        data["output"] = output
    if failure is not None:
        data["failure"] = failure
    response.json.return_value = data
    return response


def _asset_response(content: bytes = b"fake-video-bytes", content_type: str = "video/mp4") -> MagicMock:
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.content = content
    response.headers = {"content-type": content_type}
    return response


def _setup_brand(db_session) -> Brand:
    org = Organization(name="Acme Agency")
    db_session.add(org)
    db_session.flush()

    brand = Brand(organization_id=org.id, name="Acme Widgets", industry="Outdoor gear")
    db_session.add(brand)
    db_session.flush()
    return brand


def _setup_post(db_session) -> Post:
    brand = _setup_brand(db_session)
    post = Post(brand_id=brand.id)
    db_session.add(post)
    db_session.flush()
    return post


def _llm_response(payload: dict) -> LLMResponse:
    import json

    return LLMResponse(
        text=json.dumps(payload),
        model="openrouter/free",
        input_tokens=120,
        output_tokens=80,
    )


def _creative_brief(*, linkedin_format: str = "short_video", x_format: str = "text_post") -> dict:
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


def _run_node(db_session, post: Post, creative_brief: dict) -> dict:
    node = build_generation_node(db_session)
    return node(
        {
            "post_id": str(post.id),
            "completed_stages": [],
            "creative_brief": creative_brief,
        }
    )


@pytest.fixture()
def thread_cleanup():
    thread_ids: list[str] = []
    yield thread_ids
    if not thread_ids:
        return
    with get_postgres_checkpointer() as checkpointer:
        for thread_id in thread_ids:
            checkpointer.delete_thread(thread_id)


# ---------------------------------------------------------------------------
# RunwayProvider implements VideoProvider, called only through httpx (no
# vendor SDK) -- and only from this adapter file.
# ---------------------------------------------------------------------------


def test_runway_provider_implements_video_provider_interface() -> None:
    assert isinstance(_provider(), VideoProvider)


def test_runway_base_url_referenced_only_in_provider_file() -> None:
    """Nothing outside runway_provider.py should know Runway's API host —
    generation_engine.py and everything else must go through
    VideoProvider/get_video_provider() only."""
    repo_root = pathlib.Path(__file__).resolve().parents[3]
    offenders = []
    for search_dir in ("packages", "apps"):
        for path in (repo_root / search_dir).rglob("*.py"):
            if path.name in {"runway_provider.py", "test_video_gen.py"}:
                continue
            text = path.read_text(errors="ignore")
            if "runwayml.com" in text:
                offenders.append(str(path))
    assert offenders == []


def test_generate_submits_polls_and_downloads_via_httpx_only(db_session) -> None:
    responses = [
        _create_task_response("task-123"),  # POST create
    ]
    get_responses = [
        _poll_response("PENDING"),
        _poll_response("SUCCEEDED", output=["https://runway.example/output.mp4"]),
        _asset_response(),
    ]

    with (
        patch("httpx.post", side_effect=responses) as mock_post,
        patch("httpx.get", side_effect=get_responses) as mock_get,
        patch("packages.integrations.video_gen.runway_provider.time.sleep") as mock_sleep,
    ):
        result = _provider(poll_interval=0.01).generate("a short product demo video")

    assert isinstance(result, VideoResult)
    assert result.url == "https://runway.example/output.mp4"
    assert result.content == b"fake-video-bytes"
    assert result.content_type == "video/mp4"

    mock_post.assert_called_once()
    assert mock_post.call_args.args[0] == "https://api.runwayml.com/v1/text_to_video"
    assert mock_post.call_args.kwargs["headers"]["Authorization"] == "Bearer test-key"
    assert mock_post.call_args.kwargs["json"]["promptText"] == "a short product demo video"

    assert mock_get.call_count == 3
    assert mock_get.call_args_list[0].args[0] == "https://api.runwayml.com/v1/tasks/task-123"
    assert mock_get.call_args_list[2].args[0] == "https://runway.example/output.mp4"
    mock_sleep.assert_called_once()


def test_generate_raises_on_failed_task_status() -> None:
    with (
        patch("httpx.post", return_value=_create_task_response()),
        patch("httpx.get", return_value=_poll_response("FAILED", failure="content policy violation")),
    ):
        with pytest.raises(RuntimeError, match="content policy violation"):
            _provider().generate("a prompt")


def test_generate_times_out_after_max_poll_attempts() -> None:
    with (
        patch("httpx.post", return_value=_create_task_response()),
        patch("httpx.get", return_value=_poll_response("PENDING")),
        patch("packages.integrations.video_gen.runway_provider.time.sleep"),
    ):
        with pytest.raises(TimeoutError):
            _provider(max_poll_attempts=2).generate("a prompt")


def test_generate_logs_integration_call_on_success(db_session) -> None:
    with (
        patch("httpx.post", return_value=_create_task_response()),
        patch(
            "httpx.get",
            side_effect=[_poll_response("SUCCEEDED", output=["https://runway.example/o.mp4"]), _asset_response()],
        ),
    ):
        _provider().generate("a prompt")

    logged = (
        db_session.query(IntegrationCall)
        .filter_by(provider="runway", capability="video")
        .order_by(IntegrationCall.created_at.desc())
        .first()
    )
    assert logged is not None
    assert logged.success is True


def test_generate_logs_integration_call_on_failure(db_session) -> None:
    with patch("httpx.post", side_effect=Exception("network unreachable")):
        with pytest.raises(Exception, match="network unreachable"):
            _provider().generate("a prompt")

    logged = (
        db_session.query(IntegrationCall)
        .filter_by(provider="runway", capability="video")
        .order_by(IntegrationCall.created_at.desc())
        .first()
    )
    assert logged is not None
    assert logged.success is False
    assert "network unreachable" in (logged.error_message or "")


# ---------------------------------------------------------------------------
# registry.get_video_provider()
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_get_video_provider_defaults_to_runway() -> None:
    assert isinstance(get_video_provider(), RunwayProvider)


def test_unknown_video_provider_raises(monkeypatch) -> None:
    monkeypatch.setenv("VIDEO_PROVIDER", "kling")
    with pytest.raises(ValueError, match="Unknown VIDEO_PROVIDER"):
        get_video_provider()


# ---------------------------------------------------------------------------
# generation_engine.py wiring: called only through the interface, stored via
# StorageProvider, referenced on Post.media
# ---------------------------------------------------------------------------


def test_generation_engine_media_hook_calls_video_provider_only_through_interface(db_session) -> None:
    post = _setup_post(db_session)
    brief = _creative_brief(linkedin_format="short_video", x_format="text_post")

    with (
        patch(LLM_PATCH_TARGET) as mock_llm,
        patch(VIDEO_PATCH_TARGET) as mock_video,
        patch(STORAGE_PATCH_TARGET) as mock_storage,
        patch("httpx.post") as mock_httpx_post,
        patch("httpx.get") as mock_httpx_get,
    ):
        mock_llm.return_value.complete.return_value = _llm_response(_copy_payload())
        mock_video.return_value.generate.return_value = VideoResult(
            url="https://runway.example/output.mp4", content=b"bytes", content_type="video/mp4"
        )
        mock_storage.return_value.upload.return_value = "https://cdn.example/generated/linkedin.mp4"

        _run_node(db_session, post, brief)

    mock_video.return_value.generate.assert_called_once()
    mock_httpx_post.assert_not_called()
    mock_httpx_get.assert_not_called()


def test_video_format_generates_stores_and_links_to_post_media(db_session) -> None:
    post = _setup_post(db_session)
    brief = _creative_brief(linkedin_format="short_video", x_format="text_post")

    with (
        patch(LLM_PATCH_TARGET) as mock_llm,
        patch(VIDEO_PATCH_TARGET) as mock_video,
        patch(STORAGE_PATCH_TARGET) as mock_storage,
    ):
        mock_llm.return_value.complete.return_value = _llm_response(_copy_payload())
        mock_video.return_value.generate.return_value = VideoResult(
            url="https://runway.example/output.mp4", content=b"fake-bytes", content_type="video/mp4"
        )
        mock_storage.return_value.upload.return_value = "https://cdn.example/generated/linkedin.mp4"

        result = _run_node(db_session, post, brief)

    mock_storage.return_value.upload.assert_called_once()
    upload_call = mock_storage.return_value.upload.call_args
    assert upload_call.args[1] == b"fake-bytes"
    assert upload_call.args[2] == "video/mp4"

    db_session.refresh(post)
    assert post.media == {
        "linkedin": [
            {
                "status": "generated",
                "platform": "linkedin",
                "format": "short_video",
                "url": "https://cdn.example/generated/linkedin.mp4",
            }
        ]
    }
    assert "x" not in post.media

    media_out = result["generation_output"]["platforms"]["linkedin"]["media"]
    assert media_out["status"] == "generated"
    assert media_out["url"] == "https://cdn.example/generated/linkedin.mp4"


def test_carousel_format_also_uses_video_provider(db_session) -> None:
    post = _setup_post(db_session)
    brief = _creative_brief(linkedin_format="carousel", x_format="text_post")

    with (
        patch(LLM_PATCH_TARGET) as mock_llm,
        patch(VIDEO_PATCH_TARGET) as mock_video,
        patch(STORAGE_PATCH_TARGET) as mock_storage,
    ):
        mock_llm.return_value.complete.return_value = _llm_response(_copy_payload())
        mock_video.return_value.generate.return_value = VideoResult(
            url="https://runway.example/output.mp4", content=b"bytes", content_type="video/mp4"
        )
        mock_storage.return_value.upload.return_value = "https://cdn.example/generated/linkedin-carousel.mp4"

        _run_node(db_session, post, brief)

    mock_video.return_value.generate.assert_called_once()
    db_session.refresh(post)
    assert post.media["linkedin"][0]["url"] == "https://cdn.example/generated/linkedin-carousel.mp4"


def test_image_format_still_stubbed_not_wired_to_video_provider(db_session) -> None:
    """Sanity check that this issue's changes stayed narrowly scoped to
    video/carousel -- image formats aren't this issue's job (#22)."""
    post = _setup_post(db_session)
    brief = _creative_brief(linkedin_format="image", x_format="text_post")

    with patch(LLM_PATCH_TARGET) as mock_llm, patch(VIDEO_PATCH_TARGET) as mock_video:
        mock_llm.return_value.complete.return_value = _llm_response(_copy_payload())
        result = _run_node(db_session, post, brief)

    mock_video.return_value.generate.assert_not_called()
    assert result["generation_output"]["platforms"]["linkedin"]["media"]["status"] == "stubbed"
    db_session.refresh(post)
    assert post.media is None


def test_generate_media_stub_direct_call_video_format_uses_interface(db_session) -> None:
    with patch(VIDEO_PATCH_TARGET) as mock_video, patch(STORAGE_PATCH_TARGET) as mock_storage:
        mock_video.return_value.generate.return_value = VideoResult(url="https://runway.example/o.mp4", content=b"x")
        mock_storage.return_value.upload.return_value = "https://cdn.example/x.mp4"

        result = generate_media_stub(str(uuid.uuid4()), "linkedin", {"format": "short_video", "hook": "hi"})

    assert result["status"] == "generated"
    assert result["url"] == "https://cdn.example/x.mp4"


# ---------------------------------------------------------------------------
# degrade-on-failure: caught, logged, doesn't crash the node or the pipeline
# ---------------------------------------------------------------------------


def test_video_provider_failure_degrades_gracefully_at_node_level(db_session) -> None:
    post = _setup_post(db_session)
    brief = _creative_brief(linkedin_format="short_video", x_format="text_post")

    with patch(LLM_PATCH_TARGET) as mock_llm, patch(VIDEO_PATCH_TARGET) as mock_video:
        mock_llm.return_value.complete.return_value = _llm_response(_copy_payload())
        mock_video.return_value.generate.side_effect = Exception("Runway unreachable")

        result = _run_node(db_session, post, brief)

    media_out = result["generation_output"]["platforms"]["linkedin"]["media"]
    assert media_out["status"] == "failed"
    assert media_out["url"] is None

    db_session.refresh(post)
    # Post.media stays unset for the failed platform -- no placeholder written.
    assert post.media is None
    # But copy generation (unrelated to the media failure) still succeeded.
    assert post.body_text is not None


def test_storage_failure_after_successful_generation_also_degrades_gracefully(db_session) -> None:
    post = _setup_post(db_session)
    brief = _creative_brief(linkedin_format="short_video", x_format="text_post")

    with (
        patch(LLM_PATCH_TARGET) as mock_llm,
        patch(VIDEO_PATCH_TARGET) as mock_video,
        patch(STORAGE_PATCH_TARGET) as mock_storage,
    ):
        mock_llm.return_value.complete.return_value = _llm_response(_copy_payload())
        mock_video.return_value.generate.return_value = VideoResult(url="https://runway.example/o.mp4", content=b"x")
        mock_storage.return_value.upload.side_effect = Exception("storage unavailable")

        result = _run_node(db_session, post, brief)

    media_out = result["generation_output"]["platforms"]["linkedin"]["media"]
    assert media_out["status"] == "failed"
    db_session.refresh(post)
    assert post.media is None


def test_pipeline_run_does_not_crash_when_video_provider_fails(db_session, thread_cleanup) -> None:
    post = _setup_post(db_session)
    thread_cleanup.append(str(post.id))
    brief = _creative_brief(linkedin_format="short_video", x_format="text_post")

    with (
        patch(SEARCH_PATCH_TARGET) as mock_search,
        patch(EMBED_PATCH_TARGET) as mock_embed,
        patch(CREATIVE_LLM_PATCH_TARGET) as mock_creative_llm,
        patch(LLM_PATCH_TARGET) as mock_generation_llm,
        patch(VIDEO_PATCH_TARGET) as mock_video,
    ):
        mock_search.return_value.search.return_value = []
        mock_embed.return_value.embed.return_value = [0.0] * 1536
        mock_creative_llm.return_value.complete.return_value = _llm_response(brief["platforms"])
        mock_generation_llm.return_value.complete.return_value = _llm_response(_copy_payload())
        mock_video.return_value.generate.side_effect = Exception("Runway unreachable")

        # Must not raise -- a video-gen failure degrades gracefully rather
        # than crashing the whole pipeline run.
        with get_postgres_checkpointer() as checkpointer:
            list(run_pipeline(db_session, post, checkpointer))

    run = (
        db_session.query(AgentRun)
        .filter(AgentRun.post_id == post.id, AgentRun.agent_type == AgentType.GENERATION)
        .order_by(AgentRun.created_at.desc())
        .first()
    )
    assert run is not None

    db_session.refresh(post)
    assert post.body_text == _copy_payload()
    assert post.media is None
