from fastapi import FastAPI

from apps.api.auth.router import router as auth_router
from apps.api.config import get_settings
from apps.api.middleware.error_handlers import register_error_handlers
from apps.api.middleware.logging import RequestLoggingMiddleware, configure_json_logging
from apps.api.middleware.rate_limit import RateLimitMiddleware
from apps.api.observability import init_sentry
from apps.api.routers.brands import router as brands_router

settings = get_settings()
configure_json_logging()
init_sentry(settings.sentry_dsn, settings.environment)

app = FastAPI(title="Raindeer Social API")
register_error_handlers(app)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.include_router(auth_router)
app.include_router(brands_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.environment}
