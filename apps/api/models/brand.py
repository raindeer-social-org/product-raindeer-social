import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.config.database import Base


class Brand(Base):
    __tablename__ = "brands"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(nullable=False)
    industry: Mapped[str | None] = mapped_column(nullable=True)
    logo_url: Mapped[str | None] = mapped_column(nullable=True)
    target_audience: Mapped[str | None] = mapped_column(nullable=True)

    colors: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    tone_descriptors: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    product_catalog: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Output of onboarding (Issue #15) — unpopulated until then.
    brand_report: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # RAG retrieval embedding of brand_report (Issue #16) — unpopulated until then.
    report_embedding: Mapped[list | None] = mapped_column(Vector(1536), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    organization: Mapped["Organization"] = relationship(back_populates="brands")
