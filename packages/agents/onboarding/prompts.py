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


def build_synthesis_prompt(
    brand_name: str, onboarding_response: dict, research: dict
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

## Web research
Brand overview: {json.dumps(research.get("brand_overview"))}
Competitor positioning: {json.dumps(research.get("competitor_positioning"))}

## Task
Produce a JSON object with exactly these top-level string keys:
- "voice_and_tone": 2-3 sentences describing the brand's voice and tone
- "audience": 2-3 sentences describing the target audience
- "product_catalog_summary": a summary of the product catalog
- "competitive_positioning": how this brand is positioned against its
  competitors, grounded in the web research above

Respond with ONLY the JSON object. No markdown code fences, no extra text.
"""
