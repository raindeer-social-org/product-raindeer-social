import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BrandCreate(BaseModel):
    name: str
    industry: str | None = None
    logo_url: str | None = None
    target_audience: str | None = None
    colors: list[str] | None = None
    tone_descriptors: list[str] | None = None
    product_catalog: dict | None = None


class BrandUpdate(BaseModel):
    name: str | None = None
    industry: str | None = None
    logo_url: str | None = None
    target_audience: str | None = None
    colors: list[str] | None = None
    tone_descriptors: list[str] | None = None
    product_catalog: dict | None = None


class BrandRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    industry: str | None
    logo_url: str | None
    target_audience: str | None
    colors: list[str] | None
    tone_descriptors: list[str] | None
    product_catalog: dict | None
    brand_report: dict | None
    created_at: datetime
    updated_at: datetime
