"""Mock payment provider used in Milestone 1 (DESIGN.md §1).

The `PaymentProvider` interface arrives with RazorpayProvider in M2; until there is a
second implementation these are plain functions.
"""

import uuid

from sqlalchemy.orm import Session

from app.models import Order, Payment


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
