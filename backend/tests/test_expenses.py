"""Expense claims: who may submit one, what a receipt has to be, what a treasurer may decide, and
the one moment money actually moves (PRD FR-6.1, DESIGN.md §4 rule 14)."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import func, select

from app.core.errors import AppError
from app.models import Expense, ExpenseHistory, Transaction
from app.services import expenses as expense_service

DESCRIPTION = "Auto fare to the printer"
TODAY = date.today()


def png(payload: bytes = b"\x00" * 32) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + payload


def pdf(payload: bytes = b"\x00" * 32) -> bytes:
    return b"%PDF-1.4\n" + payload


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
def other_volunteer(make_user):
    return make_user("volunteer2@ssa.org", role="volunteer")


@pytest.fixture
def member(make_user):
    return make_user("member01@ssa.org", role="member")


@pytest.fixture
def tokens(treasurer, admin, organizer, volunteer, other_volunteer, member, login):
    return {
        "treasurer": login(treasurer.email),
        "admin": login(admin.email),
        "organizer": login(organizer.email),
        "volunteer": login(volunteer.email),
        "other_volunteer": login(other_volunteer.email),
        "member": login(member.email),
    }


@pytest.fixture
def make_expense(db):
    """Builds a claim row directly: these tests are about the rules, not about `create_expense`."""

    def _make(claimant, *, amount: int = 45000, status: str = "submitted", receipt: bool = False, **extra) -> Expense:
        expense = Expense(
            claimant_id=claimant.id,
            amount=amount,
            description=DESCRIPTION,
            category="printing",
            incurred_on=TODAY,
            status=status,
            receipt_path=f"receipts/{claimant.id}/seed/bill.png" if receipt else None,
            receipt_mime="image/png" if receipt else None,
            receipt_size=40 if receipt else None,
            **extra,
        )
        db.add(expense)
        db.commit()
        db.refresh(expense)
        return expense

    return _make


def fund(client, auth, token, amount: int = 1_000_000, note: str = "Sponsor - campus bookstore") -> dict:
    """Puts money in the club's hands the way a treasurer really would: a manual income entry."""
    response = client.post(
        "/api/v1/finance/transactions",
        json={"amount": amount, "source": "other_income", "note": note},
        headers=auth(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


def claims(
    *, description: str = DESCRIPTION, amount: int = 45000, category: str = "printing", incurred_on: date | None = None
) -> dict:
    return {
        "amount": str(amount),
        "description": description,
        "category": category,
        "incurred_on": (incurred_on or TODAY).isoformat(),
    }


def ledger_rows(db, *, source: str | None = None) -> int:
    statement = select(func.count()).select_from(Transaction)
    if source:
        statement = statement.where(Transaction.source == source)
    return db.scalar(statement) or 0


# --- 1. permissions ---------------------------------------------------------------
def test_a_guest_cannot_touch_claims_at_all(client):
    assert client.post("/api/v1/expenses", data=claims()).status_code == 401
    assert client.get("/api/v1/expenses/me").status_code == 401
    assert client.get("/api/v1/expenses").status_code == 401
    assert client.get("/api/v1/finance/summary").status_code == 401


def test_a_plain_member_cannot_claim_expenses(client, auth, tokens):
    response = client.post("/api/v1/expenses", data=claims(), headers=auth(tokens["member"]))
    assert response.status_code == 403, response.text


@pytest.mark.parametrize(
    "path", ["/api/v1/expenses", "/api/v1/finance/summary", "/api/v1/finance/transactions", "/api/v1/finance/reconcile"]
)
def test_the_treasury_is_closed_to_volunteers_and_organizers(client, auth, tokens, path):
    assert client.get(path, headers=auth(tokens["volunteer"])).status_code == 403
    assert client.get(path, headers=auth(tokens["organizer"])).status_code == 403
    assert client.get(path, headers=auth(tokens["treasurer"])).status_code == 200


def test_a_volunteer_cannot_read_somebody_elses_claim(client, auth, tokens, volunteer, other_volunteer, make_expense):
    expense = make_expense(other_volunteer)
    headers = auth(tokens["volunteer"])
    assert client.get(f"/api/v1/expenses/{expense.id}", headers=headers).status_code == 403
    assert client.get(f"/api/v1/expenses/{expense.id}/receipt", headers=headers).status_code == 403
    # ...but the treasurer can, which is the whole reason the queue exists.
    assert client.get(f"/api/v1/expenses/{expense.id}", headers=auth(tokens["treasurer"])).status_code == 200


# --- 2. uploads ------------------------------------------------------------------
def test_a_receipt_must_be_a_real_image_or_pdf(client, auth, tokens, volunteer):
    headers = auth(tokens["volunteer"])

    good = client.post(
        "/api/v1/expenses", data=claims(), files={"receipt": ("bill.png", png(), "image/png")}, headers=headers
    )
    assert good.status_code == 201, good.text
    assert good.json()["has_receipt"] is True
    assert good.json()["receipt_mime"] == "image/png"
    assert good.json()["receipt_size"] == 40

    # A file whose bytes are not what it claims to be is rejected, not stored.
    liar = client.post(
        "/api/v1/expenses",
        data=claims(),
        files={"receipt": ("bill.png", b"<html>not an image</html>", "image/png")},
        headers=headers,
    )
    assert liar.status_code == 422, liar.text
    assert liar.json()["error"]["code"] == "INVALID_FILE_TYPE"

    wrong_kind = client.post(
        "/api/v1/expenses",
        data=claims(),
        files={"receipt": ("bill.txt", b"hello", "text/plain")},
        headers=headers,
    )
    assert wrong_kind.status_code == 422
    assert wrong_kind.json()["error"]["code"] == "INVALID_FILE_TYPE"


def test_a_receipt_over_five_megabytes_is_refused(client, auth, tokens, volunteer):
    response = client.post(
        "/api/v1/expenses",
        data=claims(),
        files={"receipt": ("big.png", png(b"\x00" * (5 * 1024 * 1024 + 1)), "image/png")},
        headers=auth(tokens["volunteer"]),
    )
    assert response.status_code == 413, response.text
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"


def test_a_client_filename_never_reaches_the_stored_path(client, auth, tokens, db, volunteer):
    response = client.post(
        "/api/v1/expenses",
        data=claims(),
        files={"receipt": ("../../etc/passwd.png", png(), "image/png")},
        headers=auth(tokens["volunteer"]),
    )
    assert response.status_code == 201, response.text
    stored = db.get(Expense, UUID(response.json()["id"])).receipt_path
    assert stored.startswith(f"receipts/{volunteer.id}/{response.json()['id']}/")
    assert "passwd" not in stored and ".." not in stored


def test_a_pdf_receipt_is_accepted(client, auth, tokens, volunteer):
    response = client.post(
        "/api/v1/expenses",
        data=claims(),
        files={"receipt": ("bill.pdf", pdf(), "application/pdf")},
        headers=auth(tokens["volunteer"]),
    )
    assert response.status_code == 201, response.text
    assert response.json()["receipt_mime"] == "application/pdf"


# --- 3. what a claim may say ------------------------------------------------------
def test_a_receipt_is_optional_to_submit_and_required_to_approve(client, auth, tokens, db, volunteer, treasurer):
    created = client.post("/api/v1/expenses", data=claims(), headers=auth(tokens["volunteer"]))
    assert created.status_code == 201, created.text
    assert created.json()["has_receipt"] is False

    refused = client.patch(
        f"/api/v1/expenses/{created.json()['id']}/review",
        json={"decision": "approve"},
        headers=auth(tokens["treasurer"]),
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "RECEIPT_REQUIRED"

    attached = client.put(
        f"/api/v1/expenses/{created.json()['id']}/receipt",
        files={"receipt": ("bill.png", png(), "image/png")},
        headers=auth(tokens["volunteer"]),
    )
    assert attached.status_code == 200, attached.text
    assert attached.json()["has_receipt"] is True

    approved = client.patch(
        f"/api/v1/expenses/{created.json()['id']}/review",
        json={"decision": "approve"},
        headers=auth(tokens["treasurer"]),
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"


@pytest.mark.parametrize("amount", [0, -1, 5_000_001])
def test_amount_stays_inside_the_sane_range(client, auth, tokens, amount):
    response = client.post("/api/v1/expenses", data=claims(amount=amount), headers=auth(tokens["volunteer"]))
    assert response.status_code == 422, response.text


def test_the_description_has_to_say_something(client, auth, tokens):
    headers = auth(tokens["volunteer"])
    assert client.post("/api/v1/expenses", data=claims(description="bus"), headers=headers).status_code == 422
    assert client.post("/api/v1/expenses", data=claims(description="x" * 301), headers=headers).status_code == 422
    assert client.post("/api/v1/expenses", data=claims(description="   "), headers=headers).status_code == 422


def test_dating_a_claim(client, auth, tokens):
    headers = auth(tokens["volunteer"])

    future = client.post("/api/v1/expenses", data=claims(incurred_on=TODAY + timedelta(days=1)), headers=headers)
    assert future.status_code == 422 and future.json()["error"]["code"] == "INVALID_INCURRED_ON"

    stale = client.post("/api/v1/expenses", data=claims(incurred_on=TODAY - timedelta(days=91)), headers=headers)
    assert stale.status_code == 422 and stale.json()["error"]["code"] == "INVALID_INCURRED_ON"

    edge = client.post("/api/v1/expenses", data=claims(incurred_on=TODAY - timedelta(days=90)), headers=headers)
    assert edge.status_code == 201, edge.text


def test_a_claim_hangs_off_an_event_or_a_fundraiser_but_never_both(
    client, auth, tokens, make_event, make_fundraiser, organizer
):
    event = make_event()
    fundraiser = make_fundraiser(organizer)
    both = client.post(
        "/api/v1/expenses",
        data={**claims(), "event_id": str(event.id), "fundraiser_id": str(fundraiser.id)},
        headers=auth(tokens["volunteer"]),
    )
    assert both.status_code == 422, both.text

    missing = client.post(
        "/api/v1/expenses", data={**claims(), "event_id": str(UUID(int=0))}, headers=auth(tokens["volunteer"])
    )
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "EVENT_NOT_FOUND"

    ok = client.post(
        "/api/v1/expenses", data={**claims(), "event_id": str(event.id)}, headers=auth(tokens["volunteer"])
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["event_id"] == str(event.id)


def test_a_volunteer_only_sees_their_own_claims_in_my_claims(client, auth, tokens, volunteer):
    client.post("/api/v1/expenses", data=claims(), headers=auth(tokens["volunteer"]))
    client.post("/api/v1/expenses", data=claims(amount=1000), headers=auth(tokens["other_volunteer"]))

    body = client.get("/api/v1/expenses/me", headers=auth(tokens["volunteer"])).json()
    assert body["total"] == 1
    assert body["items"][0]["claimant"]["id"] == str(volunteer.id)


# --- 4. review -------------------------------------------------------------------
def test_only_a_treasurer_reviews_and_never_their_own_claim(client, auth, tokens, treasurer, make_expense):
    expense = make_expense(treasurer, receipt=True)
    # Even the admin who happens to be the claimant: the point of the queue is a second pair of eyes.
    own = client.patch(
        f"/api/v1/expenses/{expense.id}/review",
        json={"decision": "approve"},
        headers=auth(tokens["treasurer"]),
    )
    assert own.status_code == 409, own.text
    assert own.json()["error"]["code"] == "SELF_REVIEW"

    assert (
        client.patch(
            f"/api/v1/expenses/{expense.id}/review",
            json={"decision": "approve"},
            headers=auth(tokens["organizer"]),
        ).status_code
        == 403
    )


def test_a_rejection_needs_a_reason(client, auth, tokens, volunteer, make_expense):
    expense = make_expense(volunteer, receipt=True)
    headers = auth(tokens["treasurer"])

    assert (
        client.patch(f"/api/v1/expenses/{expense.id}/review", json={"decision": "reject"}, headers=headers).status_code
        == 422
    )
    assert (
        client.patch(
            f"/api/v1/expenses/{expense.id}/review", json={"decision": "reject", "note": "no"}, headers=headers
        ).status_code
        == 422
    )

    rejected = client.patch(
        f"/api/v1/expenses/{expense.id}/review",
        json={"decision": "reject", "note": "Receipt is for a different amount"},
        headers=headers,
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["review_note"] == "Receipt is for a different amount"


def test_a_settled_claim_cannot_be_reviewed_twice(client, auth, tokens, volunteer, make_expense):
    expense = make_expense(volunteer, status="reimbursed", receipt=True)
    response = client.patch(
        f"/api/v1/expenses/{expense.id}/review", json={"decision": "approve"}, headers=auth(tokens["treasurer"])
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATE"


def test_two_treasurers_deciding_at_once_leave_exactly_one_decision(db, db2, treasurer, admin, volunteer, make_expense):
    """The row lock is the point: both requests read `submitted`, and the loser must be told so
    rather than overwriting the winner."""
    expense = make_expense(volunteer, receipt=True)
    expense_id = expense.id

    def decide(session, reviewer, decision):
        try:
            fresh = session.get(Expense, expense_id)
            expense_service.review_expense(session, fresh, reviewer, decision, "looked at the receipt")
            return "ok"
        except AppError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(decide, db, treasurer, "approve"),
            pool.submit(decide, db2, admin, "reject"),
        ]
        outcomes = sorted(future.result() for future in futures)

    assert outcomes == ["INVALID_STATE", "ok"], outcomes
    db.expire_all()
    assert db.get(Expense, expense_id).status in ("approved", "rejected")


# --- 5. the rejected flow --------------------------------------------------------
def test_a_rejected_claim_can_be_fixed_and_resubmitted(client, auth, tokens, db, volunteer, make_expense):
    expense = make_expense(volunteer, receipt=True)
    client.patch(
        f"/api/v1/expenses/{expense.id}/review",
        json={"decision": "reject", "note": "Wrong category, this was printing"},
        headers=auth(tokens["treasurer"]),
    )

    fixed = client.patch(
        f"/api/v1/expenses/{expense.id}",
        json={"description": "Printing the stall banners"},
        headers=auth(tokens["volunteer"]),
    )
    assert fixed.status_code == 200, fixed.text
    body = fixed.json()
    assert body["status"] == "submitted", "editing a rejected claim puts it back in the queue"
    assert body["review_note"] is None and body["reviewed_by"] is None

    actions = [row.action for row in db.scalars(select(ExpenseHistory).where(ExpenseHistory.expense_id == expense.id))]
    assert actions == ["rejected", "resubmitted"]


def test_a_new_receipt_also_resubmits_a_rejected_claim(client, auth, tokens, volunteer, make_expense):
    expense = make_expense(volunteer, receipt=True)
    client.patch(
        f"/api/v1/expenses/{expense.id}/review",
        json={"decision": "reject", "note": "Photo is unreadable"},
        headers=auth(tokens["treasurer"]),
    )
    again = client.put(
        f"/api/v1/expenses/{expense.id}/receipt",
        files={"receipt": ("clearer.pdf", pdf(), "application/pdf")},
        headers=auth(tokens["volunteer"]),
    )
    assert again.status_code == 200, again.text
    assert again.json()["status"] == "submitted"
    assert again.json()["receipt_mime"] == "application/pdf"


def test_an_approved_claim_is_locked_to_its_owner(client, auth, tokens, volunteer, make_expense):
    expense = make_expense(volunteer, status="approved", receipt=True)
    headers = auth(tokens["volunteer"])
    assert client.patch(f"/api/v1/expenses/{expense.id}", json={"amount": 999}, headers=headers).status_code == 409
    assert (
        client.put(
            f"/api/v1/expenses/{expense.id}/receipt",
            files={"receipt": ("x.png", png(), "image/png")},
            headers=headers,
        ).status_code
        == 409
    )
    assert client.delete(f"/api/v1/expenses/{expense.id}", headers=headers).status_code == 409


def test_a_withdrawn_claim_is_out_of_the_queue(client, auth, tokens, volunteer, make_expense):
    expense = make_expense(volunteer)
    response = client.delete(f"/api/v1/expenses/{expense.id}", headers=auth(tokens["volunteer"]))
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "withdrawn"

    # Withdrawing is not deleting: the treasurer can still see it, and it can no longer be approved.
    assert client.get(f"/api/v1/expenses/{expense.id}", headers=auth(tokens["treasurer"])).status_code == 200
    assert (
        client.patch(
            f"/api/v1/expenses/{expense.id}/review",
            json={"decision": "approve"},
            headers=auth(tokens["treasurer"]),
        ).status_code
        == 409
    )


# --- 6. reimbursement: the only moment money moves --------------------------------
def test_reimbursing_pays_once_and_drops_the_balance_by_exactly_the_amount(
    client, auth, tokens, db, treasurer, volunteer, make_expense
):
    fund(client, auth, tokens["treasurer"], amount=1_000_000)
    expense = make_expense(volunteer, amount=45000, status="approved", receipt=True)

    before = client.get("/api/v1/finance/summary", headers=auth(tokens["treasurer"])).json()["balance"]

    paid = client.post(
        f"/api/v1/expenses/{expense.id}/reimburse",
        json={"method": "upi", "reference": "UPI/2026/8891"},
        headers=auth(tokens["treasurer"]),
    )
    assert paid.status_code == 200, paid.text
    body = paid.json()
    assert body["status"] == "reimbursed"
    assert body["reimbursement_method"] == "upi"
    assert body["ledger_transaction_id"] is not None

    after = client.get("/api/v1/finance/summary", headers=auth(tokens["treasurer"])).json()["balance"]
    assert before - after == 45000
    assert ledger_rows(db, source="expense_reimbursement") == 1

    entry = db.get(Transaction, UUID(body["ledger_transaction_id"]))
    assert (entry.direction, entry.source, entry.ref_type, entry.ref_id) == (
        "out",
        "expense_reimbursement",
        "expense",
        expense.id,
    )
    assert entry.logged_by == treasurer.id

    # Paying twice is a replay, not a second payment.
    again = client.post(
        f"/api/v1/expenses/{expense.id}/reimburse", json={"method": "cash"}, headers=auth(tokens["treasurer"])
    )
    assert again.status_code == 200, again.text
    assert again.json()["ledger_transaction_id"] == body["ledger_transaction_id"]
    assert ledger_rows(db, source="expense_reimbursement") == 1, "one claim, one payment, one row"
    assert client.get("/api/v1/finance/summary", headers=auth(tokens["treasurer"])).json()["balance"] == after


def test_a_claim_cannot_be_reimbursed_before_it_is_approved(client, auth, tokens, volunteer, make_expense):
    expense = make_expense(volunteer, receipt=True)
    response = client.post(
        f"/api/v1/expenses/{expense.id}/reimburse", json={"method": "cash"}, headers=auth(tokens["treasurer"])
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "INVALID_STATE"


def test_the_club_cannot_pay_out_money_it_does_not_have(client, auth, tokens, admin, volunteer, make_expense):
    fund(client, auth, tokens["treasurer"], amount=100_000)
    expense = make_expense(volunteer, amount=500_000, status="approved", receipt=True)

    refused = client.post(
        f"/api/v1/expenses/{expense.id}/reimburse", json={"method": "bank_transfer"}, headers=auth(tokens["treasurer"])
    )
    assert refused.status_code == 409, refused.text
    details = refused.json()["error"]["details"]
    assert refused.json()["error"]["code"] == "INSUFFICIENT_FUNDS"
    assert (details["balance"], details["amount"]) == (100_000, 500_000)

    # Only an admin may decide to go into the red, and only on purpose.
    assert (
        client.post(
            f"/api/v1/expenses/{expense.id}/reimburse",
            json={"method": "cash", "allow_negative": True},
            headers=auth(tokens["treasurer"]),
        ).status_code
        == 403
    )
    forced = client.post(
        f"/api/v1/expenses/{expense.id}/reimburse",
        json={"method": "cash", "allow_negative": True},
        headers=auth(tokens["admin"]),
    )
    assert forced.status_code == 200, forced.text
    assert client.get("/api/v1/finance/summary", headers=auth(tokens["admin"])).json()["balance"] == -400_000


def test_nobody_pays_themselves(client, auth, tokens, treasurer, make_expense):
    fund(client, auth, tokens["treasurer"], amount=1_000_000)
    own = make_expense(treasurer, amount=1000, status="approved", receipt=True)
    response = client.post(
        f"/api/v1/expenses/{own.id}/reimburse", json={"method": "cash"}, headers=auth(tokens["treasurer"])
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "SELF_REVIEW"


def test_a_reimbursement_is_stamped_into_the_history(client, auth, tokens, treasurer, volunteer, make_expense):
    fund(client, auth, tokens["treasurer"])
    expense = make_expense(volunteer, status="approved", receipt=True)
    client.post(f"/api/v1/expenses/{expense.id}/reimburse", json={"method": "cash"}, headers=auth(tokens["treasurer"]))

    trail = client.get(f"/api/v1/expenses/{expense.id}", headers=auth(tokens["treasurer"])).json()["history"]
    assert [row["action"] for row in trail] == ["reimbursed"]
    assert trail[0]["actor"]["id"] == str(treasurer.id)


# --- 7. receipts ------------------------------------------------------------------
def test_the_receipt_comes_back_as_a_signed_url_and_never_as_a_path(client, auth, tokens, db, volunteer, make_expense):
    expense = make_expense(volunteer, receipt=True)
    path = db.get(Expense, expense.id).receipt_path

    response = client.get(f"/api/v1/expenses/{expense.id}/receipt", headers=auth(tokens["volunteer"]))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["expires_in"] == 600
    assert body["mime"] == "image/png"
    assert "url" in body and path not in body["url"]

    detail = client.get(f"/api/v1/expenses/{expense.id}", headers=auth(tokens["volunteer"]))
    assert path not in detail.text
    assert "receipt_path" not in detail.text


def test_a_claim_with_no_receipt_says_so(client, auth, tokens, volunteer, make_expense):
    expense = make_expense(volunteer, receipt=False)
    response = client.get(f"/api/v1/expenses/{expense.id}/receipt", headers=auth(tokens["volunteer"]))
    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "RECEIPT_NOT_FOUND"


def test_replacing_a_receipt_forgets_the_old_one(client, auth, tokens, db, volunteer, make_expense):
    from app.core.config import settings
    from app.services import storage

    root = Path(settings.LOCAL_STORAGE_DIR) / settings.RECEIPTS_BUCKET
    expense = make_expense(volunteer, receipt=True)
    old = db.get(Expense, expense.id).receipt_path
    storage.get_provider().put(old, png(), "image/png")
    assert (root / old).exists()

    client.put(
        f"/api/v1/expenses/{expense.id}/receipt",
        files={"receipt": ("new.pdf", pdf(), "application/pdf")},
        headers=auth(tokens["volunteer"]),
    )
    db.expire_all()
    new = db.get(Expense, expense.id).receipt_path
    assert new != old
    assert not (root / old).exists(), "the old object is gone"
    assert (root / new).exists()


# --- 8. the treasurer's queue -----------------------------------------------------
def test_the_queue_filters_and_counts(client, auth, tokens, volunteer, other_volunteer, make_expense):
    make_expense(volunteer, amount=1000, status="submitted")
    make_expense(other_volunteer, amount=2000, status="approved", receipt=True)
    make_expense(volunteer, amount=4000, status="reimbursed", receipt=True)

    body = client.get("/api/v1/expenses", headers=auth(tokens["treasurer"])).json()
    assert body["total"] == 3
    assert body["counts"] == {"submitted": 1, "approved": 1, "rejected": 0, "reimbursed": 1, "withdrawn": 0}
    assert body["submitted_amount"] == 1000
    assert body["approved_unpaid_amount"] == 2000

    by_claimant = client.get(f"/api/v1/expenses?claimant_id={volunteer.id}", headers=auth(tokens["treasurer"])).json()
    assert by_claimant["total"] == 2

    by_amount = client.get("/api/v1/expenses?min_amount=1500", headers=auth(tokens["treasurer"])).json()
    assert [row["amount"] for row in by_amount["items"]] == [4000, 2000]

    ascending = client.get("/api/v1/expenses?sort=asc", headers=auth(tokens["treasurer"])).json()
    assert [row["amount"] for row in ascending["items"]] == [1000, 2000, 4000]
