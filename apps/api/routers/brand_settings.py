"""Per-brand agent-behavior settings (Issue #128).

A single row per brand persisting the toggles shown on the new Settings
page: auto-approve threshold, Arena reasoning visibility, the review-needed
email digest, and whether Ved is allowed to shift posting times
automatically (conceptually apps/api/services/scheduling_suggestion.py).

Unlike OnboardingResponse (apps/api/models/onboarding_response.py), GET
auto-provisions a default row instead of 404ing — Settings should always
have something sane to render, not a "not configured yet" empty state, and
there's no separate "start" action the way onboarding has one.

Nothing downstream reads this table yet — see the model's docstring
(apps/api/models/brand_settings.py). This endpoint only makes the user's
choice durable across a reload; wiring each toggle into the behavior it
describes is a follow-up.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from apps.api.auth.dependencies import CurrentUser, get_current_user
from apps.api.config.database import get_db
from apps.api.middleware.rbac import require_role
from apps.api.models import Brand, BrandSettings, UserRole
from apps.api.schemas.brand_settings import BrandSettingsRead, BrandSettingsUpdate

router = APIRouter(prefix="/brands/{brand_id}/settings", tags=["brand-settings"])

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


def _get_or_create_settings(db: Session, brand_id: uuid.UUID) -> BrandSettings:
    settings = db.query(BrandSettings).filter(BrandSettings.brand_id == brand_id).first()
    if settings is None:
        settings = BrandSettings(brand_id=brand_id)
        db.add(settings)
        db.flush()
        db.refresh(settings)
    return settings


@router.get("", response_model=BrandSettingsRead)
def get_brand_settings(
    brand_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> BrandSettings:
    _get_org_brand(db, brand_id, current_user.org_id)
    return _get_or_create_settings(db, brand_id)


@router.put("", response_model=BrandSettingsRead)
def update_brand_settings(
    brand_id: uuid.UUID,
    payload: BrandSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(*WRITE_ROLES)),
) -> BrandSettings:
    _get_org_brand(db, brand_id, current_user.org_id)
    settings = _get_or_create_settings(db, brand_id)

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(settings, field, value)
    db.flush()
    db.refresh(settings)
    return settings
