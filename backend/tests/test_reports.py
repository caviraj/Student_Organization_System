"""Event report and attendee list — numbers checked against a hand-computed fixture."""

from sqlalchemy import func, select

from app.models import Transaction
from tests.conftest import buy_tickets

MEMBER_PRICE = 30000
NON_MEMBER_PRICE = 50000


def _fixture(client, auth, login, db, make_user, make_membership, make_event, make_ticket_type):
    """5 tickets sold (2 member + 3 non-member), 2 of them scanned in at the door."""
    member = make_user("member@ssa.org", full_name="Mem Ber")
    make_membership(member)
    make_user("guest@ssa.org", full_name="Gue St")
    make_user("vol@ssa.org", role="volunteer")
    make_user("organizer@ssa.org", role="organizer")
    event = make_event()
    ticket_type = make_ticket_type(event, capacity=10)

    member_tickets = buy_tickets(client, auth, login("member@ssa.org"), ticket_type.id, quantity=2)["tickets"]
    guest_tickets = buy_tickets(client, auth, login("guest@ssa.org"), ticket_type.id, quantity=3)["tickets"]

    volunteer = auth(login("vol@ssa.org"))
    for ticket in (member_tickets[0], guest_tickets[0]):
        scanned = client.post(
            "/api/v1/checkin", json={"event_id": str(event.id), "code": ticket["code"]}, headers=volunteer
        )
        assert scanned.json()["result"] == "VALID", scanned.text

    return event, ticket_type, auth(login("organizer@ssa.org"))


def test_report_matches_the_hand_computed_fixture(
    client, auth, login, db, make_user, make_membership, make_event, make_ticket_type
):
    event, _ticket_type, organizer = _fixture(
        client, auth, login, db, make_user, make_membership, make_event, make_ticket_type
    )

    response = client.get(f"/api/v1/events/{event.id}/report", headers=organizer)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tickets_sold"] == 5
    assert body["seats_total"] == 10
    assert body["seats_left"] == 5
    assert body["checked_in"] == 2
    assert body["no_shows"] == 3
    assert body["attendance_rate"] == 40.0
    assert body["revenue"] == {"member": MEMBER_PRICE * 2, "non_member": NON_MEMBER_PRICE * 3, "total": 210000}

    (by_type,) = body["by_ticket_type"]
    assert by_type["sold"] == 5
    assert by_type["checked_in"] == 2
    assert by_type["seats_left"] == 5
    assert by_type["revenue"] == 210000


def test_report_is_organizer_only(client, auth, login, make_user, make_event, make_ticket_type):
    make_user("member@ssa.org", role="member")
    make_user("organizer@ssa.org", role="organizer")
    event = make_event()

    refused = client.get(f"/api/v1/events/{event.id}/report", headers=auth(login("member@ssa.org")))
    assert refused.status_code == 403
    assert client.get(f"/api/v1/events/{event.id}/report").status_code == 401


def test_ledger_ticket_income_equals_report_revenue_for_paid_orders(
    client, auth, login, db, make_user, make_event, make_ticket_type
):
    """Free tickets sell seats but earn nothing, so they must not move either side."""
    make_user("buyer@ssa.org")
    make_user("organizer@ssa.org", role="organizer")
    event = make_event()
    paid = make_ticket_type(event, name="General", non_member_price=NON_MEMBER_PRICE, capacity=10)
    free = make_ticket_type(event, name="Free", non_member_price=0, capacity=10)
    token = login("buyer@ssa.org")

    buy_tickets(client, auth, token, paid.id, quantity=2)
    buy_tickets(client, auth, token, free.id, quantity=3)

    body = client.get(f"/api/v1/events/{event.id}/report", headers=auth(login("organizer@ssa.org"))).json()
    db.expire_all()
    ledger_total, ledger_rows = db.execute(
        select(func.coalesce(func.sum(Transaction.amount), 0), func.count(Transaction.id)).where(
            Transaction.event_id == event.id, Transaction.source == "tickets"
        )
    ).one()

    assert body["tickets_sold"] == 5
    assert body["revenue"]["total"] == NON_MEMBER_PRICE * 2
    assert ledger_total == body["revenue"]["total"]
    assert ledger_rows == 1


def test_attendees_filter_search_and_checkin_time(
    client, auth, login, db, make_user, make_membership, make_event, make_ticket_type
):
    event, _, organizer = _fixture(client, auth, login, db, make_user, make_membership, make_event, make_ticket_type)

    everyone = client.get(f"/api/v1/events/{event.id}/attendees", headers=organizer).json()
    assert everyone["total"] == 5
    assert all(item["holder_email"] for item in everyone["items"])

    scanned = client.get(f"/api/v1/events/{event.id}/attendees?status=used", headers=organizer).json()
    assert scanned["total"] == 2
    assert all(item["checked_in_at"] for item in scanned["items"])

    # Search matches the holder, so all three of that holder's tickets come back.
    found = client.get(f"/api/v1/events/{event.id}/attendees?q=Gue St", headers=organizer).json()
    assert found["total"] == 3
    assert {item["holder_name"] for item in found["items"]} == {"Gue St"}

    paged = client.get(f"/api/v1/events/{event.id}/attendees?page=2&page_size=2", headers=organizer).json()
    assert (paged["total"], len(paged["items"]), paged["page"]) == (5, 2, 2)
