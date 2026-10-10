"""Mock payment provider (DESIGN.md §1) and the gateway-result dispatcher.

The `PaymentProvider` interface arrives with RazorpayProvider in M2; until there is a
second implementation these are plain functions.
"""

import uuid
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import Order, Payment, User


def create_mock_intent(db: Session, order: Order) -> Payment:
    payment = Payment(
        order_id=order.id,
        provider="mock",
        status="created",
        amount=order.total,
        raw={"simulated": True},
    )
    db.add(payment)
    return payment


def settle(db: Session, payment: Payment, outcome: str) -> str:
    """Applies a simulated gateway outcome. Returns the new payment status."""
    if outcome == "success":
        payment.status = "succeeded"
        payment.provider_ref = payment.provider_ref or f"mock_{uuid.uuid4().hex}"
    else:
        payment.status = "failed"
    payment.raw = {**(payment.raw or {}), "outcome": outcome}
    return payment.status


def latest_payment(db: Session, order_id: UUID) -> Payment | None:
    return db.scalar(select(Payment).where(Payment.order_id == order_id).order_by(Payment.created_at.desc()))


def confirm_mock_payment(db: Session, order_id: UUID, outcome: str, actor: User) -> dict:
    """Entry point for POST /payments/{order_id}/mock-confirm.

    Loads and authorises the order once, then hands off to the handler for its kind. Both
    handlers keep everything in ONE transaction and are idempotent; the conditional
    pending->paid claim is what makes a repeated callback a no-op.
    """
    from app.services import memberships, merch, tickets  # local: all three import this module

    order = db.get(Order, order_id)
    if order is None:
        raise AppError(404, "ORDER_NOT_FOUND", "Order not found", {"order_id": str(order_id)})
    if order.user_id != actor.id and actor.role != "admin":
        raise AppError(403, "FORBIDDEN", "You can only confirm your own orders")

    payment = latest_payment(db, order.id)

    if order.kind == "ticket":
        # Free ticket orders carry no payment row: they settle at checkout, so a repeated
        # confirmation just replays the issued tickets.
        if payment is None:
            return tickets.payment_result(db, order, None)
        return tickets.confirm_ticket_payment(db, order, payment, outcome)

    if payment is None:
        raise AppError(404, "PAYMENT_NOT_FOUND", "This order has no payment")

    if order.kind == "merch":
        return merch.confirm_merch_payment(db, order, payment, outcome)

    return memberships.confirm_membership_payment(db, order, payment, outcome)
