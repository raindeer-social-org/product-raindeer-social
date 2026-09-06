import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.config.database import Base

# Mirrors the interview UI's UPLOAD_SLOTS
# (apps/web/app/onboarding/interview/page.tsx) — kept as free text rather
# than a Postgres enum since these are just display buckets, not a value
# anything else branches on.
ONBOARDING_ASSET_SLOTS = ("product_photos", "team_photos", "past_social_posts", "style_guide")


class OnboardingAsset(Base):
    """A file uploaded during Aarav's onboarding interview (Issue #144) —
    product/team photos, past posts, a style guide. One row per (brand,
    slot): re-uploading to an already-filled slot replaces that slot's row
    (see apps/api/routers/onboarding.py::upload_onboarding_asset) rather
    than stacking indefinitely, same "one current value per slot" model
    Brand.logo_url already uses."""

    __tablename__ = "onboarding_assets"
    __table_args__ = (UniqueConstraint("brand_id", "slot", name="uq_onboarding_asset_brand_slot"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("brands.id"), nullable=False
    )

    slot: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str] = mapped_column(nullable=False)
    filename: Mapped[str] = mapped_column(nullable=False)
    content_type: Mapped[str] = mapped_column(String, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
