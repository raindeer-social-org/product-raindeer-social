import pytest

from apps.api.config import get_settings
from packages.integrations.llm.openai_provider import OpenAIProvider
from packages.integrations.llm.openrouter_provider import OpenRouterProvider
from packages.integrations.registry import get_llm_provider, get_search_provider
from packages.integrations.search.tavily import TavilyProvider


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_get_search_provider_defaults_to_tavily() -> None:
    assert isinstance(get_search_provider(), TavilyProvider)


def test_get_llm_provider_defaults_to_openrouter() -> None:
    assert isinstance(get_llm_provider(), OpenRouterProvider)


def test_get_llm_provider_resolves_openai_from_env(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    assert isinstance(get_llm_provider(), OpenAIProvider)


def test_unknown_search_provider_raises(monkeypatch) -> None:
    monkeypatch.setenv("SEARCH_PROVIDER", "serper")
    with pytest.raises(ValueError, match="Unknown SEARCH_PROVIDER"):
        get_search_provider()


def test_unknown_llm_provider_raises(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "cohere")
    with pytest.raises(ValueError, match="Unknown LLM_PROVIDER"):
        get_llm_provider()
