import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.config.database import Base


class PostVersion(Base):
    """Immutable version-history log for Post.body_text — one row appended
    per Generation Engine (Issue #21) run, same "append a log row, never
    overwrite" convention AgentRun already establishes (see
    apps/api/models/agent_run.py). Post.body_text always holds the most
    recent generation's output; this table preserves every earlier one, so
    regenerating a post's copy never loses what came before it."""

    __tablename__ = "post_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("posts.id"), nullable=False
    )
    # Same shape as Post.body_text at the time this version was written —
    # a dict keyed by platform, not just a single string, since one Post
    # carries copy for every platform its creative_brief targeted.
    body_text: Mapped[dict] = mapped_column(JSONB, nullable=False)

    model: Mapped[str | None] = mapped_column(nullable=True)
    tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
