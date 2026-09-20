import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.config.database import Base


class OnboardingResearch(Base):
    __tablename__ = "onboarding_research"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("brands.id"), nullable=False, unique=True
    )

    brand_overview: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    competitor_positioning: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Real website scrape (Issue #152) — packages/agents/onboarding/
    # research_step.py::run_website_scrape(). website_summary is an LLM
    # distillation of the scraped page text (never the raw scrape itself —
    # see that function's docstring for why); website_logo_url points at
    # our own StorageProvider-hosted copy of whatever logo/favicon the
    # scrape found (re-hosted, not linked to the brand's own site, so it
    # stays valid even if the source page changes); website_colors is the
    # small dominant-color palette extracted from that logo.
    website_summary: Mapped[str | None] = mapped_column(nullable=True)
    website_logo_url: Mapped[str | None] = mapped_column(nullable=True)
    website_colors: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
