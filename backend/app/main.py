"""SSA Hub API — Phases 1-7 (Auth & Membership, Events & Tickets, Announcements, Merchandise,
Fundraisers & Tasks, Expenses & Treasurer Finance, Hardening & Docs)."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.errors import register_error_handlers
from app.core.middleware import RequestContextMiddleware
from app.jobs.scheduler import start_scheduler, stop_scheduler
from app.routers import (
    admin_portal,
    announcements,
    auth,
    checkin,
    events,
    expenses,
    finance,
    fundraisers,
    members,
    memberships,
    merch_admin,
    orders,
    payments,
    plans,
    preferences,
    products,
    staff_portal,
    student_portal,
    tasks,
    tickets,
    users,
)

API_PREFIX = "/api/v1"

# Our own loggers are silent otherwise: nothing configures logging, so the root logger's default
# level drops INFO and `EMAIL_PROVIDER=console` would print nothing at all. Scoped to "ssa" on
# purpose - the root logger at INFO would also dump every SQL statement SQLAlchemy emits.
_ssa_log = logging.getLogger("ssa")
if not _ssa_log.handlers:
    _ssa_log.setLevel(logging.INFO)
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    _ssa_log.addHandler(_handler)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Expiry scan at startup then daily; stale-checkout sweep and announcement deliveries every
    # 5 and 60 seconds.
    settings.enforce_startup_config()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="SSA Hub API",
    version="1.0.0",
    description=(
        "Skyline Student Association platform — phases 1-7: auth & membership, events & tickets, "
        "announcements, merchandise, fundraisers & tasks, expenses & treasurer finance.\n\n"
        'All endpoints are under `/api/v1`. Errors are `{"error": {"code", "message", "details"}}`; '
        'lists are `{"items", "total", "page", "page_size"}`. Money is integer paise. '
        "Timestamps are UTC and always end in `Z`. See `docs/API_HANDOFF.md` for the client guide."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Added last, so it wraps CORS: the request id and the security headers are on the response even
# when CORS rejects the request, which is the case someone is most likely to be debugging.
app.add_middleware(RequestContextMiddleware)

register_error_handlers(app)

for router in (
    auth.router,
    users.router,
    members.router,
    plans.router,
    memberships.router,
    payments.router,
    events.router,
    events.ticket_type_router,
    tickets.router,
    checkin.router,
    announcements.router,
    preferences.router,
    products.router,
    products.variant_router,
    orders.router,
    merch_admin.router,
    fundraisers.router,
    fundraisers.income_router,
    tasks.router,
    expenses.router,
    finance.router,
    finance.periods_router,
    admin_portal.router,
    student_portal.router,
    staff_portal.router,
):
    app.include_router(router, prefix=API_PREFIX)


@app.get("/health", tags=["meta"], summary="Liveness probe")
def health():
    return {"status": "ok", "service": "ssa-hub-api", "version": app.version}
