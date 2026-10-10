"""Orders as their owner sees them, and merch checkout (DESIGN.md §5, Merch Orders).

Phase 4 adds the first customer-facing order view: tickets and memberships were each read
through their own receipt endpoint. `GET /orders/me` and `GET /orders/{id}` show any kind.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.models import User
from app.schemas import (
    MerchCheckoutIn,
    MerchCheckoutOut,
    OrderOut,
    Page,
)
from app.services import merch as merch_service

router = APIRouter(prefix="/orders", tags=["Merch Orders"])


@router.post(
    "/merch/checkout",
    response_model=MerchCheckoutOut,
    status_code=201,
    summary="Order merch (auth; active members unless MERCH_MEMBERS_ONLY=false)",
)
def merch_checkout(
    payload: MerchCheckoutIn,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=64),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order, payment = merch_service.create_merch_checkout(
        db,
        user,
        [item.model_dump() for item in payload.items],
        payload.delivery_method,
        payload.delivery_note,
        idempotency_key,
    )
    return merch_service.checkout_view(order, payment)


@router.get("/me", response_model=Page[OrderOut], summary="My orders, newest first (auth)")
def my_orders(
    kind: str | None = Query(default=None, pattern="^(membership|ticket|merch)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows, total = merch_service.list_user_orders(db, user, kind=kind, page=page, page_size=page_size)
    return {"items": merch_service.orders_view(db, rows), "total": total, "page": page, "page_size": page_size}


@router.get("/{order_id}", response_model=OrderOut, summary="One order with its payment and fulfilment (owner or admin)")
def get_order(
    order_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = merch_service.get_user_order(db, order_id, user)
    return merch_service.orders_view(db, [order])[0]
