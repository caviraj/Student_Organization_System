from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import as_utc
from app.core.deps import get_current_user, get_db
from app.core.errors import AppError
from app.models import Ticket, User
from app.schemas import Page, TicketCheckoutIn, TicketCheckoutOut, TicketOut
from app.services import tickets as ticket_service

router = APIRouter(prefix="/tickets", tags=["tickets"])

_UNSCHEDULED = (2, 0.0)


def _attention_order(ticket: dict) -> tuple[int, float]:
    """Upcoming first (soonest at the top), then the past, most recent first. A past ticket
    is still worth showing — it is a receipt."""
    starts_at = ticket["event_starts_at"]
    if starts_at is None:
        return _UNSCHEDULED
    moment = as_utc(starts_at)
    return (0, moment.timestamp()) if moment >= datetime.now(UTC) else (1, -moment.timestamp())


@router.post("/checkout", response_model=TicketCheckoutOut, status_code=201, summary="Buy tickets (auth)")
def checkout(
    payload: TicketCheckoutIn,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=64),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order, payment, tickets = ticket_service.create_ticket_checkout(
        db, user, payload.ticket_type_id, payload.quantity, idempotency_key
    )
    item = order.items[0] if order.items else None
    return {
        "order_id": order.id,
        "payment_id": payment.id if payment else None,
        "amount": order.total,
        "unit_price": item.unit_price if item else 0,
        "is_member_price": bool((order.meta or {}).get("is_member_price")),
        "quantity": item.quantity if item else payload.quantity,
        "provider": payment.provider if payment else None,
        "status": order.status,
        "tickets": [ticket_service.ticket_view(t) for t in tickets],
    }


@router.get("/me", response_model=Page[TicketOut], summary="My tickets (auth)")
def my_tickets(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    filters = [Ticket.user_id == user.id]
    total = db.scalar(select(func.count()).select_from(Ticket).where(*filters)) or 0
    rows = db.scalars(
        select(Ticket)
        .where(*filters)
        .order_by(Ticket.event_id, Ticket.created_at)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    items = [ticket_service.ticket_view(t) for t in rows]
    items.sort(key=_attention_order)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/{ticket_id}", response_model=TicketOut, summary="One ticket (owner or organizer+)")
def get_ticket(
    ticket_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ticket = db.get(Ticket, ticket_id)
    if ticket is None:
        raise AppError(404, "TICKET_NOT_FOUND", "No ticket with that id", {"ticket_id": str(ticket_id)})
    if ticket.user_id != user.id and user.role not in ("organizer", "treasurer", "admin"):
        raise AppError(403, "FORBIDDEN", "This is not your ticket")
    return ticket_service.ticket_view(ticket)
