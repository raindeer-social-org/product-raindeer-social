import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.config.database import Base


class OnboardingVoiceAnswer(Base):
    """A single real, recorded voice answer from Aarav's onboarding
    interview (Issue #144) — the raw audio (via StorageProvider) and its
    Whisper transcript are both kept, rather than discarding the audio
    once transcribed, so "everything voice" is durably on file per the
    issue's ask. Not unique-per-brand (unlike OnboardingResponse) since a
    brand can re-record the same question, or multiple voice questions
    may exist — every take is appended, never overwritten."""

    __tablename__ = "onboarding_voice_answers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("brands.id"), nullable=False
    )

    question_id: Mapped[str] = mapped_column(String, nullable=False)
    transcript: Mapped[str] = mapped_column(nullable=False)
    audio_url: Mapped[str] = mapped_column(nullable=False)
    language: Mapped[str | None] = mapped_column(String, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
