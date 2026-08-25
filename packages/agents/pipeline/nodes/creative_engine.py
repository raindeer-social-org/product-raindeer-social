"""Creative Engine — Issue #20, the second real (non-stub) stage in the
per-post pipeline graph (packages/agents/pipeline/graph.py), running right
after Research (#19).

Turns the Research Engine's brief (see
packages/agents/pipeline/nodes/research_engine.py — brand_context,
platform_trends, industry_trends, timing_signal) into a structured
*creative brief*: not free text, but the format/angle/hook/CTA decisions
the Generation Engine (#21) will actually write copy from, with
tone/format genuinely adapted per target platform rather than one generic
brief reused everywhere.

Deciding format/angle/hook/CTA is a reasoning step, not a data reshape —
unlike research's grounding-only search calls, this goes through an
LLMProvider (packages/integrations/registry.get_llm_provider(), never a
direct vendor SDK import), exactly as packages/agents/onboarding/graph.py
calls it: through the interface only, with the model read fresh from
apps.api.config.get_settings().llm_default_model on every call — never a
hardcoded model slug.

Mirrors research_engine.py's shape: a factory, build_creative_node(db),
closing over a caller-supplied Session (needed to resolve Post -> Brand,
same as research), returning the actual LangGraph node function.
graph.py's build_pipeline_graph() calls this factory for the "creative"
stage only.

Degrade-on-failure: same contract as research_engine.py's
_search_safely/_brand_context_safely — a broken/unconfigured LLM provider
(missing API key, network issue, unparseable response) must not take the
whole pipeline run down with it. Unlike a failed research query (which
just means an empty result list), a failed creative call still has to
hand Generation Engine a *usable* structured brief, so on failure this
falls back to a fixed, still platform-differentiated template rather than
an empty result.
"""

import json
import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.models.brand import Brand
from apps.api.models.content_calendar_event import ContentCalendarEvent, SUPPORTED_PLATFORMS
from apps.api.models.post import Post
from packages.integrations.registry import get_llm_provider

logger = logging.getLogger(__name__)

REQUIRED_BRIEF_KEYS = ("format", "angle", "hook", "cta", "tone")

# Used only when the LLM call/parse fails (see module docstring) — a fixed
# fallback that still differs by platform, so a degraded run doesn't hand
# Generation Engine identical content for every platform.
_FALLBACK_BRIEFS: dict[str, dict[str, str]] = {
    "linkedin": {
        "format": "text_post",
        "angle": "thought_leadership",
        "hook": "Open with a counterintuitive insight from the industry trends.",
        "cta": "Invite readers to share their own experience in the comments.",
        "tone": "professional, insight-driven",
    },
    "x": {
        "format": "short_thread",
        "angle": "timely_reaction",
        "hook": "Open with a punchy, opinionated one-liner.",
        "cta": "Ask a quick, reply-provoking question.",
        "tone": "casual, punchy",
    },
}

_DEFAULT_FALLBACK_BRIEF: dict[str, str] = {
    "format": "text_post",
    "angle": "brand_story",
    "hook": "Open with a relatable moment for the audience.",
    "cta": "Invite readers to learn more.",
    "tone": "on-brand, neutral",
}


class CreativeEngineError(Exception):
    """Raised when the creative node can't resolve the Post/Brand it was
    asked to build a brief for — a programming/data error (missing row),
    not a transient LLM-provider failure, so unlike LLM failures this is
    not swallowed."""


def _default_model() -> str:
    """Reads LLM_DEFAULT_MODEL fresh on every call (not a module constant)
    so tests and per-environment overrides take effect without a reimport
    — same convention as packages/agents/onboarding/graph.py."""
    return get_settings().llm_default_model


def _fallback_brief_for(platform: str) -> dict[str, str]:
    return dict(_FALLBACK_BRIEFS.get(platform, _DEFAULT_FALLBACK_BRIEF))


def _strip_code_fence(text: str) -> str:
    cleaned = text.strip()
    if not cleaned.startswith("```"):
        return cleaned
    cleaned = cleaned.strip("`")
    if cleaned.startswith("json"):
        cleaned = cleaned[len("json"):]
    return cleaned.strip()


def _parse_platform_briefs(text: str, platforms: list[str]) -> dict[str, dict[str, str]]:
    parsed = json.loads(_strip_code_fence(text))
    if not isinstance(parsed, dict):
        raise ValueError("Creative Engine LLM output was valid JSON but not an object")

    result: dict[str, dict[str, str]] = {}
    for platform in platforms:
        entry = parsed.get(platform)
        if not isinstance(entry, dict):
            raise ValueError(f"Creative Engine LLM output missing brief for platform {platform!r}")
        missing = [key for key in REQUIRED_BRIEF_KEYS if key not in entry]
        if missing:
            raise ValueError(
                f"Creative Engine LLM output for platform {platform!r} missing keys: {missing}"
            )
        result[platform] = {key: str(entry[key]) for key in REQUIRED_BRIEF_KEYS}
    return result


def _build_prompt(brand: Brand, research_brief: dict[str, Any], platforms: list[str]) -> str:
    industry = brand.industry or brand.name
    return f"""You are a senior social media creative strategist deciding
*how* to make a brand's next post land on each platform — not writing the
copy itself, just the creative strategy behind it. Respond with strict
JSON only — no markdown, no commentary, no code fences.

## Brand
{brand.name} ({industry})

## Research brief
Brand context: {json.dumps(research_brief.get("brand_context"))}
Platform trends: {json.dumps(research_brief.get("platform_trends"))}
Industry trends: {json.dumps(research_brief.get("industry_trends"))}
Timing signal: {json.dumps(research_brief.get("timing_signal"))}

## Task
For EACH of these target platforms — {", ".join(platforms)} — produce a
distinct creative brief, genuinely adapted to that platform's norms,
audience expectations, and format conventions. Do not reuse the same
angle, hook, CTA, or tone across platforms — each platform's brief must
reflect how that platform is actually used.

Respond with a single JSON object whose keys are exactly the platform
names listed above, and whose values are objects with these string keys:
- "format": the post format (e.g. text_post, short_thread, image, carousel)
- "angle": the creative angle/strategy for this post
- "hook": the opening line/hook to grab attention
- "cta": the call to action
- "tone": the tone of voice for this platform

Respond with ONLY the JSON object. No markdown code fences, no extra text.
"""


def _generate_platform_briefs(
    brand: Brand, research_brief: dict[str, Any], platforms: list[str]
) -> dict[str, dict[str, str]]:
    """Calls LLMProvider exclusively through its interface (never a direct
    vendor SDK import) — same degrade-on-failure contract as
    research_engine.py: a broken/unconfigured LLM provider, or a response
    that doesn't parse into a usable brief, must never take the pipeline
    down with it, just fall back to a fixed per-platform template."""
    prompt = _build_prompt(brand, research_brief, platforms)
    try:
        response = get_llm_provider().complete(
            prompt=prompt, model=_default_model(), temperature=0.6
        )
        return _parse_platform_briefs(response.text, platforms)
    except Exception:
        logger.warning("Creative Engine LLM call/parse failed; using fallback briefs", exc_info=True)
        return {platform: _fallback_brief_for(platform) for platform in platforms}


def _calendar_event_for(post: Post, db: Session) -> ContentCalendarEvent | None:
    if post.calendar_event_id is None:
        return None
    return db.get(ContentCalendarEvent, post.calendar_event_id)


def _platforms_for(post: Post, db: Session, research_brief: dict[str, Any]) -> list[str]:
    """Prefers whatever platforms Research Engine already resolved (via
    research_brief["platform_trends"]'s keys) so the two stages always
    agree on which platforms this post targets. Falls back to the same
    Post -> ContentCalendarEvent -> SUPPORTED_PLATFORMS resolution
    research_engine.py uses, for callers that invoke this node directly
    without an upstream research_brief (e.g. unit tests)."""
    platform_trends = research_brief.get("platform_trends")
    if platform_trends:
        return list(platform_trends.keys())

    event = _calendar_event_for(post, db)
    if event is not None and event.target_platforms:
        return list(event.target_platforms)
    return list(SUPPORTED_PLATFORMS)


def _creative_brief(db: Session, post: Post, research_brief: dict[str, Any]) -> dict[str, Any]:
    brand = db.get(Brand, post.brand_id)
    if brand is None:
        raise CreativeEngineError(f"Creative Engine: no Brand found for post {post.id}")

    platforms = _platforms_for(post, db, research_brief)
    platform_briefs = _generate_platform_briefs(brand, research_brief, platforms)

    return {
        "post_id": str(post.id),
        "platforms": platform_briefs,
    }


def build_creative_node(db: Session | None):
    """Builds the real "creative" stage node function, closing over `db`.
    Mirrors research_engine.py's build_research_node factory shape/
    conventions exactly.

    `db` is accepted as possibly None so build_pipeline_graph(checkpointer)
    — with no `db` argument — still works for callers that only inspect
    the compiled graph's structure (nodes/edges) without ever streaming or
    invoking it; the resulting node just isn't runnable, and raises
    clearly if it ever is.
    """

    def _node(state: dict) -> dict:
        if db is None:
            raise RuntimeError(
                "Creative Engine node has no database session — "
                "build_pipeline_graph() must be called with db=<Session> "
                "to execute (not just inspect) the pipeline graph."
            )

        post = db.get(Post, uuid.UUID(state["post_id"]))
        if post is None:
            raise CreativeEngineError(
                f"Creative Engine: no Post found for post_id={state['post_id']!r}"
            )

        research_brief = state.get("research_brief") or {}
        brief = _creative_brief(db, post, research_brief)
        return {
            "completed_stages": [*state.get("completed_stages", []), "creative"],
            "creative_brief": brief,
        }

    _node.__name__ = "creative_node"
    return _node
