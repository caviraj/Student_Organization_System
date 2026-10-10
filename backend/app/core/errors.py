"""Every error leaves the API as {"error": {"code", "message", "details"}} (DESIGN.md §5).

The handler is registered for **Starlette's** `HTTPException`, not FastAPI's. The router raises
the Starlette one for a 404 (no such path) and a 405 (known path, wrong method); `fastapi.
HTTPException` subclasses it, so one handler covers both. Registering only FastAPI's - the obvious
thing to write - silently misses those two, and the client gets Starlette's `{"detail": "Not
Found"}`, which has no `error.code` to switch on. Those are the two errors a client hits by
accident, so they are exactly the ones that must not have a different shape.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("ssa.errors")

# The framework's own statuses, named the way the rest of the API names its errors.
RAISED_BY_FRAMEWORK = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}


class AppError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict | None = None,
        headers: dict[str, str] | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}
        # Only 429 uses this so far (Retry-After), but the error handler already passed headers
        # through for the framework's own 401, and a rate limit without Retry-After is a guessing
        # game for the client.
        self.headers = headers


def error_body(code: str, message: str, details: dict | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def _validation_fields(exc: RequestValidationError) -> list[dict]:
    """`[{field, message}]`, because the frontend puts `message` under the input named `field` and
    has no use for pydantic's `loc`/`type`/`ctx`/`url` nesting. `loc[0]` is the location ("body",
    "query", "path"); the rest joined by dots is the field path."""
    fields = []
    for error in exc.errors():
        location = [str(part) for part in error.get("loc", ())]
        fields.append(
            {
                "field": ".".join(location[1:]) if len(location) > 1 else (location[0] if location else "body"),
                "message": error.get("msg", "Invalid value"),
            }
        )
    return fields


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(exc.code, exc.message, exc.details),
            headers=exc.headers,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = RAISED_BY_FRAMEWORK.get(exc.status_code, f"HTTP_{exc.status_code}")
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(code, str(exc.detail), None),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_body("VALIDATION_ERROR", "Request payload is invalid", {"fields": _validation_fields(exc)}),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # The traceback goes to the log with the request id; the response says nothing about it.
        log.exception(
            "unhandled error on %s %s [%s]", request.method, request.url.path, getattr(request.state, "request_id", "-")
        )
        return JSONResponse(status_code=500, content=error_body("INTERNAL_ERROR", "Something went wrong"))
