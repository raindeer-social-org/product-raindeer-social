from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"

    database_url: str = "postgresql://localhost:5432/raindeer"
    redis_url: str = "redis://localhost:6379/0"

    secret_key: str = "change-me"

    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    openrouter_api_key: str | None = None
    tavily_api_key: str | None = None

    search_provider: str = "tavily"
    llm_provider: str = "openrouter"
    storage_provider: str = "supabase"

    # OpenRouter's free-models router — swap for a paid model slug (e.g.
    # "anthropic/claude-sonnet-4.5") once quality/latency needs outgrow it.
    # Every agent reads its default model from here rather than hardcoding
    # one, so upgrading later is a one-line env change, not a code change.
    llm_default_model: str = "openrouter/free"

    supabase_url: str | None = None
    supabase_service_key: str | None = None
    supabase_storage_bucket: str = "brand-assets"

    sentry_dsn: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
