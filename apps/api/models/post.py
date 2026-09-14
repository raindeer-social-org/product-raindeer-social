import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.config.database import Base


class PipelineStage(str, enum.Enum):
    """Mirrors the node names in packages/agents/pipeline/graph.py, in
    pipeline order. A Post's current_pipeline_stage always reflects the
    graph's real position (see Issue #18) — set by the pipeline runner
    immediately after each node completes, not just once at the end."""

    RESEARCH = "research"
    CREATIVE = "creative"
    GENERATION = "generation"
    REVIEWER = "reviewer"
    HUMAN_REVIEW = "human_review"
    SCHEDULER = "scheduler"
    PUBLISHER = "publisher"
    ANALYTICS_COLLECTOR = "analytics_collector"
    COMPLETED = "completed"
    # Terminal state for a run a human explicitly rejected at the
    # human_review interrupt (Issue #25) — distinct from COMPLETED, which
    # implies the post made it all the way through Publisher/Analytics
    # Collector. graph.py routes human_review straight to END instead of
    # scheduler when the resumed decision is "rejected", so a rejected
    # post never reaches those later stages.
    REJECTED = "rejected"
    # Terminal state for a post whose actual publish (Issue #31's
    # Redis-backed publish queue, apps/api/services/publish_queue.py)
    # permanently failed after its retries were exhausted — distinct from
    # COMPLETED because the pipeline graph itself finishes normally
    # (`publisher` only hands the post off to the async publish queue;
    # see graph.py), so COMPLETED is set before the real publish outcome
    # is known. This stage is set out-of-band by the publish queue, not
    # by run_pipeline, once the durable retry/backoff has genuinely given
    # up — same "add a value, same table" shape as REJECTED above.
    FAILED = "failed"


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("brands.id"), nullable=False
    )
    # Optional — a post can be generated ad hoc as well as from a scheduled
    # calendar entry (Issue #26).
    calendar_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("content_calendar_events.id"), nullable=True
    )

    current_pipeline_stage: Mapped[PipelineStage] = mapped_column(
        Enum(PipelineStage, name="pipeline_stage"),
        nullable=False,
        default=PipelineStage.RESEARCH,
    )

    # Written by the Generation Engine's batch mode (Issue #106) — a shared
    # id linking every Post produced by the same batch generation run, so a
    # human can be shown "the other N-1 variants" for a post they're
    # reviewing. NULL for every Post produced by the (default, unchanged)
    # single-post generation path — those have no siblings, so there's
    # nothing to group. Not a ForeignKey to another table: it's a bare
    # shared value across sibling Post rows, the same "group id with no
    # row of its own" shape LangGraph's thread_id uses.
    variant_group_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    # This Post's 1-based position within variant_group_id (1 for the
    # original post that triggered the run, 2..N for the additional
    # sibling Posts batch mode creates). Purely presentational ordering —
    # nothing in the pipeline branches on it. NULL alongside
    # variant_group_id for non-batch Posts.
    variant_index: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Written by the Generation Engine (Issue #21) — a dict keyed by
    # platform (e.g. {"linkedin": "...", "x": "..."}), matching
    # creative_brief's per-platform shape, since a single Post carries
    # copy for every platform its creative_brief targeted rather than
    # just one. Always holds the *latest* generation; every version
    # (including this one) is also appended to PostVersion
    # (apps/api/models/post_version.py) so nothing is ever lost when a
    # post is regenerated.
    body_text: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Written by the Generation Engine's media hook (Issue #22 — image;
    # Issue #23 — video/carousel) — a JSONB list of media reference dicts
    # produced by this Post's latest generation run, e.g. [{"platform":
    # "linkedin", "format": "image", "url": "..."}]. Follows the same
    # "written by the Generation Engine, always reflects the latest run"
    # convention as body_text above; unlike body_text it is only touched
    # when a run actually produces new media — an entry for a platform
    # this run regenerated replaces that platform's prior entry, but
    # entries for platforms this run didn't touch (including a run with
    # no image/video/carousel platforms, or one where generation failed)
    # are left untouched rather than wiped.
    media: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # Written by the publish queue (Issue #31,
    # apps/api/services/publish_queue.py) — per-platform outcome of the
    # most recent publish attempt, e.g. {"linkedin": {"status":
    # "published", "platform_post_id": "...", "platform_post_url": "..."},
    # "x": {"status": "failed", "error": "..."}}. Read back on every retry
    # attempt so an already-published platform is never re-published just
    # because a sibling platform's attempt failed and the whole post gets
    # retried.
    publish_results: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # The most recent publish failure reason, across whichever platform(s)
    # failed — kept as a single human-readable summary field so a caller
    # (an API response, a future #32 notification) never has to reach
    # into publish_results just to show "why did this fail". Cleared back
    # to None on a fully successful publish. Never silently dropped: the
    # publish queue writes this on every failed attempt, not just once
    # retries are exhausted.
    publish_error: Mapped[str | None] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
