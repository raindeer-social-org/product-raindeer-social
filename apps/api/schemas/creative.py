from pydantic import BaseModel, Field

from packages.agents.pipeline.nodes.creative_engine import ANGLE_COUNT


class CreativeAnglesRequest(BaseModel):
    """Body for POST .../creative/angles. `brief` is the Creative page's
    free-form textarea — the only input generate_creative_angles needs."""

    brief: str = Field(min_length=1)
    count: int = Field(default=ANGLE_COUNT, ge=1, le=ANGLE_COUNT)


class CreativeAngleRead(BaseModel):
    format: str
    angle: str
    hook: str
    why: str
    cta: str
    score: int


class CreativeAnglesResponse(BaseModel):
    angles: list[CreativeAngleRead]
