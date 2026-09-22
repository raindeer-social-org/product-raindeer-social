import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.config.database import Base

# Hard cap on how many AI-generated pages Aarav can ask, even if the LLM
# never signals done — see packages/agents/onboarding/dynamic_questions.py.
# Keeps the interview from running forever against a model that won't stop.
# Raised from 4 — the fixed "essentials" page (voice/audience/product/
# competitors/goals) was removed and folded into this dynamic phase
# instead, so Aarav now has real ground to cover that a fixed page used
# to handle; generate_next_page's own done=True signal still lets a
# well-understood brand finish in far fewer pages than this ceiling.
MAX_DYNAMIC_PAGES = 10


class OnboardingDynamicAnswer(Base):
    """One page's worth of Aarav-generated follow-up questions and the
    brand's answers to them (Issue #153) — the durable record of the
    adaptive, LLM-driven half of the onboarding interview that runs after
    the fixed questionnaire (OnboardingResponse). `question` is the full
    generated question object (id/type/title/sub/options) as the LLM
    produced it, so a later re-read doesn't need to regenerate or guess
    what was actually asked; `answer` is whatever the brand answered it
    with (a string for text/voice/select, a list of strings for chips).
    One row per question per page — not unique per brand, since a brand
    accumulates one of these per generated question across every page."""

    __tablename__ = "onboarding_dynamic_answers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("brands.id"), nullable=False
    )

    page_index: Mapped[int] = mapped_column(Integer, nullable=False)
    question: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # str for text/voice/select, list[str] for chips — see the class
    # docstring.
    answer: Mapped[str | list] = mapped_column(JSONB, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
