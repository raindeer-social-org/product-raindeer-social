import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from apps.api.models.agent_run import AgentType
from apps.api.models.content_calendar_event import SUPPORTED_PLATFORMS, CalendarEventStatus
from apps.api.models.post import PipelineStage
from apps.api.schemas.review import ReviewFeedbackRead


def _validate_platforms(platforms: list[str]) -> list[str]:
    unknown = [p for p in platforms if p not in SUPPORTED_PLATFORMS]
    if unknown:
        raise ValueError(
            f"Unsupported platform(s) {unknown}. Supported: {list(SUPPORTED_PLATFORMS)}"
        )
    return platforms


class CalendarEventCreate(BaseModel):
    title: str
    description: str | None = None
    target_platforms: list[str]
    desired_format: str
    # Optional (#28): when omitted, the create-event endpoint calls
    # apps/api/services/scheduling_suggestion.py to propose one from the
    # brand's most recent research brief. An explicitly provided value
    # here always wins — the suggestion is never applied over it.
    target_datetime: datetime | None = None

    @field_validator("target_platforms")
    @classmethod
    def _check_platforms(cls, v: list[str]) -> list[str]:
        return _validate_platforms(v)


class CalendarEventUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    target_platforms: list[str] | None = None
    desired_format: str | None = None
    target_datetime: datetime | None = None
    status: CalendarEventStatus | None = None

    @field_validator("target_platforms")
    @classmethod
    def _check_platforms(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        return _validate_platforms(v)


class CalendarEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID
    title: str
    description: str | None
    target_platforms: list[str]
    desired_format: str
    target_datetime: datetime
    status: CalendarEventStatus
    created_at: datetime
    updated_at: datetime


class CalendarEventAgentRunRead(BaseModel):
    """One AgentRun row (apps/api/models/agent_run.py) for the Post behind
    a calendar event — real pipeline execution history, not anything
    synthesized for display. Powers the calendar event preview modal's
    "agent trail" timeline (Issue #125)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_type: AgentType
    output: dict | None
    model: str | None
    tokens: int | None
    cost: float | None
    latency_ms: float | None
    created_at: datetime


class CalendarEventPostRead(BaseModel):
    """The Post the pipeline trigger (Issue #29) has generated for a
    calendar event, plus its review history and agent run trail — every-
    thing the calendar's post preview modal needs in one round trip
    (Issue #125). GET .../post returns null (200, not 404) when no Post
    exists yet: a SCHEDULED event the trigger hasn't claimed is a normal,
    common state, not an error."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID
    calendar_event_id: uuid.UUID | None
    current_pipeline_stage: PipelineStage
    body_text: dict | None
    media: list | None
    created_at: datetime
    updated_at: datetime
    review_feedback: list[ReviewFeedbackRead]
    agent_runs: list[CalendarEventAgentRunRead]
