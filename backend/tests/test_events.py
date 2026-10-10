"""Browsing and administering events (DESIGN.md §5 Events)."""

from datetime import UTC, datetime, timedelta


def test_public_list_hides_drafts_and_filters(client, make_event, make_ticket_type):
    published = make_event(title="Spring Gala", venue="Willow Hall")
    make_event(title="Annual Meet", status="draft")
    make_event(title="Last Year's Gala", status="published", starts_in_days=-5, venue="Old Town Hall")
    make_ticket_type(published)

    body = client.get("/api/v1/events").json()
    assert [item["title"] for item in body["items"]] == ["Last Year's Gala", "Spring Gala"]  # by start time
    assert body["total"] == 2

    upcoming = client.get("/api/v1/events?upcoming=true").json()
    assert [item["title"] for item in upcoming["items"]] == ["Spring Gala"]

    searched = client.get("/api/v1/events?q=Willow Hall").json()  # venue match, case-insensitive
    assert [item["title"] for item in searched["items"]] == ["Spring Gala"]


def test_drafts_need_an_organizer_token(client, auth, login, make_user, make_event, make_ticket_type):
    make_user("organizer@ssa.org", role="organizer")
    draft = make_event(title="Annual Meet", status="draft")
    make_ticket_type(draft)

    assert client.get("/api/v1/events?include_drafts=true").status_code == 401

    organizer = client.get("/api/v1/events?include_drafts=true", headers=auth(login("organizer@ssa.org")))
    assert organizer.status_code == 200
    assert [item["title"] for item in organizer.json()["items"]] == ["Annual Meet"]

    assert client.get(f"/api/v1/events/{draft.id}").status_code == 404
    assert client.get(f"/api/v1/events/{draft.id}", headers=auth(login("organizer@ssa.org"))).status_code == 200


def test_summary_price_follows_the_caller(
    client, auth, login, make_user, make_membership, make_event, make_ticket_type
):
    member = make_user("member@ssa.org")
    make_membership(member)
    event = make_event()
    make_ticket_type(event, name="General", member_price=30000, non_member_price=50000, capacity=120)
    make_ticket_type(event, name="VIP", member_price=100000, non_member_price=150000, capacity=20)

    as_guest = client.get("/api/v1/events").json()["items"][0]
    assert (as_guest["min_price"], as_guest["seats_left"]) == (50000, 140)

    as_member = client.get("/api/v1/events", headers=auth(login("member@ssa.org"))).json()["items"][0]
    assert as_member["min_price"] == 30000


def test_organizer_adds_a_ticket_type(client, auth, login, make_user, make_event):
    make_user("organizer@ssa.org", role="organizer")
    make_user("member@ssa.org", role="member")
    event = make_event()
    organizer = auth(login("organizer@ssa.org"))

    created = client.post(
        f"/api/v1/events/{event.id}/ticket-types",
        json={"name": "VIP", "member_price": 100000, "non_member_price": 150000, "capacity": 20},
        headers=organizer,
    )
    assert created.status_code == 201, created.text
    assert created.json()["seats_left"] == 20
    assert created.json()["is_on_sale"] is True

    refused = client.post(
        f"/api/v1/events/{event.id}/ticket-types",
        json={"name": "Sneaky", "member_price": 0, "non_member_price": 0, "capacity": 5},
        headers=auth(login("member@ssa.org")),
    )
    assert refused.status_code == 403

    detail = client.get(f"/api/v1/events/{event.id}").json()
    assert [t["name"] for t in detail["ticket_types"]] == ["VIP"]


def test_status_is_one_way(client, auth, login, make_user, make_event):
    make_user("organizer@ssa.org", role="organizer")
    organizer = auth(login("organizer@ssa.org"))
    draft = make_event(status="draft")
    other_draft = make_event(title="Annual Meet", status="draft")

    published = client.patch(f"/api/v1/events/{draft.id}", json={"status": "published"}, headers=organizer)
    assert published.status_code == 200
    assert published.json()["status"] == "published"

    closed = client.patch(f"/api/v1/events/{draft.id}", json={"status": "closed"}, headers=organizer)
    assert closed.status_code == 200

    reopened = client.patch(f"/api/v1/events/{draft.id}", json={"status": "published"}, headers=organizer)
    assert reopened.status_code == 409
    assert reopened.json()["error"]["code"] == "INVALID_STATUS_TRANSITION"

    skipped = client.patch(f"/api/v1/events/{other_draft.id}", json={"status": "closed"}, headers=organizer)
    assert skipped.status_code == 200


def test_create_event_validates_its_window(client, auth, login, make_user):
    make_user("organizer@ssa.org", role="organizer")
    organizer = auth(login("organizer@ssa.org"))
    starts_at = datetime.now(UTC) + timedelta(days=10)

    backwards = client.post(
        "/api/v1/events",
        json={
            "title": "Backwards",
            "starts_at": starts_at.isoformat(),
            "ends_at": (starts_at - timedelta(hours=1)).isoformat(),
        },
        headers=organizer,
    )
    assert backwards.status_code == 422
    assert backwards.json()["error"]["code"] == "VALIDATION_ERROR"

    created = client.post(
        "/api/v1/events",
        json={
            "title": "Spring Gala",
            "venue": "Main Auditorium",
            "starts_at": starts_at.isoformat(),
            "ends_at": (starts_at + timedelta(hours=4)).isoformat(),
        },
        headers=organizer,
    )
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "draft"  # new events always start as a draft
    assert created.json()["ticket_types"] == []
