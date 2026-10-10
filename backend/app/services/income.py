"""Income logged against a fundraiser by hand (PRD FR-5.3, DESIGN.md §4 rule 13).

This is the one ledger entry a human types, so it is the one that can be typed twice. Every entry
carries its author and, when the client sends an `Idempotency-Key`, that key: a double-click then
replays the row it already wrote instead of counting the cash again. There is no edit and no
delete - a ledger you can rewrite is not a ledger.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import as_utc
from app.core.errors import AppError
from app.models import Transaction, User
from app.services import fundraisers as fundraiser_service
from app.services import ledger

MAX_AMOUNT = 10_000_000  # Rs 1,00,000 in one entry - a stall's cash box, not a bank transfer
MAX_BACKDATE_DAYS = 30  # cash counted on the day, entered within the month


def _note(source_label: str | None, note: str | None) -> str | None:
    return " - ".join(part.strip() for part in (source_label, note) if part and part.strip()) or None


def _existing(db: Session, fundraiser_id: UUID, idempotency_key: str | None) -> Transaction | None:
    if not idempotency_key:
        return None
    return db.scalar(
        select(Transaction).where(
            Transaction.fundraiser_id == fundraiser_id, Transaction.idempotency_key == idempotency_key
        )
    )


def log_fundraiser_income(
    db: Session,
    actor: User,
    fundraiser_id: UUID,
    amount: int,
    *,
    note: str | None = None,
    source_label: str | None = None,
    idempotency_key: str | None = None,
    occurred_at: datetime | None = None,
) -> tuple[Transaction, bool]:
    """Write one `in` ledger row. Returns (row, replayed)."""
    if amount <= 0 or amount > MAX_AMOUNT:
        raise AppError(
            422,
            "VALIDATION_ERROR",
            f"amount must be between 1 and {MAX_AMOUNT} paise",
            {"amount": amount, "max": MAX_AMOUNT},
        )

    fundraiser = fundraiser_service.get_fundraiser(db, fundraiser_id)
    now = datetime.now(UTC)
    when = as_utc(occurred_at) if occurred_at is not None else now
    if when > now:
        raise AppError(
            422, "INVALID_OCCURRED_AT", "Income cannot be dated in the future", {"occurred_at": when.isoformat()}
        )
    if when < now - timedelta(days=MAX_BACKDATE_DAYS):
        raise AppError(
            422,
            "INVALID_OCCURRED_AT",
            f"Income can be backdated at most {MAX_BACKDATE_DAYS} days",
            {"occurred_at": when.isoformat(), "max_days": MAX_BACKDATE_DAYS},
        )
    fundraiser_service.assert_income_open(fundraiser, now)

    replayed = _existing(db, fundraiser_id, idempotency_key)
    if replayed is not None:
        return replayed, True

    entry = ledger.add_transaction(
        db,
        direction="in",
        amount=amount,
        source="fundraiser",
        ref_type="fundraiser",
        ref_id=fundraiser_id,
        fundraiser_id=fundraiser_id,
        note=_note(source_label, note),
        created_by=actor.id,
        # A hand-logged entry is dated to the day the cash was counted, not to the day it was typed.
        occurred_at=when,
    )
    entry.idempotency_key = idempotency_key
    try:
        db.commit()
    except IntegrityError:
        # Two requests raced past the lookup above. The unique key is the real guard, so re-read
        # the winner's row rather than counting the money twice.
        db.rollback()
        replayed = _existing(db, fundraiser_id, idempotency_key)
        if replayed is not None:
            return replayed, True
        raise
    db.refresh(entry)
    return entry, False


def income_view(db: Session, entry: Transaction, fundraiser, *, replayed: bool = False) -> dict:
    raised = fundraiser_service.raised_total(db, fundraiser.id)
    return {
        "id": entry.id,
        "amount": entry.amount,
        "note": entry.note,
        "occurred_at": entry.occurred_at,
        "raised_total": raised,
        "percent_of_goal": round(raised * 100 / fundraiser.goal_amount),
        "replayed": replayed,
    }


def list_fundraiser_income(
    db: Session, fundraiser_id: UUID, *, page: int = 1, page_size: int = 20
) -> tuple[list[dict], int]:
    """Who logged what, newest first - the cash book for one fundraiser."""
    fundraiser_service.get_fundraiser(db, fundraiser_id)  # 404 rather than an empty page
    conditions = [Transaction.fundraiser_id == fundraiser_id, Transaction.direction == "in"]
    total = db.scalar(select(func.count()).select_from(Transaction).where(*conditions)) or 0
    rows = list(
        db.scalars(
            select(Transaction)
            .where(*conditions)
            .order_by(Transaction.occurred_at.desc(), Transaction.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    names = {
        user.id: user
        for user in db.scalars(select(User).where(User.id.in_({row.logged_by for row in rows if row.logged_by})))
    }
    items = [
        {
            "id": row.id,
            "amount": row.amount,
            "note": row.note,
            "occurred_at": row.occurred_at,
            "logged_by": fundraiser_service.person_ref(names.get(row.logged_by)),
            "created_at": row.created_at,
        }
        for row in rows
    ]
    return items, total
