"""The treasurer's side of the books: dashboards, manual entries, reversals, reconciliation,
reports and closed periods (PRD FR-6.2, DESIGN.md §4 rule 14).

Every number in this module comes from `services/ledger.py`'s signed expressions. Nothing here
adds up money of its own, which is the only reason the dashboard, the fundraiser pages and the
semester report can be trusted to tell the same story.

Reconciliation is the load-bearing idea. `reconcile()` recomputes each revenue stream from the
table that *caused* it (orders, claims) and compares that to what the ledger says, so a bug or a
half-finished transaction shows up as a difference instead of as a quietly wrong balance. Periods
then build on it: you cannot close a book that does not reconcile, and once closed the ledger
refuses anything dated inside it.
"""

from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import as_utc
from app.core.deps import ROLE_RANK
from app.core.errors import AppError
from app.models import Event, Expense, FinancePeriod, Fundraiser, Order, Transaction, User
from app.services import fundraisers as fundraiser_service
from app.services import ledger

MANUAL_SOURCES = ("other_income", "other_expense")
MIN_NOTE = 5
MAX_MANUAL_BACKDATE_DAYS = 60
MIN_REOPEN_REASON = 10
TOP_EXPENSES = 5

SOURCE_LABELS = {
    "dues": "Membership dues",
    "tickets": "Ticket sale",
    "merch": "Merch sale",
    "fundraiser": "Fundraiser income",
    "other_income": "Other income",
    "other_expense": "Other expense",
    "expense_reimbursement": "Expense reimbursement",
}

# The streams `reconcile()` can recompute from their source table. `fundraiser`, `other_income` and
# `other_expense` rows have no other table to check against - a hand-logged row IS the source - so
# they are covered by the amount and linkage checks instead.
SOURCE_TABLE_CHECKS = {
    "dues": "Membership dues",
    "tickets": "Ticket sales",
    "merch": "Merch sales",
    "expense_reimbursement": "Expense reimbursements",
}


def is_treasurer(actor: User) -> bool:
    return ROLE_RANK.get(actor.role, 0) >= ROLE_RANK["treasurer"]


def _range(date_from: date | None, date_to: date | None) -> list:
    conditions = []
    if date_from is not None:
        conditions.append(Transaction.occurred_at >= datetime.combine(date_from, time.min, tzinfo=UTC))
    if date_to is not None:
        # Inclusive of the whole end day: a report "to the 30th" must include the 30th.
        conditions.append(Transaction.occurred_at < datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=UTC))
    return conditions


def _totals_in_range(db: Session, date_from: date | None, date_to: date | None) -> dict[str, int]:
    return ledger.totals(db, *_range(date_from, date_to))


# --- labels -----------------------------------------------------------------------------------


def transaction_label(entry: Transaction, event_title: str | None = None, fundraiser_title: str | None = None) -> str:
    """A human line for the ledger table: the row's own note when it has one (every writer sets
    one), otherwise the source's name plus whatever the row is attached to."""
    where = event_title or fundraiser_title
    base = entry.note or SOURCE_LABELS.get(entry.source, entry.source)
    label = f"{base} - {where}" if where and where not in base else base
    return f"Reversal: {label}" if entry.is_reversal else label


def transaction_view(
    entry: Transaction,
    *,
    event_title: str | None = None,
    fundraiser_title: str | None = None,
    actor: User | None = None,
    running_balance: int | None = None,
) -> dict:
    amount = entry.amount if entry.direction == "in" else -entry.amount
    return {
        "id": entry.id,
        "occurred_at": entry.occurred_at,
        "direction": entry.direction,
        "amount": entry.amount,
        "signed_amount": amount,
        "source": entry.source,
        "label": transaction_label(entry, event_title, fundraiser_title),
        "note": entry.note,
        "ref_type": entry.ref_type,
        "ref_id": entry.ref_id,
        "event_id": entry.event_id,
        "event_title": event_title,
        "fundraiser_id": entry.fundraiser_id,
        "fundraiser_title": fundraiser_title,
        "actor": fundraiser_service.person_ref(actor),
        "is_reversal": entry.is_reversal,
        "reverses_id": entry.reverses_id,
        "running_balance": running_balance,
        "created_at": entry.created_at,
    }


# --- summary ----------------------------------------------------------------------------------


def _by_source(db: Session, conditions: list) -> list[dict]:
    rows = db.execute(
        select(
            Transaction.source,
            ledger.total_in_expr().label("total_in"),
            ledger.total_out_expr().label("total_out"),
        )
        .where(*conditions)
        .group_by(Transaction.source)
        .order_by(Transaction.source)
    ).all()
    return [
        {"source": source, "in": int(total_in), "out": int(total_out), "net": int(total_in) - int(total_out)}
        for source, total_in, total_out in rows
        if total_in or total_out
    ]


def spend_by_category(db: Session, date_from: date | None = None, date_to: date | None = None) -> list[dict]:
    """Money actually paid out, by category, over claims REIMBURSED in the window.

    Cash accounting on purpose: the ledger records the reimbursement on the day the money left, so
    an expense incurred in March but paid in April belongs to April's report. Matching the ledger's
    own `occurred_at` is what keeps this table and `total_out` describing the same rupees.
    """
    conditions = [Expense.status == "reimbursed"]
    if date_from is not None:
        conditions.append(Expense.reimbursed_at >= datetime.combine(date_from, time.min, tzinfo=UTC))
    if date_to is not None:
        conditions.append(Expense.reimbursed_at < datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=UTC))
    rows = db.execute(
        select(Expense.category, func.coalesce(func.sum(Expense.amount), 0))
        .where(*conditions)
        .group_by(Expense.category)
        .order_by(Expense.category)
    ).all()
    return [{"category": category, "amount": int(amount)} for category, amount in rows]


def pending_reimbursements(db: Session) -> dict:
    """What is owed right now. Deliberately not date-filtered: a claim from last semester that
    nobody has paid is still money the club owes today."""
    rows = db.execute(
        select(Expense.status, func.count(), func.coalesce(func.sum(Expense.amount), 0))
        .where(Expense.status.in_(("submitted", "approved")))
        .group_by(Expense.status)
    ).all()
    totals = {status: (int(count), int(amount)) for status, count, amount in rows}
    submitted = totals.get("submitted", (0, 0))
    approved = totals.get("approved", (0, 0))
    return {
        "submitted_count": submitted[0],
        "submitted_amount": submitted[1],
        "approved_unpaid_count": approved[0],
        "approved_unpaid_amount": approved[1],
    }


def _by_month(db: Session, conditions: list) -> list[dict]:
    # Postgres date_trunc; dev SQLite would need strftime, and reports are a Postgres-only feature.
    month = func.date_trunc("month", Transaction.occurred_at)
    rows = db.execute(
        select(
            month.label("month"), ledger.total_in_expr().label("total_in"), ledger.total_out_expr().label("total_out")
        )
        .where(*conditions)
        .group_by(month)
        .order_by(month)
    ).all()
    return [
        {"month": as_utc(when).strftime("%Y-%m"), "in": int(total_in), "out": int(total_out)}
        for when, total_in, total_out in rows
    ]


def summary(db: Session, date_from: date | None = None, date_to: date | None = None) -> dict:
    conditions = _range(date_from, date_to)
    money = ledger.totals(db, *conditions)
    reimbursed = db.scalar(select(func.count()).select_from(Expense).where(Expense.status == "reimbursed")) or 0
    return {
        "date_from": date_from,
        "date_to": date_to,
        **money,
        "by_source": _by_source(db, conditions),
        "by_category": spend_by_category(db, date_from, date_to),
        "pending_reimbursements": pending_reimbursements(db),
        "by_month": _by_month(db, conditions),
        "counts": {
            "transactions": db.scalar(select(func.count()).select_from(Transaction).where(*conditions)) or 0,
            "expenses_reimbursed": int(reimbursed),
        },
    }


# --- transactions -----------------------------------------------------------------------------


def _transaction_conditions(
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    source: str | None = None,
    direction: str | None = None,
    event_id: UUID | None = None,
    fundraiser_id: UUID | None = None,
    q: str | None = None,
    is_reversal: bool | None = None,
) -> list:
    conditions = _range(date_from, date_to)
    if source:
        conditions.append(Transaction.source == source)
    if direction:
        conditions.append(Transaction.direction == direction)
    if event_id is not None:
        conditions.append(Transaction.event_id == event_id)
    if fundraiser_id is not None:
        conditions.append(Transaction.fundraiser_id == fundraiser_id)
    if is_reversal is not None:
        conditions.append(Transaction.is_reversal.is_(is_reversal))
    if q:
        conditions.append(Transaction.note.ilike(f"%{q}%"))
    return conditions


def list_transactions(
    db: Session, *, sort: str = "desc", page: int = 1, page_size: int = 20, **filters
) -> tuple[list[dict], int]:
    """The ledger table. Titles and the actor come from joins, so a page is one query, not 3N.

    `running_balance` is only filled when sorting oldest-first, and it is deliberately computed in
    a subquery that is NOT filtered: a running total over a filtered subset would answer a question
    nobody asked. shortcut: the window scans the whole ledger; fine at club scale (thousands of rows).
    """
    conditions = _transaction_conditions(**filters)
    total = db.scalar(select(func.count()).select_from(Transaction).where(*conditions)) or 0

    order = (
        (Transaction.occurred_at.asc(), Transaction.id.asc())
        if sort == "asc"
        else (Transaction.occurred_at.desc(), Transaction.id.desc())
    )

    statement = (
        select(Transaction, Event.title, Fundraiser.title, User)
        .outerjoin(Event, Transaction.event_id == Event.id)
        .outerjoin(Fundraiser, Transaction.fundraiser_id == Fundraiser.id)
        .outerjoin(User, Transaction.logged_by == User.id)
    )
    if sort == "asc":
        window = select(
            Transaction.id.label("id"),
            func.sum(ledger.signed_amount_expr())
            .over(order_by=(Transaction.occurred_at, Transaction.id))
            .label("running_balance"),
        ).subquery()
        statement = statement.add_columns(window.c.running_balance).outerjoin(window, window.c.id == Transaction.id)

    rows = db.execute(
        statement.where(*conditions).order_by(*order).offset((page - 1) * page_size).limit(page_size)
    ).all()

    items = []
    for row in rows:
        entry, event_title, fundraiser_title, actor = row[0], row[1], row[2], row[3]
        running = int(row[4]) if sort == "asc" and row[4] is not None else None
        items.append(
            transaction_view(
                entry, event_title=event_title, fundraiser_title=fundraiser_title, actor=actor, running_balance=running
            )
        )
    return items, total


def _grouped_money(db: Session, *, by: str, date_from: date | None, date_to: date | None) -> list[dict]:
    """One grouped query per dimension — no per-row lookups (DESIGN.md §4 rule 14)."""
    conditions = _range(date_from, date_to)
    if by == "event":
        key, title, join = Transaction.event_id, Event.title, (Event, Transaction.event_id == Event.id)
    else:
        key, title, join = (
            Transaction.fundraiser_id,
            Fundraiser.title,
            (Fundraiser, Transaction.fundraiser_id == Fundraiser.id),
        )
    rows = db.execute(
        select(key, title, ledger.total_in_expr().label("total_in"), ledger.total_out_expr().label("total_out"))
        .join(join[0], join[1])
        .where(*conditions)
        .group_by(key, title)
        .order_by(title)
    ).all()
    return [
        {
            "id": row_id,
            "title": row_title,
            "total_in": int(total_in),
            "total_out": int(total_out),
            "net": int(total_in) - int(total_out),
        }
        for row_id, row_title, total_in, total_out in rows
    ]


def by_event(db: Session, date_from: date | None = None, date_to: date | None = None) -> list[dict]:
    return _grouped_money(db, by="event", date_from=date_from, date_to=date_to)


def by_fundraiser(db: Session, date_from: date | None = None, date_to: date | None = None) -> list[dict]:
    """Same shape, plus the goal, so the progress bar and the finance table agree."""
    rows = _grouped_money(db, by="fundraiser", date_from=date_from, date_to=date_to)
    goals = dict(db.execute(select(Fundraiser.id, Fundraiser.goal_amount)).all())
    for row in rows:
        row["goal_amount"] = int(goals.get(row["id"], 0))
    return rows


def outstanding_reimbursements(db: Session) -> list[dict]:
    """Who is waiting to be paid, oldest claim first — the answer to "who do I owe?"."""
    rows = db.execute(
        select(
            User,
            func.coalesce(func.sum(Expense.amount).filter(Expense.status == "submitted"), 0),
            func.coalesce(func.sum(Expense.amount).filter(Expense.status == "approved"), 0),
            func.min(Expense.incurred_on).filter(Expense.status.in_(("submitted", "approved"))),
        )
        .join(User, Expense.claimant_id == User.id)
        .where(Expense.status.in_(("submitted", "approved")))
        .group_by(User.id)
        .order_by(func.min(Expense.incurred_on))
    ).all()
    return [
        {
            "user": fundraiser_service.person_ref(user),
            "submitted_amount": int(submitted),
            "approved_unpaid_amount": int(approved),
            "oldest_pending_date": oldest,
        }
        for user, submitted, approved, oldest in rows
    ]


# --- writes -----------------------------------------------------------------------------------


def _idempotent_manual(db: Session, key: str | None) -> Transaction | None:
    if not key:
        return None
    return db.scalar(
        select(Transaction).where(
            Transaction.idempotency_key == key,
            Transaction.source.in_(MANUAL_SOURCES),
            Transaction.ref_type == "manual",
        )
    )


def manual_entry(db: Session, actor: User, data: dict, idempotency_key: str | None = None) -> tuple[Transaction, bool]:
    """A treasurer writing a row that no other table caused: a cash sponsorship, a banner bill.

    Returns `(entry, created)`. `created` is False when the Idempotency-Key had already been used,
    in which case the original row comes back untouched. The lookup is what makes a retry safe; the
    partial unique index `uq_transactions_manual_idem` is what makes two simultaneous retries safe.
    """
    source = data.get("source")
    if source not in MANUAL_SOURCES:
        raise AppError(
            422,
            "VALIDATION_ERROR",
            "A manual entry is other_income or other_expense",
            {"source": source, "allowed": list(MANUAL_SOURCES)},
        )
    direction = "in" if source == "other_income" else "out"

    note = (data.get("note") or "").strip()
    if len(note) < MIN_NOTE:
        raise AppError(422, "VALIDATION_ERROR", f"note must be at least {MIN_NOTE} characters", {})

    try:
        amount = int(data.get("amount"))
    except (TypeError, ValueError):
        raise AppError(
            422, "VALIDATION_ERROR", "amount must be an integer number of paise", {"amount": data.get("amount")}
        ) from None
    if amount <= 0:
        raise AppError(422, "VALIDATION_ERROR", "amount must be greater than zero", {"amount": amount})

    for key, model, code in (
        ("event_id", Event, "EVENT_NOT_FOUND"),
        ("fundraiser_id", Fundraiser, "FUNDRAISER_NOT_FOUND"),
    ):
        if data.get(key) is not None and db.get(model, data[key]) is None:
            raise AppError(404, code, f"No {model.__name__.lower()} with that id", {key: str(data[key])})

    occurred_at = None
    if data.get("occurred_at") is not None:
        occurred_at = as_utc(data["occurred_at"])
        now = datetime.now(UTC)
        if occurred_at > now:
            raise AppError(
                422,
                "INVALID_OCCURRED_AT",
                "A ledger row cannot be dated in the future",
                {"occurred_at": occurred_at.isoformat()},
            )
        if occurred_at < now - timedelta(days=MAX_MANUAL_BACKDATE_DAYS):
            raise AppError(
                422,
                "INVALID_OCCURRED_AT",
                f"A manual entry can be backdated at most {MAX_MANUAL_BACKDATE_DAYS} days",
                {"occurred_at": occurred_at.isoformat(), "max_days": MAX_MANUAL_BACKDATE_DAYS},
            )

    replayed = _idempotent_manual(db, idempotency_key)
    if replayed is not None:
        return replayed, False

    if data.get("allow_negative") and ROLE_RANK.get(actor.role, 0) < ROLE_RANK["admin"]:
        raise AppError(403, "FORBIDDEN", "Only an admin can push the balance negative", {"your_role": actor.role})

    if source == "other_expense" and not data.get("allow_negative"):
        balance = ledger.totals(db)["balance"]
        if balance - amount < 0:
            raise AppError(
                409,
                "INSUFFICIENT_FUNDS",
                "The club does not have enough on hand for this payment",
                {"balance": balance, "amount": amount},
            )

    entry = ledger.add_transaction(
        db,
        direction=direction,
        amount=amount,
        source=source,
        ref_type="manual",
        note=note,
        event_id=data.get("event_id"),
        fundraiser_id=data.get("fundraiser_id"),
        created_by=actor.id,
        occurred_at=occurred_at,
    )
    entry.idempotency_key = idempotency_key
    try:
        db.commit()
    except Exception:
        # The partial unique index rejected a racing duplicate: hand back the winner's row.
        db.rollback()
        existing = _idempotent_manual(db, idempotency_key)
        if existing is not None:
            return existing, False
        raise
    db.refresh(entry)
    return entry, True


def reverse_transaction(db: Session, actor: User, transaction_id: UUID, reason: str) -> Transaction:
    """Undoes a hand-logged row by writing its mirror image.

    Only the three sources a person typed by hand can be reversed. Dues, tickets and merch are
    undone by refunding the order; flipping their ledger row would leave the order saying "paid"
    and the ledger saying otherwise.
    """
    entry = db.get(Transaction, transaction_id)
    if entry is None:
        raise AppError(
            404, "TRANSACTION_NOT_FOUND", "No ledger row with that id", {"transaction_id": str(transaction_id)}
        )

    reason = (reason or "").strip()
    if len(reason) < MIN_NOTE:
        raise AppError(422, "VALIDATION_ERROR", f"reason must be at least {MIN_NOTE} characters", {})

    if entry.is_reversal:
        raise AppError(409, "NOT_REVERSIBLE", "A reversal cannot itself be reversed", {"transaction_id": str(entry.id)})
    if entry.source not in ledger.REVERSIBLE_SOURCES:
        raise AppError(
            409,
            "NOT_REVERSIBLE",
            f"A {entry.source} row is undone by refunding the order, not by a ledger reversal",
            {"source": entry.source, "reversible_sources": list(ledger.REVERSIBLE_SOURCES)},
        )

    already = db.scalar(select(Transaction).where(Transaction.reverses_id == entry.id))
    if already is not None:
        raise AppError(
            409,
            "ALREADY_REVERSED",
            "That row has already been reversed",
            {"transaction_id": str(entry.id), "reversal_id": str(already.id)},
        )

    mirror = ledger.add_transaction(
        db,
        direction="out" if entry.direction == "in" else "in",
        amount=entry.amount,
        source=entry.source,
        ref_type=entry.ref_type,
        note=reason,
        event_id=entry.event_id,
        fundraiser_id=entry.fundraiser_id,
        created_by=actor.id,
        is_reversal=True,
        reverses_id=entry.id,
    )
    try:
        db.commit()
    except IntegrityError:
        # `reverses_id` is UNIQUE, so two simultaneous reversals lose the race here and nowhere else.
        db.rollback()
        raise AppError(
            409, "ALREADY_REVERSED", "That row has already been reversed", {"transaction_id": str(entry.id)}
        ) from None
    db.refresh(mirror)
    return mirror


# --- reconciliation ---------------------------------------------------------------------------


def _check(name: str, ledger_total: int, source_total: int) -> dict:
    difference = ledger_total - source_total
    return {
        "name": name,
        "ledger_total": ledger_total,
        "source_total": source_total,
        "difference": difference,
        "ok": difference == 0,
    }


def reconcile(db: Session) -> dict:
    """Recomputes each stream from the table that caused it and compares it to the ledger.

    The four table-backed streams are summed from `orders` and `expenses`; the hand-logged ones
    have no other table, so they are covered by the amount and linkage checks below. If any check
    fails, the books are not fit to report on - and `close_period` refuses to freeze them.
    """
    ledger_by_source = {row["source"]: row for row in _by_source(db, [])}

    source_totals = {
        "dues": db.scalar(
            select(func.coalesce(func.sum(Order.total), 0)).where(Order.kind == "membership", Order.status == "paid")
        ),
        "tickets": db.scalar(
            select(func.coalesce(func.sum(Order.total), 0)).where(Order.kind == "ticket", Order.status == "paid")
        ),
        "merch": db.scalar(
            select(func.coalesce(func.sum(Order.total), 0)).where(Order.kind == "merch", Order.status == "paid")
        ),
        "expense_reimbursement": db.scalar(
            select(func.coalesce(func.sum(Expense.amount), 0)).where(Expense.status == "reimbursed")
        ),
    }

    checks = []
    for source, label in SOURCE_TABLE_CHECKS.items():
        ledger_total = ledger_by_source.get(source, {}).get("net", 0)
        source_total = int(source_totals[source] or 0)
        # Outflows are recorded as a positive `net` on the out side, so compare magnitudes.
        if source == "expense_reimbursement":
            ledger_total = -ledger_total
        checks.append(_check(label, ledger_total, source_total))

    # A reimbursed claim with no ledger row would be money that left no trace.
    unlinked = (
        db.scalar(
            select(func.count())
            .select_from(Expense)
            .where(Expense.status == "reimbursed", Expense.ledger_transaction_id.is_(None))
        )
        or 0
    )
    checks.append(_check("Every reimbursed claim has a ledger row", int(unlinked), 0))

    negative = db.scalar(select(func.count()).select_from(Transaction).where(Transaction.amount <= 0)) or 0
    checks.append(_check("Positive ledger amounts", int(negative), 0))

    # The invariant is "balance >= 0", so the expected value is the balance when it holds and 0 when
    # it does not - which makes `difference` zero when healthy and the (negative) balance when not.
    balance = ledger.totals(db)["balance"]
    checks.append(_check("Balance is not negative", balance, max(balance, 0)))

    return {"ok": all(check["ok"] for check in checks), "checks": checks}


# --- reports ----------------------------------------------------------------------------------


def _top_expenses(db: Session, date_from: date, date_to: date, limit: int = TOP_EXPENSES) -> list[dict]:
    rows = db.scalars(
        select(Expense)
        .where(
            Expense.status == "reimbursed",
            Expense.reimbursed_at >= datetime.combine(date_from, time.min, tzinfo=UTC),
            Expense.reimbursed_at < datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=UTC),
        )
        .order_by(Expense.amount.desc(), Expense.id)
        .limit(limit)
    ).all()
    return [
        {
            "id": expense.id,
            "claimant": fundraiser_service.person_ref(expense.claimant),
            "amount": expense.amount,
            "category": expense.category,
            "description": expense.description,
            "incurred_on": expense.incurred_on,
            "reimbursed_at": expense.reimbursed_at,
        }
        for expense in rows
    ]


def semester_report(db: Session, date_from: date, date_to: date) -> dict:
    """Everything a treasurer hands to the committee at the end of a term.

    The one assertion worth having: `opening_balance + net movement == closing_balance`. If the
    three figures below ever disagree, the report is lying and the treasurer must not sign it.
    """
    if date_from > date_to:
        raise AppError(
            422, "VALIDATION_ERROR", "`from` must not be after `to`", {"from": str(date_from), "to": str(date_to)}
        )

    opening = ledger.totals(db, Transaction.occurred_at < datetime.combine(date_from, time.min, tzinfo=UTC))["balance"]
    money = _totals_in_range(db, date_from, date_to)
    closing = opening + money["balance"]
    assert opening + money["total_in"] - money["total_out"] == closing, "report arithmetic must close"

    conditions = _range(date_from, date_to)
    categories = spend_by_category(db, date_from, date_to)
    return {
        "period": {"from": date_from, "to": date_to},
        "opening_balance": opening,
        "income": {"by_source": [row for row in _by_source(db, conditions) if row["in"]], "total": money["total_in"]},
        "expenses": {"by_category": categories, "total": money["total_out"]},
        "closing_balance": closing,
        "net_movement": money["balance"],
        "by_event": by_event(db, date_from, date_to),
        "by_fundraiser": by_fundraiser(db, date_from, date_to),
        "outstanding_reimbursements": outstanding_reimbursements(db),
        "top_expenses": _top_expenses(db, date_from, date_to),
        "reconciliation": reconcile(db),
        "generated_at": datetime.now(UTC),
    }


# --- periods ----------------------------------------------------------------------------------


def list_periods(db: Session) -> list[FinancePeriod]:
    return list(db.scalars(select(FinancePeriod).order_by(FinancePeriod.end_date.desc(), FinancePeriod.name)))


def get_period(db: Session, period_id: UUID) -> FinancePeriod:
    period = db.get(FinancePeriod, period_id)
    if period is None:
        raise AppError(404, "PERIOD_NOT_FOUND", "No finance period with that id", {"period_id": str(period_id)})
    return period


def period_view(period: FinancePeriod) -> dict:
    return {
        "id": period.id,
        "name": period.name,
        "start_date": period.start_date,
        "end_date": period.end_date,
        "status": period.status,
        "closing_balance": period.closing_balance,
        "closed_by": fundraiser_service.person_ref(period.closer),
        "closed_at": period.closed_at,
        "reopened_by": None if period.reopened_by is None else str(period.reopened_by),
        "reopened_at": period.reopened_at,
        "reopen_reason": period.reopen_reason,
    }


def _jsonable(value):
    """The snapshot column is JSON, and a `date` or a `UUID` is not. Both become strings, which is
    exactly how the API renders them, so the frozen copy reads like the report that produced it."""
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, (date, datetime, UUID)):
        return str(value)
    return value


def close_period(
    db: Session, actor: User, name: str, start_date: date, end_date: date, force: bool = False
) -> FinancePeriod:
    """Freeze a stretch of the books.

    Three things must hold: the period is in the past, it does not overlap another closed period,
    and the books reconcile. The one judgement call is claims: a submitted or approved claim dated
    inside the period is money that has not moved yet, so closing over it would be signing off on a
    number that is about to change. `force` lets an admin do it anyway, and says so in the response.
    """
    if force and ROLE_RANK.get(actor.role, 0) < ROLE_RANK["admin"]:
        raise AppError(403, "FORBIDDEN", "Only an admin can force a period closed", {"your_role": actor.role})

    name = (name or "").strip()
    if len(name) < 3:
        raise AppError(422, "VALIDATION_ERROR", "name must be at least 3 characters", {})
    if end_date >= datetime.now(UTC).date():
        raise AppError(
            422,
            "VALIDATION_ERROR",
            "A period can only be closed once it is in the past",
            {"end_date": end_date.isoformat()},
        )
    if start_date > end_date:
        raise AppError(422, "VALIDATION_ERROR", "`start_date` must not be after `end_date`", {})

    overlap = db.scalar(
        select(FinancePeriod).where(
            FinancePeriod.status == "closed", FinancePeriod.start_date <= end_date, FinancePeriod.end_date >= start_date
        )
    )
    if overlap is not None:
        raise AppError(
            409,
            "PERIOD_OVERLAP",
            f"'{overlap.name}' already covers part of that range",
            {
                "period_name": overlap.name,
                "start_date": overlap.start_date.isoformat(),
                "end_date": overlap.end_date.isoformat(),
            },
        )

    report = reconcile(db)
    if not report["ok"] and not force:
        raise AppError(
            409,
            "RECONCILIATION_FAILED",
            "The books do not reconcile; fix the difference or force the close as an admin",
            {"checks": [check for check in report["checks"] if not check["ok"]]},
        )

    pending = list(
        db.scalars(
            select(Expense)
            .where(
                Expense.status.in_(("submitted", "approved")),
                Expense.incurred_on >= start_date,
                Expense.incurred_on <= end_date,
            )
            .order_by(Expense.incurred_on, Expense.id)
        )
    )
    if pending and not force:
        raise AppError(
            409,
            "PENDING_CLAIMS",
            "Claims dated inside this period have not been settled yet",
            {
                "count": len(pending),
                "claims": [
                    {
                        "id": str(claim.id),
                        "status": claim.status,
                        "amount": claim.amount,
                        "incurred_on": claim.incurred_on.isoformat(),
                    }
                    for claim in pending
                ],
            },
        )

    snapshot = semester_report(db, start_date, end_date)
    period = FinancePeriod(
        name=name,
        start_date=start_date,
        end_date=end_date,
        status="closed",
        closing_balance=snapshot["closing_balance"],
        snapshot=_jsonable(snapshot),
        closed_by=actor.id,
        closed_at=datetime.now(UTC),
    )
    db.add(period)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError(409, "PERIOD_NAME_TAKEN", "A period with that name already exists", {"name": name}) from None
    db.refresh(period)
    return period


def reopen_period(db: Session, actor: User, period_id: UUID, reason: str) -> FinancePeriod:
    """Admin only (enforced by the route). The reason is mandatory and kept: reopening a signed-off
    book is exactly the kind of thing a treasurer should have to explain later."""
    period = get_period(db, period_id)
    reason = (reason or "").strip()
    if len(reason) < MIN_REOPEN_REASON:
        raise AppError(422, "VALIDATION_ERROR", f"reason must be at least {MIN_REOPEN_REASON} characters", {})
    if period.status != "closed":
        raise AppError(
            409, "INVALID_STATE", f"'{period.name}' is {period.status}, not closed", {"status": period.status}
        )

    period.status = "reopened"
    period.reopened_by = actor.id
    period.reopened_at = datetime.now(UTC)
    period.reopen_reason = reason
    db.commit()
    db.refresh(period)
    return period
