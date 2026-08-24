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

    # OpenRouter's free-models router — swap for a paid model slug (e.g.
    # "anthropic/claude-sonnet-4.5") once quality/latency needs outgrow it.
    # Every agent reads its default model from here rather than hardcoding
    # one, so upgrading later is a one-line env change, not a code change.
    llm_default_model: str = "openrouter/free"

    supabase_url: str | None = None
    supabase_service_key: str | None = None
    supabase_storage_bucket: str = "brand-assets"

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
