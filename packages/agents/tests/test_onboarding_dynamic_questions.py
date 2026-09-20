import json
from unittest.mock import patch

from apps.api.models import Brand, OnboardingResponse, Organization
from packages.agents.onboarding.dynamic_questions import MAX_DYNAMIC_PAGES, generate_next_page
from packages.integrations.llm.base import LLMResponse


def _setup(db_session) -> tuple[Brand, OnboardingResponse]:
    org = Organization(name="Acme Agency")
    db_session.add(org)
    db_session.flush()

    brand = Brand(organization_id=org.id, name="Acme Widgets", industry="SaaS")
    db_session.add(brand)
    db_session.flush()

    response = OnboardingResponse(
        brand_id=brand.id,
        voice="Playful",
        audience="Gen Z",
        product_catalog={"items": ["Widget A"]},
        competitors=["Widgetron"],
        goals=["Grow"],
    )
    db_session.add(response)
    db_session.flush()
    return brand, response


def _mock_llm(text: str) -> LLMResponse:
    return LLMResponse(text=text, model="test-model", input_tokens=100, output_tokens=50)


_PATCH_TARGET = "packages.agents.onboarding.dynamic_questions.get_llm_provider"


def test_generate_next_page_returns_parsed_questions(db_session) -> None:
    brand, response = _setup(db_session)
    payload = {
        "done": False,
        "questions": [
            {
                "id": "integrations",
                "type": "chips",
                "title": "Which tools do you integrate with?",
                "sub": "Helps Ved research the right competitors.",
                "options": ["QuickBooks", "Stripe", "Shopify"],
            }
        ],
    }

    with patch(_PATCH_TARGET) as mock_get_llm:
        mock_get_llm.return_value.complete.return_value = _mock_llm(json.dumps(payload))
        done, questions = generate_next_page(brand, response, [], page_index=1)

    assert done is False
    assert questions == [
        {
            "id": "integrations",
            "type": "chips",
            "title": "Which tools do you integrate with?",
            "sub": "Helps Ved research the right competitors.",
            "options": ["QuickBooks", "Stripe", "Shopify"],
        }
    ]


def test_generate_next_page_done_true_short_circuits(db_session) -> None:
    brand, response = _setup(db_session)

    with patch(_PATCH_TARGET) as mock_get_llm:
        mock_get_llm.return_value.complete.return_value = _mock_llm(json.dumps({"done": True, "questions": []}))
        done, questions = generate_next_page(brand, response, [], page_index=2)

    assert done is True
    assert questions == []


def test_generate_next_page_caps_at_five_questions(db_session) -> None:
    brand, response = _setup(db_session)
    payload = {
        "done": False,
        "questions": [
            {"id": f"q{i}", "type": "text", "title": f"Question {i}", "sub": ""} for i in range(8)
        ],
    }

    with patch(_PATCH_TARGET) as mock_get_llm:
        mock_get_llm.return_value.complete.return_value = _mock_llm(json.dumps(payload))
        done, questions = generate_next_page(brand, response, [], page_index=1)

    assert done is False
    assert len(questions) == 5


def test_generate_next_page_downgrades_chips_with_no_options_to_text(db_session) -> None:
    brand, response = _setup(db_session)
    payload = {
        "done": False,
        "questions": [{"id": "q1", "type": "chips", "title": "Pick some", "sub": "", "options": []}],
    }

    with patch(_PATCH_TARGET) as mock_get_llm:
        mock_get_llm.return_value.complete.return_value = _mock_llm(json.dumps(payload))
        done, questions = generate_next_page(brand, response, [], page_index=1)

    assert questions[0]["type"] == "text"
    assert questions[0]["options"] is None


def test_generate_next_page_drops_malformed_questions_but_keeps_valid_ones(db_session) -> None:
    brand, response = _setup(db_session)
    payload = {
        "done": False,
        "questions": [
            {"id": "", "type": "text", "title": "Missing id"},
            {"type": "text", "title": "No id field at all"},
            {"id": "valid", "type": "text", "title": "A real question", "sub": "why"},
        ],
    }

    with patch(_PATCH_TARGET) as mock_get_llm:
        mock_get_llm.return_value.complete.return_value = _mock_llm(json.dumps(payload))
        done, questions = generate_next_page(brand, response, [], page_index=1)

    assert len(questions) == 1
    assert questions[0]["id"] == "valid"


def test_generate_next_page_degrades_to_done_on_llm_failure(db_session) -> None:
    brand, response = _setup(db_session)

    with patch(_PATCH_TARGET) as mock_get_llm:
        mock_get_llm.return_value.complete.side_effect = RuntimeError("provider unreachable")
        done, questions = generate_next_page(brand, response, [], page_index=1)

    assert done is True
    assert questions == []


def test_generate_next_page_degrades_to_done_on_unparseable_json(db_session) -> None:
    brand, response = _setup(db_session)

    with patch(_PATCH_TARGET) as mock_get_llm:
        mock_get_llm.return_value.complete.return_value = _mock_llm("not json at all")
        done, questions = generate_next_page(brand, response, [], page_index=1)

    assert done is True
    assert questions == []


def test_generate_next_page_enforces_hard_cap_without_calling_llm(db_session) -> None:
    brand, response = _setup(db_session)

    with patch(_PATCH_TARGET) as mock_get_llm:
        done, questions = generate_next_page(brand, response, [], page_index=MAX_DYNAMIC_PAGES + 1)

    assert done is True
    assert questions == []
    mock_get_llm.assert_not_called()


def test_generate_next_page_works_with_no_onboarding_response_yet(db_session) -> None:
    org = Organization(name="Acme Agency")
    db_session.add(org)
    db_session.flush()
    brand = Brand(organization_id=org.id, name="Acme Widgets")
    db_session.add(brand)
    db_session.flush()

    with patch(_PATCH_TARGET) as mock_get_llm:
        mock_get_llm.return_value.complete.return_value = _mock_llm(json.dumps({"done": True, "questions": []}))
        done, questions = generate_next_page(brand, None, [], page_index=1)

    assert done is True
    assert questions == []
