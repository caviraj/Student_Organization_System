"""The ledger — the one place money becomes a row.

Every balance in the system is derived from this table, never stored (DESIGN.md §4 rule 3). Two
rules make that safe:

* **Append-only.** No code path issues an UPDATE or DELETE against `transactions`. A mistake is
  undone by writing a *reversal*: a second row that undoes the first, leaving both visible. A
  ledger you can rewrite is not a ledger.
* **One writer.** `add_transaction` is the only function that constructs a `Transaction`. Dues,
  tickets, merch, fundraiser income, reimbursements, manual entries and reversals all go through
  it, so the amount check, the source/direction pairing and the closed-period refusal cannot be
  forgotten at a new call site.

## Signed totals

A reversal row carries `is_reversal = true` and its amount must be subtracted from the side the
ORIGINAL row was on, not added to the side it points at. Reversing 5000 of fundraiser income
writes an `out`/5000 row, and the net effect on `total_in` must be -5000, not +0 on `total_out`.
So both totals are computed from four disjoint buckets:

    total_in  = SUM(amount WHERE direction='in'  AND NOT is_reversal)
              - SUM(amount WHERE direction='out' AND     is_reversal)

    total_out = SUM(amount WHERE direction='out' AND NOT is_reversal)
              - SUM(amount WHERE direction='in'  AND     is_reversal)

    balance   = total_in - total_out

`total_in_expr()`, `total_out_expr()` and `balance_expr()` are those three sums as reusable SQL
expressions, written once here so no report can invent its own arithmetic. Call them inside a
`select()` and narrow with an ordinary `where()` — a filter applies to every bucket uniformly, so
per-source, per-event and per-month figures stay consistent with the headline balance.

The four buckets are also disjoint, which is what makes `reconcile()` meaningful: a corrupted row
(amount <= 0, or a missing link between a reimbursed claim and its ledger row) moves no total.
"""

from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from app.core.db import as_utc
from app.core.errors import AppError
from app.models import LEDGER_DIRECTIONS, LEDGER_SOURCES, FinancePeriod, Transaction

# The direction a source is allowed to move money in. Reversals are exempt: a reversal of `dues`
# is an `out` row, so the pairing is checked against the row being reversed, not this table.
DIRECTION_BY_SOURCE = {
    "dues": "in",
    "tickets": "in",
    "merch": "in",
    "fundraiser": "in",
    "other_income": "in",
    "expense_reimbursement": "out",
    "other_expense": "out",
}

# The sources `reverse_transaction` will accept. Payment-driven rows (dues/tickets/merch) are
# undone by refunding the order, not by a ledger reversal, so they are refused on purpose.
REVERSIBLE_SOURCES = ("fundraiser", "other_income", "other_expense")

IN_PLAIN = and_(Transaction.direction == "in", Transaction.is_reversal.is_(False))
IN_REVERSAL = and_(Transaction.direction == "in", Transaction.is_reversal.is_(True))
OUT_PLAIN = and_(Transaction.direction == "out", Transaction.is_reversal.is_(False))
OUT_REVERSAL = and_(Transaction.direction == "out", Transaction.is_reversal.is_(True))


def _sum(predicate) -> object:
    """SUM over one bucket; COALESCE so an empty ledger totals 0 rather than NULL."""
    return func.coalesce(func.sum(case((predicate, Transaction.amount), else_=0)), 0)


def total_in_expr():
    """See the module docstring for the definition. Use as `select(total_in_expr())`."""
    return _sum(IN_PLAIN) - _sum(OUT_REVERSAL)


def total_out_expr():
    """See the module docstring for the definition. Use as `select(total_out_expr())`."""
    return _sum(OUT_PLAIN) - _sum(IN_REVERSAL)


def balance_expr():
    """`total_in - total_out`, in one expression so a report cannot mismatch the two halves."""
    return total_in_expr() - total_out_expr()


def signed_amount_expr():
    """One row's contribution to `balance`: +amount for money in, -amount for money out, with a
    reversal counting against the side its original was on. Use it in a window function to get a
    running balance:

        select(Transaction.id,
               func.sum(signed_amount_expr()).over(
                   order_by=(Transaction.occurred_at, Transaction.id)
               ).label("running_balance"))

    The window must be computed over the WHOLE ledger to mean anything, so a filtered page has to
    select from a subquery that carries the window (see `finance.list_transactions`)."""
    return (
        case((IN_PLAIN, Transaction.amount), (OUT_REVERSAL, -Transaction.amount), else_=0)
        - case((OUT_PLAIN, Transaction.amount), (IN_REVERSAL, -Transaction.amount), else_=0)
    )


# --- reads ------------------------------------------------------------------------------------


def closed_period_containing(db: Session, day: date) -> FinancePeriod | None:
    """The closed period a date falls inside, if any. `close_period` refuses overlaps, so at most
    one can match; the ordering is there so a hand-edited database still returns one row."""
    return db.scalar(
        select(FinancePeriod)
        .where(FinancePeriod.status == "closed", FinancePeriod.start_date <= day, FinancePeriod.end_date >= day)
        .order_by(FinancePeriod.start_date.desc())
        .limit(1)
    )


def totals(db: Session, *conditions) -> dict[str, int]:
    """`{total_in, total_out, balance}` over the ledger, or over whatever `conditions` narrow it to."""
    row = db.execute(
        select(total_in_expr().label("total_in"), total_out_expr().label("total_out")).where(*conditions)
    ).one()
    total_in, total_out = int(row.total_in), int(row.total_out)
    return {"total_in": total_in, "total_out": total_out, "balance": total_in - total_out}


# --- the writer -------------------------------------------------------------------------------


def add_transaction(
    db: Session,
    *,
    direction: str,
    amount: int,
    source: str,
    ref_type: str | None = None,
    ref_id: UUID | None = None,
    event_id: UUID | None = None,
    fundraiser_id: UUID | None = None,
    note: str | None = None,
    created_by: UUID | None = None,
    occurred_at: datetime | None = None,
    is_reversal: bool = False,
    reverses_id: UUID | None = None,
    seed_backdate: bool = False,
) -> Transaction:
    """Adds a ledger row to the caller's transaction — never commits (DESIGN.md §4 rule 3).

    `created_by` is stored in `logged_by`: Phase 5 named that column when fundraiser income became
    hand-logged, and one column for "who wrote this row" is better than two that always agree.

    `seed_backdate` is for `scripts/seed.py` ONLY. It is the single way to write a row into a past
    day or into a closed period, and it exists so the seed can spread a semester of history over 90
    days. No endpoint may pass it.
    """
    if amount <= 0:
        raise AppError(422, "VALIDATION_ERROR", "A ledger amount must be greater than zero", {"amount": amount})
    if direction not in LEDGER_DIRECTIONS:
        raise AppError(422, "VALIDATION_ERROR", "Unknown ledger direction", {"direction": direction})
    if source not in LEDGER_SOURCES:
        raise AppError(422, "VALIDATION_ERROR", "Unknown ledger source", {"source": source})
    if not is_reversal and DIRECTION_BY_SOURCE[source] != direction:
        raise AppError(
            422,
            "INVALID_LEDGER_ROW",
            f"A {source} row moves money {DIRECTION_BY_SOURCE[source]}, not {direction}",
            {"source": source, "direction": direction, "expected_direction": DIRECTION_BY_SOURCE[source]},
        )

    when = as_utc(occurred_at) if occurred_at is not None else datetime.now(UTC)
    if not seed_backdate:
        period = closed_period_containing(db, when.date())
        if period is not None:
            raise AppError(
                409,
                "PERIOD_CLOSED",
                f"'{period.name}' is closed; nothing may be dated inside it",
                {"period_name": period.name, "start_date": period.start_date.isoformat(), "end_date": period.end_date.isoformat()},
            )

    entry = Transaction(
        direction=direction,
        amount=amount,
        source=source,
        ref_type=ref_type,
        ref_id=ref_id,
        event_id=event_id,
        fundraiser_id=fundraiser_id,
        note=note,
        occurred_at=when,
        is_reversal=is_reversal,
        reverses_id=reverses_id,
        logged_by=created_by,
    )
    db.add(entry)
    return entry
