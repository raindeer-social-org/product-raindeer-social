import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.config.database import Base


class ReviewSource(str, enum.Enum):
    """Who produced a given ReviewFeedback row. The Reviewer Engine
    (Issue #24) only ever writes AI_REVIEWER rows; HUMAN is here because
    #25's human-review UI writes its own feedback into this same table
    (per #24's issue text) rather than a separate one — the two review
    types are meant to sit side by side for a given Post, not live in
    parallel tables a UI has to join."""

    AI_REVIEWER = "ai_reviewer"
    HUMAN = "human"


class ReviewVerdict(str, enum.Enum):
    """Coarse pass/fail signal alongside the numeric score — cheap for a
    UI to badge/filter on without re-deriving a threshold from `score`
    every time."""

    APPROVE = "approve"
    REVISE = "revise"
    REJECT = "reject"


class ReviewFeedback(Base):
    """Immutable append-only evaluation log for a Post — same "append a
    row per evaluation, never overwrite" convention as AgentRun
    (apps/api/models/agent_run.py) and PostVersion
    (apps/api/models/post_version.py). The Reviewer Engine (#24) appends
    one row here per review pass with source=ai_reviewer; #25's human
    review UI will append rows with source=human onto the very same
    table, so a Post's full review history — AI and human — reads as one
    ordered log rather than two things a caller has to reconcile."""

    __tablename__ = "review_feedback"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("posts.id"), nullable=False
    )

    source: Mapped[ReviewSource] = mapped_column(
        Enum(ReviewSource, name="review_source"), nullable=False
    )

    # 0-100 alignment score against brand voice/compliance/platform norms.
    # Kept as a plain Float (not constrained at the DB level) since the
    # meaningful validation — "is this actually low for off-brand
    # content" — lives in the Reviewer Engine's prompt/tests, not a
    # column constraint.
    score: Mapped[float] = mapped_column(Float, nullable=False)

    verdict: Mapped[ReviewVerdict] = mapped_column(
        Enum(ReviewVerdict, name="review_verdict"), nullable=False
    )

    # Specific, actionable notes — never just the score. For an AI review
    # this is the Reviewer Engine's structured critique (per-platform
    # issues + suggested edits); for a future human review (#25) this
    # would be the reviewer's own free-text comments. Kept as JSONB
    # (not a plain string) so an AI review can carry structured
    # per-platform suggestions rather than one undifferentiated blob of
    # text — same reasoning as Post.body_text/PostVersion.body_text being
    # JSONB keyed by platform rather than a single string.
    comments: Mapped[dict] = mapped_column(JSONB, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
