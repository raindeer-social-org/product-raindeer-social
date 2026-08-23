from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from packages.schemas.error import ErrorResponse

_CODE_FOR_STATUS = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    422: "validation_error",
    429: "rate_limited",
}


def _error_response(
    status_code: int, code: str, message: str, details: dict | list | None = None
) -> JSONResponse:
    # jsonable_encoder, not a plain .model_dump(): a validator that raises a
    # bare ValueError leaves that exception object sitting in
    # errors()[i]["ctx"]["error"], which json.dumps can't serialize —
    # jsonable_encoder converts it (and anything else non-JSON-native, like
    # UUIDs/datetimes surfacing from `details`) safely instead of 500ing.
    body = ErrorResponse(code=code, message=message, details=details).model_dump()
    return JSONResponse(status_code=status_code, content=jsonable_encoder(body))


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    return _error_response(
        exc.status_code,
        code=_CODE_FOR_STATUS.get(exc.status_code, "error"),
        message=str(exc.detail),
    )


def _stringify_error_ctx(errors: list[dict]) -> list[dict]:
    # pydantic-core embeds the raised exception object itself at
    # ctx["error"] (not its message) when a custom validator fails —
    # replace it with its message so it survives JSON encoding intact
    # instead of collapsing to "{}".
    sanitized = []
    for err in errors:
        err = dict(err)
        ctx = err.get("ctx")
        if isinstance(ctx, dict) and isinstance(ctx.get("error"), Exception):
            err["ctx"] = {**ctx, "error": str(ctx["error"])}
        sanitized.append(err)
    return sanitized


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return _error_response(
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        code="validation_error",
        message="Request validation failed",
        details=_stringify_error_ctx(exc.errors()),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Deliberately generic — never leak internals (stack traces, exception
    # messages) to the client. Sentry (Issue #6) still captures the real
    # exception; this handler only shapes what the client sees.
    return _error_response(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        code="internal_error",
        message="An unexpected error occurred",
    )


def register_error_handlers(app: FastAPI) -> None:
    # StarletteHTTPException, not fastapi.HTTPException: Starlette's own
    # routing raises the base class directly for cases like an unmatched
    # route (404) — a handler registered on fastapi's HTTPException (a
    # subclass) would not catch that, since dispatch matches the raised
    # exception's actual type walking up its MRO, not down into subclasses.
    # fastapi.HTTPException, used throughout the app's own route code, IS
    # an instance of this base class, so registering here catches both.
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
