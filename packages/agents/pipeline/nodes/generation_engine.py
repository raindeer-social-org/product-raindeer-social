"""Generation Engine — Issue #21, the third real (non-stub) stage in the
per-post pipeline graph (packages/agents/pipeline/graph.py), running right
after Creative (#20).

Turns the Creative Engine's brief (see
packages/agents/pipeline/nodes/creative_engine.py —
{"post_id", "platforms": {"<platform>": {"format", "angle", "hook", "cta",
"tone"}}}) into actual, publish-ready copy: not more strategy, the words
themselves. This is the first pipeline node built directly on top of
LLMProvider whose output gets *persisted* onto the Post — earlier stages
(#19/#20) only ever hand a brief to the next stage in memory.

Same interface-only contract as research_engine.py/creative_engine.py:
copy generation goes through LLMProvider
(packages/integrations/registry.get_llm_provider()) exclusively — never a
direct vendor SDK import — with the model read fresh from
apps.api.config.get_settings().llm_default_model on every call, never a
hardcoded model slug. Same degrade-on-failure contract too: a broken/
unconfigured LLM provider must not take the pipeline down with it, so a
failed call/parse falls back to simple copy composed from the (already
LLM-produced) creative brief's hook + CTA rather than raising.

Also defines generate_media_stub(): the image/video-generation hook
called (unconditionally, whenever a platform's brief calls for it) when a
platform's `format` is image/video/carousel. Issues #22 (image) and #23
(video) will replace/extend this stub with real adapters — this issue's
job is only to guarantee the call site exists and is genuinely reached
under the right conditions, not to build those adapters.

Output handling — Post.body_text with version history preserved:
  * Post.body_text (apps/api/models/post.py) is written with this run's
    generated copy, a dict keyed by platform, matching creative_brief's
    per-platform shape.
  * A PostVersion row (apps/api/models/post_version.py) is appended for
    every generation run — the same "append a log row, never overwrite"
    convention AgentRun already establishes — so regenerating a post's
    copy (e.g. after a human-review rejection) never loses the version
    that came before it.

AgentRun token/cost fields: run_pipeline (graph.py) already logs one
AgentRun row per completed node generically, from whatever dict the node
returns — this module doesn't add a second row itself (that would double-
count against packages/agents/tests/test_pipeline_graph.py's exact
per-stage row-count assertions). Instead this node's return dict includes
a "generation_output" entry with "model"/"tokens"/"cost"/"latency_ms"
keys, and graph.py's run_pipeline reads those (when present) onto the one
AgentRun row it already writes for this stage.

Mirrors research_engine.py/creative_engine.py's shape: a factory,
build_generation_node(db), closing over a caller-supplied Session (needed
to resolve Post -> Post.body_text/PostVersion, same as the earlier
stages), returning the actual LangGraph node function. graph.py's
build_pipeline_graph() calls this factory for the "generation" stage
only.
"""

import json
import logging
import time
import uuid
from typing import Any

from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.models.post import Post
from apps.api.models.post_version import PostVersion
from packages.integrations.registry import (
    get_llm_provider,
    get_storage_provider,
    get_video_provider,
)
from packages.integrations.video_gen.base import VideoResult

logger = logging.getLogger(__name__)

# A platform's creative-brief `format` is free text (e.g. "text_post",
# "carousel", "short_video") rather than a closed enum, so this matches by
# substring rather than exact value — "short_video" and "carousel_post"
# both still need the media hook.
MEDIA_FORMAT_KEYWORDS = ("image", "video", "carousel")

# Subset of MEDIA_FORMAT_KEYWORDS this issue (#23) actually implements —
# "image" stays a stub here; Issue #22 replaces that branch separately, on
# its own concurrent PR, so this file's changes stay narrowly scoped to
# video/carousel (see generate_media_stub below).
VIDEO_FORMAT_KEYWORDS = ("video", "carousel")

# Rough, provider-agnostic per-token estimate used only to keep
# AgentRun.cost/PostVersion.cost populated (per #21's acceptance criteria)
# until a real pricing/billing feed exists — not tied to any specific
# model's actual price.
_COST_PER_1K_TOKENS = 0.002


class GenerationEngineError(Exception):
    """Raised when the generation node can't resolve the Post it was asked
    to generate copy for — a programming/data error (missing row), not a
    transient LLM-provider failure, so unlike LLM failures this is not
    swallowed."""


def _default_model() -> str:
    """Reads LLM_DEFAULT_MODEL fresh on every call (not a module constant)
    so tests and per-environment overrides take effect without a reimport
    — same convention as research_engine.py/creative_engine.py."""
    return get_settings().llm_default_model


def _estimate_cost(tokens: int) -> float:
    return round((tokens / 1000) * _COST_PER_1K_TOKENS, 6)


def _requires_media(platform_brief: dict[str, Any]) -> bool:
    fmt = str(platform_brief.get("format", "")).lower()
    return any(keyword in fmt for keyword in MEDIA_FORMAT_KEYWORDS)


def _is_video_or_carousel_format(fmt: str) -> bool:
    return any(keyword in fmt for keyword in VIDEO_FORMAT_KEYWORDS)


def _build_video_prompt(platform_brief: dict[str, Any]) -> str:
    """Composes a text-to-video prompt straight from the creative brief's
    hook/angle/tone — same spirit as _fallback_copy_for below: no separate
    LLM call just to write a video prompt, reuse what the Creative Engine
    (#20) already produced."""
    hook = str(platform_brief.get("hook") or "").strip()
    angle = str(platform_brief.get("angle") or "").strip()
    tone = str(platform_brief.get("tone") or "").strip()
    parts = [part for part in (hook, angle, tone) if part]
    if parts:
        return " — ".join(parts)
    return "Short-form social media video."


def _store_generated_video(post_id: str, platform: str, result: VideoResult) -> str:
    """Persists the generated asset via this repo's own StorageProvider
    (#11) rather than linking Runway's own hosted URL directly — vendor
    output URLs for video-gen are not guaranteed to stay valid
    indefinitely. Interface-only: only ever talks to StorageProvider,
    never a vendor SDK/URL directly."""
    storage = get_storage_provider()
    extension = "mp4" if "mp4" in (result.content_type or "") else "bin"
    path = f"generated-media/{post_id}/{platform}-{uuid.uuid4().hex}.{extension}"
    return storage.upload(path, result.content, result.content_type or "video/mp4")


def generate_media_stub(post_id: str, platform: str, platform_brief: dict[str, Any]) -> dict[str, Any]:
    """Image/video-generation hook, called whenever a platform's brief
    calls for image/video/carousel. Issue #23 (this issue) fills in the
    video/carousel branch with a real VideoProvider adapter
    (packages/integrations/video_gen/runway_provider.py), called only
    through the VideoProvider interface — never a direct vendor SDK/HTTP
    call from this file. The image branch stays a stub here; Issue #22
    replaces it separately (on its own concurrent PR), so this function's
    changes stay narrowly scoped to the video/carousel case.

    Degrades gracefully: a VideoProvider failure, or a StorageProvider
    failure while persisting the result, is caught and logged (the
    VideoProvider/StorageProvider adapters themselves already log to
    integration_calls via track_integration_call) rather than raised —
    same degrade-on-failure contract every other external call in this
    pipeline follows (research_engine.py/creative_engine.py, and this
    module's own LLM copy generation above), so a broken/unconfigured
    video provider never crashes the whole pipeline run."""
    fmt = str(platform_brief.get("format") or "")
    logger.info(
        "Generation Engine: media hook called for post=%s platform=%s format=%r",
        post_id,
        platform,
        fmt,
    )

    if not _is_video_or_carousel_format(fmt.lower()):
        # Image formats: Issue #22 replaces this branch with a real
        # ImageProvider adapter.
        return {
            "status": "stubbed",
            "platform": platform,
            "format": fmt or None,
            "url": None,
        }

    try:
        prompt = _build_video_prompt(platform_brief)
        result = get_video_provider().generate(prompt=prompt)
        url = _store_generated_video(post_id, platform, result)
    except Exception:
        logger.warning(
            "Generation Engine: video/carousel generation failed for post=%s "
            "platform=%s; degrading gracefully (no media attached)",
            post_id,
            platform,
            exc_info=True,
        )
        return {
            "status": "failed",
            "platform": platform,
            "format": fmt or None,
            "url": None,
        }

    return {
        "status": "generated",
        "platform": platform,
        "format": fmt or None,
        "url": url,
    }


def _strip_code_fence(text: str) -> str:
    cleaned = text.strip()
    if not cleaned.startswith("```"):
        return cleaned
    cleaned = cleaned.strip("`")
    if cleaned.startswith("json"):
        cleaned = cleaned[len("json"):]
    return cleaned.strip()


def _parse_platform_copy(text: str, platforms: list[str]) -> dict[str, str]:
    parsed = json.loads(_strip_code_fence(text))
    if not isinstance(parsed, dict):
        raise ValueError("Generation Engine LLM output was valid JSON but not an object")

    result: dict[str, str] = {}
    for platform in platforms:
        value = parsed.get(platform)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Generation Engine LLM output missing copy for platform {platform!r}")
        result[platform] = value
    return result


def _fallback_copy_for(platform_brief: dict[str, Any], platform: str) -> str:
    """Used only when the LLM call/parse fails (see module docstring) —
    composed straight from the creative brief's hook + CTA so the fallback
    is still usable copy rather than a blank/placeholder string."""
    hook = str(platform_brief.get("hook") or "").strip()
    cta = str(platform_brief.get("cta") or "").strip()
    parts = [part for part in (hook, cta) if part]
    if parts:
        return "\n\n".join(parts)
    return f"[Generation Engine fallback] Unable to generate copy for {platform}."


def _build_prompt(platform_briefs: dict[str, dict[str, str]], platforms: list[str]) -> str:
    briefs_json = json.dumps({platform: platform_briefs.get(platform, {}) for platform in platforms})
    return f"""You are a senior social media copywriter turning an
already-approved creative brief into the final, publish-ready post copy —
the actual words that will be posted, not more strategy. Respond with
strict JSON only — no markdown, no commentary, no code fences.

## Creative briefs per platform
{briefs_json}

## Task
For EACH of these target platforms — {", ".join(platforms)} — write the
final post copy that follows that platform's brief (format, angle, hook,
cta, tone) exactly: open with (or clearly incorporate) that platform's
hook, end with (or clearly incorporate) its CTA, and match its tone. Each
platform's copy must be genuinely distinct — reflecting that platform's
own brief — not the same text reused across platforms.

Respond with a single JSON object whose keys are exactly the platform
names listed above, and whose values are the final copy text (a plain
string) for that platform.

Respond with ONLY the JSON object. No markdown code fences, no extra text.
"""


def _generate_copy(
    platform_briefs: dict[str, dict[str, str]], platforms: list[str]
) -> tuple[dict[str, str], str, int]:
    """Calls LLMProvider exclusively through its interface (never a direct
    vendor SDK import) — same degrade-on-failure contract as
    research_engine.py/creative_engine.py: a broken/unconfigured LLM
    provider, or a response that doesn't parse into usable copy, must
    never take the pipeline down with it, just fall back to simple copy
    composed from the creative brief."""
    model = _default_model()
    prompt = _build_prompt(platform_briefs, platforms)
    try:
        response = get_llm_provider().complete(prompt=prompt, model=model, temperature=0.7)
        copy_by_platform = _parse_platform_copy(response.text, platforms)
        return copy_by_platform, response.model, response.input_tokens + response.output_tokens
    except Exception:
        logger.warning("Generation Engine LLM call/parse failed; using fallback copy", exc_info=True)
        fallback = {
            platform: _fallback_copy_for(platform_briefs.get(platform, {}), platform)
            for platform in platforms
        }
        return fallback, model, 0


def _platforms_for(creative_brief: dict[str, Any]) -> tuple[list[str], dict[str, dict[str, str]]]:
    platform_briefs = creative_brief.get("platforms") or {}
    if not platform_briefs:
        # No upstream creative_brief (e.g. node invoked directly in a
        # test) — fall back to a single generic platform so this node is
        # still exercisable without a full creative_brief.
        return ["default"], {"default": {}}
    return list(platform_briefs.keys()), platform_briefs


def _generation_output(db: Session, post: Post, creative_brief: dict[str, Any]) -> dict[str, Any]:
    platforms, platform_briefs = _platforms_for(creative_brief)

    start = time.perf_counter()
    copy_by_platform, model, tokens = _generate_copy(platform_briefs, platforms)
    latency_ms = (time.perf_counter() - start) * 1000

    platform_results: dict[str, Any] = {}
    for platform in platforms:
        platform_brief = platform_briefs.get(platform, {})
        media_result = None
        if _requires_media(platform_brief):
            media_result = generate_media_stub(str(post.id), platform, platform_brief)
        platform_results[platform] = {
            "body_text": copy_by_platform[platform],
            "media": media_result,
        }

    body_text = {platform: result["body_text"] for platform, result in platform_results.items()}
    cost = _estimate_cost(tokens)

    # Link successfully generated video/carousel media onto Post.media —
    # a dict keyed by platform, each value a list of media reference dicts
    # (see apps/api/models/post.py). Only platforms whose media actually
    # generated (status == "generated", i.e. has a stored url) get an
    # entry; a failed/stubbed result is intentionally left out rather than
    # written as a placeholder. Merged onto any existing media (rather
    # than replaced wholesale) so a run that only touches some platforms
    # doesn't wipe out media a previous run already stored for others.
    media_by_platform = {
        platform: [result["media"]]
        for platform, result in platform_results.items()
        if result.get("media") and result["media"].get("url")
    }
    if media_by_platform:
        merged_media = dict(post.media or {})
        merged_media.update(media_by_platform)
        post.media = merged_media

    # Write the generated copy onto the Post itself, and append an
    # immutable version-history row (see module docstring) so a second
    # generation call never clobbers/loses the first version.
    post.body_text = body_text
    db.add(
        PostVersion(
            post_id=post.id,
            body_text=body_text,
            model=model,
            tokens=tokens,
            cost=cost,
        )
    )
    db.flush()
    db.refresh(post)

    return {
        "post_id": str(post.id),
        "platforms": platform_results,
        "model": model,
        "tokens": tokens,
        "cost": cost,
        "latency_ms": latency_ms,
    }


def build_generation_node(db: Session | None):
    """Builds the real "generation" stage node function, closing over
    `db`. Mirrors research_engine.py/creative_engine.py's factory shape
    exactly.

    `db` is accepted as possibly None so build_pipeline_graph(checkpointer)
    — with no `db` argument — still works for callers that only inspect
    the compiled graph's structure (nodes/edges) without ever streaming or
    invoking it; the resulting node just isn't runnable, and raises
    clearly if it ever is.
    """

    def _node(state: dict) -> dict:
        if db is None:
            raise RuntimeError(
                "Generation Engine node has no database session — "
                "build_pipeline_graph() must be called with db=<Session> "
                "to execute (not just inspect) the pipeline graph."
            )

        post = db.get(Post, uuid.UUID(state["post_id"]))
        if post is None:
            raise GenerationEngineError(
                f"Generation Engine: no Post found for post_id={state['post_id']!r}"
            )

        creative_brief = state.get("creative_brief") or {}
        output = _generation_output(db, post, creative_brief)
        return {
            "completed_stages": [*state.get("completed_stages", []), "generation"],
            "generation_output": output,
        }

    _node.__name__ = "generation_node"
    return _node
