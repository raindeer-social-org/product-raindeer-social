import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class OnboardingUpsert(BaseModel):
    voice: str | None = None
    audience: str | None = None
    product_catalog: dict | None = None
    competitors: list[str] | None = None
    goals: list[str] | None = None


class OnboardingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID
    voice: str | None
    audience: str | None
    product_catalog: dict | None
    competitors: list[str] | None
    goals: list[str] | None
    is_complete: bool
    created_at: datetime
    updated_at: datetime
