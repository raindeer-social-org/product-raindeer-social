import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from apps.api.auth.dependencies import CurrentUser, get_current_user
from apps.api.config.database import get_db
from apps.api.middleware.rbac import require_role
from apps.api.models import Brand, ContentCalendarEvent, UserRole
from apps.api.schemas.calendar import CalendarEventCreate, CalendarEventRead, CalendarEventUpdate
from apps.api.services.scheduling_suggestion import (
    NoResearchSignalError,
    suggest_target_datetime,
)

router = APIRouter(prefix="/brands/{brand_id}/calendar-events", tags=["calendar"])

WRITE_ROLES = (UserRole.OWNER, UserRole.ADMIN, UserRole.EDITOR)


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


def _get_event_or_404(db: Session, brand_id: uuid.UUID, event_id: uuid.UUID) -> ContentCalendarEvent:
    event = (
        db.query(ContentCalendarEvent)
        .filter(
            ContentCalendarEvent.id == event_id,
            ContentCalendarEvent.brand_id == brand_id,
        )
        .first()
    )
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Calendar event not found")
    return event


@router.post("", response_model=CalendarEventRead, status_code=status.HTTP_201_CREATED)
def create_event(
    brand_id: uuid.UUID,
    payload: CalendarEventCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(*WRITE_ROLES)),
) -> ContentCalendarEvent:
    _get_org_brand(db, brand_id, current_user.org_id)
    data = payload.model_dump()

    # #28: an explicitly provided target_datetime always wins — the
    # suggestion service is only consulted when the caller left it out.
    if data["target_datetime"] is None:
        # A calendar event can target multiple platforms at once; the
        # suggestion service proposes a single datetime for one platform,
        # so the first requested platform drives it (the same platform the
        # research brief itself would have been keyed on if this event
        # already existed when research ran).
        suggestion_platform = payload.target_platforms[0]
        try:
            suggestion = suggest_target_datetime(db, brand_id, suggestion_platform)
        except NoResearchSignalError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "target_datetime was not provided and no research signal is "
                    f"available yet to suggest one ({exc}). Provide target_datetime "
                    "explicitly."
                ),
            ) from exc
        data["target_datetime"] = suggestion.target_datetime

    event = ContentCalendarEvent(brand_id=brand_id, **data)
    db.add(event)
    db.flush()
    db.refresh(event)
    return event


@router.get("", response_model=list[CalendarEventRead])
def list_events(
    brand_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[ContentCalendarEvent]:
    _get_org_brand(db, brand_id, current_user.org_id)
    return (
        db.query(ContentCalendarEvent)
        .filter(ContentCalendarEvent.brand_id == brand_id)
        .order_by(ContentCalendarEvent.target_datetime)
        .all()
    )


@router.get("/{event_id}", response_model=CalendarEventRead)
def get_event(
    brand_id: uuid.UUID,
    event_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ContentCalendarEvent:
    _get_org_brand(db, brand_id, current_user.org_id)
    return _get_event_or_404(db, brand_id, event_id)


@router.patch("/{event_id}", response_model=CalendarEventRead)
def update_event(
    brand_id: uuid.UUID,
    event_id: uuid.UUID,
    payload: CalendarEventUpdate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(*WRITE_ROLES)),
) -> ContentCalendarEvent:
    _get_org_brand(db, brand_id, current_user.org_id)
    event = _get_event_or_404(db, brand_id, event_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(event, field, value)
    db.flush()
    db.refresh(event)
    return event


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(
    brand_id: uuid.UUID,
    event_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(*WRITE_ROLES)),
) -> None:
    _get_org_brand(db, brand_id, current_user.org_id)
    event = _get_event_or_404(db, brand_id, event_id)
    db.delete(event)
    db.flush()
