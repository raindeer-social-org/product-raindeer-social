"""Issue #126 — the standalone Research workspace page's API surface.

Before this, Research Engine (Issue #19) only ran as one stage of the
per-post pipeline (packages/agents/pipeline/graph.py) — there was no way
to see fresh trend results without paying for Creative/Generation/
Reviewer/Human Review too. This router exposes exactly the Research
Engine's own logic (packages/agents/pipeline/nodes/research_engine.py's
run_standalone_research, a thin wrapper around the same _research_brief
the pipeline node uses) through two endpoints:

  * POST .../research/run    — runs a fresh standalone research brief for
                                the brand right now.
  * GET  .../research/latest — returns the most recent standalone (or
                                pipeline) research brief for the brand
                                without re-running anything, for the page
                                to render on load.

A standalone run is stored the same way every other AgentRun is (Issue
#18's convention): as an AgentRun(agent_type=RESEARCH) row. Since
AgentRun has no brand_id column, it's tied to an ad hoc Post (brand_id
set, calendar_event_id left null) — the same "a post can be generated ad
hoc" case apps/api/models/post.py already documents, rather than a
one-off schema change to AgentRun.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from apps.api.auth.dependencies import CurrentUser, get_current_user
from apps.api.config.database import get_db
from apps.api.middleware.rbac import require_role
from apps.api.models import AgentRun, AgentType, Brand, Post, UserRole
from apps.api.schemas.research import ResearchRunRead
from packages.agents.pipeline.nodes.research_engine import run_standalone_research

router = APIRouter(prefix="/brands/{brand_id}/research", tags=["research"])

WRITE_ROLES = (UserRole.OWNER, UserRole.ADMIN, UserRole.EDITOR)


def _get_org_brand(db: Session, brand_id: uuid.UUID, org_id: str) -> Brand:
    brand = (
        db.query(Brand)
        .filter(Brand.id == brand_id, Brand.organization_id == uuid.UUID(org_id))
        .first()
    )
    if brand is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand not found")
    return brand


def _to_read(run: AgentRun, brand_id: uuid.UUID) -> ResearchRunRead:
    return ResearchRunRead(
        id=run.id,
        post_id=run.post_id,
        brand_id=brand_id,
        created_at=run.created_at,
        brief=run.output or {},
    )


@router.post("/run", response_model=ResearchRunRead, status_code=status.HTTP_201_CREATED)
def run_research(
    brand_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(*WRITE_ROLES)),
) -> ResearchRunRead:
    """Runs a fresh standalone research brief for this brand and logs it
    as an AgentRun, same as the pipeline's own research stage does — just
    without a full pipeline run around it."""
    brand = _get_org_brand(db, brand_id, current_user.org_id)

    post = Post(brand_id=brand.id)
    db.add(post)
    db.flush()
    db.refresh(post)

    brief = run_standalone_research(db, post)

    run = AgentRun(
        post_id=post.id,
        agent_type=AgentType.RESEARCH,
        input={"post_id": str(post.id), "trigger": "standalone"},
        output=brief,
    )
    db.add(run)
    db.flush()
    db.refresh(run)

    return _to_read(run, brand.id)


@router.get("/latest", response_model=ResearchRunRead)
def latest_research(
    brand_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ResearchRunRead:
    """The most recent research brief for this brand (standalone or from
    a per-post pipeline run) — lets the page show what's already known
    without triggering a new run just to view it."""
    brand = _get_org_brand(db, brand_id, current_user.org_id)

    run = (
        db.query(AgentRun)
        .join(Post, AgentRun.post_id == Post.id)
        .filter(Post.brand_id == brand.id, AgentRun.agent_type == AgentType.RESEARCH)
        .order_by(AgentRun.created_at.desc())
        .first()
    )
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No research has been run yet for this brand",
        )

    return _to_read(run, brand.id)
