import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from apps.api.models.social_account import SocialAccountStatus, SocialPlatform


class SocialAccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID
    platform: SocialPlatform
    external_account_id: str | None
    token_expires_at: datetime | None
    scopes: list[str] | None
    status: SocialAccountStatus
    created_at: datetime
    updated_at: datetime


class AuthorizeUrlRead(BaseModel):
    authorize_url: str
