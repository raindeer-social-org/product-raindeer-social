"""Issue #124 — read-only endpoint composing one pipeline run's AgentRun
history, Post, and ReviewFeedback rows for the Content Arena screen
(apps/web/app/arena/page.tsx) to render as a DAG. Nothing here writes
anything — see schemas/arena.py's docstring for why this exists as its own
join rather than the frontend fetching three separate endpoints (one of
which, AgentRun, doesn't have a list endpoint at all yet) and stitching
them together itself.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from apps.api.auth.dependencies import CurrentUser, get_current_user
from apps.api.config.database import get_db
from apps.api.models import AgentRun, Brand, ContentCalendarEvent, Post, ReviewFeedback
from apps.api.schemas.arena import (
    ArenaAgentRunRead,
    ArenaPostRead,
    ArenaReviewFeedbackRead,
    ArenaRunRead,
)
from packages.agents.pipeline.graph import PIPELINE_STAGES

router = APIRouter(prefix="/brands/{brand_id}/arena", tags=["arena"])

# Every AgentRun row run_pipeline (packages/agents/pipeline/graph.py) logs
# for a single run_pipeline() call is written inside that call's one open
# transaction, and Postgres's now() (what AgentRun.created_at's
# server_default resolves to) is constant for the whole transaction — so
# rows from the same run can share an identical created_at and a plain
# `ORDER BY created_at` can't tell them apart. Breaking ties by each row's
# position in the pipeline's own stage order gives the correct sequence
# for that common case while still respecting created_at across genuinely
# separate runs/resumes (e.g. a human_review approval that resumes the
# graph in a later request/transaction).
_STAGE_ORDER = {stage: index for index, stage in enumerate(PIPELINE_STAGES)}


def _agent_run_sort_key(run: AgentRun) -> tuple:
    return (run.created_at, _STAGE_ORDER.get(run.agent_type.value, len(PIPELINE_STAGES)))


def _get_org_brand(db: Session, brand_id: uuid.UUID, org_id: str) -> Brand:
    brand = (
        db.query(Brand)
        .filter(Brand.id == brand_id, Brand.organization_id == uuid.UUID(org_id))
        .first()
    )
    if brand is None:
        # 404, not 403 — don't leak whether a brand with this id exists in
        # another org. Same convention as review.py/calendar.py.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand not found")
    return brand


def _run_for_post(db: Session, post: Post | None, calendar_event_id: uuid.UUID | None) -> ArenaRunRead:
    if post is None:
        return ArenaRunRead(
            calendar_event_id=calendar_event_id, post=None, agent_runs=[], review_feedback=[]
        )

    agent_runs = sorted(
        db.query(AgentRun).filter(AgentRun.post_id == post.id).all(),
        key=_agent_run_sort_key,
    )
    review_feedback = (
        db.query(ReviewFeedback)
        .filter(ReviewFeedback.post_id == post.id)
        .order_by(ReviewFeedback.created_at)
        .all()
    )
    return ArenaRunRead(
        calendar_event_id=post.calendar_event_id,
        post=ArenaPostRead.model_validate(post),
        agent_runs=[ArenaAgentRunRead.model_validate(run) for run in agent_runs],
        review_feedback=[ArenaReviewFeedbackRead.model_validate(f) for f in review_feedback],
    )


@router.get("/by-event/{event_id}", response_model=ArenaRunRead)
def get_arena_run_for_event(
    brand_id: uuid.UUID,
    event_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ArenaRunRead:
    """The pipeline run for one calendar event. packages/agents/pipeline/
    trigger.py's _get_or_create_post keeps a 1:1 ContentCalendarEvent:Post
    relationship, so there is at most one Post to find here — None if the
    event hasn't been triggered yet (still SCHEDULED)."""
    brand = _get_org_brand(db, brand_id, current_user.org_id)
    event = (
        db.query(ContentCalendarEvent)
        .filter(ContentCalendarEvent.id == event_id, ContentCalendarEvent.brand_id == brand.id)
        .first()
    )
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Calendar event not found")

    post = db.query(Post).filter(Post.calendar_event_id == event.id).first()
    return _run_for_post(db, post, event.id)


@router.get("/latest", response_model=ArenaRunRead)
def get_latest_arena_run(
    brand_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ArenaRunRead:
    """The brand's most recently created Post — the run the Arena canvas
    opens by default when it isn't deep-linked to a specific calendar
    event. `post` is None (and agent_runs/review_feedback empty) when the
    brand has no posts yet at all."""
    brand = _get_org_brand(db, brand_id, current_user.org_id)
    post = (
        db.query(Post)
        .filter(Post.brand_id == brand.id)
        .order_by(Post.created_at.desc())
        .first()
    )
    return _run_for_post(db, post, post.calendar_event_id if post else None)
