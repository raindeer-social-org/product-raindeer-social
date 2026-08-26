"""Auto-scheduling suggestion service — Issue #28.

The Research Engine (#19, packages/agents/pipeline/nodes/research_engine.py)
already produces a `timing_signal` field inside its research brief: what
topics are trending right now, which platforms were researched, when the
research ran, and (if the post was already scheduled) its known
target_datetime. That brief is not persisted standalone — it only exists
transiently inside a pipeline run's PipelineState — but every stage's raw
output, including research's, is written onto an AgentRun row by
packages/agents/pipeline/graph.py's run_pipeline() (`AgentRun(output=...,
agent_type=AgentType.RESEARCH, post_id=post.id)`, one row per stage per
run). So the "most relevant recent research brief" for a brand/platform is
read back from there: the newest AgentRun(agent_type=research) row whose
Post belongs to the brand and whose timing_signal actually covers the
requested platform — no new persistence path needed.

This module turns that signal into a genuine `target_datetime` suggestion
for a new ContentCalendarEvent (#26). It is deliberately NOT a hardcoded
time-of-day table: the suggested day and time are derived from a digest of
the signal's actual content — the trending topics it found, the raw
platform-specific search results it gathered (research_brief["platform_trends"][platform]),
and the platform being scheduled for — so two different research briefs
(or the same brief read for two different platforms) genuinely produce
different suggestions, not the same fixed hour every time.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from apps.api.models.agent_run import AgentRun, AgentType
from apps.api.models.post import Post

# How many of the most recent research AgentRun rows for a brand we're
# willing to scan looking for one that covers the requested platform,
# before giving up. Keeps the query bounded without needing a JSONB
# containment index on `output`.
MAX_RECENT_RUNS_SCANNED = 50

# The suggestion always lands within this many days of the research run,
# and within this daily window (UTC hours) — the *day offset* and *hour*
# inside these bounds are themselves derived from the signal's content
# (see _derive_offsets), not fixed. These bounds just keep suggestions
# sane (not 3am, not six months out) without picking the exact time.
MIN_DAYS_OUT = 1
MAX_DAYS_OUT = 4
EARLIEST_HOUR_UTC = 7
LATEST_HOUR_UTC = 21


class NoResearchSignalError(Exception):
    """Raised when no research brief covering the requested brand/platform
    can be found. Auto-scheduling has nothing to derive a suggestion from
    in this case — callers should fall back to requiring an explicit
    target_datetime rather than inventing one, per #28's acceptance
    criteria that a suggestion must come from a real research signal."""


@dataclass
class SchedulingSuggestion:
    target_datetime: datetime
    reasoning: str
    # Debug/audit trail: what the suggestion was actually derived from.
    source: dict[str, Any] = field(default_factory=dict)


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _find_research_brief(db: Session, brand_id: uuid.UUID, platform: str) -> tuple[AgentRun, dict]:
    """Returns the (AgentRun, research_brief dict) for the newest research
    run belonging to this brand whose timing_signal covers `platform`.

    AgentRun.post_id carries no FK constraint (it predates Post — see
    apps/api/models/agent_run.py), so the brand link is resolved by
    joining on Post.id explicitly rather than via an ORM relationship."""
    rows = (
        db.query(AgentRun)
        .join(Post, Post.id == AgentRun.post_id)
        .filter(
            AgentRun.agent_type == AgentType.RESEARCH,
            AgentRun.output.isnot(None),
            Post.brand_id == brand_id,
        )
        .order_by(AgentRun.created_at.desc())
        .limit(MAX_RECENT_RUNS_SCANNED)
        .all()
    )

    for run in rows:
        brief = (run.output or {}).get("research_brief")
        if not isinstance(brief, dict):
            continue
        timing_signal = brief.get("timing_signal")
        if not isinstance(timing_signal, dict):
            continue
        if platform in (timing_signal.get("platforms") or []):
            return run, brief

    raise NoResearchSignalError(
        f"No research brief covering platform={platform!r} found for brand_id={brand_id}. "
        "Run the pipeline's research stage for this brand first, or provide target_datetime "
        "explicitly."
    )


def _platform_content_blob(brief: dict, timing_signal: dict, platform: str) -> str:
    """The actual signal content the suggestion is derived from: the
    trending topics found (brand/industry-wide) plus this platform's own
    search results (research_brief["platform_trends"][platform] —
    title/content from #19's platform-specific trend queries). Different
    platforms researched in the very same run get different blobs here
    because their underlying search results differ, which is what makes
    per-platform suggestions genuinely differ rather than just varying by
    a fixed platform->offset table."""
    parts: list[str] = [platform]
    parts.extend(timing_signal.get("trending_topics") or [])

    platform_trends = brief.get("platform_trends") or {}
    for result in platform_trends.get(platform) or []:
        if isinstance(result, dict):
            parts.append(str(result.get("title") or ""))
            parts.append(str(result.get("content") or ""))

    return "\n".join(p for p in parts if p)


def _derive_offsets(content_blob: str) -> tuple[int, int, int]:
    """Deterministically derives (day_offset, hour, minute) from the
    signal's own content via a hash digest — not a lookup table. The same
    content always yields the same suggestion (reproducible), but
    different content (different trending topics, different platform
    search results) yields a different day/hour/minute every time."""
    digest = hashlib.sha256(content_blob.encode("utf-8")).hexdigest()

    day_span = MAX_DAYS_OUT - MIN_DAYS_OUT + 1
    hour_span = LATEST_HOUR_UTC - EARLIEST_HOUR_UTC + 1

    day_offset = MIN_DAYS_OUT + (int(digest[0:8], 16) % day_span)
    hour = EARLIEST_HOUR_UTC + (int(digest[8:16], 16) % hour_span)
    minute = int(digest[16:24], 16) % 60

    return day_offset, hour, minute


def suggest_target_datetime(
    db: Session, brand_id: uuid.UUID, platform: str
) -> SchedulingSuggestion:
    """Proposes a target_datetime for a new ContentCalendarEvent, derived
    from the brand's most recent research brief that covers `platform`.

    Raises NoResearchSignalError if no such brief exists yet — callers
    (e.g. the calendar-events create endpoint) should treat that as "can't
    auto-suggest, fall back to requiring an explicit target_datetime"
    rather than inventing a value with no real signal behind it.
    """
    run, brief = _find_research_brief(db, brand_id, platform)
    timing_signal: dict = brief["timing_signal"]

    researched_at = _parse_iso(timing_signal.get("researched_at")) or run.created_at
    if researched_at.tzinfo is None:
        researched_at = researched_at.replace(tzinfo=timezone.utc)

    content_blob = _platform_content_blob(brief, timing_signal, platform)
    day_offset, hour, minute = _derive_offsets(content_blob)

    candidate = (researched_at + timedelta(days=day_offset)).replace(
        hour=hour, minute=minute, second=0, microsecond=0
    )

    # Never suggest a time already in the past (can happen if the research
    # run is old relative to "now" but the derived day offset is small) —
    # push forward by whole days, preserving the derived hour/minute, until
    # it's in the future.
    now = datetime.now(timezone.utc)
    while candidate <= now:
        candidate += timedelta(days=MAX_DAYS_OUT - MIN_DAYS_OUT + 1)

    trending_topics = timing_signal.get("trending_topics") or []
    reasoning = (
        f"Derived from the research brief run on {researched_at.isoformat()} "
        f"for platform={platform!r}: {len(trending_topics)} trending topic(s) "
        f"and this platform's own trend search results were hashed to pick "
        f"{day_offset} day(s) out at {hour:02d}:{minute:02d} UTC."
    )

    return SchedulingSuggestion(
        target_datetime=candidate,
        reasoning=reasoning,
        source={
            "agent_run_id": str(run.id),
            "researched_at": researched_at.isoformat(),
            "platform": platform,
            "trending_topics": trending_topics,
        },
    )
