"""Walk the app's real routes, with the full path each one answers on.

`app.routes` is not a flat list. `include_router` leaves a wrapper per included router that holds
the prefix and the inner `APIRoute` objects, and an inner route's `.path` is relative to that
prefix - so reading `app.routes` directly finds `/health` and misses all seventy real endpoints.
Both `scripts/contract_check.py` and `tests/test_hardening.py` need the same view of the app, and a
copy in each would be a copy that drifts.

The wrapper is FastAPI-internal, so the caller is not trusted to notice a version that renames it:
`tests/test_hardening.py` asserts the count this returns against `app.openapi()`, which fails loudly
if an upgrade changes the shape rather than quietly reporting an empty API.
"""

from collections.abc import Iterator

from fastapi import FastAPI
from fastapi.routing import APIRoute


def iter_api_routes(app: FastAPI) -> Iterator[tuple[str, APIRoute]]:
    """`(full path, route)` for every endpoint, in registration order."""
    for route in app.routes:
        context = getattr(route, "include_context", None)  # set by include_router
        inner = getattr(route, "original_router", None)
        if context is not None and inner is not None:
            for sub in inner.routes:
                if isinstance(sub, APIRoute):
                    yield context.prefix + sub.path, sub
        elif isinstance(route, APIRoute):
            yield route.path, route
