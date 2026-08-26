import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.config.database import Base


class Report(Base):
    """AI-generated weekly performance report for a Brand — Issue #35.

    Same "append an immutable row, never overwrite" convention AgentRun
    (apps/api/models/agent_run.py) and ReviewFeedback
    (apps/api/models/review_feedback.py) already establish: one row per
    weekly generation run for a brand, so a brand's report history reads
    as an ordered log a dashboard (#36) can page back through, rather than
    a single row that gets clobbered every week.

    `metrics` carries the exact #34 analytics_aggregation numbers the
    report was generated from (brand-wide totals/averages for
    [period_start, period_end), same shape as
    analytics_aggregation.BrandSummary) — kept alongside `summary` so a
    caller (or a test) can verify the written summary actually reflects
    real, storable figures rather than trusting the LLM's prose alone.
    `recommendations` is a structured list (not folded into the summary
    text) so a dashboard can render it as its own checklist/section.
    """

    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("brands.id"), nullable=False
    )

    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # The LLM-written narrative summary — must reference the real numbers
    # in `metrics`, not generic filler (see
    # packages/agents/reporting/weekly_report.py's prompt-building, which
    # injects those numbers directly into the prompt).
    summary: Mapped[str] = mapped_column(Text, nullable=False)

    # Structured, actionable recommendations derived from this period's
    # metrics — a list of short strings (or richer per-item dicts), kept
    # separate from `summary` so a UI can render them as their own
    # section rather than parsing prose.
    recommendations: Mapped[list] = mapped_column(JSONB, nullable=False)

    # The exact aggregate figures the report was generated from — the
    # audit trail proving `summary`/`recommendations` are grounded in
    # real data (analytics_aggregation.BrandSummary, dataclass-to-dict).
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # LLM model that produced this report — read fresh from
    # apps.api.config.get_settings().llm_default_model at generation time
    # (packages/agents/reporting/weekly_report.py), never hardcoded.
    model: Mapped[str | None] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
