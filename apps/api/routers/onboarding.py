import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from apps.api.auth.dependencies import CurrentUser, get_current_user
from apps.api.config.database import get_db
from apps.api.middleware.rbac import require_role
from apps.api.models import Brand, OnboardingResponse, UserRole
from apps.api.schemas.onboarding import OnboardingRead, OnboardingUpsert

router = APIRouter(prefix="/brands/{brand_id}/onboarding", tags=["onboarding"])

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


def _get_response_or_404(db: Session, brand_id: uuid.UUID) -> OnboardingResponse:
    response = (
        db.query(OnboardingResponse)
        .filter(OnboardingResponse.brand_id == brand_id)
        .first()
    )
    if response is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Onboarding not started for this brand",
        )
    return response


@router.get("", response_model=OnboardingRead)
def get_onboarding(
    brand_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> OnboardingResponse:
    _get_org_brand(db, brand_id, current_user.org_id)
    return _get_response_or_404(db, brand_id)


@router.put("", response_model=OnboardingRead)
def upsert_onboarding(
    brand_id: uuid.UUID,
    payload: OnboardingUpsert,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(*WRITE_ROLES)),
) -> OnboardingResponse:
    _get_org_brand(db, brand_id, current_user.org_id)

    response = (
        db.query(OnboardingResponse)
        .filter(OnboardingResponse.brand_id == brand_id)
        .first()
    )
    if response is None:
        response = OnboardingResponse(brand_id=brand_id)
        db.add(response)
        db.flush()
    elif response.is_complete:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Onboarding is already complete and can no longer be edited",
        )

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(response, field, value)
    db.flush()
    db.refresh(response)
    return response


@router.post("/complete", response_model=OnboardingRead)
def complete_onboarding(
    brand_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(*WRITE_ROLES)),
) -> OnboardingResponse:
    """The gate the onboarding agent (Issue #15) checks before it can run —
    fails loudly with exactly what's missing rather than letting the agent
    start against incomplete data."""
    _get_org_brand(db, brand_id, current_user.org_id)
    response = _get_response_or_404(db, brand_id)

    missing = response.missing_required_fields()
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot complete onboarding — missing required fields: {', '.join(missing)}",
        )

    response.is_complete = True
    db.flush()
    db.refresh(response)
    return response
