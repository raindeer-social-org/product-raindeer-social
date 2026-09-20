import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


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


# --- Adaptive, LLM-generated follow-up questions (Issue #153) ---
# The fixed OnboardingUpsert questionnaire above covers the required
# baseline; these run after it, generated one page at a time by Aarav from
# everything answered so far. See packages/agents/onboarding/dynamic_questions.py.

DynamicQuestionType = Literal["text", "chips", "select", "voice"]


class DynamicQuestion(BaseModel):
    """One Aarav-generated question. `options` is only meaningful for
    chips/select — text/voice questions ignore it."""

    id: str
    type: DynamicQuestionType
    title: str
    sub: str = ""
    options: list[str] | None = None


class DynamicAnswerSubmit(BaseModel):
    """One answered question from the page being submitted. `question` is
    echoed back exactly as it was generated (not re-derived) so the
    persisted OnboardingDynamicAnswer row records precisely what was
    asked. `answer` is a string for text/voice/select, a list of strings
    for chips."""

    question: DynamicQuestion
    answer: str | list[str]


class NextQuestionsRequest(BaseModel):
    # The page index whose answers are being submitted now (0 means "no
    # prior dynamic page — just generate the first one"). answers is
    # empty on that first call.
    page_index: int = Field(default=0, ge=0)
    answers: list[DynamicAnswerSubmit] = Field(default_factory=list)


class NextQuestionsResponse(BaseModel):
    done: bool
    page_index: int = 0
    questions: list[DynamicQuestion] = Field(default_factory=list)


class OnboardingDynamicAnswerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID
    page_index: int
    question: dict[str, Any]
    answer: Any
    created_at: datetime
