"""Ticket sales, fulfilment and abandoned-order cleanup (DESIGN.md §4 rules 2-3)."""

import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.db import as_utc
from app.core.errors import AppError
from app.models import Event, Order, OrderItem, Payment, Ticket, TicketType, User
from app.services import ledger, payments, pricing
from app.services.inventory import release_seats, reserve_seats

MAX_TICKETS_PER_ORDER = 10
PENDING_ORDER_TTL_MINUTES = 15

# No 0/O/1/I/L: volunteers read these codes off a ticket at the door.
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 10


def normalise_code(code: str) -> str:
    """Scanners and humans both add noise; compare on a canonical form."""
    return "".join(code.split()).upper()


def generate_ticket_code(db: Session) -> str:
    # shortcut: check-then-insert. The unique index on tickets.code is the real guard; the
    # retry loop just turns a 1-in-2^50 collision into another draw instead of a 500.
    for _ in range(10):
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
        if not db.scalar(select(Ticket.id).where(Ticket.code == code)):
            return code
    raise AppError(500, "CODE_GENERATION_FAILED", "Could not allocate a unique ticket code")


def ticket_view(ticket: Ticket) -> dict:
    event = ticket.event
    ticket_type = ticket.ticket_type
    return {
        "id": ticket.id,
        "code": ticket.code,
        "event_id": ticket.event_id,
        "event_title": event.title if event else None,
        "event_starts_at": event.starts_at if event else None,
        "event_venue": event.venue if event else None,
        "ticket_type_id": ticket.ticket_type_id,
        "ticket_type_name": ticket_type.name if ticket_type else None,
        "status": ticket.status,
        "price_paid": ticket.price_paid,
        "is_member_price": ticket.is_member_price,
        "checked_in_at": ticket.checked_in_at,
    }


def create_ticket_checkout(
    db: Session,
    user: User,
    ticket_type_id: UUID,
    quantity: int,
    idempotency_key: str | None = None,
) -> tuple[Order, Payment | None, list[Ticket]]:
    """Everything in one transaction: reserve seats, order, item, (payment), (fulfilment)."""
    if not 1 <= quantity <= MAX_TICKETS_PER_ORDER:
        raise AppError(422, "VALIDATION_ERROR", f"quantity must be between 1 and {MAX_TICKETS_PER_ORDER}")

    if idempotency_key:
        existing = db.scalar(select(Order).where(Order.idempotency_key == idempotency_key, Order.user_id == user.id))
        if existing is not None:
            return _checkout_result(db, existing)

    ticket_type = db.get(TicketType, ticket_type_id)
    if ticket_type is None:
        raise AppError(404, "TICKET_TYPE_NOT_FOUND", "No ticket type with that id", {"ticket_type_id": str(ticket_type_id)})

    event = db.get(Event, ticket_type.event_id)
    if event is None or event.status != "published":
        status = event.status if event else "missing"
        raise AppError(409, "EVENT_NOT_ON_SALE", f"Event is not on sale ({status})", {"event_status": status})

    now = datetime.now(UTC)
    if ticket_type.sale_starts_at and now < as_utc(ticket_type.sale_starts_at):
        raise AppError(409, "NOT_IN_SALE_WINDOW", "Ticket sales have not started yet",
                       {"sale_starts_at": ticket_type.sale_starts_at.isoformat()})
    if ticket_type.sale_ends_at and now > as_utc(ticket_type.sale_ends_at):
        raise AppError(409, "NOT_IN_SALE_WINDOW", "Ticket sales have ended",
                       {"sale_ends_at": ticket_type.sale_ends_at.isoformat()})

    unit_price, is_member_price = pricing.resolve_ticket_price(db, user, ticket_type)
    reserve_seats(db, ticket_type.id, quantity)

    total = unit_price * quantity
    order = Order(
        user_id=user.id,
        kind="ticket",
        status="pending",
        subtotal=total,
        discount=0,
        total=total,
        currency="INR",
        meta={
            "event_id": str(event.id),
            "event_title": event.title,
            "ticket_type_id": str(ticket_type.id),
            "ticket_type_name": ticket_type.name,
            "is_member_price": is_member_price,
            "quantity": quantity,
        },
        idempotency_key=idempotency_key or uuid4().hex,
    )
    db.add(order)
    db.flush()
    db.add(
        OrderItem(
            order_id=order.id,
            item_type="ticket_type",
            item_id=ticket_type.id,
            quantity=quantity,
            unit_price=unit_price,
            line_total=total,
        )
    )
    db.flush()  # autoflush is off, and fulfil_ticket_order looks this item up below

    if total == 0:
        # Free ticket: nothing to charge, so no payment row and no ledger entry. The seats
        # are already reserved, which is all a free ticket costs the club.
        order.status = "paid"
        tickets = fulfil_ticket_order(db, order)
        db.commit()
        return order, None, tickets

    payment = payments.create_mock_intent(db, order)
    db.commit()
    db.refresh(order)
    db.refresh(payment)
    return order, payment, []


def fulfil_ticket_order(db: Session, order: Order) -> list[Ticket]:
    """Issue the tickets for a paid order. Idempotent: an order that already has tickets
    gets no more, so a replayed payment callback cannot mint duplicates."""
    existing = list(db.scalars(select(Ticket).where(Ticket.order_id == order.id)))
    if existing:
        return existing

    item = db.scalar(select(OrderItem).where(OrderItem.order_id == order.id, OrderItem.item_type == "ticket_type"))
    if item is None:
        raise AppError(409, "NOT_A_TICKET_ORDER", "Order has no ticket type")
    ticket_type = db.get(TicketType, item.item_id)

    meta = order.meta or {}
    is_member_price = bool(meta.get("is_member_price"))
    tickets: list[Ticket] = []
    for _ in range(item.quantity):
        ticket = Ticket(
            order_id=order.id,
            event_id=ticket_type.event_id,
            ticket_type_id=ticket_type.id,
            user_id=order.user_id,
            code=generate_ticket_code(db),
            status="valid",
            price_paid=item.unit_price,  # frozen at purchase time
            is_member_price=is_member_price,
        )
        db.add(ticket)
        db.flush()  # autoflush is off; without this the next code check cannot see this one
        tickets.append(ticket)
    return tickets


def confirm_ticket_payment(db: Session, order: Order, payment: Payment | None, outcome: str) -> dict:
    """Gateway result for a ticket order. Same shape as the membership handler: the atomic
    pending->paid claim decides who does the work, so a repeat call changes nothing."""
    if outcome == "fail":
        if order.status == "pending":
            order.status = "failed"
            if payment is not None:
                payments.settle(db, payment, "fail")
            _release_order_seats(db, order)
            db.commit()
        return payment_result(db, order, payment)

    claimed = db.execute(
        update(Order)
        .where(Order.id == order.id, Order.status == "pending")
        .values(status="paid", updated_at=func.now())
        .execution_options(synchronize_session=False)
    ).rowcount
    if not claimed:
        db.rollback()  # already settled — replay the stored result
        order = db.get(Order, order.id)
        return payment_result(db, order, _latest_payment(db, order.id))

    if payment is not None:
        payments.settle(db, payment, "success")
    fulfil_ticket_order(db, order)

    meta = order.meta or {}
    item = db.scalar(select(OrderItem).where(OrderItem.order_id == order.id, OrderItem.item_type == "ticket_type"))
    ledger.add_transaction(
        db,
        direction="in",
        amount=order.total,
        source="tickets",
        ref_type="order",
        ref_id=order.id,
        event_id=UUID(meta["event_id"]) if meta.get("event_id") else None,
        note=f"Ticket sales - {meta.get('event_title', 'event')} ({meta.get('ticket_type_name', 'ticket')} x{item.quantity if item else 0})",
    )
    db.commit()
    db.refresh(order)
    return payment_result(db, order, payment)


def release_expired_pending_orders(db: Session, ttl_minutes: int = PENDING_ORDER_TTL_MINUTES) -> dict:
    """Abandoned checkouts must not hold seats hostage. Runs on a schedule; exposed for tests."""
    cutoff = datetime.now(UTC) - timedelta(minutes=ttl_minutes)
    stale = list(
        db.scalars(select(Order).where(Order.kind == "ticket", Order.status == "pending", Order.created_at < cutoff))
    )
    for order in stale:
        order.status = "cancelled"
        _release_order_seats(db, order)
    db.commit()
    return {"cancelled": len(stale)}


def payment_result(db: Session, order: Order, payment: Payment | None) -> dict:
    tickets = list(db.scalars(select(Ticket).where(Ticket.order_id == order.id).order_by(Ticket.created_at)))
    return {
        "order_id": order.id,
        "payment_id": payment.id if payment else None,
        "order_status": order.status,
        "payment_status": payment.status if payment else None,
        "provider_ref": payment.provider_ref if payment else None,
        "membership": None,
        "tickets": [ticket_view(t) for t in tickets],
    }


def _latest_payment(db: Session, order_id: UUID) -> Payment | None:
    return db.scalar(select(Payment).where(Payment.order_id == order_id).order_by(Payment.created_at.desc()))


def _checkout_result(db: Session, order: Order) -> tuple[Order, Payment | None, list[Ticket]]:
    tickets = list(db.scalars(select(Ticket).where(Ticket.order_id == order.id)))
    return order, _latest_payment(db, order.id), tickets


def _release_order_seats(db: Session, order: Order) -> None:
    item = db.scalar(select(OrderItem).where(OrderItem.order_id == order.id, OrderItem.item_type == "ticket_type"))
    if item is not None:
        release_seats(db, item.item_id, item.quantity)
