import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from apps.api.models.content_calendar_event import SUPPORTED_PLATFORMS, CalendarEventStatus


def _validate_platforms(platforms: list[str]) -> list[str]:
    unknown = [p for p in platforms if p not in SUPPORTED_PLATFORMS]
    if unknown:
        raise ValueError(
            f"Unsupported platform(s) {unknown}. Supported: {list(SUPPORTED_PLATFORMS)}"
        )
    return platforms


class CalendarEventCreate(BaseModel):
    title: str
    description: str | None = None
    target_platforms: list[str]
    desired_format: str
    target_datetime: datetime

    @field_validator("target_platforms")
    @classmethod
    def _check_platforms(cls, v: list[str]) -> list[str]:
        return _validate_platforms(v)


class CalendarEventUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    target_platforms: list[str] | None = None
    desired_format: str | None = None
    target_datetime: datetime | None = None
    status: CalendarEventStatus | None = None

    @field_validator("target_platforms")
    @classmethod
    def _check_platforms(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        return _validate_platforms(v)


class CalendarEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID
    title: str
    description: str | None
    target_platforms: list[str]
    desired_format: str
    target_datetime: datetime
    status: CalendarEventStatus
    created_at: datetime
    updated_at: datetime
