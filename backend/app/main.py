"""SSA Hub API — Phase 1 (Auth & Membership)."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.errors import register_error_handlers
from app.jobs.scheduler import start_scheduler, stop_scheduler
from app.routers import auth, members, memberships, payments, plans, users

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(_: FastAPI):
    start_scheduler()  # expiry scan at startup, then every 24h
    yield
    stop_scheduler()


app = FastAPI(
    title="SSA Hub API",
    version="1.0.0",
    description=(
        "Skyline Student Association platform — Phase 1: Auth & Membership.\n\n"
        "All endpoints are under `/api/v1`. Errors are `{\"error\": {\"code\", \"message\", \"details\"}}`; "
        "lists are `{\"items\", \"total\", \"page\", \"page_size\"}`. Money is integer paise."
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

register_error_handlers(app)

for router in (auth.router, users.router, members.router, plans.router, memberships.router, payments.router):
    app.include_router(router, prefix=API_PREFIX)


@app.get("/health", tags=["meta"], summary="Liveness probe")
def health():
    return {"status": "ok", "service": "ssa-hub-api", "version": app.version}
