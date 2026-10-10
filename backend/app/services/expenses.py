"""Volunteer expense claims: submit, review, reimburse (PRD FR-6.1, DESIGN.md §4 rule 14).

The shape of the problem is that money has already left somebody's pocket, and the books have to
record it exactly once, later, with a receipt attached. So the claim moves through a small state
machine and every move is written to `expense_history`:

    submitted ──approve──> approved ──reimburse──> reimbursed
        │  ▲                  │
        │  └───resubmit───┐   └──reject──> rejected ──edit/resubmit──> submitted
        └──withdraw──> withdrawn

Two rules are worth stating out loud because they are the ones that keep the ledger honest:

* `reimburse_expense` is the ONLY thing that moves money, and it does so through
  `ledger.add_transaction` inside one transaction that also stamps the claim. So there is no
  window where a claim says "reimbursed" and the ledger disagrees — and calling it twice writes
  exactly one row, because the second call sees `reimbursed` and returns what the first one did.
* A receipt is optional to submit and mandatory to approve. Volunteers claim from a bus queue and
  photograph the bill later; a treasurer signs off only against something they can look at.
"""

import contextlib
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.authz import has_permission
from app.core.config import settings
from app.core.errors import AppError
from app.models import EXPENSE_CATEGORIES, Event, Expense, ExpenseHistory, Fundraiser, User
from app.services import fundraisers as fundraiser_service
from app.services import ledger, storage

MIN_AMOUNT = 1
MAX_AMOUNT = 5_000_000  # paise: ₹50,000, a ceiling a student club's single claim should never hit
MIN_DESCRIPTION = 5
MAX_DESCRIPTION = 300
MIN_REVIEW_NOTE = 5

EDITABLE_FIELDS = ("amount", "description", "category", "incurred_on", "event_id", "fundraiser_id")
OPEN_STATUSES = ("submitted", "rejected")


def is_treasurer(db: Session, actor: User) -> bool:
    return has_permission(db, actor, "expenses.view_all")


def get_expense(db: Session, expense_id: UUID) -> Expense:
    expense = db.get(Expense, expense_id)
    if expense is None:
        raise AppError(404, "EXPENSE_NOT_FOUND", "No expense claim with that id", {"expense_id": str(expense_id)})
    return expense


def assert_can_view(db: Session, expense: Expense, actor: User) -> None:
    """Your own claims, or all of them if you keep the books. An organizer running an event is not
    entitled to read what a volunteer spent out of their own pocket."""
    if expense.claimant_id != actor.id and not is_treasurer(db, actor):
        raise AppError(403, "FORBIDDEN", "This claim belongs to someone else", {"expense_id": str(expense.id)})


def assert_owner(expense: Expense, actor: User) -> None:
    if expense.claimant_id != actor.id:
        raise AppError(403, "FORBIDDEN", "Only the claimant can change this claim", {"expense_id": str(expense.id)})


def _assert_open(expense: Expense, *, action: str) -> None:
    if expense.status not in OPEN_STATUSES:
        raise AppError(
            409,
            "INVALID_STATE",
            f"A {expense.status} claim cannot be {action}",
            {"status": expense.status, "expected": list(OPEN_STATUSES)},
        )


def _lock(db: Session, expense_id: UUID) -> Expense:
    """Row lock for the two decisions that move a claim forward. Both flags are load-bearing:

    * `of=Expense` keeps FOR UPDATE off the eager-loaded outer joins, which Postgres refuses to lock;
    * `populate_existing` refreshes the row we just locked. Without it the caller's stale copy of
      `status` survives the lock, and two simultaneous decisions both act on `submitted`.
    """
    return db.scalar(
        select(Expense)
        .where(Expense.id == expense_id)
        .with_for_update(of=Expense)
        .execution_options(populate_existing=True)
    )


# --- validation -------------------------------------------------------------------------------


def _clean_amount(value) -> int:
    try:
        amount = int(value)
    except (TypeError, ValueError):
        raise AppError(
            422, "VALIDATION_ERROR", "amount must be an integer number of paise", {"amount": value}
        ) from None
    if not MIN_AMOUNT <= amount <= MAX_AMOUNT:
        raise AppError(
            422,
            "VALIDATION_ERROR",
            f"amount must be between {MIN_AMOUNT} and {MAX_AMOUNT} paise",
            {"amount": amount, "max_amount": MAX_AMOUNT},
        )
    return amount


def _clean_description(value) -> str:
    text = (value or "").strip()
    if not MIN_DESCRIPTION <= len(text) <= MAX_DESCRIPTION:
        raise AppError(
            422,
            "VALIDATION_ERROR",
            f"description must be {MIN_DESCRIPTION}-{MAX_DESCRIPTION} characters",
            {"length": len(text)},
        )
    return text


def _clean_incurred_on(value) -> date:
    if isinstance(value, datetime):
        value = value.date()
    if not isinstance(value, date):
        raise AppError(422, "VALIDATION_ERROR", "incurred_on must be a date", {"incurred_on": str(value)})
    today = datetime.now(UTC).date()
    if value > today:
        raise AppError(
            422, "INVALID_INCURRED_ON", "A claim cannot be dated in the future", {"incurred_on": value.isoformat()}
        )
    if value < today - timedelta(days=settings.EXPENSE_BACKDATE_DAYS):
        raise AppError(
            422,
            "INVALID_INCURRED_ON",
            f"A claim can be dated at most {settings.EXPENSE_BACKDATE_DAYS} days back",
            {"incurred_on": value.isoformat(), "max_days": settings.EXPENSE_BACKDATE_DAYS},
        )
    return value


def _clean_bucket(db: Session, data: dict) -> tuple[UUID | None, UUID | None]:
    """At most one of event / fundraiser, and whichever is given must exist."""
    event_id, fundraiser_id = data.get("event_id"), data.get("fundraiser_id")
    if event_id is not None and fundraiser_id is not None:
        raise AppError(422, "VALIDATION_ERROR", "A claim is charged to an event or a fundraiser, not both", {})
    if event_id is not None and db.get(Event, event_id) is None:
        raise AppError(404, "EVENT_NOT_FOUND", "No event with that id", {"event_id": str(event_id)})
    if fundraiser_id is not None and db.get(Fundraiser, fundraiser_id) is None:
        raise AppError(404, "FUNDRAISER_NOT_FOUND", "No fundraiser with that id", {"fundraiser_id": str(fundraiser_id)})
    return event_id, fundraiser_id


def _clean_category(value) -> str:
    if value not in EXPENSE_CATEGORIES:
        raise AppError(
            422,
            "VALIDATION_ERROR",
            "Unknown expense category",
            {"category": value, "allowed": list(EXPENSE_CATEGORIES)},
        )
    return value


# --- history ----------------------------------------------------------------------------------


def _log(db: Session, expense: Expense, actor: User | None, action: str, note: str | None = None) -> None:
    db.add(ExpenseHistory(expense_id=expense.id, actor_id=actor.id if actor else None, action=action, note=note))


def history_view(row: ExpenseHistory) -> dict:
    return {
        "id": row.id,
        "action": row.action,
        "note": row.note,
        "actor": fundraiser_service.person_ref(row.actor),
        "created_at": row.created_at,
    }


def history(db: Session, expense_id: UUID) -> list[ExpenseHistory]:
    return list(
        db.scalars(
            select(ExpenseHistory)
            .where(ExpenseHistory.expense_id == expense_id)
            .order_by(ExpenseHistory.created_at, ExpenseHistory.id)
        )
    )


# --- views ------------------------------------------------------------------------------------


def expense_view(expense: Expense, *, actor: User | None = None) -> dict:
    """`receipt_path` is not in here on purpose. The only way to see a receipt is
    `GET /expenses/{id}/receipt`, which mints a short-lived signed URL."""
    return {
        "id": expense.id,
        "claimant": fundraiser_service.person_ref(expense.claimant),
        "amount": expense.amount,
        "description": expense.description,
        "category": expense.category,
        "incurred_on": expense.incurred_on,
        "event_id": expense.event_id,
        "fundraiser_id": expense.fundraiser_id,
        "fundraiser": (
            {"id": expense.fundraiser.id, "title": expense.fundraiser.title} if expense.fundraiser else None
        ),
        "status": expense.status,
        "has_receipt": expense.receipt_path is not None,
        "receipt_mime": expense.receipt_mime,
        "receipt_size": expense.receipt_size,
        "reviewed_by": fundraiser_service.person_ref(expense.reviewer),
        "reviewed_at": expense.reviewed_at,
        "review_note": expense.review_note,
        "reimbursed_by": None if expense.reimbursed_by is None else str(expense.reimbursed_by),
        "reimbursed_at": expense.reimbursed_at,
        "reimbursement_method": expense.reimbursement_method,
        "reimbursement_reference": expense.reimbursement_reference,
        "ledger_transaction_id": expense.ledger_transaction_id,
        "created_at": expense.created_at,
        "updated_at": expense.updated_at,
    }


# --- reads ------------------------------------------------------------------------------------


def expense_conditions(
    *,
    claimant_id: UUID | None = None,
    status: str | None = None,
    category: str | None = None,
    event_id: UUID | None = None,
    fundraiser_id: UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    q: str | None = None,
    min_amount: int | None = None,
    max_amount: int | None = None,
) -> list:
    conditions = []
    if claimant_id is not None:
        conditions.append(Expense.claimant_id == claimant_id)
    if status:
        conditions.append(Expense.status == status)
    if category:
        conditions.append(Expense.category == category)
    if event_id is not None:
        conditions.append(Expense.event_id == event_id)
    if fundraiser_id is not None:
        conditions.append(Expense.fundraiser_id == fundraiser_id)
    if date_from is not None:
        conditions.append(Expense.incurred_on >= date_from)
    if date_to is not None:
        conditions.append(Expense.incurred_on <= date_to)
    if min_amount is not None:
        conditions.append(Expense.amount >= min_amount)
    if max_amount is not None:
        conditions.append(Expense.amount <= max_amount)
    if q:
        like = f"%{q}%"
        conditions.append(or_(Expense.description.ilike(like), Expense.category.ilike(like)))
    return conditions


def list_expenses(
    db: Session, *, sort: str = "desc", page: int = 1, page_size: int = 20, **filters
) -> tuple[list[Expense], int]:
    conditions = expense_conditions(**filters)
    order = (
        (Expense.created_at.asc(), Expense.id.asc())
        if sort == "asc"
        else (Expense.created_at.desc(), Expense.id.desc())
    )
    total = db.scalar(select(func.count()).select_from(Expense).where(*conditions)) or 0
    rows = db.scalars(
        select(Expense).where(*conditions).order_by(*order).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return list(rows), total


def status_counts(db: Session, *extra) -> dict:
    """`{submitted, approved, rejected, reimbursed, withdrawn}` plus the money still in flight.
    One grouped query, so the treasurer's queue header does not cost five round trips."""
    rows = db.execute(
        select(Expense.status, func.count(), func.coalesce(func.sum(Expense.amount), 0))
        .where(*extra)
        .group_by(Expense.status)
    ).all()
    counts = dict.fromkeys(("submitted", "approved", "rejected", "reimbursed", "withdrawn"), 0)
    amounts = dict.fromkeys(counts, 0)
    for status, count, amount in rows:
        counts[status] = int(count)
        amounts[status] = int(amount)
    return {
        "counts": counts,
        "submitted_amount": amounts["submitted"],
        "approved_unpaid_amount": amounts["approved"],
    }


# --- writes -----------------------------------------------------------------------------------


def _store_receipt(expense: Expense, blob: tuple[bytes, str]) -> str:
    """Validates, then writes to the bucket. Returns the path so the caller can clean up if the
    database write later fails. The client's filename never reaches the path."""
    data, mime = blob
    storage.validate_receipt(data, mime)
    path = storage.receipt_path(expense.claimant_id, expense.id, mime)
    storage.get_provider().put(path, data, mime)
    expense.receipt_path = path
    expense.receipt_mime = mime
    expense.receipt_size = len(data)
    return path


def _discard(path: str | None) -> None:
    """Best effort: a stranded object costs a fraction of a paisa, a failed request costs a
    volunteer their claim. Never let cleanup raise over the original error."""
    if not path:
        return
    with contextlib.suppress(Exception):
        storage.get_provider().delete(path)


def create_expense(db: Session, data: dict, actor: User, blob: tuple[bytes, str] | None = None) -> Expense:
    amount = _clean_amount(data.get("amount"))
    description = _clean_description(data.get("description"))
    category = _clean_category(data.get("category", "other"))
    incurred_on = _clean_incurred_on(data.get("incurred_on"))
    event_id, fundraiser_id = _clean_bucket(db, data)

    expense = Expense(
        claimant_id=actor.id,
        amount=amount,
        description=description,
        category=category,
        incurred_on=incurred_on,
        event_id=event_id,
        fundraiser_id=fundraiser_id,
        status="submitted",
    )
    db.add(expense)
    db.flush()  # the id is part of the receipt path

    stored: str | None = None
    try:
        if blob is not None:
            stored = _store_receipt(expense, blob)
        _log(db, expense, actor, "submitted", description)
        if stored:
            _log(db, expense, actor, "receipt_attached")
        db.commit()
    except Exception:
        db.rollback()
        _discard(stored)  # the row is gone, so the object must go with it
        raise
    db.refresh(expense)
    return expense


def update_expense(db: Session, expense: Expense, data: dict, actor: User) -> Expense:
    assert_owner(expense, actor)
    _assert_open(expense, action="edited")

    changed = [key for key in EDITABLE_FIELDS if key in data and getattr(expense, key) != data[key]]
    if "amount" in data:
        data = {**data, "amount": _clean_amount(data["amount"])}
    if "description" in data:
        data = {**data, "description": _clean_description(data["description"])}
    if "category" in data:
        data = {**data, "category": _clean_category(data["category"])}
    if "incurred_on" in data:
        data = {**data, "incurred_on": _clean_incurred_on(data["incurred_on"])}
    if "event_id" in data or "fundraiser_id" in data:
        merged = {
            **{key: getattr(expense, key) for key in ("event_id", "fundraiser_id")},
            **{k: v for k, v in data.items() if k in ("event_id", "fundraiser_id")},
        }
        event_id, fundraiser_id = _clean_bucket(db, merged)
        data = {**data, "event_id": event_id, "fundraiser_id": fundraiser_id}

    for key in EDITABLE_FIELDS:
        if key in data:
            setattr(expense, key, data[key])

    was_rejected = expense.status == "rejected"
    if was_rejected:
        # A rejected claim that comes back is a new decision to make: the old verdict goes away.
        expense.status = "submitted"
        expense.reviewed_by = expense.reviewed_at = expense.review_note = None
        _log(db, expense, actor, "resubmitted", ", ".join(changed) or None)
    else:
        _log(db, expense, actor, "edited", ", ".join(changed) or None)

    db.commit()
    db.refresh(expense)
    return expense


def replace_receipt(db: Session, expense: Expense, blob: tuple[bytes, str], actor: User) -> Expense:
    assert_owner(expense, actor)
    _assert_open(expense, action="given a new receipt")

    previous = expense.receipt_path
    stored: str | None = None
    was_rejected = expense.status == "rejected"
    try:
        stored = _store_receipt(expense, blob)
        if was_rejected:
            expense.status = "submitted"
            expense.reviewed_by = expense.reviewed_at = expense.review_note = None
            _log(db, expense, actor, "resubmitted", "receipt replaced")
        else:
            _log(db, expense, actor, "receipt_attached")
        db.commit()
    except Exception:
        db.rollback()
        _discard(stored)
        raise
    # Only once the new object is safely referenced do we drop the old one.
    if previous and previous != expense.receipt_path:
        _discard(previous)
    db.refresh(expense)
    return expense


def withdraw_expense(db: Session, expense: Expense, actor: User) -> Expense:
    assert_owner(expense, actor)
    if expense.status != "submitted":
        raise AppError(
            409, "INVALID_STATE", "Only a claim that is still submitted can be withdrawn", {"status": expense.status}
        )
    expense.status = "withdrawn"
    _log(db, expense, actor, "withdrawn", expense.review_note)
    db.commit()
    db.refresh(expense)
    return expense


def review_expense(db: Session, expense: Expense, reviewer: User, decision: str, note: str | None = None) -> Expense:
    """Treasurer and above. Nobody reviews their own claim, treasurer or admin - the whole point of
    the queue is that a second pair of eyes looked at the receipt."""
    if expense.claimant_id == reviewer.id:
        raise AppError(409, "SELF_REVIEW", "You cannot review your own claim", {"expense_id": str(expense.id)})

    note = (note or "").strip() or None
    if decision == "reject" and (note is None or len(note) < MIN_REVIEW_NOTE):
        raise AppError(
            422, "VALIDATION_ERROR", f"A rejection needs a note of at least {MIN_REVIEW_NOTE} characters", {}
        )

    # Lock first: two treasurers clicking at once must not both see `submitted`.
    expense = _lock(db, expense.id)
    if expense.status != "submitted":
        raise AppError(
            409, "INVALID_STATE", f"A {expense.status} claim is not waiting for a decision", {"status": expense.status}
        )
    if decision == "approve" and expense.receipt_path is None:
        raise AppError(
            409, "RECEIPT_REQUIRED", "Attach a receipt before approving this claim", {"expense_id": str(expense.id)}
        )

    expense.status = "approved" if decision == "approve" else "rejected"
    expense.reviewed_by = reviewer.id
    expense.reviewed_at = datetime.now(UTC)
    expense.review_note = note
    _log(db, expense, reviewer, expense.status, note)
    db.commit()
    db.refresh(expense)
    return expense


def reimburse_expense(
    db: Session,
    expense: Expense,
    treasurer: User,
    method: str,
    reference: str | None = None,
    allow_negative: bool = False,
) -> tuple[Expense, bool]:
    """Pays an approved claim out of the club's balance and writes the matching ledger row.

    Returns `(expense, created)`: `created` is False when the claim was already reimbursed, in
    which case this is a replay and nothing new was written.
    """
    if expense.claimant_id == treasurer.id:
        raise AppError(409, "SELF_REVIEW", "You cannot reimburse your own claim", {"expense_id": str(expense.id)})
    if allow_negative and not has_permission(db, treasurer, "finance.allow_negative"):
        raise AppError(403, "FORBIDDEN", "Only an admin can push the balance negative", {"your_role": treasurer.role})

    expense = _lock(db, expense.id)
    if expense.status == "reimbursed":
        return expense, False  # a replay: the row and the ledger entry already exist
    if expense.status != "approved":
        raise AppError(
            409, "INVALID_STATE", f"A {expense.status} claim cannot be reimbursed", {"status": expense.status}
        )

    balance = ledger.totals(db)["balance"]
    if not allow_negative and balance - expense.amount < 0:
        raise AppError(
            409,
            "INSUFFICIENT_FUNDS",
            "The club does not have enough on hand to reimburse this claim",
            {"balance": balance, "amount": expense.amount},
        )

    entry = ledger.add_transaction(
        db,
        direction="out",
        amount=expense.amount,
        source="expense_reimbursement",
        ref_type="expense",
        ref_id=expense.id,
        event_id=expense.event_id,
        fundraiser_id=expense.fundraiser_id,
        note=expense.description,
        created_by=treasurer.id,
    )
    db.flush()  # the ledger id is part of the claim from here on

    expense.status = "reimbursed"
    expense.reimbursed_by = treasurer.id
    expense.reimbursed_at = datetime.now(UTC)
    expense.reimbursement_method = method
    expense.reimbursement_reference = reference
    expense.ledger_transaction_id = entry.id
    _log(db, expense, treasurer, "reimbursed", f"{method}" + (f" - {reference}" if reference else ""))
    db.commit()
    db.refresh(expense)
    return expense, True


def receipt_url(expense: Expense) -> dict:
    if expense.receipt_path is None:
        raise AppError(404, "RECEIPT_NOT_FOUND", "This claim has no receipt", {"expense_id": str(expense.id)})
    return {
        "url": storage.signed_receipt_url(expense.receipt_path),
        "expires_in": settings.RECEIPT_URL_TTL_SECONDS,
        "mime": expense.receipt_mime,
        "size": expense.receipt_size,
    }
