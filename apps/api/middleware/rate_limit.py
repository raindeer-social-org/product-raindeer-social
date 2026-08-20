import time
from collections.abc import Awaitable, Callable

import jwt
import redis
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from apps.api.auth.jwt import decode_access_token
from apps.api.config import get_settings
from packages.schemas.error import ErrorResponse

DEFAULT_LIMIT = 100
DEFAULT_WINDOW_SECONDS = 60
DEFAULT_RATE_LIMITED_PATH_PREFIXES = ("/auth", "/brands")


def _rate_limit_key(request: Request) -> str:
    """Per-org where possible (a real bearer token identifies the org),
    falling back to client IP for unauthenticated requests — /auth/login
    itself needs a limit too, and there's no org_id before login succeeds."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.removeprefix("Bearer ")
        try:
            payload = decode_access_token(token)
            org_id = payload.get("org_id")
            if org_id:
                return f"org:{org_id}"
        except jwt.PyJWTError:
            pass

    client_host = request.client.host if request.client else "unknown"
    return f"ip:{client_host}"


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        redis_client: redis.Redis | None = None,
        limit: int = DEFAULT_LIMIT,
        window_seconds: int = DEFAULT_WINDOW_SECONDS,
        path_prefixes: tuple[str, ...] = DEFAULT_RATE_LIMITED_PATH_PREFIXES,
    ) -> None:
        super().__init__(app)
        self.redis = redis_client or redis.from_url(get_settings().redis_url)
        self.limit = limit
        self.window_seconds = window_seconds
        self.path_prefixes = path_prefixes

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if not request.url.path.startswith(self.path_prefixes):
            return await call_next(request)

        window = int(time.time()) // self.window_seconds
        key = f"ratelimit:{_rate_limit_key(request)}:{window}"

        count = self.redis.incr(key)
        if count == 1:
            self.redis.expire(key, self.window_seconds)

        if count > self.limit:
            ttl = self.redis.ttl(key)
            retry_after = ttl if ttl and ttl > 0 else self.window_seconds
            return JSONResponse(
                status_code=429,
                content=ErrorResponse(
                    code="rate_limited", message="Too many requests"
                ).model_dump(),
                headers={"Retry-After": str(retry_after)},
            )

        return await call_next(request)
