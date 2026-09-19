"""Issue #126 — the Content AI workspace page's API surface: the
image-first fast path that skips copywriting entirely and goes straight
to visuals.

Generation Engine's media hook (packages/agents/pipeline/nodes/
generation_engine.py) already calls the real fal.ai-backed adapter
(Issue #22, packages/integrations/image_gen/fal_provider.py) through
ImageProvider — but only ever as a step of the per-post pipeline, driven
by a creative brief's `format` field. This endpoint calls a sibling
function, generate_standalone_images (added alongside that hook), which
reuses the exact same ImageProvider + StorageProvider interface calls
without requiring a Post or creative brief — just a free-form prompt plus
the aspect-ratio/style/brand-lock choices the Content AI page collects.

Logged as an AgentRun(agent_type=GENERATION, post_id=None) — same
"no Post exists for a standalone call" convention apps/api/routers/
creative.py's angle endpoint uses.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from apps.api.auth.dependencies import CurrentUser
from apps.api.config.database import get_db
from apps.api.middleware.rbac import require_role
from apps.api.models import AgentRun, AgentType, Brand, UserRole
from apps.api.schemas.content_ai import ContentAIGenerateRequest, ContentAIGenerateResponse
from packages.agents.pipeline.nodes.generation_engine import generate_standalone_images

router = APIRouter(prefix="/brands/{brand_id}/content-ai", tags=["content-ai"])

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


def _compose_prompt(brand: Brand, payload: ContentAIGenerateRequest) -> str:
    """Folds the page's aspect-ratio/style/brand-lock choices into the
    prompt handed to ImageProvider — no client-side image manipulation,
    just richer prompt text, same "reshape what's already decided, don't
    invent a second code path" spirit as generation_engine.py's own
    _build_image_prompt."""
    parts = [payload.prompt.strip()]
    if payload.style:
        parts.append(f"Style: {payload.style}.")
    if payload.aspect_ratio:
        parts.append(f"Aspect ratio: {payload.aspect_ratio}.")
    if payload.lock_brand_colors:
        colors = ", ".join(brand.colors) if brand.colors else None
        brand_hint = f"Use {brand.name}'s brand colors"
        if colors:
            brand_hint += f" ({colors})"
        brand_hint += " and logo; no off-brand palettes."
        parts.append(brand_hint)
    return " ".join(parts)


@router.post("/generate", response_model=ContentAIGenerateResponse, status_code=status.HTTP_201_CREATED)
def generate_images(
    brand_id: uuid.UUID,
    payload: ContentAIGenerateRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(*WRITE_ROLES)),
) -> ContentAIGenerateResponse:
    brand = _get_org_brand(db, brand_id, current_user.org_id)

    prompt = _compose_prompt(brand, payload)
    variants = generate_standalone_images(prompt, count=payload.count, path_prefix=str(brand.id))

    db.add(
        AgentRun(
            post_id=None,
            agent_type=AgentType.GENERATION,
            input={
                "brand_id": str(brand.id),
                "prompt": payload.prompt,
                "aspect_ratio": payload.aspect_ratio,
                "style": payload.style,
                "lock_brand_colors": payload.lock_brand_colors,
                "count": payload.count,
            },
            output={"variants": variants},
        )
    )
    db.flush()

    return ContentAIGenerateResponse(variants=variants)
