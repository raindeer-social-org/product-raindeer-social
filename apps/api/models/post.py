import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, func
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

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
