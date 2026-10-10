"""Income logged by hand: one ledger row per entry, and the Idempotency-Key that stops a
double-click from counting the cash twice (DESIGN.md §4 rule 13, §5 Fundraiser Income)."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import func, select

from app.models import Transaction

GOAL = 500000
KEY = {"Idempotency-Key": "stall-day-2"}


@pytest.fixture
def organizer(make_user):
    return make_user("organizer@ssa.org", role="organizer")


@pytest.fixture
def volunteer(make_user):
    return make_user("volunteer@ssa.org", role="volunteer")


@pytest.fixture
def member(make_user):
    return make_user("member01@ssa.org", role="member")


@pytest.fixture
def tokens(organizer, volunteer, member, login):
    return {
        "organizer": login(organizer.email),
        "volunteer": login(volunteer.email),
        "member": login(member.email),
    }


@pytest.fixture
def fundraiser(make_fundraiser, organizer):
    return make_fundraiser(organizer, goal=GOAL, days=10, status="active")


def income_rows(db, fundraiser_id) -> int:
    return db.scalar(
        select(func.count())
        .select_from(Transaction)
        .where(Transaction.fundraiser_id == fundraiser_id, Transaction.direction == "in")
    )


# --- 1. one entry, one ledger row -------------------------------------------------
def test_logging_income_writes_one_row_and_reports_the_running_total(client, tokens, auth, db, fundraiser, organizer):
    response = client.post(
        f"/api/v1/fundraisers/{fundraiser.id}/income",
        json={"amount": 150000, "note": "Coffee stall", "source_label": "Cash box"},
        headers={**auth(tokens["organizer"]), **KEY},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["amount"] == 150000
    assert body["raised_total"] == 150000
    assert body["percent_of_goal"] == 30
    assert body["replayed"] is False

    entry = db.get(Transaction, UUID(body["id"]))
    assert (entry.direction, entry.source, entry.fundraiser_id) == ("in", "fundraiser", fundraiser.id)
    assert entry.logged_by == organizer.id
    assert entry.note == "Cash box - Coffee stall"

    second = client.post(
        f"/api/v1/fundraisers/{fundraiser.id}/income",
        json={"amount": 50000},
        headers=auth(tokens["organizer"]),
    )
    assert second.json()["raised_total"] == 200000, "the total is the sum of the rows, not the last one"
    assert income_rows(db, fundraiser.id) == 2

    progress = client.get(f"/api/v1/fundraisers/{fundraiser.id}", headers=auth(tokens["volunteer"])).json()["progress"]
    assert (progress["raised"], progress["goal"], progress["percent_of_goal"]) == (200000, GOAL, 40)


def test_the_same_key_twice_writes_one_row(client, tokens, auth, db, fundraiser):
    url = f"/api/v1/fundraisers/{fundraiser.id}/income"
    headers = {**auth(tokens["organizer"]), **KEY}
    payload = {"amount": 150000, "note": "Pre-orders"}

    first = client.post(url, json=payload, headers=headers)
    again = client.post(url, json=payload, headers=headers)
    assert (first.status_code, again.status_code) == (201, 201)
    assert again.json()["id"] == first.json()["id"], "the retry replays the row it already wrote"
    assert again.json()["replayed"] is True
    assert income_rows(db, fundraiser.id) == 1

    # A different key is a different entry, and no key at all means no replay protection.
    other = client.post(url, json={"amount": 10000}, headers={**auth(tokens["organizer"]), "Idempotency-Key": "day-3"})
    assert other.json()["replayed"] is False
    assert income_rows(db, fundraiser.id) == 2


def test_a_replay_on_a_closed_fundraiser_is_still_refused(client, tokens, auth, make_fundraiser, organizer):
    """The window is checked before the key, so a late retry cannot slip cash in after closing."""
    closed = make_fundraiser(organizer, status="done", completed_at=datetime.now(UTC) - timedelta(days=9))
    response = client.post(
        f"/api/v1/fundraisers/{closed.id}/income",
        json={"amount": 1000},
        headers={**auth(tokens["organizer"]), **KEY},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "FUNDRAISER_CLOSED"


# --- 2. permissions ---------------------------------------------------------------
@pytest.mark.parametrize("caller", ["guest", "member", "volunteer"])
def test_only_organizer_and_above_may_log_income(client, tokens, auth, fundraiser, caller):
    url = f"/api/v1/fundraisers/{fundraiser.id}/income"
    if caller == "guest":
        assert client.post(url, json={"amount": 1000}).status_code == 401
        return
    response = client.post(url, json={"amount": 1000}, headers=auth(tokens[caller]))
    assert response.status_code == 403, response.text


def test_reading_the_cash_book_needs_volunteer_and_above(client, tokens, auth, fundraiser):
    url = f"/api/v1/fundraisers/{fundraiser.id}/income"
    assert client.get(url).status_code == 401
    assert client.get(url, headers=auth(tokens["member"])).status_code == 403
    assert client.get(url, headers=auth(tokens["volunteer"])).status_code == 200


# --- 3. what one entry may say ----------------------------------------------------
@pytest.mark.parametrize("amount", [0, -1, 10_000_001])
def test_amount_must_be_a_positive_small_int(client, tokens, auth, fundraiser, amount):
    response = client.post(
        f"/api/v1/fundraisers/{fundraiser.id}/income",
        json={"amount": amount},
        headers=auth(tokens["organizer"]),
    )
    assert response.status_code == 422, response.text


def test_dating_an_entry(client, tokens, auth, db, fundraiser):
    url = f"/api/v1/fundraisers/{fundraiser.id}/income"
    headers = auth(tokens["organizer"])

    future = client.post(
        url, json={"amount": 1000, "occurred_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat()}, headers=headers
    )
    assert future.status_code == 422 and future.json()["error"]["code"] == "INVALID_OCCURRED_AT"

    too_old = client.post(
        url, json={"amount": 1000, "occurred_at": (datetime.now(UTC) - timedelta(days=31)).isoformat()}, headers=headers
    )
    assert too_old.status_code == 422 and too_old.json()["error"]["code"] == "INVALID_OCCURRED_AT"

    counted_yesterday = (datetime.now(UTC) - timedelta(days=1)).replace(microsecond=0)
    ok = client.post(url, json={"amount": 25000, "occurred_at": counted_yesterday.isoformat()}, headers=headers)
    assert ok.status_code == 201, ok.text
    db.expire_all()
    assert db.get(Transaction, UUID(ok.json()["id"])).occurred_at.replace(microsecond=0) == counted_yesterday


# --- 4. the seven-day window after closing ----------------------------------------
def test_income_is_refused_once_the_grace_window_has_passed(client, tokens, auth, make_fundraiser, organizer):
    stale = make_fundraiser(organizer, status="done", completed_at=datetime.now(UTC) - timedelta(days=8))
    response = client.post(
        f"/api/v1/fundraisers/{stale.id}/income", json={"amount": 1000}, headers=auth(tokens["organizer"])
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "FUNDRAISER_CLOSED"


def test_cash_counted_on_the_day_still_arrives_within_the_week(client, tokens, auth, db, make_fundraiser, organizer):
    just_closed = make_fundraiser(organizer, status="done", completed_at=datetime.now(UTC) - timedelta(days=2))
    response = client.post(
        f"/api/v1/fundraisers/{just_closed.id}/income",
        json={"amount": 80000, "note": "Morning sales"},
        headers=auth(tokens["organizer"]),
    )
    assert response.status_code == 201, response.text
    assert response.json()["raised_total"] == 80000
    assert income_rows(db, just_closed.id) == 1


# --- 5. the cash book -------------------------------------------------------------
def test_the_cash_book_shows_who_logged_what_newest_first(client, tokens, auth, fundraiser, organizer, volunteer):
    client.post(
        f"/api/v1/fundraisers/{fundraiser.id}/income",
        json={"amount": 120000, "note": "Pre-orders", "occurred_at": (datetime.now(UTC) - timedelta(days=2)).isoformat()},
        headers=auth(tokens["organizer"]),
    )
    client.post(
        f"/api/v1/fundraisers/{fundraiser.id}/income",
        json={"amount": 80000, "note": "Morning sales"},
        headers=auth(tokens["organizer"]),
    )

    response = client.get(f"/api/v1/fundraisers/{fundraiser.id}/income", headers=auth(tokens["volunteer"]))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 2
    assert [row["note"] for row in body["items"]] == ["Morning sales", "Pre-orders"]
    assert all(row["logged_by"]["id"] == str(organizer.id) for row in body["items"])

    # The book is paginated off the same filter, so page 2 is empty rather than someone else's cash.
    assert client.get(f"/api/v1/fundraisers/{fundraiser.id}/income?page=2", headers=auth(tokens["volunteer"])).json()["items"] == []


def test_there_is_no_way_to_edit_or_delete_an_entry(client, tokens, auth, db, fundraiser):
    entry = client.post(
        f"/api/v1/fundraisers/{fundraiser.id}/income", json={"amount": 5000}, headers=auth(tokens["organizer"])
    ).json()
    headers = auth(tokens["organizer"])
    assert client.patch(f"/api/v1/fundraisers/{fundraiser.id}/income/{entry['id']}", json={"amount": 1}, headers=headers).status_code == 404
    assert client.delete(f"/api/v1/fundraisers/{fundraiser.id}/income/{entry['id']}", headers=headers).status_code == 404
    assert income_rows(db, fundraiser.id) == 1, "a ledger you can rewrite is not a ledger"
