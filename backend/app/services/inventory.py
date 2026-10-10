"""Seat reservation (DESIGN.md §4 rule 2).

The conditional UPDATE is the lock. Never read-then-write: two buyers arriving together
must not both see "1 seat left" and both succeed.
"""

from uuid import UUID

from sqlalchemy import case, func, select, update
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import TicketType


def reserve_seats(db: Session, ticket_type_id: UUID, qty: int) -> None:
    """Atomically claim `qty` seats. 0 rows updated means the seats were not there."""
    claimed = db.execute(
        update(TicketType)
        .where(TicketType.id == ticket_type_id, TicketType.sold_count + qty <= TicketType.capacity)
        .values(sold_count=TicketType.sold_count + qty, updated_at=func.now())
        .execution_options(synchronize_session=False)
    ).rowcount
    if not claimed:
        # Fresh SELECT, not the identity map: the point is to report the *current* count.
        seats_left = db.scalar(
            select(TicketType.capacity - TicketType.sold_count).where(TicketType.id == ticket_type_id)
        )
        raise AppError(
            409,
            "SOLD_OUT",
            "Not enough seats left",
            {"seats_left": max(seats_left or 0, 0), "requested": qty},
        )


def release_seats(db: Session, ticket_type_id: UUID, qty: int) -> None:
    """Give seats back. Clamped at 0 so a double release can never drive the count negative
    (the CHECK constraint would turn that into a 500)."""
    db.execute(
        update(TicketType)
        .where(TicketType.id == ticket_type_id)
        .values(
            sold_count=case((TicketType.sold_count >= qty, TicketType.sold_count - qty), else_=0),
            updated_at=func.now(),
        )
        .execution_options(synchronize_session=False)
    )
