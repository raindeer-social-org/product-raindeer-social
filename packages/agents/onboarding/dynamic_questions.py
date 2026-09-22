"""Aarav's adaptive follow-up questions — Issue #153, the core "Aarav is
actually an agent, not a static form" piece of the onboarding rebuild (see
Claude/aarav-agent/PLAN.md's Phase B for the full context this module fills
in).

The fixed OnboardingUpsert questionnaire (packages/agents/onboarding/
prompts.py's build_synthesis_prompt reads it) covers the required
baseline. This module generates what comes after it: up to MAX_DYNAMIC_PAGES
more pages of up-to-MAX_QUESTIONS_PER_PAGE questions each, one page at a
time, where every page's questions are generated from everything the brand
has answered so far — the fixed questionnaire AND every earlier dynamic
page. Aarav decides when it has enough to stop (`done`); a hard page cap
enforces an upper bound regardless of what the model says.

Same interface-only, degrade-on-failure contract as every other LLM call in
this codebase (research_engine.py/creative_engine.py/generation_engine.py/
reviewer_engine.py, packages/agents/onboarding/graph.py's own
_synthesize_node): calls LLMProvider exclusively through
packages.integrations.registry.get_llm_provider(), with the model read
fresh from apps.api.config.get_settings().llm_default_model on every call.
A broken/unconfigured provider, or a response that doesn't parse into a
usable page, must never block onboarding — it degrades to `done=True`
(the brand proceeds straight to the capstone/connect step) rather than
raising.
"""

import json
import logging
from typing import Any

from apps.api.config import get_settings
from apps.api.models.brand import Brand
from apps.api.models.onboarding_dynamic_answer import MAX_DYNAMIC_PAGES
from apps.api.models.onboarding_response import OnboardingResponse
from packages.integrations.registry import get_llm_provider

logger = logging.getLogger(__name__)

MAX_QUESTIONS_PER_PAGE = 5
ALLOWED_QUESTION_TYPES = ("text", "chips", "select", "voice")

SYSTEM_PROMPT = (
    "You are Aarav, a senior AI onboarding agent at a marketing agency, "
    "interviewing a new client brand. You've already been told some things "
    "about this brand — your job now is to ask ONLY what you don't already "
    "know and would genuinely need to write great marketing for this "
    "specific brand. Never re-ask something already answered below. Every "
    "question must be something a generic form couldn't have anticipated — "
    "specific to what THIS brand has told you, not a generic marketing "
    "questionnaire. Respond with strict JSON only — no markdown, no "
    "commentary, no code fences."
)


def _strip_code_fence(text: str) -> str:
    cleaned = text.strip()
    if not cleaned.startswith("```"):
        return cleaned
    cleaned = cleaned.strip("`")
    if cleaned.startswith("json"):
        cleaned = cleaned[len("json"):]
    return cleaned.strip()


def _default_model() -> str:
    return get_settings().llm_default_model


def _known_answers_block(brand: Brand, response: OnboardingResponse | None) -> str:
    if response is None:
        return "(nothing answered yet)"
    parts = [
        f"Voice: {response.voice or '(not given)'}",
        f"Audience: {response.audience or '(not given)'}",
        f"Product catalog: {json.dumps(response.product_catalog)}",
        f"Competitors: {', '.join(response.competitors or []) or '(not given)'}",
        f"Goals: {', '.join(response.goals or []) or '(not given)'}",
        f"Mission: {response.mission or '(not given)'}",
        f"Content dos/don'ts: {', '.join(response.content_dos_donts or []) or '(not given)'}",
        f"Posting cadence: {response.posting_cadence or '(not given)'}",
    ]
    if brand.industry:
        parts.insert(0, f"Industry: {brand.industry}")
    return "\n".join(parts)


def _prior_pages_block(prior_pages: list[dict[str, Any]]) -> str:
    if not prior_pages:
        return "(this is the first AI-generated page)"
    lines = []
    for page in prior_pages:
        for qa in page.get("answers", []):
            question = qa.get("question", {})
            lines.append(f"Q: {question.get('title')} -> A: {qa.get('answer')}")
    return "\n".join(lines) if lines else "(this is the first AI-generated page)"


def _build_prompt(
    brand: Brand,
    response: OnboardingResponse | None,
    prior_pages: list[dict[str, Any]],
    page_index: int,
    scrape_summary: str | None,
) -> str:
    return f"""{SYSTEM_PROMPT}

## Brand
{brand.name}

## Already known (fixed questionnaire)
{_known_answers_block(brand, response)}

## Already known (real website/social research summary)
{scrape_summary or "(no scrape summary available yet)"}

## Already asked and answered in earlier AI-generated pages
{_prior_pages_block(prior_pages)}

## Task
This is AI-generated page {page_index} of at most {MAX_DYNAMIC_PAGES}. Decide
whether you already have enough to write sharp, specific marketing for this
brand. If you do, respond with exactly:
{{"done": true, "questions": []}}

Otherwise, respond with up to {MAX_QUESTIONS_PER_PAGE} NEW questions (never
repeat something already known above) as:
{{"done": false, "questions": [
  {{"id": "<short_snake_case_id>", "type": "text|chips|select|voice",
    "title": "<the question>", "sub": "<one sentence on why you're asking>",
    "options": ["<only for chips/select>", "..."] }}
]}}

**Default to "chips" or "select", not "text".** A brand founder answering
on their phone should be able to tap an answer in one second, not compose a
paragraph — every question you ask should be answerable by picking from
options you already wrote for them, not by describing something in their
own words. Write 3-6 CONCRETE, SPECIFIC, mutually-distinct options per
question, grounded in what you already know about this brand (its
industry, its competitors, its own words from the scrape) — never generic
placeholders like "Option A" or vague ranges like "A little" / "A lot".
Use "select" when exactly one answer makes sense (a stage, a scale, a
single choice among alternatives) and "chips" when several can apply at
once (a set of channels, a set of pain points). Reach for "text" ONLY when
the honest answer is a specific proper noun, number, or short phrase you
could not plausibly enumerate in advance (a product name, a dollar figure,
a competitor you don't already know) — and even then, prefer phrasing the
question so a short chip-pickable answer would still make sense if you can.
Reach for "voice" only when you're deliberately inviting an open, in-their-
own-words answer (tone, story, personality) where forcing multiple choice
would flatten something worth hearing in full — use it sparingly, not as a
default.

Every `id` must be unique within this page. Respond with ONLY the JSON
object. No markdown code fences, no extra text.
"""


def _coerce_question(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Validates and normalizes one LLM-produced question dict. Returns
    None (caller drops it) rather than raising for a malformed entry —
    one bad question in the list shouldn't sink the whole page, same
    degrade-gracefully spirit as the rest of this module."""
    if not isinstance(raw, dict):
        return None
    qid = raw.get("id")
    title = raw.get("title")
    if not isinstance(qid, str) or not qid.strip() or not isinstance(title, str) or not title.strip():
        return None

    qtype = raw.get("type")
    if qtype not in ALLOWED_QUESTION_TYPES:
        qtype = "text"

    options = raw.get("options")
    if qtype in ("chips", "select"):
        if not isinstance(options, list) or not all(isinstance(o, str) for o in options) or not options:
            # A chips/select question with no usable options can't be
            # rendered — degrade it to free text instead of dropping the
            # question outright.
            qtype = "text"
            options = None
    else:
        options = None

    return {
        "id": qid.strip(),
        "type": qtype,
        "title": title.strip(),
        "sub": raw.get("sub") if isinstance(raw.get("sub"), str) else "",
        "options": options,
    }


def _parse_response(text: str) -> tuple[bool, list[dict[str, Any]]]:
    parsed = json.loads(_strip_code_fence(text))
    if not isinstance(parsed, dict):
        raise ValueError("dynamic-questions LLM output was valid JSON but not an object")

    done = bool(parsed.get("done"))
    raw_questions = parsed.get("questions")
    if not isinstance(raw_questions, list):
        raw_questions = []

    questions: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for raw in raw_questions[: MAX_QUESTIONS_PER_PAGE * 2]:  # tolerate a slightly-over-length response
        question = _coerce_question(raw)
        if question is None or question["id"] in seen_ids:
            continue
        seen_ids.add(question["id"])
        questions.append(question)
        if len(questions) >= MAX_QUESTIONS_PER_PAGE:
            break

    if not questions:
        done = True
    return done, questions


def generate_next_page(
    brand: Brand,
    response: OnboardingResponse | None,
    prior_pages: list[dict[str, Any]],
    page_index: int,
    scrape_summary: str | None = None,
) -> tuple[bool, list[dict[str, Any]]]:
    """Returns (done, questions) for AI-generated page `page_index`
    (1-indexed — page_index=1 is the first AI-generated page, right after
    the fixed questionnaire). `prior_pages` is every earlier generated
    page's questions+answers, e.g. [{"page_index": 1, "answers": [...]}],
    used so later pages don't repeat earlier ones and can build on them.

    Enforces MAX_DYNAMIC_PAGES itself (never calls the LLM past the cap)
    and degrades to (True, []) — "done, nothing more to ask" — on any
    LLM/parse failure, exactly like every other LLM call in this codebase
    degrades rather than taking onboarding down with it.
    """
    if page_index > MAX_DYNAMIC_PAGES:
        return True, []

    prompt = _build_prompt(brand, response, prior_pages, page_index, scrape_summary)
    try:
        llm_response = get_llm_provider().complete(
            prompt=prompt, model=_default_model(), temperature=0.6
        )
        return _parse_response(llm_response.text)
    except Exception:
        logger.warning(
            "Aarav dynamic-questions LLM call/parse failed for brand=%s page=%s; "
            "degrading to done=True",
            brand.id,
            page_index,
            exc_info=True,
        )
        return True, []
