"""Ticket checkout, fulfilment, seat release and the money trail (DESIGN.md §4 rules 2-3)."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select

from app.models import Order, TicketType, Transaction
from app.services.tickets import release_expired_pending_orders
from tests.conftest import buy_tickets

NON_MEMBER_PRICE = 50000


def _checkout(client, auth, token, ticket_type_id, quantity=1):
    return client.post(
        "/api/v1/tickets/checkout",
        json={"ticket_type_id": str(ticket_type_id), "quantity": quantity},
        headers=auth(token),
    )


def _sold_count(db, ticket_type_id) -> int:
    db.expire_all()
    return db.get(TicketType, ticket_type_id).sold_count


# --- 2. oversell ------------------------------------------------------------------
def test_oversell_stops_at_capacity(client, auth, login, db, make_user, make_event, make_ticket_type):
    make_user("buyer@ssa.org")
    ticket_type = make_ticket_type(make_event(), capacity=5)
    token = login("buyer@ssa.org")

    statuses, bodies = [], []
    for _ in range(8):
        response = _checkout(client, auth, token, ticket_type.id)
        statuses.append(response.status_code)
        bodies.append(response.json())

    assert statuses.count(201) == 5
    assert statuses.count(409) == 3
    for body in bodies[5:]:
        assert body["error"]["code"] == "SOLD_OUT"
        assert body["error"]["details"]["seats_left"] == 0
    assert _sold_count(db, ticket_type.id) == 5


def test_bulk_order_larger_than_capacity_is_rejected(client, auth, login, db, make_user, make_event, make_ticket_type):
    make_user("bulk@ssa.org")
    ticket_type = make_ticket_type(make_event(), capacity=5)

    response = _checkout(client, auth, login("bulk@ssa.org"), ticket_type.id, quantity=10)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SOLD_OUT"
    assert _sold_count(db, ticket_type.id) == 0


# --- 3. checkout validations ------------------------------------------------------
def test_draft_event_cannot_be_bought(client, auth, login, make_user, make_event, make_ticket_type):
    make_user("buyer@ssa.org")
    ticket_type = make_ticket_type(make_event(status="draft"))

    response = _checkout(client, auth, login("buyer@ssa.org"), ticket_type.id)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EVENT_NOT_ON_SALE"


def test_closed_event_cannot_be_bought(client, auth, login, make_user, make_event, make_ticket_type):
    make_user("buyer@ssa.org")
    ticket_type = make_ticket_type(make_event(status="closed"))

    response = _checkout(client, auth, login("buyer@ssa.org"), ticket_type.id)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EVENT_NOT_ON_SALE"


def test_sale_window_is_enforced(client, auth, login, db, make_user, make_event, make_ticket_type):
    make_user("buyer@ssa.org")
    token = login("buyer@ssa.org")
    event = make_event()
    now = datetime.now(UTC)

    too_early = make_ticket_type(event, name="Early", sale_starts_at=now + timedelta(days=1))
    too_late = make_ticket_type(event, name="Late", sale_ends_at=now - timedelta(days=1))

    for ticket_type in (too_early, too_late):
        response = _checkout(client, auth, token, ticket_type.id)
        assert response.status_code == 409, response.text
        assert response.json()["error"]["code"] == "NOT_IN_SALE_WINDOW"
    assert _sold_count(db, too_early.id) == 0


def test_quantity_bounds_and_authentication(client, auth, login, make_user, make_event, make_ticket_type):
    make_user("buyer@ssa.org")
    ticket_type = make_ticket_type(make_event())
    token = login("buyer@ssa.org")

    for quantity in (0, 11):
        response = _checkout(client, auth, token, ticket_type.id, quantity=quantity)
        assert response.status_code == 422, response.text
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    anonymous = client.post("/api/v1/tickets/checkout", json={"ticket_type_id": str(ticket_type.id), "quantity": 1})
    assert anonymous.status_code == 401
    assert anonymous.json()["error"]["code"] == "UNAUTHORIZED"


# --- 4. payment success -----------------------------------------------------------
def test_payment_success_issues_tickets_and_one_ledger_row(
    client, auth, login, db, make_user, make_event, make_ticket_type
):
    make_user("buyer@ssa.org")
    ticket_type = make_ticket_type(make_event())
    token = login("buyer@ssa.org")

    body = buy_tickets(client, auth, token, ticket_type.id, quantity=3)
    order_id = UUID(body["order_id"])

    assert body["order_status"] == "paid"
    assert body["payment_status"] == "succeeded"
    assert len(body["tickets"]) == 3
    assert len({ticket["code"] for ticket in body["tickets"]}) == 3
    assert all(len(ticket["code"]) == 10 for ticket in body["tickets"])
    assert all(ticket["price_paid"] == NON_MEMBER_PRICE for ticket in body["tickets"])

    db.expire_all()
    rows = db.scalars(select(Transaction).where(Transaction.ref_id == order_id)).all()
    assert len(rows) == 1
    assert rows[0].source == "tickets"
    assert rows[0].direction == "in"
    assert rows[0].amount == NON_MEMBER_PRICE * 3
    assert rows[0].event_id == ticket_type.event_id

    replay = client.post(f"/api/v1/payments/{order_id}/mock-confirm", json={"outcome": "success"}, headers=auth(token))
    assert replay.status_code == 200
    assert len(replay.json()["tickets"]) == 3
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Transaction).where(Transaction.ref_id == order_id)) == 1
    assert _sold_count(db, ticket_type.id) == 3


def test_repeated_checkout_with_same_idempotency_key_reuses_the_order(
    client, auth, login, db, make_user, make_event, make_ticket_type
):
    make_user("buyer@ssa.org")
    ticket_type = make_ticket_type(make_event(), capacity=5)
    token = login("buyer@ssa.org")

    first = buy_tickets(client, auth, token, ticket_type.id, quantity=2, idempotency_key="retry-me")
    second = _checkout_with_key(client, auth, token, ticket_type.id, 2, "retry-me")

    assert second.status_code == 201, second.text
    assert second.json()["order_id"] == first["order_id"]
    assert _sold_count(db, ticket_type.id) == 2


def _checkout_with_key(client, auth, token, ticket_type_id, quantity, key):
    headers = auth(token) | {"Idempotency-Key": key}
    return client.post(
        "/api/v1/tickets/checkout",
        json={"ticket_type_id": str(ticket_type_id), "quantity": quantity},
        headers=headers,
    )


# --- 5. failure and abandonment ---------------------------------------------------
def test_failed_payment_releases_seats(client, auth, login, db, make_user, make_event, make_ticket_type):
    make_user("buyer@ssa.org")
    ticket_type = make_ticket_type(make_event(), capacity=5)
    token = login("buyer@ssa.org")

    body = buy_tickets(client, auth, token, ticket_type.id, quantity=2, outcome="fail")

    assert body["order_status"] == "failed"
    assert body["tickets"] == []
    assert _sold_count(db, ticket_type.id) == 0


def test_sweep_cancels_abandoned_orders_and_releases_seats(
    client, auth, login, db, make_user, make_event, make_ticket_type
):
    make_user("buyer@ssa.org")
    ticket_type = make_ticket_type(make_event(), capacity=5)
    token = login("buyer@ssa.org")

    checkout = _checkout(client, auth, token, ticket_type.id, quantity=2)  # never confirmed
    assert checkout.status_code == 201
    assert _sold_count(db, ticket_type.id) == 2

    db.get(Order, UUID(checkout.json()["order_id"])).created_at = datetime.now(UTC) - timedelta(minutes=16)
    db.commit()

    assert release_expired_pending_orders(db) == {"cancelled": 1}
    db.expire_all()
    assert db.get(Order, UUID(checkout.json()["order_id"])).status == "cancelled"
    assert _sold_count(db, ticket_type.id) == 0


def test_sweep_leaves_fresh_orders_alone(client, auth, login, db, make_user, make_event, make_ticket_type):
    make_user("buyer@ssa.org")
    ticket_type = make_ticket_type(make_event(), capacity=5)

    _checkout(client, auth, login("buyer@ssa.org"), ticket_type.id)

    assert release_expired_pending_orders(db) == {"cancelled": 0}
    assert _sold_count(db, ticket_type.id) == 1


# --- 6. free tickets --------------------------------------------------------------
def test_free_ticket_is_fulfilled_at_checkout_without_a_ledger_row(
    client, auth, login, db, make_user, make_event, make_ticket_type
):
    make_user("buyer@ssa.org")
    event = make_event()
    ticket_type = make_ticket_type(event, name="Free", member_price=0, non_member_price=0)

    body = buy_tickets(client, auth, login("buyer@ssa.org"), ticket_type.id, quantity=2)

    assert body["status"] == "paid"
    assert body["payment_id"] is None
    assert body["amount"] == 0
    assert len(body["tickets"]) == 2
    assert _sold_count(db, ticket_type.id) == 2
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Transaction).where(Transaction.event_id == event.id)) == 0


# --- 10. capacity edits -----------------------------------------------------------
def test_capacity_cannot_drop_below_sold_count(client, auth, login, db, make_user, make_event, make_ticket_type):
    make_user("buyer@ssa.org")
    make_user("organizer@ssa.org", role="organizer")
    ticket_type = make_ticket_type(make_event(), capacity=5)
    buy_tickets(client, auth, login("buyer@ssa.org"), ticket_type.id, quantity=2)
    organizer = auth(login("organizer@ssa.org"))

    refused = client.patch(f"/api/v1/ticket-types/{ticket_type.id}", json={"capacity": 1}, headers=organizer)
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "CAPACITY_BELOW_SOLD"
    assert refused.json()["error"]["details"]["sold_count"] == 2

    allowed = client.patch(f"/api/v1/ticket-types/{ticket_type.id}", json={"capacity": 2}, headers=organizer)
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["seats_left"] == 0


# --- my tickets -------------------------------------------------------------------
def test_my_tickets_lists_upcoming_first(client, auth, login, make_user, make_event, make_ticket_type):
    make_user("buyer@ssa.org")
    past = make_ticket_type(make_event(title="Last Year", starts_in_days=-5), name="Past")
    upcoming = make_ticket_type(make_event(title="Next Month", starts_in_days=30), name="Next")
    token = login("buyer@ssa.org")

    buy_tickets(client, auth, token, past.id)
    buy_tickets(client, auth, token, upcoming.id)

    response = client.get("/api/v1/tickets/me", headers=auth(token))

    assert response.status_code == 200
    assert response.json()["total"] == 2
    assert [item["event_title"] for item in response.json()["items"]] == ["Next Month", "Last Year"]
