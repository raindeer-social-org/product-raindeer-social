import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.config.database import Base


class BrandSettings(Base):
    """Per-brand agent-behavior preferences (Issue #128).

    One row per brand, same "single row, upsert, created lazily on first
    read" shape as OnboardingResponse (apps/api/models/onboarding_response.py).

    These toggles are additive persistence only, not full behavior wiring:
    nothing in the pipeline/review/scheduling code reads this table yet.
    That's a deliberate, clearly-labeled follow-up rather than an
    oversight — see apps/api/routers/brand_settings.py's module docstring
    for exactly which real feature each field conceptually maps to
    (review auto-approval, the Arena's reasoning visibility, the
    review-needed email digest, and
    apps/api/services/scheduling_suggestion.py's automatic timing shifts).
    """

    __tablename__ = "brand_settings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("brands.id"), nullable=False, unique=True
    )

    # Maps to apps/api/routers/review.py's human-review gate — not wired to
    # actually skip human review yet.
    auto_approve_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    auto_approve_threshold: Mapped[int] = mapped_column(
        Integer, nullable=False, default=90
    )
    # Maps to the Content Arena's reasoning/tool-call visibility.
    show_agent_reasoning: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    # Maps to a daily "needs review" email digest — no email sender reads
    # this yet.
    email_review_digest_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    # Maps to apps/api/services/scheduling_suggestion.py — that service
    # only ever produces a suggestion today; nothing applies it
    # automatically regardless of this flag.
    auto_shift_posting_times: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
