"""Door check-in: one shape, four outcomes, and never two VALIDs (DESIGN.md §4 rule 4)."""

from uuid import UUID

from sqlalchemy import select

from app.models import Ticket
from app.services.checkin import check_in
from tests.conftest import buy_tickets


def _scan(client, headers, event_id, code):
    return client.post("/api/v1/checkin", json={"event_id": str(event_id), "code": code}, headers=headers)


def _ticketed_user(make_user, make_event, make_ticket_type, email="holder@ssa.org"):
    user = make_user(email, role="member", full_name="Held A. Ticket")
    event = make_event()
    ticket_type = make_ticket_type(event, name="General")
    return user, event, ticket_type


def test_scan_returns_valid_then_already_used(client, auth, login, make_user, make_event, make_ticket_type):
    make_user("vol@ssa.org", role="volunteer")
    _, event, ticket_type = _ticketed_user(make_user, make_event, make_ticket_type)
    code = buy_tickets(client, auth, login("holder@ssa.org"), ticket_type.id)["tickets"][0]["code"]
    volunteer = auth(login("vol@ssa.org"))

    first = _scan(client, volunteer, event.id, code)
    assert first.status_code == 200
    body = first.json()
    assert body["result"] == "VALID"
    assert body["holder_name"] == "Held A. Ticket"
    assert body["ticket_type"] == "General"
    assert body["ticket"]["code"] == code
    assert body["checked_in_at"] is not None
    assert (body["checked_in"], body["sold"]) == (1, 1)

    second = _scan(client, volunteer, event.id, code)
    assert second.status_code == 200
    assert second.json()["result"] == "ALREADY_USED"
    assert second.json()["checked_in_at"] == body["checked_in_at"]
    assert second.json()["checked_in"] == 1


def test_scan_normalises_case_and_spacing(client, auth, login, make_user, make_event, make_ticket_type):
    make_user("vol@ssa.org", role="volunteer")
    _, event, ticket_type = _ticketed_user(make_user, make_event, make_ticket_type)
    code = buy_tickets(client, auth, login("holder@ssa.org"), ticket_type.id)["tickets"][0]["code"]

    noisy = f"  {code[:4].lower()} {code[4:].lower()} "

    assert _scan(client, auth(login("vol@ssa.org")), event.id, noisy).json()["result"] == "VALID"


def test_scan_of_unknown_code_is_invalid(client, auth, login, make_user, make_event):
    make_user("vol@ssa.org", role="volunteer")
    event = make_event()

    body = _scan(client, auth(login("vol@ssa.org")), event.id, "ZZZZZZZZZZ").json()

    assert body["result"] == "INVALID"
    assert body["ticket"] is None
    assert body["holder_name"] is None


def test_scan_of_a_voided_ticket_is_invalid(client, auth, login, db, make_user, make_event, make_ticket_type):
    make_user("vol@ssa.org", role="volunteer")
    _, event, ticket_type = _ticketed_user(make_user, make_event, make_ticket_type)
    code = buy_tickets(client, auth, login("holder@ssa.org"), ticket_type.id)["tickets"][0]["code"]
    db.scalar(select(Ticket).where(Ticket.code == code)).status = "void"
    db.commit()

    body = _scan(client, auth(login("vol@ssa.org")), event.id, code).json()

    assert body["result"] == "INVALID"
    assert body["ticket"] is None
    assert "void" in body["message"].lower()


def test_scan_of_a_ticket_for_another_event_names_that_event(
    client, auth, login, make_user, make_event, make_ticket_type
):
    make_user("vol@ssa.org", role="volunteer")
    _, _, other_type = _ticketed_user(make_user, make_event, make_ticket_type, email="other@ssa.org")
    code = buy_tickets(client, auth, login("other@ssa.org"), other_type.id)["tickets"][0]["code"]
    elsewhere = make_event(title="Coding Workshop")

    body = _scan(client, auth(login("vol@ssa.org")), elsewhere.id, code).json()

    assert body["result"] == "WRONG_EVENT"
    assert "Spring Gala" in body["message"]
    assert body["sold"] == 0  # the counters belong to the scanned event


def test_volunteer_may_scan_but_a_member_may_not(client, auth, login, make_user, make_event, make_ticket_type):
    make_user("vol@ssa.org", role="volunteer")
    make_user("plain@ssa.org", role="member")
    _, event, ticket_type = _ticketed_user(make_user, make_event, make_ticket_type)
    code = buy_tickets(client, auth, login("holder@ssa.org"), ticket_type.id)["tickets"][0]["code"]

    assert _scan(client, auth(login("vol@ssa.org")), event.id, code).status_code == 200

    refused = _scan(client, auth(login("plain@ssa.org")), event.id, code)
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "FORBIDDEN"

    anonymous = client.post("/api/v1/checkin", json={"event_id": str(event.id), "code": code})
    assert anonymous.status_code == 401


def test_race_two_scanners_one_valid(client, auth, login, db, db2, make_user, make_event, make_ticket_type):
    """Two doors, one ticket. The conditional UPDATE decides; a read-then-write would hand
    both scanners a green screen."""
    make_user("holder@ssa.org")
    staff = make_user("vol@ssa.org", role="volunteer")
    event = make_event()
    ticket_type = make_ticket_type(event)
    ticket = buy_tickets(client, auth, login("holder@ssa.org"), ticket_type.id)["tickets"][0]

    db2.get(Ticket, UUID(ticket["id"]))  # db2 now holds a stale 'valid' copy

    results = [
        check_in(db, staff, event.id, ticket["code"])["result"],
        check_in(db2, staff, event.id, ticket["code"])["result"],
    ]

    assert results.count("VALID") == 1
    assert results.count("ALREADY_USED") == 1
