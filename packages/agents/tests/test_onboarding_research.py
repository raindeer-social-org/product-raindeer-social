from unittest.mock import MagicMock, patch

from apps.api.models import Brand, IntegrationCall, OnboardingResearch, OnboardingResponse, Organization
from packages.agents.onboarding.research_step import run_onboarding_research
from packages.integrations.search.base import SearchResult


def _setup_brand(db_session, competitors: list[str] | None = None) -> tuple[Brand, OnboardingResponse]:
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
        competitors=competitors or [],
        goals=["Grow"],
    )
    db_session.add(response)
    db_session.flush()
    return brand, response


def test_research_step_stores_structured_overview_and_positioning(db_session) -> None:
    brand, response = _setup_brand(db_session, competitors=["Widgetron", "GadgetCo"])

    overview_results = [SearchResult(title="Acme raises Series A", url="https://x.test/a", content="...")]
    competitor_results = [SearchResult(title="Widgetron review", url="https://x.test/b", content="...")]

    with patch("packages.agents.onboarding.research_step.get_search_provider") as mock_provider:
        mock_provider.return_value.search.side_effect = [
            overview_results,  # brand overview query
            competitor_results,  # vs Widgetron
            competitor_results,  # vs GadgetCo
        ]
        research = run_onboarding_research(db_session, brand, response)

    assert research.brand_overview == [
        {"title": "Acme raises Series A", "url": "https://x.test/a", "content": "..."}
    ]
    assert set(research.competitor_positioning.keys()) == {"Widgetron", "GadgetCo"}
    assert research.competitor_positioning["Widgetron"][0]["title"] == "Widgetron review"


def test_research_step_calls_search_provider_only_through_interface(db_session) -> None:
    brand, response = _setup_brand(db_session)

    with patch("packages.agents.onboarding.research_step.get_search_provider") as mock_provider:
        mock_provider.return_value.search.return_value = []
        run_onboarding_research(db_session, brand, response)

    mock_provider.assert_called()


def test_research_step_degrades_gracefully_on_provider_failure(db_session) -> None:
    brand, response = _setup_brand(db_session, competitors=["Widgetron"])

    with patch("packages.agents.onboarding.research_step.get_search_provider") as mock_provider:
        mock_provider.return_value.search.side_effect = Exception("Tavily timed out")
        research = run_onboarding_research(db_session, brand, response)

    assert research.brand_overview == []
    assert research.competitor_positioning == {"Widgetron": []}


def test_research_step_limits_competitors_queried(db_session) -> None:
    brand, response = _setup_brand(
        db_session, competitors=["A", "B", "C", "D", "E"]
    )

    with patch("packages.agents.onboarding.research_step.get_search_provider") as mock_provider:
        mock_provider.return_value.search.return_value = []
        research = run_onboarding_research(db_session, brand, response)

    assert len(research.competitor_positioning) == 3


def test_research_step_upserts_on_rerun(db_session) -> None:
    brand, response = _setup_brand(db_session)

    with patch("packages.agents.onboarding.research_step.get_search_provider") as mock_provider:
        mock_provider.return_value.search.return_value = []
        run_onboarding_research(db_session, brand, response)
        run_onboarding_research(db_session, brand, response)

    rows = db_session.query(OnboardingResearch).filter(OnboardingResearch.brand_id == brand.id).all()
    assert len(rows) == 1


def test_research_step_logs_integration_call_via_real_provider(db_session) -> None:
    brand, response = _setup_brand(db_session)

    mock_response = MagicMock()
    mock_response.json.return_value = {"results": []}
    mock_response.raise_for_status.return_value = None

    with patch("httpx.post", return_value=mock_response):
        run_onboarding_research(db_session, brand, response)

    logged = (
        db_session.query(IntegrationCall)
        .filter_by(provider="tavily", capability="search")
        .order_by(IntegrationCall.created_at.desc())
        .first()
    )
    assert logged is not None
