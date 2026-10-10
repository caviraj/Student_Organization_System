"""Request identity, security headers and one log line per request (Phase 7).

The log line is deliberately poor in detail: method, path, status, duration, request id. Query
strings are dropped and headers are never touched, because this API carries the things that must
never reach a log file - an `Authorization` header, an unsubscribe token in a query string, a
signed receipt URL, the Supabase service-role key. A request log that leaks one of those is worse
than no request log, so the safe thing is not optional. `tests/test_hardening.py` proves it.
"""

import logging
import time
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

log = logging.getLogger("ssa.request")

REQUEST_ID_HEADER = "X-Request-ID"

# Static, so they cost nothing and apply to every response including errors. The API is JSON-only
# and serves no HTML, so the usual CSP is unnecessary; these three close the classic browser holes
# if someone ever points a browser at it.
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
}


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid4().hex
        # On `request.state` so the error handlers and anything else can quote it in a log line.
        request.state.request_id = request_id
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # The exception handlers turn this into a response; this line exists so a crash is
            # still one line in the request log with its duration, alongside the traceback.
            log.exception(
                "%s %s -> 500 in %.0fms [%s]",
                request.method,
                request.url.path,
                (time.perf_counter() - started) * 1000,
                request_id,
            )
            raise
        elapsed_ms = (time.perf_counter() - started) * 1000
        response.headers[REQUEST_ID_HEADER] = request_id
        for header, value in SECURITY_HEADERS.items():
            response.headers[header] = value
        log.info(
            "%s %s -> %s in %.0fms [%s]",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            request_id,
        )
        return response
