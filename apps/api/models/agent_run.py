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


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # No FK yet — Post doesn't exist until a later issue (M3). Nullable so
    # onboarding runs (not tied to any Post) can log here too.
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
