"""The fulfilment desk: what to pack, what to hand over, what to reorder (DESIGN.md §5, Merch Admin)."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_role
from app.models import User
from app.schemas import (
    FulfilmentUpdateIn,
    MerchAdminOrderOut,
    MerchAdminOrdersOut,
    StockSummaryOut,
)
from app.services import merch as merch_service
from app.services import reports

router = APIRouter(prefix="/admin/merch", tags=["Merch Admin"])


@router.get(
    "/orders",
    response_model=MerchAdminOrdersOut,
    summary="Fulfilment board, newest first (admin)",
)
def admin_orders(
    fulfilment_status: str | None = Query(default=None, pattern="^(paid|packed|handed_over)$"),
    product_id: UUID | None = Query(default=None, description="Only orders holding this product"),
    size: str | None = Query(default=None, description="Only orders holding this size"),
    q: str | None = Query(default=None, description="Search buyer name, email or member code"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    rows, total, counts = merch_service.admin_orders(
        db,
        fulfilment_status=fulfilment_status,
        product_id=product_id,
        size=size,
        q=q,
        page=page,
        page_size=page_size,
    )
    orders = [row[0] for row in rows]
    lines = merch_service.admin_lines(db, orders)
    return {
        "counts": counts,
        "items": {
            "items": [
                merch_service.admin_order_view(order, fulfilment, buyer, lines[order.id])
                for order, fulfilment, buyer in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    }


@router.patch(
    "/orders/{order_id}",
    response_model=MerchAdminOrderOut,
    summary="Move an order to packed / handed_over (admin)",
)
def update_fulfilment(
    order_id: UUID,
    payload: FulfilmentUpdateIn,
    user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    merch_service.update_fulfilment(db, order_id, payload.fulfilment_status, user)
    return merch_service.admin_order(db, order_id)


@router.get("/stock-summary", response_model=StockSummaryOut, summary="Stock, sales and demand by size (admin)")
def stock_summary(_: User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    return reports.stock_summary(db)
