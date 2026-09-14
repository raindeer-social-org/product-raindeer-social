import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.config.database import Base

# Platforms #30/#108/#109/#110's publishing adapters actually support —
# kept in sync with those issues' scope so this table can't hold events no
# adapter can publish.
SUPPORTED_PLATFORMS = ("linkedin", "x", "instagram", "threads", "facebook")


class CalendarEventStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    PIPELINE_RUNNING = "pipeline_running"
    READY_FOR_REVIEW = "ready_for_review"
    APPROVED = "approved"
    PUBLISHED = "published"
    FAILED = "failed"


class ContentCalendarEvent(Base):
    __tablename__ = "content_calendar_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("brands.id"), nullable=False
    )

    title: Mapped[str] = mapped_column(nullable=False)
    description: Mapped[str | None] = mapped_column(nullable=True)
    target_platforms: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)
    desired_format: Mapped[str] = mapped_column(nullable=False)
    target_datetime: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    status: Mapped[CalendarEventStatus] = mapped_column(
        Enum(CalendarEventStatus, name="calendar_event_status"),
        nullable=False,
        default=CalendarEventStatus.SCHEDULED,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
