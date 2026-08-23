from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"

    database_url: str = "postgresql://localhost:5432/raindeer"
    redis_url: str = "redis://localhost:6379/0"

    secret_key: str = "change-me"
    # Dev-only default (a real, valid Fernet key so local/test runs work
    # out of the box) — MUST be overridden via env var in any shared or
    # production environment, same as secret_key above.
    token_encryption_key: str = "QtL_FkRTyDfHNqO_DEnaz8S3DIbvvz9MwmTn1hmfe1o="

    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    openrouter_api_key: str | None = None
    tavily_api_key: str | None = None

    linkedin_client_id: str | None = None
    linkedin_client_secret: str | None = None
    linkedin_redirect_uri: str | None = None

    search_provider: str = "tavily"
    llm_provider: str = "openrouter"
    storage_provider: str = "supabase"
    embedding_provider: str = "openai"

    supabase_url: str | None = None
    supabase_service_key: str | None = None
    supabase_storage_bucket: str = "brand-assets"

    sentry_dsn: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
