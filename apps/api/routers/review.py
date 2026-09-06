"""Issue #25 — the API surface for the pipeline's human_review interrupt
(packages/agents/pipeline/graph.py). A Post paused there sits durably in
Postgres (Issue #18's checkpointer) until one of four actions moves it
forward:

  * approve    — resumes the checkpointed graph; it proceeds through
                 `scheduler` (and, for now, straight on to `publisher`/
                 `analytics_collector`, since those are still stub nodes —
                 see graph.py) toward COMPLETED.
  * reject     — resumes the graph with a decision that
                 _route_after_human_review (graph.py) routes to END
                 instead of `scheduler`; the post lands on the REJECTED
                 terminal stage and never reaches publisher.
  * edit       — updates Post.body_text (and appends a PostVersion, same
                 "never lose an earlier draft" convention Generation
                 Engine established) without touching the checkpointed
                 graph at all — the post stays paused at human_review so
                 the edited draft can still be approved or rejected.
  * reschedule — updates the linked ContentCalendarEvent's
                 target_datetime (Issue #26/#27) — reused as-is rather
                 than adding a second scheduling field to Post — again
                 without touching the graph.
  * regenerate — Issue #140: asks Generation Engine to revise the draft
                 using the latest AI review's per-platform issues/
                 suggested_edits, appending a PostVersion the same way
                 edit does, again without touching the graph.

Approve and reject both append a ReviewFeedback row (Issue #24's table)
with source=human, sitting alongside the Reviewer Engine's own
source=ai_reviewer row for the same post — one ordered review log, not
two things a caller has to reconcile (see review_feedback.py's
docstring).
"""

import uuid
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from apps.api.auth.dependencies import CurrentUser, get_current_user
from apps.api.config.database import get_db
from apps.api.middleware.rbac import require_role
from apps.api.models import (
    Brand,
    ContentCalendarEvent,
    PipelineStage,
    Post,
    PostVersion,
    ReviewFeedback,
    ReviewSource,
    ReviewVerdict,
    UserRole,
)
from apps.api.schemas.calendar import CalendarEventRead
from apps.api.schemas.review import (
    HumanReviewDecision,
    HumanReviewEdit,
    HumanReviewReschedule,
    ReviewFeedbackRead,
    ReviewQueuePostRead,
)
from packages.agents.pipeline.checkpointer import get_postgres_checkpointer
from packages.agents.pipeline.graph import run_pipeline
from packages.agents.pipeline.nodes.generation_engine import regenerate_copy_with_feedback

router = APIRouter(prefix="/brands/{brand_id}/review-queue", tags=["review"])

WRITE_ROLES = (UserRole.OWNER, UserRole.ADMIN, UserRole.EDITOR)

_DEFAULT_APPROVE_SCORE = 100.0
_DEFAULT_REJECT_SCORE = 0.0


def _get_org_brand(db: Session, brand_id: uuid.UUID, org_id: str) -> Brand:
    brand = (
        db.query(Brand)
        .filter(Brand.id == brand_id, Brand.organization_id == uuid.UUID(org_id))
        .first()
    )
    if brand is None:
        # 404, not 403 — don't leak whether a brand with this id exists in
        # another org.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand not found")
    return brand


def _get_post_or_404(db: Session, brand_id: uuid.UUID, post_id: uuid.UUID) -> Post:
    post = db.query(Post).filter(Post.id == post_id, Post.brand_id == brand_id).first()
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    return post


def _require_paused_at_human_review(post: Post) -> None:
    if post.current_pipeline_stage != PipelineStage.HUMAN_REVIEW:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Post is not awaiting human review "
                f"(current stage: {post.current_pipeline_stage.value})"
            ),
        )


def _latest_ai_review_or_409(db: Session, post: Post) -> ReviewFeedback:
    feedback = (
        db.query(ReviewFeedback)
        .filter(ReviewFeedback.post_id == post.id, ReviewFeedback.source == ReviewSource.AI_REVIEWER)
        .order_by(ReviewFeedback.created_at.desc())
        .first()
    )
    if feedback is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Post has no AI review yet — nothing to regenerate from",
        )
    return feedback


def _feedback_by_post(db: Session, post_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[ReviewFeedback]]:
    grouped: dict[uuid.UUID, list[ReviewFeedback]] = defaultdict(list)
    if not post_ids:
        return grouped
    for feedback in (
        db.query(ReviewFeedback)
        .filter(ReviewFeedback.post_id.in_(post_ids))
        .order_by(ReviewFeedback.created_at)
        .all()
    ):
        grouped[feedback.post_id].append(feedback)
    return grouped


def _post_response(db: Session, post: Post) -> ReviewQueuePostRead:
    feedback = _feedback_by_post(db, [post.id]).get(post.id, [])
    return ReviewQueuePostRead(
        id=post.id,
        brand_id=post.brand_id,
        calendar_event_id=post.calendar_event_id,
        current_pipeline_stage=post.current_pipeline_stage,
        body_text=post.body_text,
        created_at=post.created_at,
        updated_at=post.updated_at,
        review_feedback=[ReviewFeedbackRead.model_validate(f) for f in feedback],
    )


@router.get("", response_model=list[ReviewQueuePostRead])
def list_review_queue(
    brand_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[ReviewQueuePostRead]:
    """Every Post currently paused at the human_review interrupt for this
    brand, oldest first, with its full AI + human review history attached."""
    brand = _get_org_brand(db, brand_id, current_user.org_id)
    posts = (
        db.query(Post)
        .filter(Post.brand_id == brand.id, Post.current_pipeline_stage == PipelineStage.HUMAN_REVIEW)
        .order_by(Post.created_at)
        .all()
    )
    feedback = _feedback_by_post(db, [post.id for post in posts])
    return [
        ReviewQueuePostRead(
            id=post.id,
            brand_id=post.brand_id,
            calendar_event_id=post.calendar_event_id,
            current_pipeline_stage=post.current_pipeline_stage,
            body_text=post.body_text,
            created_at=post.created_at,
            updated_at=post.updated_at,
            review_feedback=[ReviewFeedbackRead.model_validate(f) for f in feedback.get(post.id, [])],
        )
        for post in posts
    ]


@router.post("/{post_id}/approve", response_model=ReviewQueuePostRead)
def approve_post(
    brand_id: uuid.UUID,
    post_id: uuid.UUID,
    payload: HumanReviewDecision = HumanReviewDecision(),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(*WRITE_ROLES)),
) -> ReviewQueuePostRead:
    """Records the human's approval as a ReviewFeedback row (source=human)
    and resumes the checkpointed graph from exactly the human_review
    interrupt — LangGraph replays nothing upstream, it just continues on
    toward `scheduler` (see graph.py's _route_after_human_review)."""
    brand = _get_org_brand(db, brand_id, current_user.org_id)
    post = _get_post_or_404(db, brand.id, post_id)
    _require_paused_at_human_review(post)

    db.add(
        ReviewFeedback(
            post_id=post.id,
            source=ReviewSource.HUMAN,
            score=payload.score if payload.score is not None else _DEFAULT_APPROVE_SCORE,
            verdict=ReviewVerdict.APPROVE,
            comments={"comments": payload.comments} if payload.comments else {},
        )
    )
    db.flush()

    with get_postgres_checkpointer() as checkpointer:
        list(run_pipeline(db, post, checkpointer, resume={"decision": "approved", "comments": payload.comments}))

    return _post_response(db, post)


@router.post("/{post_id}/reject", response_model=ReviewQueuePostRead)
def reject_post(
    brand_id: uuid.UUID,
    post_id: uuid.UUID,
    payload: HumanReviewDecision = HumanReviewDecision(),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(*WRITE_ROLES)),
) -> ReviewQueuePostRead:
    """Records the human's rejection as a ReviewFeedback row (source=human)
    and resumes the checkpointed graph with a decision that
    _route_after_human_review (graph.py) routes straight to END instead of
    `scheduler` — the post halts at the REJECTED terminal stage and never
    reaches `publisher`."""
    brand = _get_org_brand(db, brand_id, current_user.org_id)
    post = _get_post_or_404(db, brand.id, post_id)
    _require_paused_at_human_review(post)

    db.add(
        ReviewFeedback(
            post_id=post.id,
            source=ReviewSource.HUMAN,
            score=payload.score if payload.score is not None else _DEFAULT_REJECT_SCORE,
            verdict=ReviewVerdict.REJECT,
            comments={"comments": payload.comments} if payload.comments else {},
        )
    )
    db.flush()

    with get_postgres_checkpointer() as checkpointer:
        list(run_pipeline(db, post, checkpointer, resume={"decision": "rejected", "comments": payload.comments}))

    return _post_response(db, post)


@router.post("/{post_id}/edit", response_model=ReviewQueuePostRead)
def edit_post(
    brand_id: uuid.UUID,
    post_id: uuid.UUID,
    payload: HumanReviewEdit,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(*WRITE_ROLES)),
) -> ReviewQueuePostRead:
    """Lets the human modify the draft before approving — updates
    Post.body_text and appends a PostVersion (same "never overwrite, only
    append" convention Generation Engine established) without touching the
    checkpointed graph at all: the post stays paused at human_review,
    ready for a subsequent approve/reject call."""
    brand = _get_org_brand(db, brand_id, current_user.org_id)
    post = _get_post_or_404(db, brand.id, post_id)
    _require_paused_at_human_review(post)

    post.body_text = payload.body_text
    db.add(PostVersion(post_id=post.id, body_text=payload.body_text))
    db.flush()
    db.refresh(post)

    return _post_response(db, post)


@router.post("/{post_id}/regenerate", response_model=ReviewQueuePostRead)
def regenerate_post(
    brand_id: uuid.UUID,
    post_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(*WRITE_ROLES)),
) -> ReviewQueuePostRead:
    """Asks Kavi (generation_engine.py) to revise the draft using Neer's
    (reviewer_engine.py) latest AI review — the per-platform `issues`/
    `suggested_edits` already shown on the review-queue card — instead of
    the human having to hand-edit the text themselves. Same "never touch
    the checkpointed graph" contract as edit_post: the post stays paused
    at human_review, ready for a follow-up edit/approve/reject call, and
    a PostVersion is appended so the pre-regeneration draft is never
    lost."""
    brand = _get_org_brand(db, brand_id, current_user.org_id)
    post = _get_post_or_404(db, brand.id, post_id)
    _require_paused_at_human_review(post)

    ai_review = _latest_ai_review_or_409(db, post)
    feedback_by_platform = ai_review.comments.get("platforms", {}) if ai_review.comments else {}

    revised_body_text, _model, _tokens = regenerate_copy_with_feedback(
        post.body_text or {}, feedback_by_platform
    )

    post.body_text = revised_body_text
    db.add(PostVersion(post_id=post.id, body_text=revised_body_text))
    db.flush()
    db.refresh(post)

    return _post_response(db, post)


@router.post("/{post_id}/reschedule", response_model=CalendarEventRead)
def reschedule_post(
    brand_id: uuid.UUID,
    post_id: uuid.UUID,
    payload: HumanReviewReschedule,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(*WRITE_ROLES)),
) -> ContentCalendarEvent:
    """Updates the linked ContentCalendarEvent's target_datetime (Issue
    #26/#27) rather than inventing a separate scheduling field on Post.
    Like edit, this doesn't touch the checkpointed graph — the post stays
    paused at human_review."""
    brand = _get_org_brand(db, brand_id, current_user.org_id)
    post = _get_post_or_404(db, brand.id, post_id)
    _require_paused_at_human_review(post)

    if post.calendar_event_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Post has no associated calendar event to reschedule",
        )

    event = (
        db.query(ContentCalendarEvent)
        .filter(
            ContentCalendarEvent.id == post.calendar_event_id,
            ContentCalendarEvent.brand_id == brand.id,
        )
        .first()
    )
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Calendar event not found")

    event.target_datetime = payload.target_datetime
    db.flush()
    db.refresh(event)

    return event
