from apps.api.config import get_settings
from packages.integrations.llm.base import LLMProvider
from packages.integrations.llm.openai_provider import OpenAIProvider
from packages.integrations.llm.openrouter_provider import OpenRouterProvider
from packages.integrations.search.base import SearchProvider
from packages.integrations.search.tavily import TavilyProvider

_SEARCH_PROVIDERS = {
    "tavily": lambda settings: TavilyProvider(api_key=settings.tavily_api_key or ""),
}

_LLM_PROVIDERS = {
    "openrouter": lambda settings: OpenRouterProvider(
        api_key=settings.openrouter_api_key or ""
    ),
    "openai": lambda settings: OpenAIProvider(api_key=settings.openai_api_key or ""),
}


def get_search_provider() -> SearchProvider:
    settings = get_settings()
    try:
        factory = _SEARCH_PROVIDERS[settings.search_provider]
    except KeyError:
        raise ValueError(
            f"Unknown SEARCH_PROVIDER '{settings.search_provider}'. "
            f"Valid options: {sorted(_SEARCH_PROVIDERS)}"
        ) from None
    return factory(settings)


def get_llm_provider() -> LLMProvider:
    settings = get_settings()
    try:
        factory = _LLM_PROVIDERS[settings.llm_provider]
    except KeyError:
        raise ValueError(
            f"Unknown LLM_PROVIDER '{settings.llm_provider}'. "
            f"Valid options: {sorted(_LLM_PROVIDERS)}"
        ) from None
    return factory(settings)
