"""Test harness: in-memory SQLite, one session per test, fast bcrypt."""

import os

# Must be set before app.core.config is imported.
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["JWT_SECRET"] = "test-secret-long-enough-for-hs256-32-bytes"
os.environ["BCRYPT_ROUNDS"] = "4"

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.deps import get_db
from app.core.security import hash_password
from app.main import app
from app.models import Base, Event, Membership, MembershipPlan, TicketType, User

PASSWORD = "Passw0rd!"
_PASSWORD_HASH = hash_password(PASSWORD)  # hashed once: bcrypt is deliberately slow

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
# expire_on_commit: one session serves the whole test, while production gets a fresh one per
# request. Without this the session keeps handing back rows that a service-level UPDATE has
# already changed behind its back (sold_count, capacity, ticket status).
TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=True)


@pytest.fixture(autouse=True)
def _schema():
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def db() -> Session:
    session = TestingSession()
    yield session
    session.close()


@pytest.fixture
def db2() -> Session:
    """A second session on the same in-memory DB, so a test can hold a stale read."""
    session = TestingSession()
    yield session
    session.close()


@pytest.fixture
def client(db: Session) -> TestClient:
    app.dependency_overrides[get_db] = lambda: db
    # Not used as a context manager: that would start the APScheduler job.
    yield TestClient(app)
    app.dependency_overrides.clear()


# --- helpers ----------------------------------------------------------------------
@pytest.fixture
def make_user(db):
    def _make(email: str, role: str = "member", full_name: str | None = None) -> User:
        user = User(
            email=email,
            password_hash=_PASSWORD_HASH,
            full_name=full_name or email.split("@")[0].title(),
            role=role,
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
