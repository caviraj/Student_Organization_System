"""The shop front and the stockroom (DESIGN.md §5, Products)."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_optional_user, require_role
from app.core.errors import AppError
from app.models import User
from app.schemas import (
    Page,
    ProductCreateIn,
    ProductOut,
    ProductUpdateIn,
    StockAdjustIn,
    StockMovementOut,
    VariantCreateIn,
    VariantOut,
    VariantUpdateIn,
)
from app.services import inventory
from app.services import merch as merch_service

router = APIRouter(prefix="/products", tags=["Products"])
variant_router = APIRouter(prefix="/variants", tags=["Products"])


@router.get("", response_model=Page[ProductOut], summary="Browse products (public; token adds member pricing)")
def list_products(
    q: str | None = Query(default=None, description="Search name or description"),
    include_inactive: bool = Query(default=False, description="Admin only: include retired products"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    if include_inactive and (user is None or user.role != "admin"):
        raise AppError(403, "FORBIDDEN", "Requires role: admin", {"your_role": user.role if user else "guest"})

    rows, total = merch_service.list_products(
        db, user, q=q, include_inactive=include_inactive, page=page, page_size=page_size
    )
    return {
        "items": [merch_service.product_view(db, p, user, include_inactive=include_inactive) for p in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{product_id}", response_model=ProductOut, summary="One product (public; retired products are 404)")
def get_product(
    product_id: UUID,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    is_admin = user is not None and user.role == "admin"
    product = merch_service.get_product(db, product_id, include_inactive=is_admin)
    return merch_service.product_view(db, product, user, include_inactive=is_admin)


@router.post("", response_model=ProductOut, status_code=201, summary="Create a product (admin)")
def create_product(
    payload: ProductCreateIn,
    user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    product = merch_service.create_product(db, payload.model_dump())
    return merch_service.product_view(db, product, user, include_inactive=True)


@router.patch("/{product_id}", response_model=ProductOut, summary="Update a product (admin)")
def update_product(
    product_id: UUID,
    payload: ProductUpdateIn,
    user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    product = merch_service.get_product(db, product_id, include_inactive=True)
    updated = merch_service.update_product(db, product, payload.model_dump(exclude_unset=True))
    return merch_service.product_view(db, updated, user, include_inactive=True)


@router.post(
    "/{product_id}/variants",
    response_model=VariantOut,
    status_code=201,
    summary="Add a size/variant (admin)",
)
def create_variant(
    product_id: UUID,
    payload: VariantCreateIn,
    user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    product = merch_service.get_product(db, product_id, include_inactive=True)
    variant = merch_service.create_variant(db, product, payload.model_dump(), user)
    return merch_service.variant_view(variant)


@variant_router.patch(
    "/{variant_id}", response_model=VariantOut, summary="Update a variant (admin; stock moves via stock-adjust)"
)
def update_variant(
    variant_id: UUID,
    payload: VariantUpdateIn,
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    variant = merch_service.get_variant(db, variant_id)
    return merch_service.variant_view(merch_service.update_variant(db, variant, payload.model_dump(exclude_unset=True)))


@variant_router.post(
    "/{variant_id}/stock-adjust",
    response_model=VariantOut,
    summary="Restock or write off stock (admin)",
)
def adjust_stock(
    variant_id: UUID,
    payload: StockAdjustIn,
    user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    variant = merch_service.get_variant(db, variant_id)
    inventory.adjust_stock(db, variant, payload.delta, payload.reason, user, payload.note)
    db.commit()
    db.refresh(variant)
    return merch_service.variant_view(variant)


@variant_router.get(
    "/{variant_id}/stock-movements",
    response_model=Page[StockMovementOut],
    summary="Stock audit trail, newest first (admin)",
)
def stock_movements(
    variant_id: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    items, total = merch_service.stock_movements(db, variant_id, page=page, page_size=page_size)
    return {"items": items, "total": total, "page": page, "page_size": page_size}
