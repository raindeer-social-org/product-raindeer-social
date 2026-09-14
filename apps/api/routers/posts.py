"""Issue #126 — a general, read-only Post listing for a brand.

Every existing Post-reading endpoint is scoped to one pipeline stage:
apps/api/routers/review.py's review-queue only lists Posts paused at
human_review, and apps/api/routers/calendar.py returns
ContentCalendarEvent rows, whose own status field a rejection never
updates (see packages/agents/pipeline/graph.py — rejecting only ever sets
Post.current_pipeline_stage to REJECTED). The Create Post page's "Recent
runs" list needs every Post regardless of stage — including terminal
REJECTED/FAILED ones — so it can show a real "Blocked" status rather than
one invented for the UI. This router adds exactly that: one additive,
read-only endpoint over the existing Post table.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from apps.api.auth.dependencies import CurrentUser, get_current_user
from apps.api.config.database import get_db
from apps.api.models import Brand, Post
from apps.api.schemas.post import PostRead

router = APIRouter(prefix="/brands/{brand_id}/posts", tags=["posts"])

DEFAULT_LIMIT = 20
MAX_LIMIT = 100


def _get_org_brand(db: Session, brand_id: uuid.UUID, org_id: str) -> Brand:
    brand = (
        db.query(Brand)
        .filter(Brand.id == brand_id, Brand.organization_id == uuid.UUID(org_id))
        .first()
    )
    if brand is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand not found")
    return brand


@router.get("", response_model=list[PostRead])
def list_posts(
    brand_id: uuid.UUID,
    limit: int = DEFAULT_LIMIT,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[Post]:
    """Every Post for this brand, newest first, regardless of pipeline
    stage — for the Create Post page's "Recent runs" list."""
    brand = _get_org_brand(db, brand_id, current_user.org_id)
    capped_limit = max(1, min(limit, MAX_LIMIT))
    return (
        db.query(Post)
        .filter(Post.brand_id == brand.id)
        .order_by(Post.created_at.desc())
        .limit(capped_limit)
        .all()
    )
