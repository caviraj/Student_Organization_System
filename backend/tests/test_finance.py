"""The treasurer's books: the signed arithmetic, hand-logged rows and their reversals,
reconciliation, the semester report and closed periods (PRD FR-6.2, DESIGN.md §4 rule 14)."""

import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import event, func, select

from app.core.errors import AppError
from app.models import Expense, FinancePeriod, Order, Transaction
from app.services import ledger
from tests.conftest import buy_tickets

BACKEND_DIR = Path(__file__).resolve().parents[1]
TODAY = datetime.now(UTC).date()


# --- fixtures ---------------------------------------------------------------------


@pytest.fixture
def treasurer(make_user):
    return make_user("treasurer@ssa.org", role="treasurer")


@pytest.fixture
def admin(make_user):
    return make_user("admin@ssa.org", role="admin")


@pytest.fixture
def organizer(make_user):
    return make_user("organizer@ssa.org", role="organizer")


@pytest.fixture
def volunteer(make_user):
    return make_user("volunteer@ssa.org", role="volunteer")


@pytest.fixture
def tokens(treasurer, admin, organizer, volunteer, login):
    return {
        "treasurer": login(treasurer.email),
        "admin": login(admin.email),
        "organizer": login(organizer.email),
        "volunteer": login(volunteer.email),
    }


@pytest.fixture
def queries(pg_engine):
    """Every SQL statement the database actually receives. An N+1 is visible here and nowhere
    else: the count grows with the number of rows."""
    statements: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(pg_engine, "before_cursor_execute", record)
    yield statements
    event.remove(pg_engine, "before_cursor_execute", record)


def post(client, auth, token, body, key: str | None = None) -> dict:
    headers = auth(token)
    if key:
        headers["Idempotency-Key"] = key
    response = client.post("/api/v1/finance/transactions", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def income(client, auth, token, amount: int = 500_000, note: str = "Sponsor - campus bookstore") -> dict:
    return post(client, auth, token, {"amount": amount, "source": "other_income", "note": note})


def expense_row(db, claimant, *, amount: int, status: str = "approved", receipt: bool = True, **extra) -> Expense:
    extra.setdefault("incurred_on", TODAY)
    row = Expense(
        claimant_id=claimant.id,
        amount=amount,
        description="Banner printing at the corner shop",
        category="printing",
        status=status,
        receipt_path=f"receipts/{claimant.id}/seed/bill.png" if receipt else None,
        receipt_mime="image/png" if receipt else None,
        receipt_size=40 if receipt else None,
        **extra,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def balance(client, auth, token) -> int:
    return client.get("/api/v1/finance/summary", headers=auth(token)).json()["balance"]


# --- 1. the signed arithmetic -----------------------------------------------------
def test_a_reversal_subtracts_from_the_side_its_original_was_on(db):
    """The whole reason reversals are a second row: the original stays visible, and the totals
    move in the right direction."""
    original = ledger.add_transaction(db, direction="in", amount=100_000, source="other_income", note="Cash box A")
    ledger.add_transaction(db, direction="out", amount=30_000, source="other_expense", note="Banner printing")
    db.commit()

    assert ledger.totals(db) == {"total_in": 100_000, "total_out": 30_000, "balance": 70_000}

    ledger.add_transaction(
        db,
        direction="out",
        amount=100_000,
        source="other_income",
        note="Double-counted the second cash box",
        is_reversal=True,
        reverses_id=original.id,
    )
    db.commit()

    # A naively-summed ledger would say 100_000 in and 130_000 out. It is 0 and 30_000.
    assert ledger.totals(db) == {"total_in": 0, "total_out": 30_000, "balance": -30_000}
    assert db.scalar(select(Transaction.amount).where(Transaction.source == "other_income", Transaction.is_reversal)) == 100_000


def test_the_central_writer_refuses_what_would_corrupt_the_books(db):
    with pytest.raises(AppError) as zero:
        ledger.add_transaction(db, direction="in", amount=0, source="other_income")
    assert zero.value.code == "VALIDATION_ERROR"

    with pytest.raises(AppError) as backwards:
        ledger.add_transaction(db, direction="out", amount=1000, source="other_income")
    assert backwards.value.code == "INVALID_LEDGER_ROW"

    with pytest.raises(AppError) as unknown:
        ledger.add_transaction(db, direction="in", amount=1000, source="gifts")
    assert unknown.value.code == "VALIDATION_ERROR"


def test_the_writer_never_commits_on_its_own(db):
    """A caller that rolls back must take the ledger row with it, or the balance counts money that
    never arrived."""
    before = ledger.totals(db)["balance"]
    ledger.add_transaction(db, direction="in", amount=9900, source="other_income", note="test")
    db.rollback()
    assert ledger.totals(db)["balance"] == before


def test_only_the_ledger_module_builds_a_ledger_row():
    """Every writer goes through `add_transaction`, because that is where the amount check, the
    source/direction pairing and the closed-period refusal live. A new `Transaction(...)` elsewhere
    would quietly skip all three - so this reads the source rather than trusting a review."""
    offenders = []
    # `class Transaction(Base)` is the model, not a writer.
    constructs = re.compile(r"(?<!class )\bTransaction\(")
    for path in sorted((BACKEND_DIR / "app").rglob("*.py")):
        if path.name == "ledger.py":
            continue
        source = path.read_text(encoding="utf-8")
        if constructs.search(source) or "update(Transaction)" in source or "delete(Transaction)" in source:
            offenders.append(path.relative_to(BACKEND_DIR).as_posix())
    assert offenders == [], f"the ledger is written outside services/ledger.py: {offenders}"


# --- 2. manual entries ------------------------------------------------------------
def test_a_treasurer_can_log_a_row_no_other_table_caused(client, auth, tokens, db, treasurer):
    entry = income(client, auth, tokens["treasurer"], amount=500_000, note="Sponsor - campus bookstore")
    assert entry["source"] == "other_income"
    assert entry["direction"] == "in" and entry["signed_amount"] == 500_000
    assert entry["label"] == "Sponsor - campus bookstore"
    assert entry["actor"]["id"] == str(treasurer.id)
    assert balance(client, auth, tokens["treasurer"]) == 500_000

    spent = post(
        client, auth, tokens["treasurer"], {"amount": 80_000, "source": "other_expense", "note": "Banner printing"}
    )
    assert spent["signed_amount"] == -80_000
    assert balance(client, auth, tokens["treasurer"]) == 420_000

    summary = client.get("/api/v1/finance/summary", headers=auth(tokens["treasurer"])).json()
    by_source = {row["source"]: row for row in summary["by_source"]}
    assert by_source["other_income"]["in"] == 500_000
    assert by_source["other_expense"]["out"] == 80_000


def test_an_idempotency_key_makes_a_retry_a_replay(client, auth, tokens, db):
    first = post(
        client, auth, tokens["treasurer"],
        {"amount": 500_000, "source": "other_income", "note": "Sponsor - campus bookstore"}, key="sponsor-1",
    )
    # A different body with the same key is still the same entry: the key wins, once it exists.
    again = post(
        client, auth, tokens["treasurer"],
        {"amount": 700_000, "source": "other_income", "note": "Sponsor - campus bookstore"}, key="sponsor-1",
    )
    assert again["id"] == first["id"]
    assert again["amount"] == 500_000
    rows = select(func.count()).select_from(Transaction).where(Transaction.idempotency_key == "sponsor-1")
    assert db.scalar(rows) == 1, "a replay must not write a second row"
    assert db.scalar(select(Transaction.amount).where(Transaction.idempotency_key == "sponsor-1")) == 500_000
    assert balance(client, auth, tokens["treasurer"]) == 500_000


def test_a_manual_entry_has_to_be_sane(client, auth, tokens):
    headers = auth(tokens["treasurer"])
    short_note = client.post(
        "/api/v1/finance/transactions", json={"amount": 1000, "source": "other_income", "note": "x"}, headers=headers
    )
    assert short_note.status_code == 422

    wrong_way = client.post(
        "/api/v1/finance/transactions",
        json={"amount": 1000, "source": "other_income", "note": "Sponsor cheque", "direction": "out"},
        headers=headers,
    )
    assert wrong_way.status_code == 422, wrong_way.text


def test_the_club_cannot_log_an_expense_it_cannot_afford(client, auth, tokens):
    income(client, auth, tokens["treasurer"], amount=100_000)
    response = client.post(
        "/api/v1/finance/transactions",
        json={"amount": 150_000, "source": "other_expense", "note": "Van hire for the stall"},
        headers=auth(tokens["treasurer"]),
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "INSUFFICIENT_FUNDS"
    assert response.json()["error"]["details"] == {"balance": 100_000, "amount": 150_000}

    # An admin may decide to go into the red, on purpose.
    forced = post(
        client, auth, tokens["admin"],
        {"amount": 150_000, "source": "other_expense", "note": "Van hire for the stall", "allow_negative": True},
    )
    assert forced["signed_amount"] == -150_000
    assert balance(client, auth, tokens["admin"]) == -50_000


def test_only_an_admin_may_ask_a_manual_entry_to_go_negative(client, auth, tokens):
    """`allow_negative` is a rank check, not a wish: without one a treasurer could empty the account
    with a single hand-logged bill, and no reimbursement would ever hit the funds check again."""
    refused = client.post(
        "/api/v1/finance/transactions",
        json={"amount": 1, "source": "other_expense", "note": "Not the treasurer's call", "allow_negative": True},
        headers=auth(tokens["treasurer"]),
    )
    assert refused.status_code == 403, refused.text
    assert refused.json()["error"]["code"] == "FORBIDDEN"
    assert balance(client, auth, tokens["treasurer"]) == 0


def test_a_hand_logged_row_may_be_backdated_but_only_recently(client, auth, tokens):
    headers = auth(tokens["treasurer"])
    body = {"amount": 20_000, "source": "other_income", "note": "Cash from the bake stall"}

    too_far = client.post(
        "/api/v1/finance/transactions",
        json={**body, "occurred_at": (datetime.now(UTC) - timedelta(days=61)).isoformat()},
        headers=headers,
    )
    assert too_far.status_code == 422 and too_far.json()["error"]["code"] == "INVALID_OCCURRED_AT"

    ahead = client.post(
        "/api/v1/finance/transactions",
        json={**body, "occurred_at": (datetime.now(UTC) + timedelta(days=1)).isoformat()},
        headers=headers,
    )
    assert ahead.status_code == 422 and ahead.json()["error"]["code"] == "INVALID_OCCURRED_AT"

    backdated = post(
        client, auth, tokens["treasurer"],
        {**body, "occurred_at": (datetime.now(UTC) - timedelta(days=30)).isoformat()},
    )
    assert backdated["occurred_at"][:10] == (datetime.now(UTC) - timedelta(days=30)).date().isoformat()


# --- 3. reversals -----------------------------------------------------------------
def test_a_reversal_is_a_second_row_that_cancels_the_first(client, auth, tokens, db):
    original = income(client, auth, tokens["treasurer"], amount=500_000)
    assert balance(client, auth, tokens["treasurer"]) == 500_000

    reversal = client.post(
        f"/api/v1/finance/transactions/{original['id']}/reverse",
        json={"reason": "Sponsor paid by cheque, this was the cash entry"},
        headers=auth(tokens["treasurer"]),
    )
    assert reversal.status_code == 201, reversal.text
    body = reversal.json()
    assert body["is_reversal"] is True and body["reverses_id"] == original["id"]
    assert body["direction"] == "out" and body["signed_amount"] == -500_000
    assert body["label"].startswith("Reversal: ")
    assert balance(client, auth, tokens["treasurer"]) == 0

    # Both rows survive: that is what makes the correction auditable.
    assert db.scalar(select(Transaction).where(Transaction.id == UUID(original["id"]))) is not None

    twice = client.post(
        f"/api/v1/finance/transactions/{original['id']}/reverse",
        json={"reason": "Trying again"},
        headers=auth(tokens["treasurer"]),
    )
    assert twice.status_code == 409 and twice.json()["error"]["code"] == "ALREADY_REVERSED"

    of_a_reversal = client.post(
        f"/api/v1/finance/transactions/{body['id']}/reverse",
        json={"reason": "Undoing the undo"},
        headers=auth(tokens["treasurer"]),
    )
    assert of_a_reversal.status_code == 409 and of_a_reversal.json()["error"]["code"] == "NOT_REVERSIBLE"


def test_a_ticket_sale_is_undone_by_refunding_not_by_a_reversal(client, auth, tokens, db, make_event, make_ticket_type):
    event_row = make_event()
    ticket_type = make_ticket_type(event_row)
    buy_tickets(client, auth, tokens["volunteer"], ticket_type.id)
    entry = db.scalar(select(Transaction).where(Transaction.source == "tickets"))

    response = client.post(
        f"/api/v1/finance/transactions/{entry.id}/reverse",
        json={"reason": "Buyer asked for a refund"},
        headers=auth(tokens["treasurer"]),
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "NOT_REVERSIBLE"


# --- 4. reconciliation ------------------------------------------------------------
def test_the_books_reconcile_after_a_normal_run(client, auth, tokens, db, treasurer, volunteer, make_event, make_ticket_type):
    event_row = make_event()
    buy_tickets(client, auth, tokens["volunteer"], make_ticket_type(event_row).id, quantity=2)
    income(client, auth, tokens["treasurer"], amount=500_000)
    post(client, auth, tokens["treasurer"], {"amount": 80_000, "source": "other_expense", "note": "Banner printing"})
    claim = expense_row(db, volunteer, amount=45_000, status="approved")
    client.post(f"/api/v1/expenses/{claim.id}/reimburse", json={"method": "cash"}, headers=auth(tokens["treasurer"]))

    report = client.get("/api/v1/finance/reconcile", headers=auth(tokens["treasurer"])).json()
    assert report["ok"] is True, report
    assert [check["name"] for check in report["checks"]] == [
        "Membership dues",
        "Ticket sales",
        "Merch sales",
        "Expense reimbursements",
        "Every reimbursed claim has a ledger row",
        "Positive ledger amounts",
        "Balance is not negative",
    ]
    reimbursements = next(check for check in report["checks"] if check["name"] == "Expense reimbursements")
    assert (reimbursements["ledger_total"], reimbursements["source_total"], reimbursements["difference"]) == (
        45_000, 45_000, 0,
    )


def test_reconciliation_catches_a_reimbursed_claim_that_left_no_trace(client, auth, tokens, db, volunteer):
    """`ledger_transaction_id` is the link between the claim and the row that paid it. Break it - the
    way a half-finished write would - and the books must refuse to call themselves sound."""
    expense_row(db, volunteer, amount=45_000, status="reimbursed")
    report = client.get("/api/v1/finance/reconcile", headers=auth(tokens["treasurer"])).json()
    assert report["ok"] is False
    unlinked = next(check for check in report["checks"] if check["name"] == "Every reimbursed claim has a ledger row")
    assert (unlinked["ok"], unlinked["ledger_total"], unlinked["difference"]) == (False, 1, 1)


def test_reconciliation_catches_a_negative_balance(client, auth, tokens):
    post(
        client, auth, tokens["admin"],
        {"amount": 150_000, "source": "other_expense", "note": "Van hire for the stall", "allow_negative": True},
    )
    report = client.get("/api/v1/finance/reconcile", headers=auth(tokens["admin"])).json()
    assert report["ok"] is False
    negative = next(check for check in report["checks"] if check["name"] == "Balance is not negative")
    assert (negative["ledger_total"], negative["difference"]) == (-150_000, -150_000)


# --- 5. the semester report -------------------------------------------------------
def test_the_report_adds_up(client, auth, tokens, db, treasurer, volunteer, make_event, make_ticket_type, make_fundraiser, organizer):
    event_row = make_event()
    make_fundraiser(organizer)
    buy_tickets(client, auth, tokens["volunteer"], make_ticket_type(event_row).id, quantity=2)
    income(client, auth, tokens["treasurer"], amount=500_000)
    claim = expense_row(db, volunteer, amount=45_000, status="approved", event_id=event_row.id)
    client.post(f"/api/v1/expenses/{claim.id}/reimburse", json={"method": "cash"}, headers=auth(tokens["treasurer"]))

    body = client.get(
        f"/api/v1/finance/report?from={(TODAY - timedelta(days=7)).isoformat()}&to={TODAY.isoformat()}",
        headers=auth(tokens["treasurer"]),
    ).json()

    assert body["opening_balance"] + body["net_movement"] == body["closing_balance"]
    # Recomputed from the tables that caused the rows, not from the ledger the report already read.
    ticket_money = db.scalar(select(func.coalesce(func.sum(Order.total), 0)).where(Order.status == "paid"))
    assert body["income"]["total"] == int(ticket_money) + 500_000
    assert body["expenses"]["total"] == 45_000
    assert body["net_movement"] == body["income"]["total"] - body["expenses"]["total"]
    assert body["expenses"]["by_category"] == [{"category": "printing", "amount": 45_000}]
    assert [row["id"] for row in body["by_event"]] == [str(event_row.id)]
    assert body["by_event"][0]["total_out"] == 45_000
    assert body["top_expenses"][0]["amount"] == 45_000
    assert body["reconciliation"]["ok"] is True
    assert body["generated_at"]

    backwards = client.get(
        f"/api/v1/finance/report?from={TODAY.isoformat()}&to={(TODAY - timedelta(days=7)).isoformat()}",
        headers=auth(tokens["treasurer"]),
    )
    assert backwards.status_code == 422


def test_by_event_and_outstanding_are_grouped_not_per_row(client, auth, tokens, queries, volunteer, make_event, make_ticket_type, db):
    for index in range(6):
        event_row = make_event(title=f"Event {index}")
        buy_tickets(client, auth, tokens["volunteer"], make_ticket_type(event_row).id)
    queries.clear()
    rows = client.get("/api/v1/finance/by-event", headers=auth(tokens["treasurer"])).json()
    assert len(rows) == 6
    assert len(queries) <= 3, f"{len(queries)} statements for a per-event table"

    for index in range(6):
        expense_row(db, volunteer, amount=1000 * (index + 1), status="submitted", receipt=False)
    queries.clear()
    owed = client.get("/api/v1/finance/outstanding-reimbursements", headers=auth(tokens["treasurer"])).json()
    assert len(owed) == 1 and owed[0]["submitted_amount"] == 21_000
    assert len(queries) <= 3, f"{len(queries)} statements for one claimant"


def test_the_ledger_table_costs_the_same_for_three_rows_as_for_fifteen(client, auth, tokens, queries):
    for index in range(3):
        income(client, auth, tokens["treasurer"], amount=1000 * (index + 1), note=f"Cash box {index}")
    queries.clear()
    client.get("/api/v1/finance/transactions", headers=auth(tokens["treasurer"]))
    few = len(queries)

    for index in range(12):
        income(client, auth, tokens["treasurer"], amount=1000, note=f"Cash box b{index}")
    queries.clear()
    page = client.get("/api/v1/finance/transactions", headers=auth(tokens["treasurer"])).json()
    assert page["total"] == 15
    assert len(queries) == few, f"{few} statements for 3 rows, {len(queries)} for 15 - that is an N+1"


def test_a_running_balance_walks_the_ledger_oldest_first(client, auth, tokens):
    income(client, auth, tokens["treasurer"], amount=500_000, note="First")
    income(client, auth, tokens["treasurer"], amount=200_000, note="Second")
    post(client, auth, tokens["treasurer"], {"amount": 50_000, "source": "other_expense", "note": "Third"})

    rows = client.get("/api/v1/finance/transactions?sort=asc", headers=auth(tokens["treasurer"])).json()["items"]
    assert [row["running_balance"] for row in rows] == [500_000, 700_000, 650_000]

    newest_first = client.get("/api/v1/finance/transactions", headers=auth(tokens["treasurer"])).json()["items"]
    assert all(row["running_balance"] is None for row in newest_first)
    assert [row["amount"] for row in newest_first] == [50_000, 200_000, 500_000]


# --- 6. closed periods ------------------------------------------------------------
def close(client, auth, token, name: str, start: date, end: date, force: bool = False):
    return client.post(
        "/api/v1/finance/periods",
        json={"name": name, "start_date": start.isoformat(), "end_date": end.isoformat(), "force": force},
        headers=auth(token),
    )


def test_a_closed_period_freezes_the_books(client, auth, tokens, treasurer, admin):
    income(client, auth, tokens["treasurer"], amount=500_000)
    start, end = TODAY - timedelta(days=50), TODAY - timedelta(days=10)

    closed = close(client, auth, tokens["treasurer"], "Semester 1 2026", start, end)
    assert closed.status_code == 201, closed.text
    body = closed.json()
    assert body["status"] == "closed"
    assert body["closed_by"]["id"] == str(treasurer.id)
    assert body["closing_balance"] == 0, "the only ledger row is today's, which is outside the period"

    # Nothing may be dated inside it any more.
    inside = client.post(
        "/api/v1/finance/transactions",
        json={
            "amount": 10_000,
            "source": "other_income",
            "note": "Late entry for the fair",
            "occurred_at": datetime.combine(end - timedelta(days=5), datetime.min.time(), tzinfo=UTC).isoformat(),
        },
        headers=auth(tokens["treasurer"]),
    )
    assert inside.status_code == 409, inside.text
    assert inside.json()["error"]["code"] == "PERIOD_CLOSED"
    assert inside.json()["error"]["details"]["period_name"] == "Semester 1 2026"

    # A row dated outside it is fine.
    assert income(client, auth, tokens["treasurer"], amount=1000, note="Today's cash")["amount"] == 1000

    listed = client.get("/api/v1/finance/periods", headers=auth(tokens["treasurer"])).json()
    assert [row["name"] for row in listed] == ["Semester 1 2026"]


def test_a_period_cannot_be_closed_over_unsettled_claims_or_a_broken_book(client, auth, tokens, db, volunteer):
    start, end = TODAY - timedelta(days=50), TODAY - timedelta(days=10)
    expense_row(db, volunteer, amount=5000, status="submitted", receipt=False, incurred_on=start + timedelta(days=1))

    pending = close(client, auth, tokens["treasurer"], "Semester 1 2026", start, end)
    assert pending.status_code == 409, pending.text
    assert pending.json()["error"]["code"] == "PENDING_CLAIMS"
    assert pending.json()["error"]["details"]["count"] == 1

    # Only an admin may overrule that, and it has to be said out loud.
    assert close(
        client, auth, tokens["treasurer"], "Semester 1 2026", start, end, force=True
    ).status_code == 403
    forced = close(client, auth, tokens["admin"], "Semester 1 2026", start, end, force=True)
    assert forced.status_code == 201, forced.text


def test_a_period_must_be_in_the_past_and_must_not_overlap(client, auth, tokens):
    income(client, auth, tokens["treasurer"], amount=500_000)
    start, end = TODAY - timedelta(days=50), TODAY - timedelta(days=10)
    assert close(client, auth, tokens["treasurer"], "Semester 1 2026", start, TODAY).status_code == 422
    assert close(client, auth, tokens["treasurer"], "Semester 1 2026", start, end).status_code == 201

    overlapping = close(client, auth, tokens["treasurer"], "Semester 2 2026", end - timedelta(days=1), TODAY - timedelta(days=1))
    assert overlapping.status_code == 409, overlapping.text
    assert overlapping.json()["error"]["code"] == "PERIOD_OVERLAP"
    assert overlapping.json()["error"]["details"]["period_name"] == "Semester 1 2026"

    same_name = close(client, auth, tokens["treasurer"], "Semester 1 2026", start - timedelta(days=60), start - timedelta(days=1))
    assert same_name.status_code == 409
    assert same_name.json()["error"]["code"] == "PERIOD_NAME_TAKEN"


def test_only_an_admin_reopens_and_only_with_a_reason(client, auth, tokens):
    income(client, auth, tokens["treasurer"], amount=500_000)
    start, end = TODAY - timedelta(days=50), TODAY - timedelta(days=10)
    period_id = close(client, auth, tokens["treasurer"], "Semester 1 2026", start, end).json()["id"]

    assert client.post(
        f"/api/v1/finance/periods/{period_id}/reopen", json={"reason": "Missed October"}, headers=auth(tokens["treasurer"])
    ).status_code == 403
    assert client.post(
        f"/api/v1/finance/periods/{period_id}/reopen", json={"reason": "oops"}, headers=auth(tokens["admin"])
    ).status_code == 422

    reopened = client.post(
        f"/api/v1/finance/periods/{period_id}/reopen",
        json={"reason": "Missed the printer invoice for October"},
        headers=auth(tokens["admin"]),
    )
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["status"] == "reopened"
    assert reopened.json()["reopen_reason"] == "Missed the printer invoice for October"

    # Reopened means writable again - and the reason is kept for whoever audits this later.
    backdated = post(
        client, auth, tokens["treasurer"],
        {
            "amount": 10_000,
            "source": "other_income",
            "note": "Late entry for the fair",
            "occurred_at": datetime.combine(end - timedelta(days=5), datetime.min.time(), tzinfo=UTC).isoformat(),
        },
    )
    assert backdated["amount"] == 10_000

    again = client.post(
        f"/api/v1/finance/periods/{period_id}/reopen",
        json={"reason": "Trying to reopen a reopened period"},
        headers=auth(tokens["admin"]),
    )
    assert again.status_code == 409 and again.json()["error"]["code"] == "INVALID_STATE"


def test_the_seed_style_backdate_is_the_only_way_into_a_closed_period(db, treasurer):
    start, end = TODAY - timedelta(days=40), TODAY - timedelta(days=5)
    db.add(
        FinancePeriod(
            name="Semester 1 2026", start_date=start, end_date=end, status="closed",
            closing_balance=0, snapshot={}, closed_by=treasurer.id, closed_at=datetime.now(UTC),
        )
    )
    db.commit()
    when = datetime.combine(end - timedelta(days=1), datetime.min.time(), tzinfo=UTC)

    with pytest.raises(AppError) as refused:
        ledger.add_transaction(db, direction="in", amount=1000, source="other_income", occurred_at=when)
    assert refused.value.code == "PERIOD_CLOSED"

    ledger.add_transaction(
        db, direction="in", amount=1000, source="other_income", occurred_at=when, seed_backdate=True
    )
    db.commit()
    assert ledger.totals(db)["total_in"] == 1000


# --- 7. row level security --------------------------------------------------------
def test_every_new_table_keeps_its_door_shut(db):
    """Supabase publishes `public` over its own REST API; RLS-on-with-no-policies is the only thing
    keeping these tables off it."""
    from sqlalchemy import text

    rows = dict(
        db.execute(
            text(
                "select tablename, rowsecurity from pg_tables "
                "where schemaname = 'public' and tablename in "
                "('expenses', 'expense_history', 'finance_periods', 'transactions')"
            )
        ).all()
    )
    assert rows == {
        "expenses": True,
        "expense_history": True,
        "finance_periods": True,
        "transactions": True,
    }


# --- 8. the fundraiser page and the books agree ------------------------------------
def claim_for(client, auth, token, fundraiser_id, amount: int = 45_000) -> dict:
    """A receipted claim charged to a fundraiser, all the way through the real endpoints."""
    created = client.post(
        "/api/v1/expenses",
        data={
            "amount": str(amount),
            "description": "Stall banner and leaflets",
            "category": "printing",
            "incurred_on": TODAY.isoformat(),
            "fundraiser_id": str(fundraiser_id),
        },
        files={"receipt": ("bill.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 16, "image/png")},
        headers=auth(token),
    )
    assert created.status_code == 201, created.text
    return created.json()


def test_a_fundraiser_reports_gross_raised_and_net_after_its_own_bills(client, auth, tokens, organizer, volunteer, make_fundraiser):
    fundraiser = make_fundraiser(organizer)
    cash = client.post(
        f"/api/v1/fundraisers/{fundraiser.id}/income",
        json={"amount": 100_000, "note": "Coffee stall, day 1"},
        headers=auth(tokens["organizer"]),
    )
    assert cash.status_code == 201, cash.text

    claim = claim_for(client, auth, tokens["volunteer"], fundraiser.id, amount=45_000)
    client.patch(
        f"/api/v1/expenses/{claim['id']}/review", json={"decision": "approve"}, headers=auth(tokens["treasurer"])
    )
    paid = client.post(
        f"/api/v1/expenses/{claim['id']}/reimburse", json={"method": "cash"}, headers=auth(tokens["treasurer"])
    )
    assert paid.status_code == 200, paid.text

    progress = client.get(f"/api/v1/fundraisers/{fundraiser.id}", headers=auth(tokens["volunteer"])).json()["progress"]
    assert progress["raised"] == 100_000, "raised stays gross: what the stall took"
    assert progress["spent"] == 45_000
    assert progress["net_raised"] == 55_000

    # The list card says the same thing as the detail page.
    card = client.get("/api/v1/fundraisers", headers=auth(tokens["volunteer"])).json()["items"][0]["progress"]
    assert (card["raised"], card["spent"], card["net_raised"]) == (100_000, 45_000, 55_000)

    # ...and so does the finance table, which is the point of both reading the ledger.
    per_fundraiser = client.get("/api/v1/finance/by-fundraiser", headers=auth(tokens["treasurer"])).json()
    assert [(row["total_in"], row["total_out"]) for row in per_fundraiser] == [(100_000, 45_000)]


def test_a_reversed_donation_leaves_the_fundraiser_total(client, auth, tokens, db, organizer, make_fundraiser):
    fundraiser = make_fundraiser(organizer)
    client.post(
        f"/api/v1/fundraisers/{fundraiser.id}/income",
        json={"amount": 100_000, "note": "Coffee stall, day 1"},
        headers=auth(tokens["organizer"]),
    )
    entry = db.scalar(select(Transaction).where(Transaction.fundraiser_id == fundraiser.id))

    reversed_row = client.post(
        f"/api/v1/finance/transactions/{entry.id}/reverse",
        json={"reason": "Counted the same cash box twice"},
        headers=auth(tokens["treasurer"]),
    )
    assert reversed_row.status_code == 201, reversed_row.text

    progress = client.get(f"/api/v1/fundraisers/{fundraiser.id}", headers=auth(tokens["volunteer"])).json()["progress"]
    assert progress["raised"] == 0, "a reversal has to come out of the total it inflated"
    assert progress["net_raised"] == 0


def test_the_fundraiser_list_does_not_query_per_card(client, auth, tokens, queries, organizer, make_fundraiser):
    make_fundraiser(organizer, title="Raffle")
    queries.clear()
    client.get("/api/v1/fundraisers", headers=auth(tokens["volunteer"]))
    few = len(queries)

    for index in range(9):
        make_fundraiser(organizer, title=f"Raffle {index}")
    queries.clear()
    body = client.get("/api/v1/fundraisers", headers=auth(tokens["volunteer"])).json()
    assert body["total"] == 10
    assert len(queries) == few, f"{few} statements for 1 card, {len(queries)} for 10 - that is an N+1"
