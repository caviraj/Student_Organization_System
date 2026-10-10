"""Event reporting and the attendee list (DESIGN.md §5)."""

from uuid import UUID

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.models import Ticket, TicketType, User
from app.services.events import get_event, seats_left

SOLD_STATUSES = ("valid", "used")  # void tickets were never sold


def event_report(db: Session, event_id: UUID) -> dict:
    event = get_event(db, event_id)
    types = list(db.scalars(select(TicketType).where(TicketType.event_id == event_id).order_by(TicketType.name)))

    revenue = {"member": 0, "non_member": 0}
    counts = {"member": 0, "non_member": 0}
    for is_member, count, total in db.execute(
        select(Ticket.is_member_price, func.count(Ticket.id), func.coalesce(func.sum(Ticket.price_paid), 0))
        .where(Ticket.event_id == event_id, Ticket.status.in_(SOLD_STATUSES))
        .group_by(Ticket.is_member_price)
    ):
        bucket = "member" if is_member else "non_member"
        counts[bucket] = count
        revenue[bucket] = int(total or 0)

    tickets_sold = counts["member"] + counts["non_member"]
    checked_in = db.scalar(
        select(func.count()).select_from(Ticket).where(Ticket.event_id == event_id, Ticket.status == "used")
    ) or 0
    seats_total = sum(t.capacity for t in types)

    by_type = []
    for ticket_type in types:
        sold, total, in_count = db.execute(
            select(
                func.count(Ticket.id),
                func.coalesce(func.sum(Ticket.price_paid), 0),
                func.coalesce(func.sum(case((Ticket.status == "used", 1), else_=0)), 0),
            ).where(Ticket.ticket_type_id == ticket_type.id, Ticket.status.in_(SOLD_STATUSES))
        ).one()
        by_type.append(
            {
                "ticket_type_id": ticket_type.id,
                "name": ticket_type.name,
                "capacity": ticket_type.capacity,
                "sold": sold,
                "seats_left": seats_left(ticket_type),
                "checked_in": int(in_count),
                "revenue": int(total or 0),
            }
        )

    return {
        "event_id": event.id,
        "title": event.title,
        "status": event.status,
        "tickets_sold": tickets_sold,
        "seats_total": seats_total,
        # Live availability (capacity - reserved), so this agrees with GET /events/{id}.
        "seats_left": seats_total - sum(t.sold_count for t in types),
        "checked_in": checked_in,
        "no_shows": tickets_sold - checked_in,
        "attendance_rate": round(checked_in * 100 / tickets_sold, 1) if tickets_sold else 0.0,
        "revenue": {"member": revenue["member"], "non_member": revenue["non_member"],
                    "total": revenue["member"] + revenue["non_member"]},
        "by_ticket_type": by_type,
    }


def event_attendees(
    db: Session,
    event_id: UUID,
    *,
    status: str | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    get_event(db, event_id)  # 404 rather than an empty page for an unknown event
    filters = [Ticket.event_id == event_id]
    if status:
        filters.append(Ticket.status == status)
    if q:
        like = f"%{q}%"
        filters.append(
            or_(
                Ticket.code.ilike(like),
                Ticket.user_id.in_(select(User.id).where(or_(User.full_name.ilike(like), User.email.ilike(like)))),
            )
        )

    total = db.scalar(select(func.count()).select_from(Ticket).where(*filters)) or 0
    rows = db.scalars(
        select(Ticket)
        .where(*filters)
        .order_by(Ticket.checked_in_at.desc().nullslast(), Ticket.created_at)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    return {
        "items": [_attendee(db, t) for t in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def _attendee(db: Session, ticket: Ticket) -> dict:
    holder = db.get(User, ticket.user_id)
    return {
        "ticket_id": ticket.id,
        "code": ticket.code,
        "status": ticket.status,
        "holder_name": holder.full_name if holder else None,
        "holder_email": holder.email if holder else None,
        "ticket_type": ticket.ticket_type.name if ticket.ticket_type else None,
        "price_paid": ticket.price_paid,
        "is_member_price": ticket.is_member_price,
        "checked_in_at": ticket.checked_in_at,
    }
