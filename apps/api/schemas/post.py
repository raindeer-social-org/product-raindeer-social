import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from apps.api.models.post import PipelineStage


class PostRead(BaseModel):
    """Issue #126 — the Create Post page's "Recent runs" list needs every
    Post for a brand regardless of pipeline stage (including the terminal
    REJECTED/FAILED stages), which no existing endpoint returns: the
    review-queue (apps/api/routers/review.py) only lists Posts paused at
    human_review, and calendar events (apps/api/routers/calendar.py)
    track a separate, coarser status that a rejection never updates (see
    packages/agents/pipeline/graph.py — REJECTED only ever sets
    Post.current_pipeline_stage). This mirrors ReviewQueuePostRead's shape
    minus the review-history join, which "recent runs" doesn't need."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID
    calendar_event_id: uuid.UUID | None
    current_pipeline_stage: PipelineStage
    body_text: dict | None
    created_at: datetime
    updated_at: datetime
