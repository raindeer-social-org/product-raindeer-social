from fastapi import FastAPI

from apps.api.auth.router import router as auth_router
from apps.api.config import get_settings
from apps.api.middleware.logging import RequestLoggingMiddleware, configure_json_logging
from apps.api.observability import init_sentry

settings = get_settings()
configure_json_logging()
init_sentry(settings.sentry_dsn, settings.environment)

app = FastAPI(title="Raindeer Social API")
app.add_middleware(RequestLoggingMiddleware)
app.include_router(auth_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.environment}
