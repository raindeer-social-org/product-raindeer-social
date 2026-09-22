import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.config.database import Base


class OnboardingResponse(Base):
    """Structured questionnaire fields — historically the only source for
    voice/audience/product/competitors/goals (via a fixed "essentials"
    page), now just one input among several Aarav's synthesis prompt
    reads. All fields here are optional: a brand can complete onboarding
    having answered none of them directly, with the same ground covered
    instead through Aarav's dynamic questions (OnboardingDynamicAnswer)."""

    __tablename__ = "onboarding_responses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("brands.id"), nullable=False, unique=True
    )

    voice: Mapped[str | None] = mapped_column(nullable=True)
    audience: Mapped[str | None] = mapped_column(nullable=True)
    product_catalog: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    competitors: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    goals: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # Deeper-questionnaire fields (Issue #144) — same "optional enrichment"
    # status as everything else on this model now.
    mission: Mapped[str | None] = mapped_column(nullable=True)
    content_dos_donts: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    posting_cadence: Mapped[str | None] = mapped_column(nullable=True)

    is_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
