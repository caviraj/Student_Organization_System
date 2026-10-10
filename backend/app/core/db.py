from datetime import UTC, datetime

from sqlalchemy import create_engine, make_url
from sqlalchemy.orm import sessionmaker

from app.core.config import settings


def connect_args(url: str) -> dict:
    """Driver-level options for one connection.

    The Postgres branch is written for Supabase's TRANSACTION pooler: it may hand a connection to
    a different backend after every statement, so server-side prepared statements would arrive at
    a session that never prepared them - hence `prepare_threshold=None`. For the same reason there
    must be no advisory locks or other session-level state anywhere in the app. Row locks inside a
    transaction (`SELECT ... FOR UPDATE SKIP LOCKED`) are fine: they live and die with the
    transaction, which is what transaction pooling preserves.
    """
    if url.startswith("sqlite"):
        return {"check_same_thread": False}
    if url.startswith("postgresql+psycopg"):
        args: dict = {"prepare_threshold": None}
        if "sslmode=" not in url:  # Supabase requires TLS; a local Postgres may not offer it
            args["sslmode"] = "require"
        return args
    return {}


def engine_kwargs(url: str) -> dict:
    """create_engine() arguments for the app's pools (Alembic uses `connect_args` only)."""
    if url.startswith("postgresql+psycopg"):
        return {
            "connect_args": connect_args(url),
            "pool_pre_ping": True,  # a pooler drops idle connections without warning
            "pool_size": 5,
            "max_overflow": 5,
        }
    return {"connect_args": connect_args(url)}


# The app: transaction pooler, small pool, no prepared statements.
engine = create_engine(settings.DATABASE_URL, **engine_kwargs(settings.DATABASE_URL))
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

# Migrations and seed scripts: DDL and long transactions need a real session, so they use
# DIRECT_URL. Same engine object when the deployment only has one URL.
_migration_url = settings.migration_url
migration_engine = (
    engine if _migration_url == settings.DATABASE_URL else create_engine(_migration_url, **engine_kwargs(_migration_url))
)
MigrationSessionLocal = sessionmaker(bind=migration_engine, autoflush=False, expire_on_commit=False)


def as_utc(value: datetime) -> datetime:
    """SQLite stores `DateTime(timezone=True)` as naive UTC and hands it back naive, while
    Postgres returns it aware. Normalise before comparing, so both behave the same."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def duplicate_database_reason(test_url: str | None, app_url: str | None) -> str | None:
    """Why a test run must not proceed, or None when it is safe.

    Compared on host + database name, not the whole URL: DATABASE_URL and TEST_DATABASE_URL can
    legitimately differ only by port (6543 transaction pooler vs 5432 session pooler) while
    pointing at the SAME database - which is exactly the accident that would let a test run
    truncate production tables.
    """
    if not test_url:
        return (
            "TEST_DATABASE_URL is not set.\n"
            "Tests create and truncate their own tables, so they need a database of their own.\n"
            "Create one (e.g. `create database ssa_hub_test`) and point TEST_DATABASE_URL at it."
        )
    test = make_url(test_url)
    app = make_url(app_url) if app_url else None
    if app is not None and (test.host, test.database) == (app.host, app.database):
        return (
            f"TEST_DATABASE_URL points at the same database as DATABASE_URL "
            f"({test.host}/{test.database}).\n"
            "Tests truncate every table between cases - refusing to run against the real one.\n"
            "Point TEST_DATABASE_URL at a separate database (e.g. .../ssa_hub_test)."
        )
    return None
