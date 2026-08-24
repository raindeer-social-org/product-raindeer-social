import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from apps.api.models.post import PipelineStage
from apps.api.models.review_feedback import ReviewSource, ReviewVerdict


class ReviewFeedbackRead(BaseModel):
    """Mirrors apps/api/models/review_feedback.py::ReviewFeedback — the
    same shape whether `source` is ai_reviewer (Issue #24) or human
    (Issue #25), so the review-queue UI renders both off one list."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    post_id: uuid.UUID
    source: ReviewSource
    score: float
    verdict: ReviewVerdict
    comments: dict
    created_at: datetime


class ReviewQueuePostRead(BaseModel):
    """A paused Post plus its full review history (AI + human) — what the
    review-queue UI needs to render a draft next to the AI reviewer's
    score/suggestions without a second round-trip."""

    id: uuid.UUID
    brand_id: uuid.UUID
    calendar_event_id: uuid.UUID | None
    current_pipeline_stage: PipelineStage
    body_text: dict | None
    created_at: datetime
    updated_at: datetime
    review_feedback: list[ReviewFeedbackRead]


class HumanReviewDecision(BaseModel):
    """Body for POST .../approve and POST .../reject. `score` overrides
    the default (100 for approve, 0 for reject) if a reviewer wants to
    record something more nuanced than a bare pass/fail."""

    comments: str | None = None
    score: float | None = None


class HumanReviewEdit(BaseModel):
    """Body for POST .../edit — same per-platform-keyed shape as
    Post.body_text/PostVersion.body_text (Issue #21)."""

    body_text: dict[str, Any]


class HumanReviewReschedule(BaseModel):
    """Body for POST .../reschedule. Reuses ContentCalendarEvent's own
    target_datetime field (Issue #26/#27) rather than adding a second
    scheduling field to Post."""

    target_datetime: datetime
