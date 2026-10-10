from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_optional_user, require_role
from app.core.errors import AppError
from app.models import Event, TicketType, User
from app.schemas import (
    AttendeeOut,
    EventCreateIn,
    EventDetail,
    EventListItem,
    EventReportOut,
    EventUpdateIn,
    Page,
    TicketTypeCreateIn,
    TicketTypeOut,
    TicketTypeUpdateIn,
)
from app.services import events as event_service
from app.services import reports
from app.services.pricing import is_active_member

router = APIRouter(prefix="/events", tags=["events"])
ticket_type_router = APIRouter(prefix="/ticket-types", tags=["events"])


@router.get("", response_model=Page[EventListItem], summary="Browse events (public)")
def list_events(
    include_drafts: bool = Query(default=False, description="organizer+ only"),
    upcoming: bool | None = Query(default=None, description="Only events that have not started yet"),
    q: str | None = Query(default=None, description="Search title or venue"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    filters = []
    if include_drafts:
        if user is None:
            raise AppError(401, "UNAUTHORIZED", "Sign in to include drafts")
        if user.role not in ("organizer", "treasurer", "admin"):
            raise AppError(403, "FORBIDDEN", "Requires role: organizer or above", {"your_role": user.role})
    else:
        filters.append(Event.status == "published")
    if upcoming:
        filters.append(Event.starts_at >= datetime.now(UTC))
    if q:
        like = f"%{q}%"
        filters.append(or_(Event.title.ilike(like), Event.venue.ilike(like)))

    total = db.scalar(select(func.count()).select_from(Event).where(*filters)) or 0
    rows = db.scalars(
        select(Event).where(*filters).order_by(Event.starts_at).offset((page - 1) * page_size).limit(page_size)
    ).all()

    member = is_active_member(db, user)
    return {
        "items": [event_service.event_summary(e, is_member=member) for e in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{event_id}", response_model=EventDetail, summary="Event detail with ticket types (public when published)")
def get_event(
    event_id: UUID,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    event = event_service.get_event(db, event_id)
    is_staff = user is not None and user.role in ("organizer", "treasurer", "admin")
    if event.status != "published" and not is_staff:
        raise AppError(404, "EVENT_NOT_FOUND", "No event with that id", {"event_id": str(event_id)})
    return event_service.event_detail(db, event, user)


@router.post("", response_model=EventDetail, status_code=201, summary="Create an event (organizer+)")
def create_event(
    payload: EventCreateIn,
    user: User = Depends(require_role("organizer")),
    db: Session = Depends(get_db),
):
    return event_service.event_detail(db, event_service.create_event(db, user, payload), user)


@router.patch("/{event_id}", response_model=EventDetail, summary="Update or publish an event (organizer+)")
def update_event(
    event_id: UUID,
    payload: EventUpdateIn,
    user: User = Depends(require_role("organizer")),
    db: Session = Depends(get_db),
):
    event = event_service.get_event(db, event_id)
    return event_service.event_detail(db, event_service.update_event(db, event, payload), user)


@router.post(
    "/{event_id}/ticket-types",
    response_model=TicketTypeOut,
    status_code=201,
    summary="Add a ticket type (organizer+)",
)
def create_ticket_type(
    event_id: UUID,
    payload: TicketTypeCreateIn,
    user: User = Depends(require_role("organizer")),
    db: Session = Depends(get_db),
):
    event = event_service.get_event(db, event_id)
    ticket_type = event_service.add_ticket_type(db, event, payload)
    return event_service.ticket_type_view(ticket_type, is_member=is_active_member(db, user))


@ticket_type_router.patch(
    "/{ticket_type_id}", response_model=TicketTypeOut, summary="Update a ticket type (organizer+)"
)
def update_ticket_type(
    ticket_type_id: UUID,
    payload: TicketTypeUpdateIn,
    user: User = Depends(require_role("organizer")),
    db: Session = Depends(get_db),
):
    ticket_type = db.get(TicketType, ticket_type_id)
    if ticket_type is None:
        raise AppError(
            404, "TICKET_TYPE_NOT_FOUND", "No ticket type with that id", {"ticket_type_id": str(ticket_type_id)}
        )
    updated = event_service.update_ticket_type(db, ticket_type, payload)
    return event_service.ticket_type_view(updated, is_member=is_active_member(db, user))


@router.get("/{event_id}/report", response_model=EventReportOut, summary="Sales and attendance report (organizer+)")
def event_report(event_id: UUID, _: User = Depends(require_role("organizer")), db: Session = Depends(get_db)):
    return reports.event_report(db, event_id)


@router.get("/{event_id}/attendees", response_model=Page[AttendeeOut], summary="Attendee list (organizer+)")
def event_attendees(
    event_id: UUID,
    status: str | None = Query(default=None, pattern="^(valid|used|void)$"),
    q: str | None = Query(default=None, description="Search name, email or ticket code"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: User = Depends(require_role("organizer")),
    db: Session = Depends(get_db),
):
    return reports.event_attendees(db, event_id, status=status, q=q, page=page, page_size=page_size)
