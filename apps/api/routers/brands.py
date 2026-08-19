import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from apps.api.auth.dependencies import CurrentUser, get_current_user
from apps.api.config.database import get_db
from apps.api.middleware.rbac import require_role
from apps.api.models import Brand, UserRole
from apps.api.schemas.brand import BrandCreate, BrandRead, BrandUpdate
from packages.integrations.registry import get_storage_provider

router = APIRouter(prefix="/brands", tags=["brands"])

WRITE_ROLES = (UserRole.OWNER, UserRole.ADMIN, UserRole.EDITOR)


def _brand_logo_path(org_id: str, brand_id: uuid.UUID) -> str:
    # Fixed name (no original filename/extension) so delete can always
    # reconstruct the same path deterministically from org_id + brand_id
    # alone, and re-upload overwrites rather than accumulating orphans.
    # UUIDs, not incrementing ids — you can't guess another brand's path.
    return f"{org_id}/{brand_id}/logo"


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


@router.post("", response_model=BrandRead, status_code=status.HTTP_201_CREATED)
def create_brand(
    payload: BrandCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(*WRITE_ROLES)),
) -> Brand:
    brand = Brand(organization_id=uuid.UUID(current_user.org_id), **payload.model_dump())
    db.add(brand)
    db.flush()
    db.refresh(brand)
    return brand


@router.get("", response_model=list[BrandRead])
def list_brands(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[Brand]:
    return (
        db.query(Brand)
        .filter(Brand.organization_id == uuid.UUID(current_user.org_id))
        .all()
    )


@router.get("/{brand_id}", response_model=BrandRead)
def get_brand(
    brand_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> Brand:
    return _get_org_brand(db, brand_id, current_user.org_id)


@router.patch("/{brand_id}", response_model=BrandRead)
def update_brand(
    brand_id: uuid.UUID,
    payload: BrandUpdate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(*WRITE_ROLES)),
) -> Brand:
    brand = _get_org_brand(db, brand_id, current_user.org_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(brand, field, value)
    db.flush()
    db.refresh(brand)
    return brand


@router.delete("/{brand_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_brand(
    brand_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(*WRITE_ROLES)),
) -> None:
    brand = _get_org_brand(db, brand_id, current_user.org_id)
    db.delete(brand)
    db.flush()


@router.put("/{brand_id}/logo", response_model=BrandRead)
def upload_brand_logo(
    brand_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(*WRITE_ROLES)),
) -> Brand:
    brand = _get_org_brand(db, brand_id, current_user.org_id)
    content = file.file.read()
    path = _brand_logo_path(current_user.org_id, brand_id)

    storage = get_storage_provider()
    url = storage.upload(path, content, file.content_type or "application/octet-stream")

    brand.logo_url = url
    db.flush()
    db.refresh(brand)
    return brand


@router.delete("/{brand_id}/logo", response_model=BrandRead)
def delete_brand_logo(
    brand_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(*WRITE_ROLES)),
) -> Brand:
    brand = _get_org_brand(db, brand_id, current_user.org_id)
    storage = get_storage_provider()
    storage.delete(_brand_logo_path(current_user.org_id, brand_id))

    brand.logo_url = None
    db.flush()
    db.refresh(brand)
    return brand
