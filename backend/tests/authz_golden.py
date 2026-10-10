"""The authorisation golden matrix: one seed world, every route, every legacy role.

`scripts/generate_authz_golden.py` records what the API answers today; `tests/test_authz_golden.py`
replays it after the permission-based RBAC refactor. This module is the part both need, so the two
runs cannot drift apart - a copy in each would be a copy that quietly stops testing the same thing.

Two decisions worth knowing.

**The recorded signal is allow/deny, not the status code.** A denied call is 401 (no token) or 403
(wrong role); everything else - 200, 201, 202, 204, 400, 404, 409, 422 - means the request got
*past* authorisation and was then rejected for its own reasons (an empty body, a resource that does
not exist). That is the distinction the refactor must preserve. The raw status is stored beside it
for a human reading a diff, and a change in it is reported but does not fail the replay.

**Bodies are `{}`.** A valid payload would mutate the world mid-pass and make the next cell depend
on the previous one. An invalid one is rejected after the security dependencies have already run,
which is exactly what we are measuring. The one exception is a DELETE that succeeds - it is
re-seeded before the next role, so every role starts from the identical world.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.core.deps import get_db
from app.core.routes import iter_api_routes
from app.core.security import hash_password
from app.models import (
    Announcement,
    Event,
    Expense,
    FinancePeriod,
    Fundraiser,
    Membership,
    MembershipPlan,
    Order,
    OrderItem,
    Product,
    ProductVariant,
    Task,
    Ticket,
    TicketType,
    Transaction,
    User,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
GOLDEN_PATH = FIXTURES / "authz_golden.json"
INTENDED_PATH = FIXTURES / "authz_intended_changes.json"

PASSWORD = "Passw0rd!"

# Seven identities, not six. `guest` here is a *registered user whose stored role is "guest"* -
# someone who signed up and has not paid dues yet. That is a different thing from `anonymous`, and
# conflating the two is how a refactor that makes guest implicit hands every unpaid registrant
# member-level access without anyone noticing. See app/services/accounts.py - registration assigns
# role="guest", and app/services/memberships.py promotes it to "member" when dues are paid.
LEGACY_ROLES = ("anonymous", "guest", "member", "volunteer", "organizer", "treasurer", "admin")

DENY_STATUSES = (401, 403)


def decision(status: int) -> str:
    """`deny` only when authorisation is what said no.

    A 500 means the request reached the handler and the handler broke, so it is neither allow nor
    deny and the replay must not read it as either. 502/503/504 are excluded from that: this app
    uses 503 deliberately to say "this environment has not configured the thing"
    (PAYMENTS_NOT_CONFIGURED), which is a real answer, not a crash.
    """
    if status in DENY_STATUSES:
        return "deny"
    return "error" if status in (500, 501) else "allow"


# --- the world ---------------------------------------------------------------------
def build_world(db: Session) -> dict[str, UUID]:
    """A small but complete world: one user per legacy role, and one row of every resource the
    routes take an id for, so an allowed call reaches the handler instead of stopping at a 404.

    Written straight to the tables. This is a fixture builder, not a test of the services.
    """
    password = hash_password(PASSWORD)
    ids: dict[str, UUID] = {}

    def user(email: str, role: str) -> User:
        row = User(email=email, password_hash=password, full_name=email.split("@")[0].title(), role=role)
        db.add(row)
        db.flush()
        return row

    for role in ("admin", "treasurer", "organizer", "volunteer", "member", "guest"):
        ids[role] = user(f"{role}@ssa.org", role).id
    target = user("target@ssa.org", "member")
    ids["target_user"] = target.id

    plan = MembershipPlan(name="Standard", price=90000, duration_months=12, is_active=True)
    db.add(plan)
    db.flush()
    ids["plan_id"] = plan.id

    # An active membership is what unlocks member pricing and the members-only announcement feed.
    today = date.today()
    for role in ("member", "volunteer", "organizer", "treasurer", "admin"):
        db.add(
            Membership(
                user_id=ids[role],
                plan_id=plan.id,
                status="active",
                start_date=today - timedelta(days=1),
                end_date=today + timedelta(days=90),
            )
        )

    starts = datetime.now(UTC) + timedelta(days=14)
    event = Event(
        title="Spring Gala",
        venue="Main Auditorium",
        starts_at=starts,
        ends_at=starts + timedelta(hours=4),
        status="published",
        created_by=ids["organizer"],
    )
    draft = Event(
        title="Unpublished Draft",
        venue="Back Room",
        starts_at=starts,
        ends_at=starts + timedelta(hours=2),
        status="draft",
        created_by=ids["organizer"],
    )
    db.add_all([event, draft])
    db.flush()
    ids["event_id"] = event.id
    ids["draft_event_id"] = draft.id

    ticket_type = TicketType(
        event_id=event.id, name="General", member_price=30000, non_member_price=50000, capacity=100
    )
    db.add(ticket_type)
    db.flush()
    ids["ticket_type_id"] = ticket_type.id

    order = Order(user_id=ids["member"], kind="ticket", status="paid", subtotal=30000, discount=0, total=30000)
    db.add(order)
    db.flush()
    ids["order_id"] = order.id
    db.add(
        OrderItem(
            order_id=order.id,
            item_type="ticket_type",
            item_id=ticket_type.id,
            quantity=1,
            unit_price=30000,
            line_total=30000,
        )
    )
    ticket = Ticket(
        order_id=order.id,
        event_id=event.id,
        ticket_type_id=ticket_type.id,
        user_id=ids["member"],
        code="AAAA111111",
        status="valid",
        price_paid=30000,
        is_member_price=True,
    )
    db.add(ticket)
    db.flush()
    ids["ticket_id"] = ticket.id

    announcement = Announcement(
        title="Welcome back",
        body="Term starts Monday.",
        category="general",
        audience="all",
        author_id=ids["organizer"],
    )
    db.add(announcement)
    db.flush()
    ids["announcement_id"] = announcement.id

    product = Product(name="SSA Hoodie", base_price=150000, member_discount_pct=10, is_active=True)
    db.add(product)
    db.flush()
    ids["product_id"] = product.id
    variant = ProductVariant(product_id=product.id, size="M", sku="HOOD-M", stock=10)
    db.add(variant)
    db.flush()
    ids["variant_id"] = variant.id

    fundraiser = Fundraiser(
        title="Spring Bake Sale",
        goal_amount=500000,
        event_date=today + timedelta(days=10),
        status="planning",
        owner_id=ids["organizer"],
    )
    db.add(fundraiser)
    db.flush()
    ids["fundraiser_id"] = fundraiser.id

    task = Task(
        fundraiser_id=fundraiser.id,
        title="Bake 200 cookies",
        category="baking",
        status="todo",
        assignee_id=ids["volunteer"],
        created_by=ids["organizer"],
    )
    db.add(task)
    db.flush()
    ids["task_id"] = task.id

    expense = Expense(
        claimant_id=ids["volunteer"],
        amount=45000,
        description="Auto fare to the printer",
        category="printing",
        incurred_on=today,
        status="submitted",
    )
    db.add(expense)
    db.flush()
    ids["expense_id"] = expense.id

    period = FinancePeriod(name="Semester 1", start_date=today - timedelta(days=180), end_date=today, closing_balance=0)
    db.add(period)
    db.flush()
    ids["period_id"] = period.id

    entry = Transaction(direction="in", amount=100000, source="other_income", note="Opening float")
    db.add(entry)
    db.flush()
    ids["transaction_id"] = entry.id

    db.commit()
    return ids


# Path parameters, by name, to the row the route should be pointed at.
PARAM_SOURCES = {
    "plan_id": "plan_id",
    "order_id": "order_id",
    "event_id": "event_id",
    "ticket_type_id": "ticket_type_id",
    "ticket_id": "ticket_id",
    "announcement_id": "announcement_id",
    "product_id": "product_id",
    "variant_id": "variant_id",
    "fundraiser_id": "fundraiser_id",
    "task_id": "task_id",
    "expense_id": "expense_id",
    "period_id": "period_id",
    "transaction_id": "transaction_id",
    "user_id": "target_user",
}

BODY_METHODS = ("POST", "PUT", "PATCH")

# Seeded reference data, not test data. `permissions` / `roles` / `role_permissions` / `sod_rules`
# are filled by `sync_catalog` in the migration, and every table is truncated between tests - so
# without this exclusion the catalog exists for whichever test happened to run first and is empty
# for all the rest. Nothing here writes them, and `tests/test_rbac.py` is what checks they match
# app/core/permissions.py.
REFERENCE_TABLES = ("permissions", "roles", "role_permissions", "sod_rules")


def truncate_all(engine) -> None:
    """Tables discovered from the catalogue, not hard-coded, so a later Phase's tables are cleaned
    without editing this."""
    with engine.begin() as conn:
        names = [
            row[0]
            for row in conn.execute(
                text(
                    "select tablename from pg_tables where schemaname = 'public' "
                    "and tablename <> 'alembic_version' and tablename <> all(:keep)"
                ),
                {"keep": list(REFERENCE_TABLES)},
            )
        ]
    if names:
        with engine.begin() as conn:
            conn.execute(text("TRUNCATE " + ", ".join(f'"{n}"' for n in names) + " RESTART IDENTITY CASCADE"))


def make_harness(app, engine) -> tuple[TestClient, callable]:
    """A client whose every request gets a fresh session, plus a `reset()` that rebuilds the world.

    Fresh-session-per-request is not a detail: `reset()` truncates, and a session shared across the
    whole run would still be serving the previous world out of its identity map.
    """
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=True)

    def reset() -> dict[str, UUID]:
        truncate_all(engine)
        session = Session()
        try:
            return build_world(session)
        finally:
            session.close()

    def _get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _get_db
    return TestClient(app), reset


def resolve(path: str, world: dict[str, UUID]) -> str:
    """Fill `{param}` from the world. A parameter with no row behind it keeps a fixed UUID, so the
    route still answers and the answer is still the same on every run."""
    for name in list(PARAM_SOURCES):
        if "{" + name + "}" in path:
            path = path.replace("{" + name + "}", str(world[PARAM_SOURCES[name]]))
    # Anything left over (a `{token}` or a future parameter) becomes a stable dummy.
    while "{" in path:
        head, _, tail = path.partition("{")
        _, _, rest = tail.partition("}")
        path = head + "00000000-0000-0000-0000-000000000000" + rest
    return path


def route_keys(app) -> list[tuple[str, str]]:
    """`(method, path_template)` for every route, sorted - the matrix's row order."""
    keys = []
    for path, route in iter_api_routes(app):
        for method in route.methods or set():
            if method in ("HEAD", "OPTIONS"):
                continue
            keys.append((method, path))
    return sorted(keys)


def login(client, role: str) -> str:
    """A bearer token for the seeded user of that role."""
    response = client.post("/api/v1/auth/login", json={"email": f"{role}@ssa.org", "password": PASSWORD})
    assert response.status_code == 200, f"could not log in as {role}: {response.text}"
    return response.json()["access_token"]


# Some routes are public until a query flag turns them into a privileged one, and the flag is where
# the real role rule lives (`?include_drafts=true` is organizer+, `?include_inactive=true` is
# admin). Probing only the default call would record "public" for both and quietly stop testing the
# check that Steps 1-2 have to preserve. Keyed by "METHOD /path", like the matrix rows.
PROBE_VARIANTS: dict[str, tuple[str, ...]] = {
    "GET /api/v1/events": ("?include_drafts=true",),
    "GET /api/v1/products": ("?include_inactive=true",),
}


def collect(client, app, reset) -> dict[str, dict[str, str]]:
    """Call every route as every legacy role, re-seeding first.

    `reset()` truncates and rebuilds the world, returning its ids. Each role therefore starts from
    the identical database: a route that a previous role managed to mutate (a DELETE that succeeds)
    cannot make the next role's answer depend on it.
    """
    matrix: dict[str, dict[str, str]] = {}
    for role in LEGACY_ROLES:
        world = reset()
        headers = {} if role == "anonymous" else {"Authorization": f"Bearer {login(client, role)}"}
        for method, template in route_keys(app):
            key = f"{method} {template}"
            kwargs: dict = {"headers": headers}
            if method in BODY_METHODS:
                kwargs["json"] = {}
            calls = [(key, "")] + [(f"{key}{q}", q) for q in PROBE_VARIANTS.get(key, ())]
            for row_key, query in calls:
                response = client.request(method, resolve(template, world) + query, **kwargs)
                row = matrix.setdefault(row_key, {})
                row[role] = decision(response.status_code)
                row[f"_{role}_status"] = str(response.status_code)
    return matrix


def load_golden() -> dict:
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def load_intended() -> dict[str, dict[str, str]]:
    """`{"METHOD /path": {"role": "reason"}}` - the cells the refactor is allowed to change."""
    if not INTENDED_PATH.exists():
        return {}
    return json.loads(INTENDED_PATH.read_text(encoding="utf-8")).get("changes", {})


def diff(golden: dict, current: dict, intended: dict[str, dict[str, str]]) -> list[str]:
    """Every cell that moved without being declared. Empty means the refactor was faithful."""
    problems = []
    for key in sorted(set(golden["routes"]) | set(current)):
        if key not in golden["routes"]:
            problems.append(f"{key}: new route, not in the golden matrix")
            continue
        if key not in current:
            problems.append(f"{key}: route disappeared")
            continue
        declared = intended.get(key, {})
        for role in LEGACY_ROLES:
            before = golden["routes"][key].get(role)
            after = current[key].get(role)
            if before == after:
                continue
            if role in declared:
                continue
            problems.append(f"{key} [{role}]: {before} -> {after} (undeclared)")
    return problems


__all__ = [
    "DENY_STATUSES",
    "GOLDEN_PATH",
    "INTENDED_PATH",
    "LEGACY_ROLES",
    "PASSWORD",
    "REFERENCE_TABLES",
    "build_world",
    "collect",
    "decision",
    "diff",
    "load_golden",
    "load_intended",
    "login",
    "make_harness",
    "resolve",
    "route_keys",
    "truncate_all",
]
