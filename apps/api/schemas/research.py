import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ResearchRunRead(BaseModel):
    """Issue #126 — one standalone Research Engine run (see
    packages/agents/pipeline/nodes/research_engine.py::run_standalone_research),
    surfaced outside the per-post pipeline so the Research workspace page
    can render trend cards without a full 5-stage run. `brief` is exactly
    the dict _research_brief produces: brand_context, platform_trends,
    industry_trends, timing_signal."""

    id: uuid.UUID
    post_id: uuid.UUID
    brand_id: uuid.UUID
    created_at: datetime
    brief: dict[str, Any]
