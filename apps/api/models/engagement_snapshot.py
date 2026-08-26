import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.config.database import Base


class EngagementSnapshot(Base):
    """Immutable time-series log of a published Post's engagement metrics
    on one platform — one row appended per poll (Issue #33's
    apps/api/services/engagement_polling.py), same "append a log row,
    never overwrite" convention AgentRun/PostVersion already establish
    (see apps/api/models/agent_run.py, apps/api/models/post_version.py).
    A post polled repeatedly over its lifetime accumulates many rows here,
    each capturing whatever the platform reported *at that poll* — never
    updated in place, so #34's dashboard and #35's weekly report (and
    eventually #19/#28's timing signal) can read real engagement growth
    over time instead of only ever seeing the latest count."""

    __tablename__ = "engagement_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("posts.id"), nullable=False
    )
    # A plain string, not apps/api/models/social_account.py's
    # SocialPlatform enum — that enum only defines LINKEDIN today (X has
    # no connectable SocialAccount row yet), while a post's *published*
    # platforms (Post.publish_results, Issue #31) can include "x". Same
    # choice content_calendar_event.py's target_platforms already made,
    # for the same reason (see that module's SUPPORTED_PLATFORMS).
    platform: Mapped[str] = mapped_column(String, nullable=False)

    # Cumulative counts as reported by the platform at polled_at — not
    # deltas since the previous snapshot. Defaults of 0 rather than
    # nullable: a poll that succeeded always has a real number for every
    # metric the platform reports (a metric the platform doesn't support
    # at all comes back 0, not NULL — there's no "unknown" state for a
    # snapshot that was actually written).
    likes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    comments: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    shares: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    impressions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    polled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
