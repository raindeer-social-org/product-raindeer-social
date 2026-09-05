import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class BrandSettingsUpdate(BaseModel):
    auto_approve_enabled: bool | None = None
    auto_approve_threshold: int | None = Field(default=None, ge=0, le=100)
    show_agent_reasoning: bool | None = None
    email_review_digest_enabled: bool | None = None
    auto_shift_posting_times: bool | None = None


class BrandSettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID
    auto_approve_enabled: bool
    auto_approve_threshold: int
    show_agent_reasoning: bool
    email_review_digest_enabled: bool
    auto_shift_posting_times: bool
    created_at: datetime
    updated_at: datetime
