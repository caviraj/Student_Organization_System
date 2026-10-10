from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.models import User
from app.schemas import MockConfirmIn, PaymentResultOut
from app.services.payments import confirm_mock_payment

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post(
    "/{order_id}/mock-confirm",
    response_model=PaymentResultOut,
    summary="Simulate the gateway result for an order (owner or admin)",
)
def mock_confirm(
    order_id: UUID,
    payload: MockConfirmIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return confirm_mock_payment(db, order_id, payload.outcome, user)
