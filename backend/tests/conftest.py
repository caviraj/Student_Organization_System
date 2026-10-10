"""Test harness: a real Postgres database of its own (TEST_DATABASE_URL), one session per test.

The suite runs against Postgres, not SQLite, because that is what the app ships on - the pooler,
the JSONB columns, the enum CHECK constraints and the row locks all behave differently from
SQLite. The database is built by running the actual Alembic migrations (never `create_all`), so a
migration that drifts from the models fails here.

Safety: conftest refuses to start unless TEST_DATABASE_URL is set and points somewhere other than
DATABASE_URL. Every table is truncated between tests - against the real database that would be
data loss, so the guard is the difference between a test run and an incident.
"""

import os
from pathlib import Path

# Must be set before app.core.config is imported.
os.environ["JWT_SECRET"] = "test-secret-long-enough-for-hs256-32-bytes"
os.environ["BCRYPT_ROUNDS"] = "4"

from datetime import UTC, date, datetime, timedelta  # noqa: E402

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, select, text  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.db import duplicate_database_reason, engine_kwargs  # noqa: E402
from app.core.deps import get_db  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Event, Membership, MembershipPlan, TicketType, User  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[1]

_reason = duplicate_database_reason(settings.TEST_DATABASE_URL, settings.DATABASE_URL)
if _reason:
    raise RuntimeError(_reason)

TEST_URL = settings.TEST_DATABASE_URL

PASSWORD = "Passw0rd!"
_PASSWORD_HASH = hash_password(PASSWORD)  # hashed once: bcrypt is deliberately slow

engine = create_engine(TEST_URL, **engine_kwargs(TEST_URL))
# expire_on_commit: one session serves the whole test, while production gets a fresh one per
# request. Without this the session keeps handing back rows that a service-level UPDATE has
# already changed behind its back (sold_count, capacity, ticket status).
TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=True)


def _migrate() -> None:
    """Build the test schema with the real migrations. ALEMBIC_DATABASE_URL is what stops a test
    run from ever touching the database Alembic would otherwise choose."""
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    os.environ["ALEMBIC_DATABASE_URL"] = TEST_URL
    command.upgrade(config, "head")


def _truncate_all(target_engine) -> None:
    """Discovered, not hard-coded, so a new Phase's tables are cleaned without editing this."""
    with target_engine.begin() as conn:
        names = (
            conn.execute(
                text("select tablename from pg_tables where schemaname = 'public' and tablename <> 'alembic_version'")
            )
            .scalars()
            .all()
        )
        if names:
            conn.execute(text("TRUNCATE TABLE " + ", ".join(f'"{name}"' for name in names) + " RESTART IDENTITY CASCADE"))


@pytest.fixture(scope="session")
def pg_engine():
    _migrate()
    _truncate_all(engine)  # an earlier run that died mid-test must not leak rows into this one
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def _clean(pg_engine):
    """Truncate after every test: the next one starts from an empty database."""
    yield
    _truncate_all(pg_engine)


@pytest.fixture
def db(pg_engine) -> Session:
    session = TestingSession()
    yield session
    session.close()


@pytest.fixture
def db2(pg_engine) -> Session:
    """A second session on the same database, so a test can hold a stale read."""
    session = TestingSession()
    yield session
    session.close()


@pytest.fixture
def client(db: Session, monkeypatch) -> TestClient:
    app.dependency_overrides[get_db] = lambda: db
    # POST /announcements kicks the delivery worker through BackgroundTasks. Unpatched it would
    # open its own session on the app's engine - the real database. Point it at the test session.
    from app.jobs import scheduler
    from app.services.delivery_worker import process_queued_deliveries

    monkeypatch.setattr(scheduler, "run_deliveries_once", lambda: process_queued_deliveries(db))
    # Not used as a context manager: that would start the APScheduler job.
    yield TestClient(app)
    app.dependency_overrides.clear()


# --- helpers ----------------------------------------------------------------------
@pytest.fixture
def make_user(db):
    def _make(email: str, role: str = "member", full_name: str | None = None, **extra) -> User:
        user = User(
            email=email,
            password_hash=_PASSWORD_HASH,
            full_name=full_name or email.split("@")[0].title(),
            role=role,
            **extra,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    return _make


@pytest.fixture
def make_plan(db):
    def _make(name: str = "Standard", price: int = 90000, duration_months: int = 12) -> MembershipPlan:
        plan = MembershipPlan(name=name, price=price, duration_months=duration_months, is_active=True)
        db.add(plan)
        db.commit()
        db.refresh(plan)
        return plan

    return _make


@pytest.fixture
def make_membership(db):
    """Gives a user a membership; `active` and in the future is what unlocks member pricing."""

    def _make(user: User, *, status: str = "active", days_left: int = 90) -> Membership:
        plan = db.scalar(select(MembershipPlan).limit(1))
        if plan is None:
            plan = MembershipPlan(name="Test Plan", price=90000, duration_months=12)
            db.add(plan)
            db.commit()
        membership = Membership(
            user_id=user.id,
            plan_id=plan.id,
            status=status,
            start_date=date.today() - timedelta(days=1),
            end_date=date.today() + timedelta(days=days_left),
        )
        db.add(membership)
        db.commit()
        db.refresh(membership)
        return membership

    return _make


@pytest.fixture
def make_event(db):
    def _make(
        *,
        title: str = "Spring Gala",
        status: str = "published",
        starts_in_days: int = 14,
        venue: str = "Main Auditorium",
    ) -> Event:
        starts_at = datetime.now(UTC) + timedelta(days=starts_in_days)
        event = Event(
            title=title,
            venue=venue,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(hours=4),
            status=status,
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        return event

    return _make


@pytest.fixture
def make_ticket_type(db):
    def _make(
        event: Event,
        *,
        name: str = "General",
        member_price: int = 30000,
        non_member_price: int = 50000,
        capacity: int = 10,
        sale_starts_at: datetime | None = None,
        sale_ends_at: datetime | None = None,
    ) -> TicketType:
        ticket_type = TicketType(
            event_id=event.id,
            name=name,
            member_price=member_price,
            non_member_price=non_member_price,
            capacity=capacity,
            sale_starts_at=sale_starts_at,
            sale_ends_at=sale_ends_at,
        )
        db.add(ticket_type)
        db.commit()
        db.refresh(ticket_type)
        return ticket_type

    return _make


@pytest.fixture
def login(client):
    def _login(email: str, password: str = PASSWORD) -> str:
        response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert response.status_code == 200, response.text
        return response.json()["access_token"]

    return _login


@pytest.fixture
def auth():
    def _auth(token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    return _auth


def buy_membership(client, auth, token: str, plan_id: str, outcome: str = "success") -> dict:
    """checkout -> mock-confirm; returns the confirm response body."""
    checkout = client.post("/api/v1/memberships/checkout", json={"plan_id": plan_id}, headers=auth(token))
    assert checkout.status_code == 201, checkout.text
    order_id = checkout.json()["order_id"]
    confirm = client.post(
        f"/api/v1/payments/{order_id}/mock-confirm", json={"outcome": outcome}, headers=auth(token)
    )
    assert confirm.status_code == 200, confirm.text
    return confirm.json()


def buy_tickets(
    client,
    auth,
    token: str,
    ticket_type_id,
    quantity: int = 1,
    outcome: str = "success",
    idempotency_key: str | None = None,
) -> dict:
    """checkout -> mock-confirm; returns whichever body carries the tickets. A free order is
    already paid at checkout, so there is nothing to confirm."""
    headers = auth(token)
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    checkout = client.post(
        "/api/v1/tickets/checkout",
        json={"ticket_type_id": str(ticket_type_id), "quantity": quantity},
        headers=headers,
    )
    assert checkout.status_code == 201, checkout.text
    if checkout.json()["status"] == "paid":
        return checkout.json()
    order_id = checkout.json()["order_id"]
    confirm = client.post(f"/api/v1/payments/{order_id}/mock-confirm", json={"outcome": outcome}, headers=auth(token))
    assert confirm.status_code == 200, confirm.text
    return confirm.json()
