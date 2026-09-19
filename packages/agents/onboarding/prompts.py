import json

SYSTEM_PROMPT = (
    "You are a senior brand strategist synthesizing a Brand Report from a "
    "client's onboarding questionnaire and public web research. Respond "
    "with strict JSON only — no markdown, no commentary, no code fences."
)

REQUIRED_REPORT_KEYS = (
    "voice_and_tone",
    "audience",
    "product_catalog_summary",
    "competitive_positioning",
)


def _format_dynamic_qa(dynamic_qa: list[dict] | None) -> str:
    """Renders the adaptive-interview Q&A history (Issue #153) — each page
    Aarav generated at onboarding time, with what the brand answered — into
    plain text for the synthesis prompt. `dynamic_qa` mirrors
    apps/api/routers/onboarding.py::_prior_dynamic_pages's shape: a list of
    {"page_index", "answers": [{"question": {...}, "answer": ...}, ...]}."""
    if not dynamic_qa:
        return "(no follow-up questions were asked)"

    lines = []
    for page in dynamic_qa:
        for item in page.get("answers", []):
            question = item.get("question") or {}
            title = question.get("title") or question.get("id") or "(untitled question)"
            answer = item.get("answer")
            answer_text = ", ".join(answer) if isinstance(answer, list) else str(answer)
            lines.append(f"- {title} — {answer_text}")
    return "\n".join(lines) if lines else "(no follow-up questions were answered)"


def build_synthesis_prompt(
    brand_name: str,
    onboarding_response: dict,
    research: dict,
    dynamic_qa: list[dict] | None = None,
) -> str:
    return f"""{SYSTEM_PROMPT}

## Brand
{brand_name}

## Questionnaire answers
Voice: {onboarding_response.get("voice")}
Audience: {onboarding_response.get("audience")}
Product catalog: {json.dumps(onboarding_response.get("product_catalog"))}
Competitors: {", ".join(onboarding_response.get("competitors") or [])}
Goals: {", ".join(onboarding_response.get("goals") or [])}
Mission: {onboarding_response.get("mission") or "(not provided)"}
Content dos and don'ts: {", ".join(onboarding_response.get("content_dos_donts") or []) or "(none given)"}
Preferred posting cadence: {onboarding_response.get("posting_cadence") or "(not specified)"}

## Aarav's follow-up questions & answers (Issue #153)
Aarav asked these adaptively, each one informed by everything answered
before it — treat this as the most specific, most current signal about the
brand, ahead of the fixed questionnaire above where the two conflict.
{_format_dynamic_qa(dynamic_qa)}

## Web research
Brand overview: {json.dumps(research.get("brand_overview"))}
Competitor positioning: {json.dumps(research.get("competitor_positioning"))}

## What the brand's own website says about itself (Issue #152)
{research.get("website_summary") or "(no website scrape available)"}

## Task
Produce a JSON object with exactly these top-level string keys:
- "voice_and_tone": 2-3 sentences describing the brand's voice and tone —
  incorporate the stated mission and any content dos/don'ts so this reads
  as this brand's actual voice, not a generic tone description
- "audience": 2-3 sentences describing the target audience
- "product_catalog_summary": a summary of the product catalog — ground it
  in what the brand's own website says about itself above when that's
  available, not just the questionnaire's product_catalog field alone
- "competitive_positioning": how this brand is positioned against its
  competitors, grounded in the web research above

If a preferred posting cadence was given, factor it into how ambitious
"competitive_positioning" assumes this brand's content output can be.

Respond with ONLY the JSON object. No markdown code fences, no extra text.
"""
