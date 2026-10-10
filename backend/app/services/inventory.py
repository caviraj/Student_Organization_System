"""Stock and seat reservation (DESIGN.md §4 rules 2 and 12).

The conditional UPDATE is the lock. Never read-then-write: two buyers arriving together
must not both see "1 left" and both succeed.
"""

from uuid import UUID

from sqlalchemy import case, func, select, update
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import Order, OrderItem, ProductVariant, StockMovement, TicketType, User


def reserve_seats(db: Session, ticket_type_id: UUID, qty: int) -> None:
    """Atomically claim `qty` seats. 0 rows updated means the seats were not there."""
    claimed = db.execute(
        update(TicketType)
        .where(TicketType.id == ticket_type_id, TicketType.sold_count + qty <= TicketType.capacity)
        .values(sold_count=TicketType.sold_count + qty, updated_at=func.now())
        .execution_options(synchronize_session=False)
    ).rowcount
    if not claimed:
        # Fresh SELECT, not the identity map: the point is to report the *current* count.
        seats_left = db.scalar(
            select(TicketType.capacity - TicketType.sold_count).where(TicketType.id == ticket_type_id)
        )
        raise AppError(
            409,
            "SOLD_OUT",
            "Not enough seats left",
            {"seats_left": max(seats_left or 0, 0), "requested": qty},
        )


def release_seats(db: Session, ticket_type_id: UUID, qty: int) -> None:
    """Give seats back. Clamped at 0 so a double release can never drive the count negative
    (the CHECK constraint would turn that into a 500)."""
    db.execute(
        update(TicketType)
        .where(TicketType.id == ticket_type_id)
        .values(
            sold_count=case((TicketType.sold_count >= qty, TicketType.sold_count - qty), else_=0),
            updated_at=func.now(),
        )
        .execution_options(synchronize_session=False)
    )


# --- merch stock (Phase 4) ----------------------------------------------------------------------


def _record(
    db: Session,
    variant_id: UUID,
    delta: int,
    reason: str,
    user: User | None,
    order_id: UUID | None = None,
    note: str | None = None,
) -> None:
    """One audit row per change, added to the caller's transaction - never committed here."""
    db.add(
        StockMovement(
            variant_id=variant_id,
            delta=delta,
            reason=reason,
            order_id=order_id,
            created_by=user.id if user else None,
            note=note,
        )
    )


def reserve_stock(db: Session, items: list[tuple[ProductVariant, int]], user: User, order_id: UUID) -> None:
    """Atomically take `qty` of each variant, writing the audit row for each line.

    Lines are sorted by variant id so two checkouts holding overlapping lines always take their row
    locks in the same order - otherwise they could deadlock (Postgres kills one with a 500). Every
    line is in the caller's transaction: one failure means nothing was reserved.
    """
    for variant, qty in sorted(items, key=lambda pair: pair[0].id.hex):
        claimed = db.execute(
            update(ProductVariant)
            .where(ProductVariant.id == variant.id, ProductVariant.stock >= qty, ProductVariant.is_active.is_(True))
            .values(stock=ProductVariant.stock - qty, updated_at=func.now())
            .execution_options(synchronize_session=False)
        ).rowcount
        if not claimed:
            available = db.scalar(select(ProductVariant.stock).where(ProductVariant.id == variant.id)) or 0
            raise AppError(
                409,
                "OUT_OF_STOCK",
                f"Only {available} left of {variant.product.name} ({variant.size})",
                {
                    "variant_id": str(variant.id),
                    "product_name": variant.product.name,
                    "size": variant.size,
                    "available": available,
                    "requested": qty,
                },
            )
        _record(db, variant.id, -qty, "sale", user, order_id=order_id)


def release_stock(db: Session, order: Order, user: User | None = None) -> bool:
    """Give an order's stock back (a failed payment, or an abandoned checkout). Returns whether
    anything was released.

    Idempotent by marker: the order row is locked FIRST (`SELECT ... FOR UPDATE`), then
    `meta.stock_released` is checked, so two sweeps racing over the same order cannot both credit
    the stock back. The marker is written inside this same transaction, so it is only ever set if
    the credit really happened.
    """
    # A pending change to this order (the sweep cancelling it, a payment failing) has to reach the
    # row before the refresh below reads it back - autoflush is off, so the refresh would otherwise
    # silently undo that change.
    db.flush()
    db.execute(select(Order.id).where(Order.id == order.id).with_for_update()).scalar()
    db.refresh(order)  # the lock is what makes this read authoritative
    meta = order.meta or {}
    if meta.get("stock_released"):
        return False

    items = list(db.scalars(select(OrderItem).where(OrderItem.order_id == order.id, OrderItem.item_type == "variant")))
    for item in items:
        variant = db.get(ProductVariant, item.item_id)
        if variant is None:  # the variant was deleted with its product; nothing to credit
            continue
        db.execute(
            update(ProductVariant)
            .where(ProductVariant.id == variant.id)
            .values(stock=ProductVariant.stock + item.quantity, updated_at=func.now())
            .execution_options(synchronize_session=False)
        )
        _record(db, variant.id, item.quantity, "release", user, order_id=order.id)

    order.meta = {**meta, "stock_released": True}
    db.flush()
    return bool(items)


def adjust_stock(db: Session, variant: ProductVariant, delta: int, reason: str, user: User, note: str | None) -> int:
    """Manual correction or restock. The UPDATE refuses to go below zero, so the CHECK constraint
    is never the thing that fails. Returns the new stock."""
    changed = db.execute(
        update(ProductVariant)
        .where(ProductVariant.id == variant.id, ProductVariant.stock + delta >= 0)
        .values(stock=ProductVariant.stock + delta, updated_at=func.now())
        .execution_options(synchronize_session=False)
    ).rowcount
    if not changed:
        raise AppError(
            409,
            "NEGATIVE_STOCK",
            "That change would take the stock below zero",
            {"variant_id": str(variant.id), "stock": variant.stock, "delta": delta},
        )
    _record(db, variant.id, delta, reason, user, note=note)
    return variant.stock + delta


def opening_stock(db: Session, variant: ProductVariant, user: User | None = None) -> None:
    """The `initial` audit row for a freshly created variant, so SUM(delta) rebuilds the stock."""
    if variant.stock:
        _record(db, variant.id, variant.stock, "initial", user)
