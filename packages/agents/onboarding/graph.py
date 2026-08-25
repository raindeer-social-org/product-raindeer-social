import json
import time
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.models.agent_run import AgentRun, AgentType
from apps.api.models.brand import Brand
from apps.api.models.onboarding_research import OnboardingResearch
from apps.api.models.onboarding_response import OnboardingResponse
from packages.agents.onboarding.prompts import REQUIRED_REPORT_KEYS, build_synthesis_prompt
from packages.integrations.registry import get_llm_provider


def _default_model() -> str:
    """Reads LLM_DEFAULT_MODEL fresh on every call (not a module constant)
    so tests and per-environment overrides take effect without a reimport."""
    return get_settings().llm_default_model


class OnboardingSynthesisError(Exception):
    """Raised when the LLM's output can't be parsed into a usable brand_report."""


class _GraphState(TypedDict):
    prompt: str
    llm_text: str
    model: str
    tokens: int
    brand_report: dict


def _strip_code_fence(text: str) -> str:
    cleaned = text.strip()
    if not cleaned.startswith("```"):
        return cleaned
    cleaned = cleaned.strip("`")
    if cleaned.startswith("json"):
        cleaned = cleaned[len("json"):]
    return cleaned.strip()


def _parse_report(text: str) -> dict:
    try:
        report = json.loads(_strip_code_fence(text))
    except json.JSONDecodeError as exc:
        raise OnboardingSynthesisError(f"LLM output was not valid JSON: {exc}") from exc

    if not isinstance(report, dict):
        raise OnboardingSynthesisError("LLM output was valid JSON but not an object")

    missing = [key for key in REQUIRED_REPORT_KEYS if key not in report]
    if missing:
        raise OnboardingSynthesisError(f"brand_report missing required keys: {missing}")
    return report


def _synthesize_node(state: _GraphState) -> dict:
    llm = get_llm_provider()
    response = llm.complete(prompt=state["prompt"], model=_default_model(), temperature=0.4)
    report = _parse_report(response.text)
    return {
        "llm_text": response.text,
        "model": response.model,
        "tokens": response.input_tokens + response.output_tokens,
        "brand_report": report,
    }


def _build_graph():
    graph = StateGraph(_GraphState)
    graph.add_node("synthesize", _synthesize_node)
    graph.add_edge(START, "synthesize")
    graph.add_edge("synthesize", END)
    return graph.compile()


_COMPILED_GRAPH = _build_graph()


def run_onboarding_agent(
    db: Session,
    brand: Brand,
    onboarding_response: OnboardingResponse,
    research: OnboardingResearch | None,
) -> dict:
    """Runs the onboarding LangGraph graph end-to-end: questionnaire +
    research in, structured brand_report out, written onto the Brand row.
    Always logs an AgentRun — including on failure, where output is left
    None but latency/timing is still captured — before letting the
    exception (if any) propagate."""
    prompt = build_synthesis_prompt(
        brand_name=brand.name,
        onboarding_response={
            "voice": onboarding_response.voice,
            "audience": onboarding_response.audience,
            "product_catalog": onboarding_response.product_catalog,
            "competitors": onboarding_response.competitors,
            "goals": onboarding_response.goals,
        },
        research={
            "brand_overview": research.brand_overview if research else [],
            "competitor_positioning": research.competitor_positioning if research else {},
        },
    )

    start = time.perf_counter()
    result_state: _GraphState | None = None
    try:
        result_state = _COMPILED_GRAPH.invoke({"prompt": prompt})
    finally:
        latency_ms = (time.perf_counter() - start) * 1000
        db.add(
            AgentRun(
                agent_type=AgentType.ONBOARDING,
                input={"brand_id": str(brand.id)},
                output=result_state.get("brand_report") if result_state else None,
                model=result_state.get("model") if result_state else _default_model(),
                tokens=result_state.get("tokens") if result_state else None,
                latency_ms=latency_ms,
            )
        )
        db.flush()

    report = result_state["brand_report"]
    brand.brand_report = report
    db.flush()
    db.refresh(brand)
    return report
