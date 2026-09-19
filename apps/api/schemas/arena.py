"""Issue #124 — read-only composition of one pipeline run for the Content
Arena screen (apps/web/app/arena/page.tsx) to render as a DAG: the
ContentCalendarEvent it's for (if any), the Post it produced, every
AgentRun row logged for that Post so far, and the Post's full
ReviewFeedback history. Nothing here writes anything — it's a join over
three tables the pipeline (packages/agents/pipeline/graph.py) already
populates node-by-node, so the Arena canvas doesn't have to stitch
together several existing endpoints (none of which currently expose
AgentRun at all) itself.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from apps.api.models.agent_run import AgentType
from apps.api.models.post import PipelineStage
from apps.api.models.review_feedback import ReviewSource, ReviewVerdict


class ArenaAgentRunRead(BaseModel):
    """Mirrors apps/api/models/agent_run.py::AgentRun. `input` is
    deliberately omitted: run_pipeline (packages/agents/pipeline/graph.py)
    only ever writes {"post_id": ...} into it, never a real prompt, so it
    has nothing an inspector panel could usefully show. `output` is kept
    since it's the node's real structured result (research_brief /
    creative_brief / generation_output / review_output, per stage)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_type: AgentType
    output: dict | None
    model: str | None
    tokens: int | None
    cost: float | None
    latency_ms: float | None
    created_at: datetime


class ArenaReviewFeedbackRead(BaseModel):
    """Same shape as apps/api/schemas/review.py::ReviewFeedbackRead, minus
    post_id (redundant here — the whole payload is already scoped to one
    post)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source: ReviewSource
    score: float
    verdict: ReviewVerdict
    comments: dict
    created_at: datetime


class ArenaPostRead(BaseModel):
    """A thin Post projection — just what the Arena canvas needs to know
    where the run stands and what it produced, not the full Post row
    (publish_results/publish_error are omitted; they're the publish
    queue's concern, not this run's DAG)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    calendar_event_id: uuid.UUID | None
    current_pipeline_stage: PipelineStage
    body_text: dict | None
    media: list | None
    created_at: datetime
    updated_at: datetime


class ArenaRunRead(BaseModel):
    """One pipeline run, in a shape the Content Arena canvas (Issue #124)
    can render directly: the calendar event it's for (if any), the Post it
    produced (None if the event has no Post yet — e.g. still SCHEDULED),
    every AgentRun row logged for that Post so far — oldest first, the
    same order the pipeline graph actually executed them in — and the
    Post's full review history (AI + human, same "one ordered log"
    convention as apps/api/schemas/review.py::ReviewQueuePostRead)."""

    calendar_event_id: uuid.UUID | None
    post: ArenaPostRead | None
    agent_runs: list[ArenaAgentRunRead]
    review_feedback: list[ArenaReviewFeedbackRead]
