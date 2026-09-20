import json
import uuid
from collections.abc import Generator

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from apps.api.auth.dependencies import CurrentUser, get_current_user
from apps.api.config.database import get_db
from apps.api.middleware.rbac import require_role
from apps.api.models import (
    ONBOARDING_ASSET_SLOTS,
    Brand,
    OnboardingAsset,
    OnboardingDynamicAnswer,
    OnboardingResponse,
    OnboardingVoiceAnswer,
    UserRole,
)
from apps.api.schemas.brand import BrandRead
from apps.api.schemas.onboarding import (
    NextQuestionsRequest,
    NextQuestionsResponse,
    OnboardingAssetRead,
    OnboardingRead,
    OnboardingUpsert,
    OnboardingVoiceAnswerRead,
)
from packages.agents.onboarding.dynamic_questions import generate_next_page
from packages.agents.onboarding.embedding import embed_brand_report
from packages.agents.onboarding.graph import run_onboarding_agent
from packages.agents.onboarding.research_step import (
    run_onboarding_research,
    run_website_scrape,
    search_brand_overview,
)
from packages.integrations.registry import get_speech_provider, get_storage_provider

router = APIRouter(prefix="/brands/{brand_id}/onboarding", tags=["onboarding"])

WRITE_ROLES = (UserRole.OWNER, UserRole.ADMIN, UserRole.EDITOR)


def _get_org_brand(db: Session, brand_id: uuid.UUID, org_id: str) -> Brand:
    brand = (
        db.query(Brand)
        .filter(Brand.id == brand_id, Brand.organization_id == uuid.UUID(org_id))
        .first()
    )
    if brand is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand not found")
    return brand


def _get_response_or_404(db: Session, brand_id: uuid.UUID) -> OnboardingResponse:
    response = (
        db.query(OnboardingResponse)
        .filter(OnboardingResponse.brand_id == brand_id)
        .first()
    )
    if response is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Onboarding not started for this brand",
        )
    return response


@router.get("", response_model=OnboardingRead)
def get_onboarding(
    brand_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> OnboardingResponse:
    _get_org_brand(db, brand_id, current_user.org_id)
    return _get_response_or_404(db, brand_id)


@router.put("", response_model=OnboardingRead)
def upsert_onboarding(
    brand_id: uuid.UUID,
    payload: OnboardingUpsert,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(*WRITE_ROLES)),
) -> OnboardingResponse:
    _get_org_brand(db, brand_id, current_user.org_id)

    response = (
        db.query(OnboardingResponse)
        .filter(OnboardingResponse.brand_id == brand_id)
        .first()
    )
    if response is None:
        response = OnboardingResponse(brand_id=brand_id)
        db.add(response)
        db.flush()
    elif response.is_complete:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Onboarding is already complete and can no longer be edited",
        )

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(response, field, value)
    db.flush()
    db.refresh(response)
    return response


@router.post("/complete", response_model=OnboardingRead)
def complete_onboarding(
    brand_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(*WRITE_ROLES)),
) -> OnboardingResponse:
    """The gate the onboarding agent (Issue #15) checks before it can run —
    fails loudly with exactly what's missing rather than letting the agent
    start against incomplete data."""
    _get_org_brand(db, brand_id, current_user.org_id)
    response = _get_response_or_404(db, brand_id)

    missing = response.missing_required_fields()
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot complete onboarding — missing required fields: {', '.join(missing)}",
        )

    response.is_complete = True
    db.flush()
    db.refresh(response)
    return response


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.get("/research-stream")
def stream_research_preview(
    brand_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> StreamingResponse:
    """Issue #123: Server-Sent-Events endpoint the Aarav onboarding
    interview's "scrape" question uses to show real progress while
    previewing what public web research turns up for a brand.

    This reuses the exact same SearchProvider-backed search
    (search_brand_overview, a thin wrapper the onboarding research step
    below already used privately) that run_onboarding_research runs later
    for the brand_report synthesis agent — just surfaced live, and earlier
    in the flow. It deliberately does NOT call run_onboarding_research
    itself: that function also requires a competitors list and is only
    reachable once onboarding.is_complete, neither of which holds this
    early in the interview.

    Issue #152 adds a second, real phase after the search preview: if the
    brand has a website on file (product_catalog["website"], the field
    this same interview step already displays), this actually fetches and
    scrapes it (run_website_scrape) — extracting a logo/color-palette
    suggestion and an LLM-distilled summary — and, unlike the search
    preview above, DOES persist the result onto OnboardingResearch (an
    "extracted" event carries it to the frontend as a one-click-accept
    suggestion; see interview/page.tsx's runScrape). A brand with no
    website on file, or an unreachable one, simply skips straight to
    "done" — this never blocks the interview.
    """
    brand = _get_org_brand(db, brand_id, current_user.org_id)
    website = (brand.product_catalog or {}).get("website") if isinstance(brand.product_catalog, dict) else None

    def event_stream() -> Generator[str, None, None]:
        yield _sse("log", {"text": f"Connecting to {brand.name}’s public presence…"})
        yield _sse("log", {"text": "Searching the public web for a company overview…"})
        results = search_brand_overview(brand.name)
        yield _sse("log", {"text": f"Found {len(results)} public signal(s)."})
        for result in results:
            yield _sse("signal", {"title": result.title, "url": result.url})

        if website:
            yield _sse("log", {"text": f"Fetching {website}…"})
            research = run_website_scrape(db, brand, website)
            if research.website_summary or research.website_logo_url or research.website_colors:
                yield _sse("log", {"text": "Extracted a logo, colors, and a brand summary."})
                yield _sse(
                    "extracted",
                    {
                        "logo_url": research.website_logo_url,
                        "colors": research.website_colors or [],
                        "summary": research.website_summary,
                    },
                )
            else:
                yield _sse("log", {"text": "Couldn't extract anything usable from that site — that's okay."})

        yield _sse("done", {"count": len(results)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/run-agent", response_model=BrandRead)
def run_agent(
    brand_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(*WRITE_ROLES)),
) -> Brand:
    """Runs the onboarding research step (#14) followed by the onboarding
    LangGraph agent (#15), writing the resulting brand_report onto the
    Brand row. Requires onboarding to already be complete — the agent
    reads questionnaire answers that may still be missing otherwise."""
    brand = _get_org_brand(db, brand_id, current_user.org_id)
    response = _get_response_or_404(db, brand_id)

    if not response.is_complete:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Onboarding must be completed before running the agent",
        )

    research = run_onboarding_research(db, brand, response)
    run_onboarding_agent(db, brand, response, research)
    # Re-embeds on every completion/update of brand_report — embed_brand_report
    # replaces this brand's existing chunks rather than appending to them.
    embed_brand_report(db, brand)
    return brand


# --- Real voice recording + free open-source transcription (Issue #144) ---
# Replaces the interview's old "voice" question, which recorded nothing at
# all ("Recording is illustrative only — no audio is captured").


@router.post("/voice-answers", response_model=OnboardingVoiceAnswerRead)
def create_voice_answer(
    brand_id: uuid.UUID,
    question_id: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(*WRITE_ROLES)),
) -> OnboardingVoiceAnswer:
    """Transcribes a recorded onboarding answer via SpeechToTextProvider
    (packages/integrations/speech — faster-whisper, free and fully
    open-source, no API key/cost) and durably stores both the raw audio
    (via StorageProvider, same as brand logos/generated media) and the
    transcript — "everything voice" persisted, not discarded once read.
    Every take is appended as its own row (see OnboardingVoiceAnswer's
    docstring) rather than overwriting a prior recording for the same
    question."""
    brand = _get_org_brand(db, brand_id, current_user.org_id)
    audio_bytes = file.file.read()
    content_type = file.content_type or "audio/webm"

    result = get_speech_provider().transcribe(audio_bytes, content_type)

    extension = content_type.split("/")[-1].split(";")[0] or "webm"
    path = f"onboarding/{brand.id}/voice/{question_id}/{uuid.uuid4().hex}.{extension}"
    audio_url = get_storage_provider().upload(path, audio_bytes, content_type)

    answer = OnboardingVoiceAnswer(
        brand_id=brand.id,
        question_id=question_id,
        transcript=result.text,
        audio_url=audio_url,
        language=result.language,
        duration_seconds=result.duration_seconds,
    )
    db.add(answer)
    db.flush()
    db.refresh(answer)
    return answer


@router.get("/voice-answers", response_model=list[OnboardingVoiceAnswerRead])
def list_voice_answers(
    brand_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[OnboardingVoiceAnswer]:
    _get_org_brand(db, brand_id, current_user.org_id)
    return (
        db.query(OnboardingVoiceAnswer)
        .filter(OnboardingVoiceAnswer.brand_id == brand_id)
        .order_by(OnboardingVoiceAnswer.created_at)
        .all()
    )


# --- Real asset uploads (Issue #144) ---
# Replaces the interview's old 4 upload slots, which were decorative divs
# wired to no file input at all.


@router.post("/assets", response_model=OnboardingAssetRead)
def upload_onboarding_asset(
    brand_id: uuid.UUID,
    slot: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(*WRITE_ROLES)),
) -> OnboardingAsset:
    if slot not in ONBOARDING_ASSET_SLOTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown slot {slot!r}. Valid options: {sorted(ONBOARDING_ASSET_SLOTS)}",
        )
    brand = _get_org_brand(db, brand_id, current_user.org_id)
    content = file.file.read()
    content_type = file.content_type or "application/octet-stream"
    filename = file.filename or slot

    path = f"onboarding/{brand.id}/assets/{slot}/{uuid.uuid4().hex}-{filename}"
    url = get_storage_provider().upload(path, content, content_type)

    asset = (
        db.query(OnboardingAsset)
        .filter(OnboardingAsset.brand_id == brand.id, OnboardingAsset.slot == slot)
        .first()
    )
    if asset is None:
        asset = OnboardingAsset(brand_id=brand.id, slot=slot, url=url, filename=filename, content_type=content_type)
        db.add(asset)
    else:
        # Re-uploading to an already-filled slot replaces it — one current
        # value per slot, same model as Brand.logo_url.
        asset.url = url
        asset.filename = filename
        asset.content_type = content_type
    db.flush()
    db.refresh(asset)
    return asset


@router.get("/assets", response_model=list[OnboardingAssetRead])
def list_onboarding_assets(
    brand_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[OnboardingAsset]:
    _get_org_brand(db, brand_id, current_user.org_id)
    return (
        db.query(OnboardingAsset)
        .filter(OnboardingAsset.brand_id == brand_id)
        .order_by(OnboardingAsset.created_at)
        .all()
    )


# --- Adaptive, LLM-generated follow-up questions (Issue #153) ---
# Runs after the fixed questionnaire above: each page's questions are
# generated by Aarav from everything answered so far (fixed fields + every
# earlier dynamic page), instead of being a static form. See
# packages/agents/onboarding/dynamic_questions.py for the generation logic
# and Claude/aarav-agent/PLAN.md for the wider context.


def _prior_dynamic_pages(db: Session, brand_id: uuid.UUID) -> list[dict]:
    rows = (
        db.query(OnboardingDynamicAnswer)
        .filter(OnboardingDynamicAnswer.brand_id == brand_id)
        .order_by(OnboardingDynamicAnswer.page_index, OnboardingDynamicAnswer.created_at)
        .all()
    )
    pages: dict[int, list[dict]] = {}
    for row in rows:
        pages.setdefault(row.page_index, []).append({"question": row.question, "answer": row.answer})
    return [{"page_index": index, "answers": answers} for index, answers in sorted(pages.items())]


@router.post("/next-questions", response_model=NextQuestionsResponse)
def next_questions(
    brand_id: uuid.UUID,
    payload: NextQuestionsRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(*WRITE_ROLES)),
) -> NextQuestionsResponse:
    """Persists `payload.answers` (the page the caller just finished, if
    any — empty on the very first call) as OnboardingDynamicAnswer rows,
    then asks Aarav to generate the next page. Durable by construction:
    an answered page is on file before the next page is even generated,
    so a client that disconnects mid-flow never loses what was already
    answered."""
    brand = _get_org_brand(db, brand_id, current_user.org_id)

    if payload.answers:
        for item in payload.answers:
            db.add(
                OnboardingDynamicAnswer(
                    brand_id=brand.id,
                    page_index=payload.page_index,
                    question=item.question.model_dump(),
                    answer=item.answer,
                )
            )
        db.flush()

    response = (
        db.query(OnboardingResponse)
        .filter(OnboardingResponse.brand_id == brand_id)
        .first()
    )
    prior_pages = _prior_dynamic_pages(db, brand_id)
    next_page_index = payload.page_index + 1

    done, questions = generate_next_page(brand, response, prior_pages, next_page_index)

    if done:
        return NextQuestionsResponse(done=True, page_index=0, questions=[])
    return NextQuestionsResponse(done=False, page_index=next_page_index, questions=questions)
