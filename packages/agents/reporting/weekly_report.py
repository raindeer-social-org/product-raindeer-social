"""Weekly AI-generated brand report — Issue #35.

A scheduled (Celery Beat, apps/api/worker.py) per-brand job that closes
the loop on #34's analytics aggregates: reads the past week's
per-platform totals/averages (apps/api/services/analytics_aggregation.py
— the same GROUP-BY-in-Postgres aggregation the analytics dashboard
endpoints use, apps/api/routers/analytics.py), asks an LLM to turn those
real numbers into a written summary + actionable recommendations, and
appends the result as an immutable Report row (apps/api/models/report.py)
per brand — same "append a row, never overwrite" convention AgentRun/
ReviewFeedback already establish.

Same interface-only contract as every other LLM-backed stage in this repo
(research_engine.py/creative_engine.py/generation_engine.py/
reviewer_engine.py): calls go through LLMProvider
(packages.integrations.registry.get_llm_provider()) exclusively — never a
direct vendor SDK import — with the model read fresh from
apps.api.config.get_settings().llm_default_model on every call, never a
hardcoded model slug. Same degrade-on-failure contract too: a broken/
unconfigured LLM provider, or a response that doesn't parse into a usable
report, must not take the weekly sweep down with it (one brand's failure
must not block any other brand's report) — it falls back to a
deterministic, numbers-only summary built directly from `metrics` rather
than raising, so even the fallback path genuinely "references actual
numbers, not generic filler" per #35's acceptance criteria.

Every call is logged as an AgentRun (agent_type=WEEKLY_REPORT). Unlike
the per-post pipeline stages, this job isn't tied to any single Post — it
runs once per brand over a date range — so AgentRun.post_id is left null
and brand_id/period bounds are carried in `input` instead (post_id
already tolerates null; it predates Post entirely, see
apps/api/models/agent_run.py).
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.models.agent_run import AgentRun, AgentType
from apps.api.models.brand import Brand
from apps.api.models.report import Report
from apps.api.services import analytics_aggregation
from packages.integrations.registry import get_llm_provider

logger = logging.getLogger(__name__)

# The report always covers the 7 days immediately before `period_end`
# (defaults to "now" — see generate_weekly_report below).
REPORT_PERIOD_DAYS = 7

# Rough, provider-agnostic per-token estimate used only to keep this
# module's diagnostic output populated — same convention (and same rate)
# as generation_engine.py/reviewer_engine.py's _COST_PER_1K_TOKENS, not
# tied to any specific model's actual price.
_COST_PER_1K_TOKENS = 0.002

_FALLBACK_RECOMMENDATION = (
    "Automated recommendations were unavailable this week (LLM provider "
    "error or unparseable response) — review the metrics above manually "
    "until the next scheduled report."
)


class WeeklyReportError(Exception):
    """Raised when the report can't be generated because the requested
    brand doesn't exist — a data/programming error, not a transient LLM
    failure, so unlike LLM call/parse failures this is not swallowed."""


def _default_model() -> str:
    """Reads LLM_DEFAULT_MODEL fresh on every call (not a module
    constant) so tests and per-environment overrides take effect without
    a reimport — same convention as every other LLM-backed stage."""
    return get_settings().llm_default_model


def _estimate_cost(tokens: int) -> float:
    return round((tokens / 1000) * _COST_PER_1K_TOKENS, 6)


def _strip_code_fence(text: str) -> str:
    cleaned = text.strip()
    if not cleaned.startswith("```"):
        return cleaned
    cleaned = cleaned.strip("`")
    if cleaned.startswith("json"):
        cleaned = cleaned[len("json"):]
    return cleaned.strip()


def _metrics_dict(summary: analytics_aggregation.BrandSummary) -> dict[str, Any]:
    """Plain-dict form of #34's BrandSummary dataclass — what both the
    LLM prompt and Report.metrics store, so the exact figures the prompt
    was given are also the exact figures persisted for later audit."""
    return {
        "post_count": summary.post_count,
        "platforms": [asdict(row) for row in summary.platforms],
        "overall": asdict(summary.overall),
    }


def _build_prompt(
    brand: Brand, metrics: dict[str, Any], period_start: datetime, period_end: datetime
) -> str:
    """Injects the *actual* aggregate numbers (not a description of where
    to find them) directly into the prompt text, per #35's explicit
    acceptance criteria that the generated summary must reference real
    figures rather than generic filler. `metrics` is the exact dict this
    module also persists onto Report.metrics, so a test can assert the
    same numbers both went into the prompt and came back out in the
    stored report."""
    overall = metrics["overall"]
    platforms_json = json.dumps(metrics["platforms"])

    return f"""You are a social media performance analyst writing a
concise weekly report for a brand manager. You are given this brand's
REAL, ACTUAL engagement metrics for the past week, computed directly
from recorded platform data. You MUST ground your summary in these exact
figures — cite specific numbers from the data below. Never write generic
filler like "engagement was steady" without a number attached; always
say things like "342 likes across 5 posts, up from the prior period" (if
a real number, not an invented one). Respond with strict JSON only — no
markdown, no commentary, no code fences.

## Brand
{brand.name} ({brand.industry or "unspecified industry"})

## Reporting period
{period_start.date().isoformat()} to {period_end.date().isoformat()}

## Real metrics for this period
Total posts with activity: {metrics["post_count"]}
Overall across all platforms: {overall["total_likes"]} likes,
{overall["total_comments"]} comments, {overall["total_shares"]} shares,
{overall["total_impressions"]} impressions, from
{overall["snapshot_count"]} recorded snapshots (average per snapshot:
{overall["average_likes"]:.2f} likes, {overall["average_comments"]:.2f}
comments, {overall["average_shares"]:.2f} shares,
{overall["average_impressions"]:.2f} impressions).

Per-platform breakdown (JSON, one entry per platform with totals and
averages): {platforms_json}

## Task
Write a `summary`: 2-4 sentences that explicitly cite the real numbers
above (totals and/or per-platform figures) and describe what happened
this period — which platform performed best/worst, any notable
patterns visible in the numbers, comparing platforms to each other using
the actual figures given. Then write `recommendations`: a list of 2-4
short, specific, actionable next steps genuinely grounded in this
period's numbers (e.g. which platform to invest more in, what content
pattern the numbers suggest worked) — never generic advice that could
apply to any brand's report.

Respond with a single JSON object of exactly this shape:
{{"summary": "<2-4 sentences citing real numbers>", "recommendations":
["<specific recommendation 1>", "<specific recommendation 2>", ...]}}

Respond with ONLY the JSON object. No markdown code fences, no extra text.
"""


def _parse_report(text: str) -> tuple[str, list[str]]:
    parsed = json.loads(_strip_code_fence(text))
    if not isinstance(parsed, dict):
        raise ValueError("Weekly Report LLM output was valid JSON but not an object")

    summary = parsed.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise ValueError("Weekly Report LLM output missing 'summary'")

    recommendations = parsed.get("recommendations")
    if not isinstance(recommendations, list) or not recommendations:
        raise ValueError("Weekly Report LLM output missing 'recommendations'")

    return summary.strip(), [str(item) for item in recommendations]


def _fallback_report(
    brand: Brand, metrics: dict[str, Any], period_start: datetime, period_end: datetime
) -> tuple[str, list[str]]:
    """Used only when the LLM call/parse fails (see module docstring) —
    unlike reviewer_engine.py's fallback (a fixed score with no real
    content), this fallback is still built directly from `metrics`, so
    even a degraded report cites real recorded numbers rather than
    generic placeholder text."""
    overall = metrics["overall"]
    summary = (
        f"Weekly report for {brand.name}, {period_start.date().isoformat()} to "
        f"{period_end.date().isoformat()}: {metrics['post_count']} post(s) with "
        f"activity recorded {overall['total_likes']} likes, "
        f"{overall['total_comments']} comments, {overall['total_shares']} shares, "
        f"and {overall['total_impressions']} impressions across "
        f"{overall['snapshot_count']} recorded snapshots. Automated narrative "
        "generation was unavailable this week (LLM provider error or "
        "unparseable response) — the figures above are the real recorded "
        "totals for this period."
    )
    return summary, [_FALLBACK_RECOMMENDATION]


def _generate_content(
    brand: Brand, metrics: dict[str, Any], period_start: datetime, period_end: datetime
) -> tuple[str, list[str], str, int]:
    """Calls LLMProvider exclusively through its interface (never a
    direct vendor SDK import) — same degrade-on-failure contract as
    reviewer_engine.py/generation_engine.py: a broken/unconfigured LLM
    provider, or a response that doesn't parse into a usable report, must
    never take the weekly sweep down with it, just fall back to a
    deterministic numbers-only summary."""
    model = _default_model()
    prompt = _build_prompt(brand, metrics, period_start, period_end)
    try:
        response = get_llm_provider().complete(prompt=prompt, model=model, temperature=0.3)
        summary, recommendations = _parse_report(response.text)
        return summary, recommendations, response.model, response.input_tokens + response.output_tokens
    except Exception:
        logger.warning("Weekly Report LLM call/parse failed; using fallback report", exc_info=True)
        summary, recommendations = _fallback_report(brand, metrics, period_start, period_end)
        return summary, recommendations, model, 0


def generate_weekly_report(
    db: Session, brand_id: uuid.UUID, period_end: datetime | None = None
) -> Report:
    """Generates and persists one weekly Report row for `brand_id`,
    covering the REPORT_PERIOD_DAYS days immediately before `period_end`
    (defaults to now, UTC). Also appends the AgentRun log row (see module
    docstring). Flushes but does not commit — same convention as
    reviewer_engine.py's _reviewer_output and scheduling_suggestion.py:
    callers (a Celery task, a test) control the transaction boundary.

    Raises WeeklyReportError if brand_id doesn't resolve to a real Brand.
    """
    brand = db.get(Brand, brand_id)
    if brand is None:
        raise WeeklyReportError(f"Weekly Report: no Brand found for brand_id={brand_id}")

    resolved_end = period_end or datetime.now(timezone.utc)
    if resolved_end.tzinfo is None:
        resolved_end = resolved_end.replace(tzinfo=timezone.utc)
    resolved_start = resolved_end - timedelta(days=REPORT_PERIOD_DAYS)

    brand_summary = analytics_aggregation.get_brand_summary(
        db, brand_id, resolved_start, resolved_end
    )
    metrics = _metrics_dict(brand_summary)

    start = time.perf_counter()
    summary_text, recommendations, model, tokens = _generate_content(
        brand, metrics, resolved_start, resolved_end
    )
    latency_ms = (time.perf_counter() - start) * 1000
    cost = _estimate_cost(tokens)

    # Append an immutable Report row — never overwritten, same "append a
    # log row" convention AgentRun/ReviewFeedback already establish (see
    # module docstring).
    report = Report(
        brand_id=brand_id,
        period_start=resolved_start,
        period_end=resolved_end,
        summary=summary_text,
        recommendations=recommendations,
        metrics=metrics,
        model=model,
    )
    db.add(report)
    db.flush()
    db.refresh(report)

    run = AgentRun(
        post_id=None,
        agent_type=AgentType.WEEKLY_REPORT,
        input={
            "brand_id": str(brand_id),
            "period_start": resolved_start.isoformat(),
            "period_end": resolved_end.isoformat(),
        },
        output={
            "report_id": str(report.id),
            "summary": summary_text,
            "recommendations": recommendations,
            "metrics": metrics,
        },
        model=model,
        tokens=tokens,
        cost=cost,
        latency_ms=latency_ms,
    )
    db.add(run)
    db.flush()

    return report
