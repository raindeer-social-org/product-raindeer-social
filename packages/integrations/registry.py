from apps.api.config import get_settings
from packages.integrations.embedding.base import EmbeddingProvider
from packages.integrations.embedding.openai_provider import OpenAIEmbeddingProvider
from packages.integrations.image_gen.base import ImageProvider
from packages.integrations.image_gen.fal_provider import FalImageProvider
from packages.integrations.llm.base import LLMProvider
from packages.integrations.llm.openai_provider import OpenAIProvider
from packages.integrations.llm.openrouter_provider import OpenRouterProvider
from packages.integrations.search.base import SearchProvider
from packages.integrations.search.tavily import TavilyProvider
from packages.integrations.social.base import SocialOAuthProvider, SocialPublisher
from packages.integrations.social.facebook_provider import FacebookProvider
from packages.integrations.social.instagram_provider import InstagramProvider
from packages.integrations.social.linkedin_provider import LinkedInProvider
from packages.integrations.social.threads_provider import ThreadsProvider
from packages.integrations.social.x_provider import XProvider
from packages.integrations.storage.base import StorageProvider
from packages.integrations.storage.supabase_provider import SupabaseStorageProvider
from packages.integrations.video_gen.base import VideoProvider
from packages.integrations.video_gen.runway_provider import RunwayProvider

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
    "x": lambda settings: XProvider(
        client_id=settings.x_client_id or "",
        client_secret=settings.x_client_secret or "",
    ),
    # Instagram, Threads, and Facebook are all Meta Graph API products
    # registered under one Meta developer app, so they share
    # META_APP_ID/META_APP_SECRET rather than each getting its own
    # client_id/secret pair the way LinkedIn/X do.
    "instagram": lambda settings: InstagramProvider(
        client_id=settings.meta_app_id or "",
        client_secret=settings.meta_app_secret or "",
    ),
    "threads": lambda settings: ThreadsProvider(
        client_id=settings.meta_app_id or "",
        client_secret=settings.meta_app_secret or "",
    ),
    "facebook": lambda settings: FacebookProvider(
        client_id=settings.meta_app_id or "",
        client_secret=settings.meta_app_secret or "",
    ),
}

# Every publisher is currently the same adapter instance that also
# implements SocialOAuthProvider for its platform (one class, two
# interfaces) — kept as a separate registry/lookup function anyway so
# callers (the #31 publish queue) depend only on SocialPublisher, not on
# the OAuth-connection interface.
_SOCIAL_PUBLISHERS = {
    "linkedin": lambda settings: LinkedInProvider(
        client_id=settings.linkedin_client_id or "",
        client_secret=settings.linkedin_client_secret or "",
    ),
    "x": lambda settings: XProvider(
        client_id=settings.x_client_id or "",
        client_secret=settings.x_client_secret or "",
    ),
    "instagram": lambda settings: InstagramProvider(
        client_id=settings.meta_app_id or "",
        client_secret=settings.meta_app_secret or "",
    ),
    "threads": lambda settings: ThreadsProvider(
        client_id=settings.meta_app_id or "",
        client_secret=settings.meta_app_secret or "",
    ),
    "facebook": lambda settings: FacebookProvider(
        client_id=settings.meta_app_id or "",
        client_secret=settings.meta_app_secret or "",
    ),
}

_STORAGE_PROVIDERS = {
    "supabase": lambda settings: SupabaseStorageProvider(
        base_url=settings.supabase_url or "",
        service_key=settings.supabase_service_key or "",
        bucket=settings.supabase_storage_bucket,
    ),
}

_IMAGE_PROVIDERS = {
    "fal": lambda settings: FalImageProvider(api_key=settings.fal_api_key or ""),
}

_VIDEO_PROVIDERS = {
    "runway": lambda settings: RunwayProvider(api_key=settings.runway_api_key or ""),
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


def get_social_publisher(platform: str) -> SocialPublisher:
    # Same one-per-platform shape as get_social_oauth_provider above, and
    # for the same reason: a brand publishes to every platform it's
    # connected, not just one selected via settings.
    settings = get_settings()
    try:
        factory = _SOCIAL_PUBLISHERS[platform]
    except KeyError:
        raise ValueError(
            f"Unknown social platform '{platform}'. "
            f"Valid options: {sorted(_SOCIAL_PUBLISHERS)}"
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


def get_image_provider() -> ImageProvider:
    settings = get_settings()
    try:
        factory = _IMAGE_PROVIDERS[settings.image_provider]
    except KeyError:
        raise ValueError(
            f"Unknown IMAGE_PROVIDER '{settings.image_provider}'. "
            f"Valid options: {sorted(_IMAGE_PROVIDERS)}"
        ) from None
    return factory(settings)


def get_video_provider() -> VideoProvider:
    settings = get_settings()
    try:
        factory = _VIDEO_PROVIDERS[settings.video_provider]
    except KeyError:
        raise ValueError(
            f"Unknown VIDEO_PROVIDER '{settings.video_provider}'. "
            f"Valid options: {sorted(_VIDEO_PROVIDERS)}"
        ) from None
    return factory(settings)
