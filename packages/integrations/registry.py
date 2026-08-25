from apps.api.config import get_settings
from packages.integrations.embedding.base import EmbeddingProvider
from packages.integrations.embedding.openai_provider import OpenAIEmbeddingProvider
from packages.integrations.llm.base import LLMProvider
from packages.integrations.llm.openai_provider import OpenAIProvider
from packages.integrations.llm.openrouter_provider import OpenRouterProvider
from packages.integrations.search.base import SearchProvider
from packages.integrations.search.tavily import TavilyProvider
from packages.integrations.social.base import SocialOAuthProvider
from packages.integrations.social.linkedin_provider import LinkedInProvider
from packages.integrations.storage.base import StorageProvider
from packages.integrations.storage.supabase_provider import SupabaseStorageProvider

_SEARCH_PROVIDERS = {
    "tavily": lambda settings: TavilyProvider(api_key=settings.tavily_api_key or ""),
}

_LLM_PROVIDERS = {
    "openrouter": lambda settings: OpenRouterProvider(
        api_key=settings.openrouter_api_key or ""
    ),
    "openai": lambda settings: OpenAIProvider(api_key=settings.openai_api_key or ""),
}

_EMBEDDING_PROVIDERS = {
    "openai": lambda settings: OpenAIEmbeddingProvider(api_key=settings.openai_api_key or ""),
}

_SOCIAL_OAUTH_PROVIDERS = {
    "linkedin": lambda settings: LinkedInProvider(
        client_id=settings.linkedin_client_id or "",
        client_secret=settings.linkedin_client_secret or "",
    ),
}

_STORAGE_PROVIDERS = {
    "supabase": lambda settings: SupabaseStorageProvider(
        base_url=settings.supabase_url or "",
        service_key=settings.supabase_service_key or "",
        bucket=settings.supabase_storage_bucket,
    ),
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


def get_embedding_provider() -> EmbeddingProvider:
    settings = get_settings()
    try:
        factory = _EMBEDDING_PROVIDERS[settings.embedding_provider]
    except KeyError:
        raise ValueError(
            f"Unknown EMBEDDING_PROVIDER '{settings.embedding_provider}'. "
            f"Valid options: {sorted(_EMBEDDING_PROVIDERS)}"
        ) from None
    return factory(settings)


def get_social_oauth_provider(platform: str) -> SocialOAuthProvider:
    # Unlike search/LLM/storage, every platform coexists (a brand can
    # connect LinkedIn and X at once) rather than one being selected via
    # settings — so this is keyed by the requested platform, not by a
    # single *_PROVIDER setting.
    settings = get_settings()
    try:
        factory = _SOCIAL_OAUTH_PROVIDERS[platform]
    except KeyError:
        raise ValueError(
            f"Unknown social platform '{platform}'. "
            f"Valid options: {sorted(_SOCIAL_OAUTH_PROVIDERS)}"
        ) from None
    return factory(settings)


def get_storage_provider() -> StorageProvider:
    settings = get_settings()
    try:
        factory = _STORAGE_PROVIDERS[settings.storage_provider]
    except KeyError:
        raise ValueError(
            f"Unknown STORAGE_PROVIDER '{settings.storage_provider}'. "
            f"Valid options: {sorted(_STORAGE_PROVIDERS)}"
        ) from None
    return factory(settings)
