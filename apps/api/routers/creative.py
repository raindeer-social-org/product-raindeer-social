"""Issue #126 — the standalone Creative workspace page's API surface.

Creative Engine (Issue #20) previously only ran as the pipeline's second
stage, turning an upstream Research brief into one per-platform brief.
The Creative page instead takes a free-form brief typed directly by the
user and wants six distinct angle/format cards to choose from — a
different shape (many candidate angles, not one brief per platform), so
this calls a sibling function, generate_creative_angles (added alongside
_creative_brief in packages/agents/pipeline/nodes/creative_engine.py),
rather than the existing per-post node. Same LLMProvider-only,
degrade-on-failure contract as the rest of that module.

Logged as an AgentRun(agent_type=CREATIVE, post_id=None) — no Post exists
for a standalone angle-generation call, same "post_id null, context in
input" convention apps/api/models/agent_run.py documents for
weekly_report.py.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from apps.api.auth.dependencies import CurrentUser
from apps.api.config.database import get_db
from apps.api.middleware.rbac import require_role
from apps.api.models import AgentRun, AgentType, Brand, UserRole
from apps.api.schemas.creative import CreativeAnglesRequest, CreativeAnglesResponse
from packages.agents.pipeline.nodes.creative_engine import generate_creative_angles

router = APIRouter(prefix="/brands/{brand_id}/creative", tags=["creative"])

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


@router.post("/angles", response_model=CreativeAnglesResponse, status_code=status.HTTP_201_CREATED)
def generate_angles(
    brand_id: uuid.UUID,
    payload: CreativeAnglesRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(*WRITE_ROLES)),
) -> CreativeAnglesResponse:
    brand = _get_org_brand(db, brand_id, current_user.org_id)

    angles = generate_creative_angles(brand, payload.brief, count=payload.count)

    db.add(
        AgentRun(
            post_id=None,
            agent_type=AgentType.CREATIVE,
            input={"brand_id": str(brand.id), "brief": payload.brief, "count": payload.count},
            output={"angles": angles},
        )
    )
    db.flush()

    return CreativeAnglesResponse(angles=angles)
