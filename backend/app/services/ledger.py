from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import Transaction


def record_transaction(
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
) -> Transaction:
    """Adds a ledger row to the caller's transaction — never commits (DESIGN.md §4 rule 3)."""
    entry = Transaction(
        direction=direction,
        amount=amount,
        source=source,
        ref_type=ref_type,
        ref_id=ref_id,
        event_id=event_id,
        fundraiser_id=fundraiser_id,
        note=note,
        occurred_at=datetime.now(UTC),
    )
    db.add(entry)
    return entry
