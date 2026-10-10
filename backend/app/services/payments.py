"""Payment providers (DESIGN.md §1) and the gateway-result dispatcher.

`create_intent` is the whole seam: it asks the configured provider for a payment attempt and keeps
the gateway's reference on the row. Everything downstream - the confirm handlers in tickets, merch
and memberships - is untouched, because none of it knows where the confirmation came from.

Provider selection follows `services/mailer.py`: a registry keyed by a setting.
"""

import hashlib
import hmac
import json
import logging
import uuid
from abc import ABC, abstractmethod
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.authz import has_permission
from app.core.config import settings
from app.core.errors import AppError
from app.models import Order, Payment, User
from app.schemas import RazorpayVerifyIn

log = logging.getLogger("ssa.payments")

RAZORPAY_API = "https://api.razorpay.com/v1"
# Ten seconds is longer than the gateway's p99 and short enough that a dead network does not hold
# a request thread for a minute. The call happens inside the checkout transaction; if it never
# returns, the order is rolled back and no money is owed.
GATEWAY_TIMEOUT_SECONDS = 10.0


def _hmac_hex(secret: str, message: bytes) -> str:
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def _require(value: str | None, name: str) -> str:
    if not (value or "").strip():
        raise AppError(503, "PAYMENTS_NOT_CONFIGURED", f"{name} is unset")
    return value.strip()


class PaymentProvider(ABC):
    name: str

    @abstractmethod
    def create_intent(self, order: Order) -> Payment:
        """A payment attempt for this order, unsaved and unsettled."""


class MockProvider(PaymentProvider):
    """No gateway. `POST /payments/{order_id}/mock-confirm` settles the row by assertion."""

    name = "mock"

    def create_intent(self, order: Order) -> Payment:
        return Payment(
            order_id=order.id,
            provider="mock",
            status="created",
            amount=order.total,
            raw={"simulated": True},
        )


class RazorpayProvider(PaymentProvider):
    """Real orders through the Razorpay Orders API.

    `provider_ref` holds the Razorpay **order** id (`order_...`) rather than the payment id: every
    event and callback carries it, so it is what an incoming webhook can look the row up by. The
    payment ids seen against it are appended to `raw["payments"]` instead - a customer who retries
    after a failure can produce two, and the treasurer has to be able to see that.
    """

    name = "razorpay"

    def keys(self) -> tuple[str, str]:
        return (
            _require(settings.RAZORPAY_KEY_ID, "RAZORPAY_KEY_ID"),
            _require(settings.RAZORPAY_KEY_SECRET, "RAZORPAY_KEY_SECRET"),
        )

    def create_intent(self, order: Order) -> Payment:
        key_id, key_secret = self.keys()
        body = {
            "amount": order.total,
            "currency": order.currency or "INR",
            "receipt": str(order.id),  # the API caps this at 40 characters; a UUID is 36
            "notes": {"kind": order.kind, "order_id": str(order.id)},
        }
        try:
            response = httpx.post(
                f"{RAZORPAY_API}/orders",
                json=body,
                auth=(key_id, key_secret),
                timeout=GATEWAY_TIMEOUT_SECONDS,
            )
        except httpx.HTTPError as exc:
            raise AppError(
                502,
                "PAYMENT_GATEWAY_UNREACHABLE",
                "Could not reach the payment gateway",
                {"reason": str(exc)},
            ) from exc
        if response.status_code >= 400:
            # The body explains the refusal (bad key, amount below the minimum) and is safe to
            # pass on: it never contains the secret.
            raise AppError(
                502,
                "PAYMENT_GATEWAY_ERROR",
                "The payment gateway refused to create the order",
                {"status": response.status_code, "details": response.text[:400]},
            )
        payload = response.json()
        return Payment(
            order_id=order.id,
            provider="razorpay",
            provider_ref=payload["id"],
            status="created",
            amount=order.total,
            raw={"razorpay_order_id": payload["id"], "gateway_status": payload.get("status"), "payments": []},
        )


_PROVIDERS: dict[str, type[PaymentProvider]] = {"mock": MockProvider, "razorpay": RazorpayProvider}


def get_provider() -> PaymentProvider:
    try:
        return _PROVIDERS[settings.PAYMENTS_PROVIDER]()
    except KeyError:
        raise RuntimeError(
            f"Unknown PAYMENTS_PROVIDER {settings.PAYMENTS_PROVIDER!r}; known: {', '.join(sorted(_PROVIDERS))}"
        ) from None


def create_intent(db: Session, order: Order) -> Payment:
    """The one call every checkout makes. Caller owns the transaction."""
    payment = get_provider().create_intent(order)
    db.add(payment)
    return payment


def settle(db: Session, payment: Payment, outcome: str) -> str:
    """Applies a gateway outcome. Returns the new payment status."""
    if outcome == "success":
        payment.status = "succeeded"
        payment.provider_ref = payment.provider_ref or f"mock_{uuid.uuid4().hex}"
    else:
        payment.status = "failed"
    payment.raw = {**(payment.raw or {}), "outcome": outcome}
    return payment.status


def latest_payment(db: Session, order_id: UUID) -> Payment | None:
    return db.scalar(select(Payment).where(Payment.order_id == order_id).order_by(Payment.created_at.desc()))


def record_gateway_payment(
    payment: Payment, gateway_payment_id: str | None, amount: int | None, status: str | None
) -> None:
    """Append what the gateway told us about this attempt. Kept as a list, not overwritten: two
    successful payments against one order is exactly the case a refund has to be raised for."""
    if not gateway_payment_id:
        return
    raw = dict(payment.raw or {})
    seen = [p for p in raw.get("payments", []) if p.get("id") != gateway_payment_id]
    raw["payments"] = [
        *seen,
        {"id": gateway_payment_id, "amount": amount, "status": status},
    ]
    payment.raw = raw


# --- signature verification -----------------------------------------------------------------


def verify_webhook_signature(raw_body: bytes, signature: str | None) -> None:
    """Razorpay signs the raw body bytes with the webhook secret.

    Nothing in the request may be parsed, trusted or acted on before this passes: an unverified
    webhook endpoint is a free-money endpoint (M2_BACKLOG §1).
    """
    secret = _require(settings.RAZORPAY_WEBHOOK_SECRET, "RAZORPAY_WEBHOOK_SECRET")
    if not signature or not hmac.compare_digest(_hmac_hex(secret, raw_body), signature):
        raise AppError(400, "INVALID_SIGNATURE", "The webhook signature does not match the body")


def verify_checkout_signature(gateway_order_id: str, gateway_payment_id: str, signature: str) -> None:
    """The Checkout widget's callback signs `order_id|payment_id` with the API **key secret** -
    a different secret from the webhook's, and the only thing standing between a client callback
    and a settled order."""
    _, key_secret = RazorpayProvider().keys()
    expected = _hmac_hex(key_secret, f"{gateway_order_id}|{gateway_payment_id}".encode())
    if not hmac.compare_digest(expected, signature):
        raise AppError(400, "INVALID_SIGNATURE", "The payment signature does not match the checkout")


# --- entry points ---------------------------------------------------------------------------


def _authorise(db: Session, order_id: UUID, actor: User) -> Order:
    order = db.get(Order, order_id)
    if order is None:
        raise AppError(404, "ORDER_NOT_FOUND", "Order not found", {"order_id": str(order_id)})
    if order.user_id != actor.id and not has_permission(db, actor, "orders.manage"):
        raise AppError(403, "FORBIDDEN", "You can only confirm your own orders")
    return order


def confirm_mock_payment(db: Session, order_id: UUID, outcome: str, actor: User) -> dict:
    """POST /payments/{order_id}/mock-confirm.

    Refused unless the mock provider is configured: on a live deployment nobody may settle an order
    by asserting an outcome.
    """
    if settings.PAYMENTS_PROVIDER != "mock":
        raise AppError(
            409,
            "SIMULATED_PAYMENT_DISABLED",
            "This deployment takes real payments; a simulated outcome cannot settle an order",
        )
    return dispatch(db, _authorise(db, order_id, actor), outcome)


def verify_client_payment(db: Session, order_id: UUID, payload: RazorpayVerifyIn, actor: User) -> dict:
    """POST /payments/{order_id}/verify - the Checkout widget's success callback.

    The webhook is the authority, but it can lag or never arrive (no public URL in dev), and the
    customer is standing there watching. Both paths land on the same idempotent claim, so whichever
    arrives first settles and the other replays.
    """
    order = _authorise(db, order_id, actor)
    payment = latest_payment(db, order.id)
    if payment is None:
        raise AppError(404, "PAYMENT_NOT_FOUND", "This order has no payment")
    if payment.provider != "razorpay":
        raise AppError(409, "NOT_A_GATEWAY_PAYMENT", "This order is not paid through Razorpay")
    if payload.razorpay_order_id != payment.provider_ref:
        raise AppError(400, "ORDER_MISMATCH", "That payment belongs to a different order")

    verify_checkout_signature(payload.razorpay_order_id, payload.razorpay_payment_id, payload.razorpay_signature)
    record_gateway_payment(payment, payload.razorpay_payment_id, payment.amount, "captured")
    return dispatch(db, order, "success")


# `order.paid` is the order-level signal; `payment.captured` is the payment-level one. Both mean
# the money is in, and Razorpay may send either (or both - the claim below makes the second a
# replay). Anything not listed here is acknowledged and ignored so it is not retried forever.
_EVENTS = {"payment.captured": "success", "order.paid": "success", "payment.failed": "fail"}


def handle_webhook(db: Session, event: dict) -> dict | None:
    """Settle the order a gateway event refers to. None means "no action", which the router still
    answers 200 to - a 4xx would have Razorpay retry a no-op until it gives up."""
    name = event.get("event")
    outcome = _EVENTS.get(name)
    if outcome is None:
        log.info("payments: ignoring webhook event %s", name)
        return None

    payload = event.get("payload") or {}
    payment_entity = (payload.get("payment") or {}).get("entity") or {}
    order_entity = (payload.get("order") or {}).get("entity") or {}
    gateway_order_id = payment_entity.get("order_id") or order_entity.get("id")
    if not gateway_order_id:
        raise AppError(400, "MALFORMED_WEBHOOK", "The event carries no gateway order id")

    payment = db.scalar(select(Payment).where(Payment.provider_ref == gateway_order_id))
    if payment is None:
        raise AppError(
            404, "PAYMENT_NOT_FOUND", "No payment for that gateway order", {"gateway_order_id": gateway_order_id}
        )

    amount = payment_entity.get("amount")
    if outcome == "success" and isinstance(amount, int) and amount != payment.amount:
        # Money moved, but not the money we asked for. Settling would put a wrong number in the
        # ledger, so refuse loudly instead - and the dashboard shows the non-200.
        raise AppError(
            400,
            "AMOUNT_MISMATCH",
            "The paid amount does not match the order",
            {"expected": payment.amount, "received": amount},
        )

    record_gateway_payment(payment, payment_entity.get("id"), amount, payment_entity.get("status"))
    log.info("payments: webhook %s for gateway order %s", name, gateway_order_id)
    return dispatch(db, payment.order, outcome)


def dispatch(db: Session, order: Order, outcome: str) -> dict:
    """Hand the outcome to the handler for this order's kind.

    Every handler keeps its work in ONE transaction and is idempotent: the conditional
    pending->paid claim is the lock, so a repeated webhook, a client verify racing the webhook, or
    two different events for one payment all settle exactly once and the loser replays the stored
    result (DESIGN.md §4 rule 3).
    """
    from app.services import memberships, merch, tickets  # local: all three import this module

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


def payment_intent(db: Session, order_id: UUID, actor: User) -> dict:
    """What the checkout page needs to open the gateway, and to redraw itself after a reload or a
    redirect back from a bank page (where `location.state` is long gone)."""
    order = _authorise(db, order_id, actor)
    payment = latest_payment(db, order.id)
    key_id = None
    if payment is not None and payment.provider == "razorpay":
        key_id = _require(settings.RAZORPAY_KEY_ID, "RAZORPAY_KEY_ID")
    return {
        "order_id": order.id,
        "kind": order.kind,
        "order_status": order.status,
        "amount": order.total,
        "currency": order.currency,
        "provider": payment.provider if payment else "mock",
        "payment_status": payment.status if payment else None,
        "key_id": key_id,
        "gateway_order_id": payment.provider_ref if payment and payment.provider == "razorpay" else None,
    }


def load_webhook_event(raw_body: bytes) -> dict:
    try:
        event = json.loads(raw_body)
    except ValueError as exc:
        raise AppError(400, "MALFORMED_WEBHOOK", "The body is not JSON") from exc
    if not isinstance(event, dict):
        raise AppError(400, "MALFORMED_WEBHOOK", "The body is not a JSON object")
    return event
