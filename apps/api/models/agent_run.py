import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, Integer, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.config.database import Base


class AgentType(str, enum.Enum):
    ONBOARDING = "onboarding"
    RESEARCH = "research"
    CREATIVE = "creative"
    GENERATION = "generation"
    REVIEWER = "reviewer"
    # Added by Issue #18 (pipeline orchestration) alongside the Post model —
    # the remaining stub nodes in packages/agents/pipeline/graph.py.
    HUMAN_REVIEW = "human_review"
    SCHEDULER = "scheduler"
    PUBLISHER = "publisher"
    ANALYTICS_COLLECTOR = "analytics_collector"
    # Issue #35: the weekly per-brand AI report generation job
    # (packages/agents/reporting/weekly_report.py). Not a pipeline stage —
    # runs on its own Celery Beat schedule (apps/api/worker.py) over every
    # brand rather than once per Post, so AgentRun.post_id is left null
    # for these rows (brand_id lives in `input` instead — see that
    # module's docstring for why, same reasoning
    # scheduling_suggestion.py's research-lookup already established for
    # a service that isn't a pipeline node).
    WEEKLY_REPORT = "weekly_report"


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Still no FK constraint: Post now exists (Issue #18) but agent_runs
    # predates it and onboarding runs aren't tied to any Post, so this
    # stays a plain nullable UUID rather than a hard FK.
    post_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    agent_type: Mapped[AgentType] = mapped_column(
        Enum(AgentType, name="agent_type"), nullable=False
    )
    input: Mapped[dict] = mapped_column(JSONB, nullable=False)
    output: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    model: Mapped[str | None] = mapped_column(nullable=True)
    tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
