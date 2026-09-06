import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class OnboardingUpsert(BaseModel):
    voice: str | None = None
    audience: str | None = None
    product_catalog: dict | None = None
    competitors: list[str] | None = None
    goals: list[str] | None = None
    mission: str | None = None
    content_dos_donts: list[str] | None = None
    posting_cadence: str | None = None


class OnboardingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID
    voice: str | None
    audience: str | None
    product_catalog: dict | None
    competitors: list[str] | None
    goals: list[str] | None
    mission: str | None
    content_dos_donts: list[str] | None
    posting_cadence: str | None
    is_complete: bool
    created_at: datetime
    updated_at: datetime


class OnboardingVoiceAnswerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID
    question_id: str
    transcript: str
    audio_url: str
    language: str | None
    duration_seconds: float | None
    created_at: datetime


class OnboardingAssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID
    slot: str
    url: str
    filename: str
    content_type: str
    created_at: datetime
