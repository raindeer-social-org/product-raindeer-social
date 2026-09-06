import pytest

from apps.api.config import get_settings
from packages.integrations.llm.openai_provider import OpenAIProvider
from packages.integrations.llm.openrouter_provider import OpenRouterProvider
from packages.integrations.embedding.openai_provider import OpenAIEmbeddingProvider
from packages.integrations.registry import (
    get_embedding_provider,
    get_llm_provider,
    get_search_provider,
    get_social_oauth_provider,
)
from packages.integrations.search.tavily import TavilyProvider
from packages.integrations.social.linkedin_provider import LinkedInProvider


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


def test_get_social_oauth_provider_resolves_linkedin() -> None:
    assert isinstance(get_social_oauth_provider("linkedin"), LinkedInProvider)


def test_get_social_oauth_provider_resolves_new_platforms() -> None:
    from packages.integrations.social.facebook_provider import FacebookProvider
    from packages.integrations.social.instagram_provider import InstagramProvider
    from packages.integrations.social.pinterest_provider import PinterestProvider
    from packages.integrations.social.threads_provider import ThreadsProvider
    from packages.integrations.social.tiktok_provider import TikTokProvider
    from packages.integrations.social.youtube_provider import YouTubeProvider

    assert isinstance(get_social_oauth_provider("facebook"), FacebookProvider)
    assert isinstance(get_social_oauth_provider("instagram"), InstagramProvider)
    assert isinstance(get_social_oauth_provider("threads"), ThreadsProvider)
    assert isinstance(get_social_oauth_provider("youtube"), YouTubeProvider)
    assert isinstance(get_social_oauth_provider("tiktok"), TikTokProvider)
    assert isinstance(get_social_oauth_provider("pinterest"), PinterestProvider)


def test_unknown_social_platform_raises() -> None:
    with pytest.raises(ValueError, match="Unknown social platform"):
        get_social_oauth_provider("snapchat")


def test_get_embedding_provider_defaults_to_openai() -> None:
    assert isinstance(get_embedding_provider(), OpenAIEmbeddingProvider)


def test_unknown_embedding_provider_raises(monkeypatch) -> None:
    monkeypatch.setenv("EMBEDDING_PROVIDER", "cohere")
    with pytest.raises(ValueError, match="Unknown EMBEDDING_PROVIDER"):
        get_embedding_provider()
