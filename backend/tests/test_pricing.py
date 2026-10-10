"""Member pricing comes from an ACTIVE membership, never from the role alone (DESIGN.md §4)."""

MEMBER_PRICE = 30000
NON_MEMBER_PRICE = 50000


def _checkout(client, auth, login, email, ticket_type_id, quantity=1):
    response = client.post(
        "/api/v1/tickets/checkout",
        json={"ticket_type_id": str(ticket_type_id), "quantity": quantity},
        headers=auth(login(email)),
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_active_member_gets_member_price(client, auth, login, make_user, make_membership, make_event, make_ticket_type):
    user = make_user("member@ssa.org")
    make_membership(user)
    ticket_type = make_ticket_type(make_event(), member_price=MEMBER_PRICE, non_member_price=NON_MEMBER_PRICE)

    body = _checkout(client, auth, login, "member@ssa.org", ticket_type.id, quantity=2)

    assert body["unit_price"] == MEMBER_PRICE
    assert body["amount"] == MEMBER_PRICE * 2
    assert body["is_member_price"] is True


def test_expired_membership_falls_back_to_non_member_price(
    client, auth, login, make_user, make_membership, make_event, make_ticket_type
):
    """The row still says `active`; the end date is what decides."""
    user = make_user("lapsed@ssa.org")
    make_membership(user, days_left=-1)
    ticket_type = make_ticket_type(make_event())

    body = _checkout(client, auth, login, "lapsed@ssa.org", ticket_type.id)

    assert body["unit_price"] == NON_MEMBER_PRICE
    assert body["is_member_price"] is False


def test_role_alone_does_not_grant_member_price(client, auth, login, make_user, make_event, make_ticket_type):
    make_user("notyet@ssa.org", role="member")  # the role, but no membership row
    ticket_type = make_ticket_type(make_event())

    body = _checkout(client, auth, login, "notyet@ssa.org", ticket_type.id)

    assert body["unit_price"] == NON_MEMBER_PRICE
    assert body["is_member_price"] is False


def test_event_detail_personalises_price_for_you(
    client, auth, login, make_user, make_membership, make_event, make_ticket_type
):
    user = make_user("member@ssa.org")
    make_membership(user)
    event = make_event()
    make_ticket_type(event)

    guest = client.get(f"/api/v1/events/{event.id}")
    assert guest.status_code == 200
    assert guest.json()["ticket_types"][0]["price_for_you"] is None

    personal = client.get(f"/api/v1/events/{event.id}", headers=auth(login("member@ssa.org")))
    assert personal.json()["ticket_types"][0]["price_for_you"] == MEMBER_PRICE
