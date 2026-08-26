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

Predicted engagement (Issue #107): alongside its brand-alignment/
compliance/platform-fit scoring, this node now also predicts, per
platform, how well the draft is likely to perform (0-100 plus a short
natural-language reasoning string). Grounded in the brand's actual
historical performance where it exists: _historical_engagement_safely
computes each platform's average engagement rate ((likes + comments +
shares) / impressions) across the brand's own past EngagementSnapshot
rows (Issue #33/#34) and hands the real numbers to the LLM as grounding
data in the same prompt, alongside brand_context — the same "give the
LLM real reference material rather than have it guess" pattern this node
already uses for brand voice. When a platform doesn't yet have enough
history (_MIN_HISTORICAL_SAMPLES), the prompt says so explicitly and asks
for a pure qualitative estimate instead. One LLM call still produces
every field for a platform (score/verdict/issues/suggested_edits plus
predicted_engagement_score/predicted_engagement_reasoning) — same
all-or-nothing parse/fallback contract as the rest of this module.
"""

import json
import logging
import time
import uuid
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.models.brand import Brand
from apps.api.models.engagement_snapshot import EngagementSnapshot
from apps.api.models.post import Post
from apps.api.models.review_feedback import ReviewFeedback, ReviewSource, ReviewVerdict
from apps.api.services.brand_retrieval import get_relevant_brand_context
from packages.integrations.registry import get_llm_provider

logger = logging.getLogger(__name__)

BRAND_CONTEXT_TOP_K = 3
BRAND_CONTEXT_QUERY = "brand voice, tone, compliance guidelines, and platform norms"

# A brand needs at least this many past snapshot rows with real impressions
# on a given platform before its historical engagement rate is trusted
# enough to ground the LLM's prediction — a 1-2 post sample is too noisy to
# hand over as if it were a reliable benchmark.
_MIN_HISTORICAL_SAMPLES = 3

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
_FALLBACK_ENGAGEMENT_SCORE = 50.0
_FALLBACK_ENGAGEMENT_REASONING = (
    "Automated engagement prediction unavailable (LLM provider error or "
    "unparseable response) — could not estimate predicted engagement for "
    "this draft."
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


def _historical_engagement_stats(db: Session, brand_id: Any, platform: str) -> dict[str, Any] | None:
    """The brand's own average engagement rate on `platform` — (likes +
    comments + shares) / impressions, averaged over every past
    EngagementSnapshot row for this brand on this platform that actually
    has impressions to divide by — plus how many snapshots that average is
    built from. Computed as a single SQL AVG/COUNT (same "aggregate in
    Postgres, don't fetch-and-reduce in Python" convention
    analytics_aggregation.py establishes), returning None when there isn't
    at least _MIN_HISTORICAL_SAMPLES worth of data to trust."""
    row = (
        db.query(
            func.count(EngagementSnapshot.id).label("sample_size"),
            func.avg(
                (EngagementSnapshot.likes + EngagementSnapshot.comments + EngagementSnapshot.shares)
                * 1.0
                / EngagementSnapshot.impressions
            ).label("avg_rate"),
        )
        .join(Post, Post.id == EngagementSnapshot.post_id)
        .filter(
            Post.brand_id == brand_id,
            EngagementSnapshot.platform == platform,
            EngagementSnapshot.impressions > 0,
        )
        .one()
    )
    sample_size = int(row.sample_size or 0)
    if sample_size < _MIN_HISTORICAL_SAMPLES or row.avg_rate is None:
        return None
    return {"sample_size": sample_size, "average_engagement_rate": float(row.avg_rate)}


def _historical_engagement_safely(
    db: Session, brand_id: Any, platforms: list[str]
) -> dict[str, dict[str, Any] | None]:
    """Same degrade-on-failure contract as _brand_context_safely: a broken
    query here (e.g. a transient DB issue) must not take the whole
    Reviewer Engine node down — it just means this run falls back to a
    pure LLM estimate for every platform, same as a brand with no history
    yet."""
    stats: dict[str, dict[str, Any] | None] = {}
    for platform in platforms:
        try:
            stats[platform] = _historical_engagement_stats(db, brand_id, platform)
        except Exception:
            logger.warning(
                "Reviewer Engine historical engagement lookup failed for platform %r",
                platform,
                exc_info=True,
            )
            stats[platform] = None
    return stats


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

    # Issue #107 — predicted engagement is required per platform, same
    # all-or-nothing parse contract as the fields above: a response that
    # skips it degrades the whole review to the fixed fallback rather than
    # silently shipping a review with no engagement prediction.
    predicted_engagement_score = _clamp_score(entry.get("predicted_engagement_score"))
    predicted_engagement_reasoning = entry.get("predicted_engagement_reasoning")
    if not isinstance(predicted_engagement_reasoning, str) or not predicted_engagement_reasoning.strip():
        raise ValueError("missing 'predicted_engagement_reasoning'")

    return {
        "score": score,
        "verdict": verdict.value,
        "issues": [str(issue) for issue in issues],
        "suggested_edits": suggested_edits.strip(),
        "predicted_engagement_score": predicted_engagement_score,
        "predicted_engagement_reasoning": predicted_engagement_reasoning.strip(),
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
            "predicted_engagement_score": _FALLBACK_ENGAGEMENT_SCORE,
            "predicted_engagement_reasoning": _FALLBACK_ENGAGEMENT_REASONING,
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


def _format_historical_engagement(historical_engagement: dict[str, dict[str, Any] | None], platforms: list[str]) -> str:
    lines = []
    for platform in platforms:
        stats = historical_engagement.get(platform)
        if stats is None:
            lines.append(
                f"- {platform}: insufficient historical data (fewer than "
                f"{_MIN_HISTORICAL_SAMPLES} past posts with impressions) — "
                "give a pure qualitative estimate based on the draft "
                "content and brand context instead."
            )
        else:
            lines.append(
                f"- {platform}: {stats['sample_size']} historical posts, "
                f"average engagement rate {stats['average_engagement_rate'] * 100:.2f}% "
                "((likes + comments + shares) / impressions) — ground your "
                "prediction in this real number and say so in your reasoning."
            )
    return "\n".join(lines)


def _build_prompt(
    brand: Brand,
    brand_context: list[dict],
    body_text: dict[str, Any],
    platforms: list[str],
    historical_engagement: dict[str, dict[str, Any] | None],
) -> str:
    industry = brand.industry or brand.name
    tone_descriptors = brand.tone_descriptors or []
    target_audience = brand.target_audience or "not specified"
    content_json = json.dumps({platform: body_text.get(platform, "") for platform in platforms})
    historical_engagement_text = _format_historical_engagement(historical_engagement, platforms)

    return f"""You are a meticulous brand-voice, compliance, and
platform-fit reviewer. You are given a finished draft post and must
critically evaluate it BEFORE a human ever sees it — your job is to catch
obvious misses so human review time goes toward judgment calls, not
basic problems. Respond with strict JSON only — no markdown, no
commentary, no code fences.

## Brand
{brand.name} ({industry})
Tone descriptors: {json.dumps(tone_descriptors)}
Target audience: {target_audience}

## Brand voice / compliance reference material
{json.dumps(brand_context)}

## Draft post copy to review, per platform
{content_json}

## Historical engagement performance, per platform
{historical_engagement_text}

## Task
For EACH of these target platforms — {", ".join(platforms)} — critically
evaluate that platform's draft copy against:
1. Brand voice alignment — does it match the brand's tone descriptors and
   the reference material above, or does it read generic/off-brand/
   inconsistent with how this brand actually talks?
2. Compliance and safety — unsubstantiated claims, prohibited or risky
   language, missing required disclosures, anything a legal/compliance
   reviewer would flag.
3. Platform fit — does it respect that platform's norms (length,
   formality, format conventions, audience expectations)?
4. Predicted engagement — using the historical engagement performance
   data above when it's available for that platform (cite the actual
   numbers in your reasoning), or your best qualitative estimate when
   historical data is insufficient, predict how well THIS draft will
   perform relative to typical performance.

Score each platform from 0 (severely off-brand, non-compliant, or wrong
for the platform) to 100 (fully on-brand, compliant, and platform-
appropriate). Assign a verdict: "approve" for a score of 80 or higher
(ready as-is), "revise" for 50-79 (fixable issues), or "reject" below 50
(fundamental problems). List the SPECIFIC issues you found — never a
generic "needs improvement" — and give SPECIFIC, actionable suggested
edits: concrete rewording, a concrete fix, or a concrete rewritten
passage, tied to what is actually wrong with THIS draft. Separately,
score predicted engagement from 0 (very low predicted engagement) to 100
(very high predicted engagement) and give a short (1-3 sentence)
natural-language reasoning string for that prediction.

Respond with a single JSON object of exactly this shape:
{{"platforms": {{"<platform>": {{"score": <number 0-100>, "verdict":
"approve"|"revise"|"reject", "issues": ["specific issue 1", "specific
issue 2"], "suggested_edits": "specific, actionable edit instructions or
a concrete rewritten passage", "predicted_engagement_score": <number
0-100>, "predicted_engagement_reasoning": "short reasoning, citing
historical numbers when they were provided above"}}, ...}}}}

Respond with ONLY the JSON object. No markdown code fences, no extra text.
"""


def _review_content(
    brand: Brand,
    brand_context: list[dict],
    body_text: dict[str, Any],
    platforms: list[str],
    historical_engagement: dict[str, dict[str, Any] | None],
) -> tuple[dict[str, dict[str, Any]], str, int]:
    """Calls LLMProvider exclusively through its interface (never a direct
    vendor SDK import) — same degrade-on-failure contract as
    research_engine.py/creative_engine.py/generation_engine.py: a broken/
    unconfigured LLM provider, or a response that doesn't parse into a
    usable review, must never take the pipeline down with it, just fall
    back to a fixed "needs manual review" verdict."""
    model = _default_model()
    prompt = _build_prompt(brand, brand_context, body_text, platforms, historical_engagement)
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


def _overall_predicted_engagement(platform_reviews: dict[str, dict[str, Any]]) -> tuple[float, str]:
    """Unlike the brand-alignment score/verdict (worst platform wins,
    since a single off-brand platform is a real risk that must not be
    masked), predicted engagement isn't a risk signal — it's averaged
    across platforms so a strong-predicted-engagement platform and a
    weak-predicted-engagement one net out to a representative overall
    number rather than the post being judged solely by its worst channel.
    Reasoning is the single platform's own reasoning when there's only
    one, otherwise each platform's reasoning prefixed by its name so the
    UI/API can show one short string without losing per-platform nuance."""
    scores = [entry["predicted_engagement_score"] for entry in platform_reviews.values()]
    overall_score = round(sum(scores) / len(scores), 1)

    if len(platform_reviews) == 1:
        (only_entry,) = platform_reviews.values()
        reasoning = only_entry["predicted_engagement_reasoning"]
    else:
        reasoning = "; ".join(
            f"{platform}: {entry['predicted_engagement_reasoning']}"
            for platform, entry in platform_reviews.items()
        )
    return overall_score, reasoning


def _reviewer_output(db: Session, post: Post) -> dict[str, Any]:
    brand = db.get(Brand, post.brand_id)
    if brand is None:
        raise ReviewerEngineError(f"Reviewer Engine: no Brand found for post {post.id}")

    body_text = post.body_text or {}
    platforms = _platforms_for(body_text)
    brand_context = _brand_context_safely(db, brand.id)
    historical_engagement = _historical_engagement_safely(db, brand.id, platforms)

    start = time.perf_counter()
    platform_reviews, model, tokens = _review_content(
        brand, brand_context, body_text, platforms, historical_engagement
    )
    latency_ms = (time.perf_counter() - start) * 1000

    overall_score, overall_verdict = _overall_from_platforms(platform_reviews)
    predicted_engagement_score, predicted_engagement_reasoning = _overall_predicted_engagement(
        platform_reviews
    )
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
        predicted_engagement_score=predicted_engagement_score,
        predicted_engagement_reasoning=predicted_engagement_reasoning,
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
        "predicted_engagement_score": predicted_engagement_score,
        "predicted_engagement_reasoning": predicted_engagement_reasoning,
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
