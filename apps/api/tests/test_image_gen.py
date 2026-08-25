"""Tests for the Issue #22 fal.ai image-generation adapter and its wiring
into the Generation Engine's media hook (packages/agents/pipeline/nodes/
generation_engine.py, from Issue #21).

Per the issue's acceptance criteria:
  1. FalImageProvider implements ImageProvider and is reached only through
     that interface — no other module imports fal.ai's SDK/URL/base path
     directly (mirrors test_integrations_llm.py / test_storage.py's
     "mock the HTTP layer, assert the adapter is the only caller" style).
  2. A generated image is stored via StorageProvider (Issue #11) and
     referenced on Post.media.
  3. A generation/storage failure is caught, logged to integration_calls,
     and degrades gracefully — it must not crash run_pipeline.
"""

import pathlib
import uuid
from unittest.mock import MagicMock, patch

import pytest

from apps.api.config import get_settings
from apps.api.models import AgentType, Brand, IntegrationCall, Organization, Post
from packages.agents.pipeline.checkpointer import get_postgres_checkpointer
from packages.agents.pipeline.graph import run_pipeline
from packages.agents.pipeline.nodes.generation_engine import (
    build_generation_node,
    generate_media_stub,
)
from packages.integrations.image_gen.base import ImageProvider, ImageResult
from packages.integrations.image_gen.fal_provider import FalImageProvider
from packages.integrations.registry import get_image_provider

IMAGE_PATCH_TARGET = "packages.agents.pipeline.nodes.generation_engine.get_image_provider"
STORAGE_PATCH_TARGET = "packages.agents.pipeline.nodes.generation_engine.get_storage_provider"
LLM_PATCH_TARGET = "packages.agents.pipeline.nodes.generation_engine.get_llm_provider"
SEARCH_PATCH_TARGET = "packages.agents.pipeline.nodes.research_engine.get_search_provider"
EMBED_PATCH_TARGET = "apps.api.services.brand_retrieval.get_embedding_provider"
CREATIVE_LLM_PATCH_TARGET = "packages.agents.pipeline.nodes.creative_engine.get_llm_provider"

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
FAL_PROVIDER_FILE = REPO_ROOT / "packages" / "integrations" / "image_gen" / "fal_provider.py"


# --- FalImageProvider: interface conformance + HTTP layer mocked only ------


def _fal_response(url: str = "https://fal.media/files/generated-abc123.png") -> MagicMock:
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"images": [{"url": url}]}
    return response


def test_fal_provider_implements_image_provider_interface() -> None:
    provider = FalImageProvider(api_key="test-key")
    assert isinstance(provider, ImageProvider)


def test_fal_provider_generate_calls_fal_and_parses_result() -> None:
    with patch("httpx.post", return_value=_fal_response()) as mock_post:
        result = FalImageProvider(api_key="test-key").generate("a mountain at sunrise")

    assert isinstance(result, ImageResult)
    assert result.url == "https://fal.media/files/generated-abc123.png"
    call_args, call_kwargs = mock_post.call_args
    assert call_args[0].startswith("https://fal.run/")
    assert call_kwargs["headers"]["Authorization"] == "Key test-key"
    assert call_kwargs["json"]["prompt"] == "a mountain at sunrise"


def test_fal_provider_raises_when_response_has_no_images() -> None:
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"images": []}

    with patch("httpx.post", return_value=response):
        with pytest.raises(ValueError, match="no generated image URL"):
            FalImageProvider(api_key="test-key").generate("a mountain at sunrise")


def test_fal_provider_logs_successful_call_to_integration_calls(db_session) -> None:
    with patch("httpx.post", return_value=_fal_response()):
        FalImageProvider(api_key="test-key").generate("a mountain at sunrise")

    logged = (
        db_session.query(IntegrationCall)
        .filter_by(provider="fal", capability="image_gen")
        .order_by(IntegrationCall.created_at.desc())
        .first()
    )
    assert logged is not None
    assert logged.success is True


def test_fal_provider_propagates_and_logs_http_failures(db_session) -> None:
    with patch("httpx.post", side_effect=Exception("fal.ai unreachable")):
        with pytest.raises(Exception, match="fal.ai unreachable"):
            FalImageProvider(api_key="test-key").generate("a mountain at sunrise")

    logged = (
        db_session.query(IntegrationCall)
        .filter_by(provider="fal", capability="image_gen")
        .order_by(IntegrationCall.created_at.desc())
        .first()
    )
    assert logged is not None
    assert logged.success is False
    assert "fal.ai unreachable" in (logged.error_message or "")


def test_no_module_other_than_fal_provider_references_fals_base_url() -> None:
    """The adapter file is the only place allowed to know fal.ai's HTTP
    endpoint — everything else (registry.py, generation_engine.py, ...)
    must go through the ImageProvider interface only."""
    skip_dir_markers = ("/.git/", "/.venv/", "/node_modules/", "/.claude/")
    offenders = []
    for path in REPO_ROOT.rglob("*.py"):
        path_str = str(path)
        if path == FAL_PROVIDER_FILE or "/tests/" in path_str:
            continue
        if any(marker in path_str for marker in skip_dir_markers):
            continue
        text = path.read_text(errors="ignore")
        if "fal.run" in text or "fal-ai/flux" in text:
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == []


# --- registry wiring ---------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_get_image_provider_defaults_to_fal() -> None:
    assert isinstance(get_image_provider(), FalImageProvider)


def test_unknown_image_provider_raises(monkeypatch) -> None:
    monkeypatch.setenv("IMAGE_PROVIDER", "midjourney")
    with pytest.raises(ValueError, match="Unknown IMAGE_PROVIDER"):
        get_image_provider()


# --- Generation Engine wiring: image stored + referenced on Post.media -----


def _setup_post(db_session) -> Post:
    org = Organization(name="Acme Agency")
    db_session.add(org)
    db_session.flush()

    brand = Brand(organization_id=org.id, name="Acme Widgets", industry="Outdoor gear")
    db_session.add(brand)
    db_session.flush()

    post = Post(brand_id=brand.id)
    db_session.add(post)
    db_session.flush()
    return post


def _image_brief() -> dict:
    return {
        "platforms": {
            "linkedin": {
                "format": "image",
                "angle": "product_launch",
                "hook": "Our new pack just dropped.",
                "cta": "Shop the collection.",
                "tone": "confident",
            },
        }
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


def _mock_llm_for_copy():
    from packages.integrations.llm.base import LLMResponse
    import json

    return LLMResponse(
        text=json.dumps({"linkedin": "Our new pack just dropped. Shop the collection."}),
        model="openrouter/free",
        input_tokens=50,
        output_tokens=20,
    )


def test_generate_media_stub_calls_image_provider_only_through_interface_for_image_format() -> None:
    with patch(IMAGE_PATCH_TARGET) as mock_get_image, patch(STORAGE_PATCH_TARGET) as mock_get_storage:
        mock_get_image.return_value.generate.return_value = ImageResult(
            url="https://fal.media/files/generated-abc123.png"
        )
        mock_get_storage.return_value.upload.return_value = (
            "https://project.supabase.co/storage/v1/object/public/brand-assets/generated/x.png"
        )

        with patch("httpx.get") as mock_httpx_get:
            mock_httpx_get.return_value.raise_for_status.return_value = None
            mock_httpx_get.return_value.content = b"fake-png-bytes"
            mock_httpx_get.return_value.headers = {"content-type": "image/png"}

            result = generate_media_stub(
                "post-123", "linkedin", _image_brief()["platforms"]["linkedin"]
            )

    mock_get_image.return_value.generate.assert_called_once()
    assert result["status"] == "generated"
    assert result["url"] == (
        "https://project.supabase.co/storage/v1/object/public/brand-assets/generated/x.png"
    )
    upload_args = mock_get_storage.return_value.upload.call_args.args
    assert upload_args[1] == b"fake-png-bytes"
    assert upload_args[2] == "image/png"


def test_generation_engine_stores_image_and_references_it_on_post_media(db_session) -> None:
    post = _setup_post(db_session)

    with (
        patch(LLM_PATCH_TARGET) as mock_llm,
        patch(IMAGE_PATCH_TARGET) as mock_get_image,
        patch(STORAGE_PATCH_TARGET) as mock_get_storage,
    ):
        mock_llm.return_value.complete.return_value = _mock_llm_for_copy()
        mock_get_image.return_value.generate.return_value = ImageResult(
            url="https://fal.media/files/generated-abc123.png"
        )
        stored_url = (
            "https://project.supabase.co/storage/v1/object/public/brand-assets/"
            f"generated/{post.id}/linkedin/img.png"
        )
        mock_get_storage.return_value.upload.return_value = stored_url

        with patch("httpx.get") as mock_httpx_get:
            mock_httpx_get.return_value.raise_for_status.return_value = None
            mock_httpx_get.return_value.content = b"fake-png-bytes"
            mock_httpx_get.return_value.headers = {"content-type": "image/png"}

            result = _run_node(db_session, post, _image_brief())

    # Stored via the storage adapter interface only.
    mock_get_storage.return_value.upload.assert_called_once()

    db_session.refresh(post)
    assert post.media == [{"platform": "linkedin", "format": "image", "url": stored_url}]
    assert result["generation_output"]["platforms"]["linkedin"]["media"]["url"] == stored_url
    assert result["generation_output"]["platforms"]["linkedin"]["media"]["status"] == "generated"


def test_generation_engine_does_not_touch_post_media_for_plain_text_format(db_session) -> None:
    post = _setup_post(db_session)
    brief = {
        "platforms": {
            "linkedin": {
                "format": "text_post",
                "angle": "thought_leadership",
                "hook": "hook",
                "cta": "cta",
                "tone": "professional",
            },
        }
    }

    with patch(LLM_PATCH_TARGET) as mock_llm:
        mock_llm.return_value.complete.return_value = _mock_llm_for_copy()
        _run_node(db_session, post, brief)

    db_session.refresh(post)
    assert post.media is None


# --- degrade-on-failure: caught, logged, never crashes the pipeline --------


def test_image_generation_failure_is_caught_and_returns_failed_status(db_session) -> None:
    with patch(IMAGE_PATCH_TARGET) as mock_get_image:
        mock_get_image.return_value.generate.side_effect = Exception("fal.ai quota exceeded")

        result = generate_media_stub("post-123", "linkedin", _image_brief()["platforms"]["linkedin"])

    assert result["status"] == "failed"
    assert result["platform"] == "linkedin"


def test_image_generation_failure_logged_to_integration_calls(db_session) -> None:
    """Uses the real FalImageProvider (only its HTTP layer mocked) so
    track_integration_call actually runs and logs the failure, exactly
    the same context manager every other adapter call in this codebase
    uses."""
    with (
        patch(STORAGE_PATCH_TARGET),
        patch(
            "packages.agents.pipeline.nodes.generation_engine.get_image_provider",
            return_value=FalImageProvider(api_key="test-key"),
        ),
        patch("httpx.post", side_effect=Exception("fal.ai unreachable")),
    ):
        result = generate_media_stub("post-123", "linkedin", _image_brief()["platforms"]["linkedin"])

    assert result["status"] == "failed"

    logged = (
        db_session.query(IntegrationCall)
        .filter_by(provider="fal", capability="image_gen")
        .order_by(IntegrationCall.created_at.desc())
        .first()
    )
    assert logged is not None
    assert logged.success is False


def test_storage_upload_failure_is_caught_and_does_not_propagate(db_session) -> None:
    with patch(IMAGE_PATCH_TARGET) as mock_get_image, patch(STORAGE_PATCH_TARGET) as mock_get_storage:
        mock_get_image.return_value.generate.return_value = ImageResult(
            url="https://fal.media/files/generated-abc123.png"
        )
        mock_get_storage.return_value.upload.side_effect = Exception("supabase storage unreachable")

        with patch("httpx.get") as mock_httpx_get:
            mock_httpx_get.return_value.raise_for_status.return_value = None
            mock_httpx_get.return_value.content = b"fake-png-bytes"
            mock_httpx_get.return_value.headers = {"content-type": "image/png"}

            result = generate_media_stub("post-123", "linkedin", _image_brief()["platforms"]["linkedin"])

    assert result["status"] == "failed"


@pytest.fixture()
def thread_cleanup():
    """Same teardown as test_generation_engine.py's fixture — pipeline
    checkpoint rows live in Postgres on a connection separate from
    db_session's rolled-back transaction, so they need explicit cleanup."""
    thread_ids: list[str] = []
    yield thread_ids
    if not thread_ids:
        return
    with get_postgres_checkpointer() as checkpointer:
        for thread_id in thread_ids:
            checkpointer.delete_thread(thread_id)


def test_image_generation_failure_does_not_crash_run_pipeline(db_session, thread_cleanup) -> None:
    post = _setup_post(db_session)
    thread_cleanup.append(str(post.id))

    # No calendar_event_id on this Post, so Creative Engine falls back to
    # SUPPORTED_PLATFORMS ("linkedin", "x") — both platform briefs must be
    # mocked or Creative Engine's own parse-failure fallback kicks in.
    with (
        patch(SEARCH_PATCH_TARGET) as mock_search,
        patch(EMBED_PATCH_TARGET) as mock_embed,
        patch(CREATIVE_LLM_PATCH_TARGET) as mock_creative_llm,
        patch(LLM_PATCH_TARGET) as mock_generation_llm,
        patch(IMAGE_PATCH_TARGET) as mock_get_image,
    ):
        mock_search.return_value.search.return_value = []
        mock_embed.return_value.embed.return_value = [0.0] * 1536
        mock_creative_llm.return_value.complete.return_value = _two_platform_brief_llm_response()
        mock_generation_llm.return_value.complete.return_value = _two_platform_copy_llm_response()
        mock_get_image.return_value.generate.side_effect = Exception("fal.ai quota exceeded")

        with get_postgres_checkpointer() as checkpointer:
            # Must not raise — an image-gen failure degrades gracefully
            # rather than crashing the whole pipeline run.
            events = list(run_pipeline(db_session, post, checkpointer))

    assert events  # the pipeline still ran to completion
    db_session.refresh(post)
    # Copy generation still succeeded (both platforms) even though
    # linkedin's media generation failed.
    assert post.body_text == {
        "linkedin": "Our new pack just dropped. Shop the collection.",
        "x": "Quick take on the new pack. Check it out.",
    }
    # No media was stored, since generation failed.
    assert post.media is None
    # Failure -> integration_calls logging is exercised directly against
    # the real FalImageProvider in
    # test_image_generation_failure_logged_to_integration_calls above
    # (get_image_provider is mocked wholesale here to isolate "the
    # pipeline survives a media failure" from "the adapter logs its own
    # failures").


def _two_platform_brief_llm_response():
    from packages.integrations.llm.base import LLMResponse
    import json

    return LLMResponse(
        text=json.dumps(
            {
                "linkedin": _image_brief()["platforms"]["linkedin"],
                "x": {
                    "format": "text_post",
                    "angle": "hot_take",
                    "hook": "Quick take on the new pack.",
                    "cta": "Check it out.",
                    "tone": "casual",
                },
            }
        ),
        model="openrouter/free",
        input_tokens=50,
        output_tokens=20,
    )


def _two_platform_copy_llm_response():
    from packages.integrations.llm.base import LLMResponse
    import json

    return LLMResponse(
        text=json.dumps(
            {
                "linkedin": "Our new pack just dropped. Shop the collection.",
                "x": "Quick take on the new pack. Check it out.",
            }
        ),
        model="openrouter/free",
        input_tokens=50,
        output_tokens=20,
    )
