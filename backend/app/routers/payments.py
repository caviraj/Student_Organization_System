from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.models import User
from app.schemas import MockConfirmIn, PaymentIntentOut, PaymentResultOut, RazorpayVerifyIn, WebhookAckOut
from app.services import payments

router = APIRouter(prefix="/payments", tags=["payments"])


@router.get(
    "/{order_id}",
    response_model=PaymentIntentOut,
    summary="What the checkout page needs to open the gateway (owner or admin)",
)
def get_intent(
    order_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return payments.payment_intent(db, order_id, user)


@router.post(
    "/{order_id}/verify",
    response_model=PaymentResultOut,
    summary="Verify the Checkout widget's success callback and settle the order (owner or admin)",
)
def verify(
    order_id: UUID,
    payload: RazorpayVerifyIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return payments.verify_client_payment(db, order_id, payload, user)


@router.post(
    "/webhook",
    response_model=WebhookAckOut,
    summary="Razorpay webhook (signature-verified; unauthenticated by design)",
)
async def webhook(request: Request, db: Session = Depends(get_db)):
    # Read the raw bytes BEFORE anything parses them: the signature covers the exact body, and
    # FastAPI's JSON binding would have consumed it (M2_BACKLOG §1). Nothing below this line may
    # run on an unverified body.
    raw_body = await request.body()
    payments.verify_webhook_signature(raw_body, request.headers.get("X-Razorpay-Signature"))
    result = payments.handle_webhook(db, payments.load_webhook_event(raw_body))
    return {"status": "ignored" if result is None else "processed", "order_id": (result or {}).get("order_id")}


@router.post(
    "/{order_id}/mock-confirm",
    response_model=PaymentResultOut,
    summary="Simulate the gateway result for an order (owner or admin; mock provider only)",
)
def mock_confirm(
    order_id: UUID,
    payload: MockConfirmIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return payments.confirm_mock_payment(db, order_id, payload.outcome, user)
