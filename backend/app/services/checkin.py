"""Door check-in (DESIGN.md §4 rule 4).

The conditional UPDATE is the whole design: two scanners pointing at the same ticket can
never both be told VALID, because only one of them can update a row whose status is still
'valid'. A read-then-write would hand both of them a green screen.
"""

from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import Event, Ticket, TicketType, User
from app.services.tickets import normalise_code, ticket_view

RESULT_MESSAGES = {
    "VALID": "Welcome!",
    "ALREADY_USED": "This ticket has already been scanned",
    "WRONG_EVENT": "This ticket is for a different event",
    "INVALID": "No ticket found for that code",
}


def check_in(db: Session, staff: User, event_id: UUID, code: str) -> dict:
    event = db.get(Event, event_id)
    if event is None:
        raise AppError(404, "EVENT_NOT_FOUND", "No event with that id", {"event_id": str(event_id)})

    ticket = db.scalar(select(Ticket).where(Ticket.code == normalise_code(code)))

    if ticket is None:
        return _result(db, event_id, "INVALID")
    if ticket.status == "void":
        return _result(db, event_id, "INVALID", ticket=None, message="This ticket has been voided")
    if ticket.event_id != event_id:
        other = db.get(Event, ticket.event_id)
        return _result(
            db,
            event_id,
            "WRONG_EVENT",
            ticket=ticket,
            message=f"This ticket is for {other.title if other else 'another event'}",
        )

    claimed = db.execute(
        update(Ticket)
        .where(Ticket.id == ticket.id, Ticket.status == "valid")
        .values(status="used", checked_in_at=func.now(), checked_in_by=staff.id, updated_at=func.now())
        .execution_options(synchronize_session=False)
    ).rowcount

    if not claimed:
        db.refresh(ticket)  # another scanner got there first; show their timestamp
        return _result(db, event_id, "ALREADY_USED", ticket=ticket)

    db.commit()
    db.refresh(ticket)
    return _result(db, event_id, "VALID", ticket=ticket)


def _result(
    db: Session,
    event_id: UUID,
    result: str,
    *,
    ticket: Ticket | None = None,
    message: str | None = None,
) -> dict:
    """One shape for all four outcomes — the scanner renders it without branching on status."""
    holder_name = None
    ticket_type_name = None
    if ticket is not None:
        holder = db.get(User, ticket.user_id)
        holder_name = holder.full_name if holder else None
        ticket_type = db.get(TicketType, ticket.ticket_type_id)
        ticket_type_name = ticket_type.name if ticket_type else None

    checked_in, sold = counters(db, event_id)
    return {
        "result": result,
        "ticket": ticket_view(ticket) if ticket is not None else None,
        "holder_name": holder_name,
        "ticket_type": ticket_type_name,
        "checked_in_at": ticket.checked_in_at if ticket is not None else None,
        "message": message or RESULT_MESSAGES[result],
        "checked_in": checked_in,
        "sold": sold,
    }


def counters(db: Session, event_id: UUID) -> tuple[int, int]:
    """The scanner header: how many are in, out of how many tickets exist."""
    checked_in = db.scalar(
        select(func.count()).select_from(Ticket).where(Ticket.event_id == event_id, Ticket.status == "used")
    ) or 0
    sold = db.scalar(
        select(func.count()).select_from(Ticket).where(Ticket.event_id == event_id, Ticket.status.in_(("valid", "used")))
    ) or 0
    return checked_in, sold
