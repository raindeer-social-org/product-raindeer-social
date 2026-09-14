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

    # --- Status notifications (Issue #32) ---
    # Generic SMTP, not a vendor SDK — works with any transactional-email
    # provider that exposes SMTP credentials (SES/SendGrid/Postmark/
    # Resend/...). Left unset (smtp_host=None) disables email sending;
    # apps/api/services/notifications.py's EmailAdapter no-ops rather than
    # attempting a connection.
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    notification_from_email: str | None = None
    # Slack incoming-webhook URL. Left unset disables Slack notifications;
    # apps/api/services/notifications.py's SlackWebhookAdapter no-ops
    # rather than posting to an empty URL.
    slack_webhook_url: str | None = None

    # Issue #29: how far ahead of a ContentCalendarEvent's target_datetime
    # (in minutes) the pipeline trigger job starts its pipeline run. Read
    # by apps/api/worker.py's Celery Beat task; the actual selection logic
    # in packages/agents/pipeline/trigger.py takes it as a plain argument
    # so it stays unit-testable without touching Settings.
    pipeline_trigger_lead_minutes: int = 60

    # Issue #105: how often (in hours) Ved's standing research job
    # (packages/agents/pipeline/nodes/research_engine.py's
    # run_standalone_brand_research) re-runs research for every active
    # brand, independent of whether a post happens to be scheduled onto
    # the calendar — keeps research fresh between calendar slots rather
    # than only refreshing each time the #29 pipeline trigger above fires
    # for a due post. Read by apps/api/worker.py's Celery Beat schedule at
    # process start, same "Settings field feeds a worker.py schedule/
    # parameter" convention as pipeline_trigger_lead_minutes above.
    # Default of 4.5h sits in the middle of the "every 4-5 hours" band
    # the issue asks for.
    research_refresh_interval_hours: float = 4.5

    # --- CORS (Issue #68) ---
    # Comma-separated list of origins allowed to make cross-origin
    # requests to the API (e.g. the Next.js dev server). Kept as a raw
    # string here (rather than a `list[str]` field) so a plain
    # comma-separated env var works without needing JSON-encoding —
    # see `cors_origins_list` for the parsed form.
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
