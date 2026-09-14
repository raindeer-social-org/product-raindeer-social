from pydantic import BaseModel, Field

DEFAULT_VARIANT_COUNT = 4
MAX_VARIANT_COUNT = 4


class ContentAIGenerateRequest(BaseModel):
    """Body for POST .../content-ai/generate — the Content AI page's
    image-first fast path. `prompt` is the free-form image description;
    `aspect_ratio`/`style` are folded into the composed prompt handed to
    ImageProvider, and `lock_brand_colors` appends an instruction to stay
    within the brand's palette/logo rather than doing any client-side
    color manipulation."""

    prompt: str = Field(min_length=1)
    aspect_ratio: str | None = None
    style: str | None = None
    lock_brand_colors: bool = True
    count: int = Field(default=DEFAULT_VARIANT_COUNT, ge=1, le=MAX_VARIANT_COUNT)


class ContentAIVariantRead(BaseModel):
    status: str
    url: str | None


class ContentAIGenerateResponse(BaseModel):
    variants: list[ContentAIVariantRead]
