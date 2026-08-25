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
    fal_api_key: str | None = None

    linkedin_client_id: str | None = None
    linkedin_client_secret: str | None = None
    linkedin_redirect_uri: str | None = None

    x_client_id: str | None = None
    x_client_secret: str | None = None
    x_redirect_uri: str | None = None
    # Reserved for X API app-level auth (e.g. the v1.1 media/upload
    # endpoint, which needs OAuth 1.0a rather than the OAuth2 bearer token
    # used everywhere else here) — not required by the OAuth2 publish flow
    # XProvider uses today.
    x_api_key: str | None = None

    search_provider: str = "tavily"
    llm_provider: str = "openrouter"
    storage_provider: str = "supabase"
    embedding_provider: str = "openai"
    video_provider: str = "runway"
    image_provider: str = "fal"

    # OpenRouter's free-models router — swap for a paid model slug (e.g.
    # "anthropic/claude-sonnet-4.5") once quality/latency needs outgrow it.
    # Every agent reads its default model from here rather than hardcoding
    # one, so upgrading later is a one-line env change, not a code change.
    llm_default_model: str = "openrouter/free"

    supabase_url: str | None = None
    supabase_service_key: str | None = None
    supabase_storage_bucket: str = "brand-assets"

    # Generation Engine's video/carousel branch (Issue #23).
    runway_api_key: str | None = None

    sentry_dsn: str | None = None

    # Issue #29: how far ahead of a ContentCalendarEvent's target_datetime
    # (in minutes) the pipeline trigger job starts its pipeline run. Read
    # by apps/api/worker.py's Celery Beat task; the actual selection logic
    # in packages/agents/pipeline/trigger.py takes it as a plain argument
    # so it stays unit-testable without touching Settings.
    pipeline_trigger_lead_minutes: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()
