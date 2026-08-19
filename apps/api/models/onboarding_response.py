import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.config.database import Base

# Fields the onboarding agent (Issue #15) needs before it can run.
REQUIRED_FIELDS = ("voice", "audience", "product_catalog", "competitors", "goals")


class OnboardingResponse(Base):
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

    is_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def missing_required_fields(self) -> list[str]:
        return [
            field
            for field in REQUIRED_FIELDS
            if getattr(self, field) in (None, "", [], {})
        ]
