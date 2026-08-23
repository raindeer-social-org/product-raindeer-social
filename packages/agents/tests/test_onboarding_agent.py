import json
from unittest.mock import patch

import pytest

from apps.api.models import AgentRun, AgentType, Brand, OnboardingResearch, OnboardingResponse, Organization
from packages.agents.onboarding.graph import OnboardingSynthesisError, run_onboarding_agent
from packages.integrations.llm.base import LLMResponse

VALID_REPORT = {
    "voice_and_tone": "Playful and direct.",
    "audience": "Gen Z consumers who value sustainability.",
    "product_catalog_summary": "A line of eco-friendly widgets.",
    "competitive_positioning": "Positioned as the premium, sustainable alternative to Widgetron.",
}


def _setup(db_session) -> tuple[Brand, OnboardingResponse, OnboardingResearch]:
    org = Organization(name="Acme Agency")
    db_session.add(org)
    db_session.flush()

    brand = Brand(organization_id=org.id, name="Acme Widgets")
    db_session.add(brand)
    db_session.flush()

    response = OnboardingResponse(
        brand_id=brand.id,
        voice="Playful",
        audience="Gen Z",
        product_catalog={"items": ["Widget A"]},
        competitors=["Widgetron"],
        goals=["Grow"],
        is_complete=True,
    )
    research = OnboardingResearch(
        brand_id=brand.id,
        brand_overview=[{"title": "Acme raises Series A", "url": "https://x.test", "content": "..."}],
        competitor_positioning={"Widgetron": [{"title": "Widgetron review", "url": "https://x.test", "content": "..."}]},
    )
    db_session.add_all([response, research])
    db_session.flush()
    return brand, response, research


def _mock_llm(text: str) -> LLMResponse:
    return LLMResponse(text=text, model="anthropic/claude-sonnet-4.5", input_tokens=500, output_tokens=150)


def test_graph_runs_end_to_end_and_writes_brand_report(db_session) -> None:
    brand, response, research = _setup(db_session)

    with patch("packages.agents.onboarding.graph.get_llm_provider") as mock_get_llm:
        mock_get_llm.return_value.complete.return_value = _mock_llm(json.dumps(VALID_REPORT))
        report = run_onboarding_agent(db_session, brand, response, research)

    assert report == VALID_REPORT
    db_session.refresh(brand)
    assert brand.brand_report == VALID_REPORT


def test_graph_logs_agent_run_with_tokens_model_latency(db_session) -> None:
    brand, response, research = _setup(db_session)

    with patch("packages.agents.onboarding.graph.get_llm_provider") as mock_get_llm:
        mock_get_llm.return_value.complete.return_value = _mock_llm(json.dumps(VALID_REPORT))
        run_onboarding_agent(db_session, brand, response, research)

    run = (
        db_session.query(AgentRun)
        .filter(AgentRun.agent_type == AgentType.ONBOARDING)
        .order_by(AgentRun.created_at.desc())
        .first()
    )
    assert run is not None
    assert run.tokens == 650
    assert run.model == "anthropic/claude-sonnet-4.5"
    assert run.latency_ms is not None and run.latency_ms >= 0
    assert run.output == VALID_REPORT


def test_graph_uses_llm_provider_interface_not_direct_sdk(db_session) -> None:
    brand, response, research = _setup(db_session)

    with patch("packages.agents.onboarding.graph.get_llm_provider") as mock_get_llm:
        mock_get_llm.return_value.complete.return_value = _mock_llm(json.dumps(VALID_REPORT))
        run_onboarding_agent(db_session, brand, response, research)

    mock_get_llm.assert_called_once()
    mock_get_llm.return_value.complete.assert_called_once()


def test_graph_raises_and_still_logs_agent_run_on_malformed_json(db_session) -> None:
    brand, response, research = _setup(db_session)

    with patch("packages.agents.onboarding.graph.get_llm_provider") as mock_get_llm:
        mock_get_llm.return_value.complete.return_value = _mock_llm("not json at all")
        with pytest.raises(OnboardingSynthesisError):
            run_onboarding_agent(db_session, brand, response, research)

    run = (
        db_session.query(AgentRun)
        .filter(AgentRun.agent_type == AgentType.ONBOARDING)
        .order_by(AgentRun.created_at.desc())
        .first()
    )
    assert run is not None
    assert run.output is None

    db_session.refresh(brand)
    assert brand.brand_report is None  # untouched on failure


def test_graph_raises_on_missing_required_keys(db_session) -> None:
    brand, response, research = _setup(db_session)
    incomplete = {"voice_and_tone": "Playful"}

    with patch("packages.agents.onboarding.graph.get_llm_provider") as mock_get_llm:
        mock_get_llm.return_value.complete.return_value = _mock_llm(json.dumps(incomplete))
        with pytest.raises(OnboardingSynthesisError, match="missing required keys"):
            run_onboarding_agent(db_session, brand, response, research)


def test_graph_strips_markdown_code_fences() -> None:
    from packages.agents.onboarding.graph import _parse_report

    fenced = "```json\n" + json.dumps(VALID_REPORT) + "\n```"
    assert _parse_report(fenced) == VALID_REPORT


def test_graph_handles_missing_research(db_session) -> None:
    brand, response, _research = _setup(db_session)

    with patch("packages.agents.onboarding.graph.get_llm_provider") as mock_get_llm:
        mock_get_llm.return_value.complete.return_value = _mock_llm(json.dumps(VALID_REPORT))
        report = run_onboarding_agent(db_session, brand, response, research=None)

    assert report == VALID_REPORT
