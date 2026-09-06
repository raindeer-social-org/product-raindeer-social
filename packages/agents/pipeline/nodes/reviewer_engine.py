"""Reviewer Engine — Issue #24, the fourth real (non-stub) stage in the
per-post pipeline graph (packages/agents/pipeline/graph.py), running right
after Generation (#21).

An automated brand-alignment, compliance, and platform-fit pass over the
Generation Engine's output (see
packages/agents/pipeline/nodes/generation_engine.py — Post.body_text, a
dict keyed by platform) before a human ever sees the draft, so human
review time (#25) goes toward judgment calls, not catching obvious
misses. #25's human-review UI surfaces this AI review alongside the
human's own — the human isn't reviewing blind.

Same interface-only contract as research_engine.py/creative_engine.py/
generation_engine.py: scoring goes through LLMProvider
(packages/integrations/registry.get_llm_provider()) exclusively — never a
direct vendor SDK import — with the model read fresh from
apps.api.config.get_settings().llm_default_model on every call, never a
hardcoded model slug. Same degrade-on-failure contract too: a broken/
unconfigured LLM provider, or a response that doesn't parse into a usable
review, must not take the pipeline down with it — it falls back to a
fixed "needs manual review" verdict rather than raising.

Brand grounding: pulls the brand's tone/audience fields directly off the
Brand row (same as creative_engine.py) plus #16's pgvector retrieval
helper (apps.api.services.brand_retrieval.get_relevant_brand_context) for
the deeper brand-voice/compliance reference material a plain tone
descriptor list doesn't capture — reused as-is, with the same
degrade-gracefully wrapper research_engine.py already established
(_brand_context_safely), since a broken embedding provider must not take
this node down either.

Output — a ReviewFeedback row (apps/api/models/review_feedback.py) per
review pass, source=ai_reviewer, mirroring the "append an immutable row
per evaluation" convention AgentRun/PostVersion already establish: never
overwritten, so a Post's review history (AI now, human via #25 later)
reads as one ordered log. The row carries one overall score/verdict for
the whole Post (never just a bare number) plus per-platform score/
verdict/issues/specific suggested edits packed into `comments` — the
worst-scoring platform sets the overall score, and the most severe
per-platform verdict sets the overall verdict, so a single badly off-
brand platform can't be masked by an on-brand one elsewhere in the same
post.

Mirrors research_engine.py/creative_engine.py/generation_engine.py's
shape: a factory, build_reviewer_node(db), closing over a caller-supplied
Session (needed to resolve Post -> Brand, same as the earlier stages),
returning the actual LangGraph node function. graph.py's
build_pipeline_graph() calls this factory for the "reviewer" stage only.
"""

import json
import logging
import time
import uuid
from typing import Any

from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.models.brand import Brand
from apps.api.models.post import Post
from apps.api.models.review_feedback import ReviewFeedback, ReviewSource, ReviewVerdict
from apps.api.services.brand_retrieval import get_relevant_brand_context
from packages.integrations.registry import get_llm_provider

logger = logging.getLogger(__name__)

BRAND_CONTEXT_TOP_K = 3
BRAND_CONTEXT_QUERY = "brand voice, tone, compliance guidelines, and platform norms"

# Worst-verdict-wins ordering used to derive one overall verdict from
# several per-platform verdicts (see module docstring).
_VERDICT_SEVERITY: dict[ReviewVerdict, int] = {
    ReviewVerdict.APPROVE: 0,
    ReviewVerdict.REVISE: 1,
    ReviewVerdict.REJECT: 2,
}

# Used only when the LLM call/parse fails (see module docstring) — a
# neutral-but-cautious fallback (REVISE, not APPROVE) so a broken reviewer
# never silently waves a draft through, and comments that clearly explain
# *why* this row is a fallback rather than a real automated review.
_FALLBACK_SCORE = 50.0
_FALLBACK_VERDICT = ReviewVerdict.REVISE
_FALLBACK_ISSUE = (
    "Automated review unavailable (LLM provider error or unparseable "
    "response) — brand voice, compliance, and platform fit could not be "
    "verified automatically."
)
_FALLBACK_SUGGESTED_EDITS = (
    "The Reviewer Engine could not complete an automated pass on this "
    "draft. Route this post to manual human review before it proceeds "
    "rather than relying on this fallback score."
)

# Rough, provider-agnostic per-token estimate used only to keep this
# node's diagnostic output populated, same convention (and same rate) as
# generation_engine.py's _COST_PER_1K_TOKENS — not tied to any specific
# model's actual price.
_COST_PER_1K_TOKENS = 0.002


class ReviewerEngineError(Exception):
    """Raised when the reviewer node can't resolve the Post/Brand it was
    asked to review — a programming/data error (missing row), not a
    transient LLM-provider failure, so unlike LLM failures this is not
    swallowed."""


def _default_model() -> str:
    """Reads LLM_DEFAULT_MODEL fresh on every call (not a module constant)
    so tests and per-environment overrides take effect without a reimport
    — same convention as research_engine.py/creative_engine.py/
    generation_engine.py."""
    return get_settings().llm_default_model


def _estimate_cost(tokens: int) -> float:
    return round((tokens / 1000) * _COST_PER_1K_TOKENS, 6)


def _brand_context_safely(db: Session, brand_id: Any) -> list[dict]:
    """Same degrade-on-failure contract as research_engine.py's
    _brand_context_safely: a broken embedding provider (missing/invalid
    API key, network issue, etc.) must not take the whole Reviewer Engine
    node — and therefore the whole pipeline run — down with it."""
    try:
        return get_relevant_brand_context(
            db, brand_id, query=BRAND_CONTEXT_QUERY, top_k=BRAND_CONTEXT_TOP_K
        )
    except Exception:
        logger.warning("Reviewer Engine brand context retrieval failed", exc_info=True)
        return []


def _strip_code_fence(text: str) -> str:
    cleaned = text.strip()
    if not cleaned.startswith("```"):
        return cleaned
    cleaned = cleaned.strip("`")
    if cleaned.startswith("json"):
        cleaned = cleaned[len("json"):]
    return cleaned.strip()


def _clamp_score(value: Any) -> float:
    score = float(value)  # raises TypeError/ValueError for non-numeric input
    return max(0.0, min(100.0, score))


def _parse_verdict(value: Any) -> ReviewVerdict:
    return ReviewVerdict(str(value).strip().lower())  # raises ValueError if unrecognized


def _parse_platform_review(entry: dict) -> dict[str, Any]:
    score = _clamp_score(entry.get("score"))
    verdict = _parse_verdict(entry.get("verdict"))

    # An empty issues list is legitimate — an on-brand, compliant,
    # platform-fit platform genuinely has nothing to flag. Only the type
    # is validated here; "no issues found" must not be treated as a
    # parse failure.
    issues = entry.get("issues")
    if not isinstance(issues, list):
        raise ValueError("'issues' must be a list")

    suggested_edits = entry.get("suggested_edits")
    if not isinstance(suggested_edits, str) or not suggested_edits.strip():
        raise ValueError("missing 'suggested_edits'")

    return {
        "score": score,
        "verdict": verdict.value,
        "issues": [str(issue) for issue in issues],
        "suggested_edits": suggested_edits.strip(),
    }


def _parse_review(text: str, platforms: list[str]) -> dict[str, dict[str, Any]]:
    parsed = json.loads(_strip_code_fence(text))
    if not isinstance(parsed, dict):
        raise ValueError("Reviewer Engine LLM output was valid JSON but not an object")

    platforms_entry = parsed.get("platforms")
    if not isinstance(platforms_entry, dict):
        raise ValueError("Reviewer Engine LLM output missing 'platforms'")

    platform_reviews: dict[str, dict[str, Any]] = {}
    for platform in platforms:
        entry = platforms_entry.get(platform)
        if not isinstance(entry, dict):
            raise ValueError(f"Reviewer Engine LLM output missing review for platform {platform!r}")
        platform_reviews[platform] = _parse_platform_review(entry)
    return platform_reviews


def _fallback_review(platforms: list[str]) -> dict[str, dict[str, Any]]:
    return {
        platform: {
            "score": _FALLBACK_SCORE,
            "verdict": _FALLBACK_VERDICT.value,
            "issues": [_FALLBACK_ISSUE],
            "suggested_edits": _FALLBACK_SUGGESTED_EDITS,
        }
        for platform in platforms
    }


def _platforms_for(body_text: dict[str, Any]) -> list[str]:
    """Reviews whatever platforms Generation Engine actually wrote copy
    for (Post.body_text's keys). Falls back to a single generic platform
    so this node is still exercisable when invoked directly (e.g. a unit
    test) against a Post with no body_text yet — same fallback shape
    generation_engine.py's _platforms_for uses for creative_brief."""
    if not body_text:
        return ["default"]
    return list(body_text.keys())


def _build_prompt(
    brand: Brand,
    brand_context: list[dict],
    body_text: dict[str, Any],
    platforms: list[str],
) -> str:
    industry = brand.industry or brand.name
    tone_descriptors = brand.tone_descriptors or []
    target_audience = brand.target_audience or "not specified"
    content_json = json.dumps({platform: body_text.get(platform, "") for platform in platforms})

    return f"""You are Neer, a meticulous brand-voice, compliance, and
platform-fit reviewer — the last automated check before a human ever
sees this draft. You are notoriously hard to impress: generic AI-sounding
copy fails your review even if nothing is technically "wrong" with it,
because bland, forgettable copy is itself a brand-fit failure. Your job
is to catch obvious misses so human review time goes toward judgment
calls, not basic problems. Respond with strict JSON only — no markdown,
no commentary, no code fences.

## Brand
{brand.name} ({industry})
Tone descriptors: {json.dumps(tone_descriptors)}
Target audience: {target_audience}

## Brand voice / compliance reference material
{json.dumps(brand_context)}

## Draft post copy to review, per platform
{content_json}

## Task
For EACH of these target platforms — {", ".join(platforms)} — critically
evaluate that platform's draft copy against:
1. Brand voice alignment — does it match the brand's tone descriptors and
   the reference material above, or does it read generic/off-brand/
   inconsistent with how this brand actually talks?
2. Genericness / "AI slop" check — could this exact copy be pasted onto a
   different, unrelated brand's post with only the name swapped and no
   one would notice? If yes, that alone justifies a "revise" or lower,
   even with zero compliance issues — flag it as an issue by name (e.g.
   "hook is a generic template, not specific to this brand/post") and
   give a suggested edit that adds the missing specificity.
3. Compliance and safety — unsubstantiated claims, prohibited or risky
   language, missing required disclosures, anything a legal/compliance
   reviewer would flag.
4. Platform fit — does it respect that platform's norms (length,
   formality, hashtag/emoji conventions, whether the hook earns attention
   in the first line, audience expectations)?

Score each platform from 0 (severely off-brand, non-compliant, or wrong
for the platform) to 100 (fully on-brand, compliant, specific, and
platform-appropriate). Assign a verdict: "approve" for a score of 80 or
higher (ready as-is), "revise" for 50-79 (fixable issues), or "reject"
below 50 (fundamental problems, including copy so generic it doesn't
represent this brand at all). List the SPECIFIC issues you found — never
a generic "needs improvement" — and give SPECIFIC, actionable suggested
edits: concrete rewording, a concrete fix, or a concrete rewritten
passage, tied to what is actually wrong with THIS draft. A reviewer
reading only your suggested_edits should be able to fix the draft without
re-reading it.

Respond with a single JSON object of exactly this shape:
{{"platforms": {{"<platform>": {{"score": <number 0-100>, "verdict":
"approve"|"revise"|"reject", "issues": ["specific issue 1", "specific
issue 2"], "suggested_edits": "specific, actionable edit instructions or
a concrete rewritten passage"}}, ...}}}}

Respond with ONLY the JSON object. No markdown code fences, no extra text.
"""


def _review_content(
    brand: Brand, brand_context: list[dict], body_text: dict[str, Any], platforms: list[str]
) -> tuple[dict[str, dict[str, Any]], str, int]:
    """Calls LLMProvider exclusively through its interface (never a direct
    vendor SDK import) — same degrade-on-failure contract as
    research_engine.py/creative_engine.py/generation_engine.py: a broken/
    unconfigured LLM provider, or a response that doesn't parse into a
    usable review, must never take the pipeline down with it, just fall
    back to a fixed "needs manual review" verdict."""
    model = _default_model()
    prompt = _build_prompt(brand, brand_context, body_text, platforms)
    try:
        response = get_llm_provider().complete(prompt=prompt, model=model, temperature=0.2)
        platform_reviews = _parse_review(response.text, platforms)
        return platform_reviews, response.model, response.input_tokens + response.output_tokens
    except Exception:
        logger.warning("Reviewer Engine LLM call/parse failed; using fallback review", exc_info=True)
        return _fallback_review(platforms), model, 0


def _overall_from_platforms(platform_reviews: dict[str, dict[str, Any]]) -> tuple[float, ReviewVerdict]:
    """The worst-scoring platform sets the overall score, and the most
    severe per-platform verdict sets the overall verdict (see module
    docstring) — a single badly off-brand platform must not be masked by
    an on-brand one elsewhere in the same post."""
    scores = [entry["score"] for entry in platform_reviews.values()]
    verdicts = [ReviewVerdict(entry["verdict"]) for entry in platform_reviews.values()]
    overall_score = min(scores)
    overall_verdict = max(verdicts, key=lambda v: _VERDICT_SEVERITY[v])
    return overall_score, overall_verdict


def _reviewer_output(db: Session, post: Post) -> dict[str, Any]:
    brand = db.get(Brand, post.brand_id)
    if brand is None:
        raise ReviewerEngineError(f"Reviewer Engine: no Brand found for post {post.id}")

    body_text = post.body_text or {}
    platforms = _platforms_for(body_text)
    brand_context = _brand_context_safely(db, brand.id)

    start = time.perf_counter()
    platform_reviews, model, tokens = _review_content(brand, brand_context, body_text, platforms)
    latency_ms = (time.perf_counter() - start) * 1000

    overall_score, overall_verdict = _overall_from_platforms(platform_reviews)
    cost = _estimate_cost(tokens)

    # Append an immutable ReviewFeedback row for this review pass — never
    # overwritten, same "append a log row" convention AgentRun/PostVersion
    # already establish (see module docstring).
    feedback = ReviewFeedback(
        post_id=post.id,
        source=ReviewSource.AI_REVIEWER,
        score=overall_score,
        verdict=overall_verdict,
        comments={"platforms": platform_reviews, "model": model},
    )
    db.add(feedback)
    db.flush()
    db.refresh(feedback)

    return {
        "post_id": str(post.id),
        "review_feedback_id": str(feedback.id),
        "score": overall_score,
        "verdict": overall_verdict.value,
        "platforms": platform_reviews,
        "model": model,
        "tokens": tokens,
        "cost": cost,
        "latency_ms": latency_ms,
    }


def build_reviewer_node(db: Session | None):
    """Builds the real "reviewer" stage node function, closing over `db`.
    Mirrors research_engine.py/creative_engine.py/generation_engine.py's
    factory shape exactly.

    `db` is accepted as possibly None so build_pipeline_graph(checkpointer)
    — with no `db` argument — still works for callers that only inspect
    the compiled graph's structure (nodes/edges) without ever streaming or
    invoking it; the resulting node just isn't runnable, and raises
    clearly if it ever is.
    """

    def _node(state: dict) -> dict:
        if db is None:
            raise RuntimeError(
                "Reviewer Engine node has no database session — "
                "build_pipeline_graph() must be called with db=<Session> "
                "to execute (not just inspect) the pipeline graph."
            )

        post = db.get(Post, uuid.UUID(state["post_id"]))
        if post is None:
            raise ReviewerEngineError(
                f"Reviewer Engine: no Post found for post_id={state['post_id']!r}"
            )

        output = _reviewer_output(db, post)
        return {
            "completed_stages": [*state.get("completed_stages", []), "reviewer"],
            "review_output": output,
        }

    _node.__name__ = "reviewer_node"
    return _node
