"""Test harness: in-memory SQLite, one session per test, fast bcrypt."""

import os

# Must be set before app.core.config is imported.
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["JWT_SECRET"] = "test-secret-long-enough-for-hs256-32-bytes"
os.environ["BCRYPT_ROUNDS"] = "4"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.deps import get_db
from app.core.security import hash_password
from app.main import app
from app.models import Base, MembershipPlan, User

PASSWORD = "Passw0rd!"
_PASSWORD_HASH = hash_password(PASSWORD)  # hashed once: bcrypt is deliberately slow

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


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
