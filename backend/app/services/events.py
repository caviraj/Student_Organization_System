"""Event and ticket-type rules (DESIGN.md §4). No HTTP here."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.db import as_utc
from app.core.errors import AppError
from app.models import Event, TicketType, User
from app.services.pricing import is_active_member, price_for

# Status is one-way: an event never un-publishes, so tickets already sold stay meaningful.
ALLOWED_TRANSITIONS = {
    "draft": {"published", "closed"},
    "published": {"closed"},
    "closed": set(),
}


def is_on_sale(ticket_type: TicketType, now: datetime) -> bool:
    """The sale window decides, independent of seats left (that is a separate 409)."""
    started = not ticket_type.sale_starts_at or now >= as_utc(ticket_type.sale_starts_at)
    not_ended = not ticket_type.sale_ends_at or now <= as_utc(ticket_type.sale_ends_at)
    return started and not_ended


def seats_left(ticket_type: TicketType) -> int:
    return max(ticket_type.capacity - ticket_type.sold_count, 0)


def ticket_type_view(ticket_type: TicketType, *, is_member: bool | None, now: datetime | None = None) -> dict:
    """`is_member=None` means nobody is asking on their own behalf (anonymous caller), so
    there is no "price for you" to quote — only the two list prices."""
    now = now or datetime.now(UTC)
    return {
        "id": ticket_type.id,
        "event_id": ticket_type.event_id,
        "name": ticket_type.name,
        "member_price": ticket_type.member_price,
        "non_member_price": ticket_type.non_member_price,
        "capacity": ticket_type.capacity,
        "sold_count": ticket_type.sold_count,
        "seats_left": seats_left(ticket_type),
        "is_on_sale": is_on_sale(ticket_type, now),
        "price_for_you": price_for(ticket_type, is_member) if is_member is not None else None,
        "sale_starts_at": ticket_type.sale_starts_at,
        "sale_ends_at": ticket_type.sale_ends_at,
    }


def event_summary(event: Event, *, is_member: bool) -> dict:
    """A row in GET /events. `min_price` is the cheapest price that applies to the caller."""
    types = list(event.ticket_types)
    return {
        "id": event.id,
        "title": event.title,
        "venue": event.venue,
        "starts_at": event.starts_at,
        "ends_at": event.ends_at,
        "banner_url": event.banner_url,
        "status": event.status,
        "department": event.department,
        "min_price": min((price_for(t, is_member) for t in types), default=None),
        "seats_left": sum(seats_left(t) for t in types),
    }


def event_detail(db: Session, event: Event, user: User | None = None) -> dict:
    member = is_active_member(db, user) if user is not None else None
    now = datetime.now(UTC)
    return {
        "id": event.id,
        "title": event.title,
        "description": event.description,
        "venue": event.venue,
        "starts_at": event.starts_at,
        "ends_at": event.ends_at,
        "banner_url": event.banner_url,
        "status": event.status,
        "department": event.department,
        "created_by": event.created_by,
        "created_at": event.created_at,
        "seats_left": sum(seats_left(t) for t in event.ticket_types),
        "ticket_types": [ticket_type_view(t, is_member=member, now=now) for t in event.ticket_types],
    }


def get_event(db: Session, event_id) -> Event:
    event = db.get(Event, event_id)
    if event is None:
        raise AppError(404, "EVENT_NOT_FOUND", "No event with that id", {"event_id": str(event_id)})
    return event


def create_event(db: Session, creator: User, payload) -> Event:
    if payload.ends_at <= payload.starts_at:
        raise AppError(422, "VALIDATION_ERROR", "ends_at must be after starts_at")
    event = Event(
        title=payload.title,
        description=payload.description,
        venue=payload.venue,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        banner_url=payload.banner_url,
        status="draft",
        department=payload.department,
        created_by=creator.id,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def update_event(db: Session, event: Event, payload) -> Event:
    fields = payload.model_dump(exclude_unset=True)
    status = fields.pop("status", None)

    starts_at = fields.get("starts_at", event.starts_at)
    ends_at = fields.get("ends_at", event.ends_at)
    if ends_at <= starts_at:
        raise AppError(422, "VALIDATION_ERROR", "ends_at must be after starts_at")

    if status is not None and status != event.status:
        if status not in ALLOWED_TRANSITIONS[event.status]:
            raise AppError(
                409,
                "INVALID_STATUS_TRANSITION",
                f"Cannot move an event from {event.status} to {status}",
                {"from": event.status, "to": status},
            )
        event.status = status

    for key, value in fields.items():
        setattr(event, key, value)
    db.commit()
    db.refresh(event)
    return event


def add_ticket_type(db: Session, event: Event, payload) -> TicketType:
    _check_window(payload.sale_starts_at, payload.sale_ends_at)
    ticket_type = TicketType(
        event_id=event.id,
        name=payload.name,
        member_price=payload.member_price,
        non_member_price=payload.non_member_price,
        capacity=payload.capacity,
        sale_starts_at=payload.sale_starts_at,
        sale_ends_at=payload.sale_ends_at,
    )
    db.add(ticket_type)
    db.commit()
    db.refresh(ticket_type)
    return ticket_type


def update_ticket_type(db: Session, ticket_type: TicketType, payload) -> TicketType:
    fields = payload.model_dump(exclude_unset=True)
    capacity = fields.get("capacity")
    if capacity is not None and capacity < ticket_type.sold_count:
        raise AppError(
            409,
            "CAPACITY_BELOW_SOLD",
            "Capacity cannot be reduced below the seats already sold",
            {"sold_count": ticket_type.sold_count, "capacity": capacity},
        )
    if capacity is not None and capacity <= 0:
        raise AppError(422, "VALIDATION_ERROR", "capacity must be greater than 0")

    for key, value in fields.items():
        setattr(ticket_type, key, value)
    _check_window(ticket_type.sale_starts_at, ticket_type.sale_ends_at)
    db.commit()
    db.refresh(ticket_type)
    return ticket_type


def _check_window(starts_at: datetime | None, ends_at: datetime | None) -> None:
    if starts_at and ends_at and ends_at <= starts_at:
        raise AppError(422, "VALIDATION_ERROR", "sale_ends_at must be after sale_starts_at")
