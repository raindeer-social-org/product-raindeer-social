from fastapi import FastAPI, Request, status
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
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(code=code, message=message, details=details).model_dump(),
    )


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    return _error_response(
        exc.status_code,
        code=_CODE_FOR_STATUS.get(exc.status_code, "error"),
        message=str(exc.detail),
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return _error_response(
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        code="validation_error",
        message="Request validation failed",
        details=exc.errors(),
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
