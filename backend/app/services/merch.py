"""The shop: products, variants, checkout, fulfilment (PRD FR-4, DESIGN.md §4 rules 12-13).

Stock is reserved at checkout, in the same transaction as the order, and released when the order
dies (a failed payment, or 15 idle minutes). Payment success does NOT touch stock again: it only
writes the fulfilment row and the ledger entry.
"""

import uuid
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError
from app.models import (
    MembershipPlan,
    MerchOrder,
    Order,
    OrderItem,
    Payment,
    Product,
    ProductVariant,
    StockMovement,
    TicketType,
    User,
)
from app.services import ledger, payments, pricing
from app.services.inventory import opening_stock, release_stock, reserve_stock
from app.services.tickets import PENDING_ORDER_TTL_MINUTES

MAX_LINES = 5
MAX_QTY_PER_LINE = 5
MIN_DELIVERY_NOTE = 5
ADMIN_PAGE = 100

# One step forward only: a parcel is packed before it is handed over (PRD FR-4.4).
NEXT_FULFILMENT: dict[str, str | None] = {"paid": "packed", "packed": "handed_over", "handed_over": None}


# --- views ------------------------------------------------------------------------------------


def stock_status(stock: int, threshold: int) -> str:
    if stock <= 0:
        return "out_of_stock"
    return "low" if stock <= threshold else "in_stock"


def variant_view(variant: ProductVariant) -> dict:
    return {
        "id": variant.id,
        "size": variant.size,
        "color": variant.color,
        "sku": variant.sku,
        "stock": variant.stock,
        "stock_status": stock_status(variant.stock, variant.low_stock_threshold),
        "is_active": variant.is_active,
    }


def product_view(db: Session, product: Product, user: User | None, *, include_inactive: bool = False) -> dict:
    """A shop row. `price_for_you` is null for an anonymous caller - there is no "you" to price
    for - and `is_member_price` says whether member pricing applied at all (DESIGN.md §5)."""
    variants = [v for v in product.variants if include_inactive or v.is_active]
    unit_price, _pct, _source = pricing.resolve_merch_unit_price(db, user, product)
    return {
        "id": product.id,
        "name": product.name,
        "description": product.description,
        "image_url": product.image_url,
        "base_price": product.base_price,
        "member_discount_pct": product.member_discount_pct,
        "is_active": product.is_active,
        # One price level per product in M1, so both ends are equal - the shop grid renders
        # "from Rs X" and stays correct if per-size pricing ever arrives.
        "price_range": {"min": unit_price, "max": unit_price},
        "total_stock": sum(v.stock for v in variants),
        "variants": [variant_view(v) for v in variants],
        "price_for_you": unit_price if user is not None else None,
        "is_member_price": pricing.is_active_member(db, user) if user is not None else None,
    }


# --- products & variants ----------------------------------------------------------------------


def list_products(
    db: Session,
    user: User | None,
    *,
    q: str | None = None,
    include_inactive: bool = False,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Product], int]:
    conditions = []
    if not include_inactive:
        conditions.append(Product.is_active.is_(True))
    if q:
        like = f"%{q}%"
        conditions.append(or_(Product.name.ilike(like), Product.description.ilike(like)))

    total = db.scalar(select(func.count()).select_from(Product).where(*conditions)) or 0
    rows = db.scalars(
        select(Product)
        .where(*conditions)
        .order_by(Product.name, Product.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return list(rows), total


def get_product(db: Session, product_id: UUID, *, include_inactive: bool = False) -> Product:
    product = db.get(Product, product_id)
    # A retired product is 404 to shoppers, exactly as if it had never existed.
    if product is None or (not product.is_active and not include_inactive):
        raise AppError(404, "PRODUCT_NOT_FOUND", "No product with that id", {"product_id": str(product_id)})
    return product


def get_variant(db: Session, variant_id: UUID) -> ProductVariant:
    variant = db.get(ProductVariant, variant_id)
    if variant is None:
        raise AppError(404, "VARIANT_NOT_FOUND", "No variant with that id", {"variant_id": str(variant_id)})
    return variant


def create_product(db: Session, data: dict) -> Product:
    product = Product(
        name=data["name"],
        description=data.get("description"),
        image_url=data.get("image_url"),
        base_price=data["base_price"],
        member_discount_pct=data.get("member_discount_pct", 0),
        is_active=data.get("is_active", True),
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


def update_product(db: Session, product: Product, data: dict) -> Product:
    for key, value in data.items():
        setattr(product, key, value)
    db.commit()
    db.refresh(product)
    return product


def _assert_variant_free(db: Session, product_id: UUID, size: str, color: str | None, *, exclude: UUID | None = None) -> None:
    """The unique index covers (product_id, size, color), but Postgres treats NULLs as distinct -
    so a colourless variant needs this check to be unique at all."""
    conditions = [ProductVariant.product_id == product_id, ProductVariant.size == size]
    conditions.append(ProductVariant.color.is_(None) if color is None else ProductVariant.color == color)
    if exclude is not None:
        conditions.append(ProductVariant.id != exclude)
    if db.scalar(select(ProductVariant.id).where(*conditions)):
        raise AppError(
            409,
            "VARIANT_TAKEN",
            f"{size}{' / ' + color if color else ''} already exists for this product",
            {"product_id": str(product_id), "size": size, "color": color},
        )


def _assert_sku_free(db: Session, sku: str, *, exclude: UUID | None = None) -> None:
    # shortcut: check-then-insert. The unique index is the real guard; this turns the ordinary
    # case (a typo'd SKU) into a 409 instead of an IntegrityError.
    conditions = [ProductVariant.sku == sku]
    if exclude is not None:
        conditions.append(ProductVariant.id != exclude)
    if db.scalar(select(ProductVariant.id).where(*conditions)):
        raise AppError(409, "SKU_TAKEN", "That SKU is already in use", {"sku": sku})


def create_variant(db: Session, product: Product, data: dict, actor: User) -> ProductVariant:
    _assert_variant_free(db, product.id, data["size"], data.get("color"))
    _assert_sku_free(db, data["sku"])
    variant = ProductVariant(
        product_id=product.id,
        size=data["size"],
        color=data.get("color"),
        sku=data["sku"],
        stock=data.get("stock", 0),
        low_stock_threshold=data.get("low_stock_threshold", 5),
        is_active=data.get("is_active", True),
    )
    db.add(variant)
    db.flush()
    opening_stock(db, variant, actor)  # the audit trail starts at the opening balance
    db.commit()
    db.refresh(variant)
    return variant


def update_variant(db: Session, variant: ProductVariant, data: dict) -> ProductVariant:
    """Stock is deliberately not editable here: it moves through stock-adjust, which writes the
    audit row."""
    size = data.get("size", variant.size)
    color = data.get("color", variant.color)
    if size != variant.size or color != variant.color:
        _assert_variant_free(db, variant.product_id, size, color, exclude=variant.id)
    if "sku" in data and data["sku"] != variant.sku:
        _assert_sku_free(db, data["sku"], exclude=variant.id)

    for key, value in data.items():
        setattr(variant, key, value)
    db.commit()
    db.refresh(variant)
    return variant


# --- checkout ---------------------------------------------------------------------------------


def create_merch_checkout(
    db: Session,
    user: User,
    items: list[dict],
    delivery_method: str = "pickup",
    delivery_note: str | None = None,
    idempotency_key: str | None = None,
) -> tuple[Order, Payment]:
    """Reserve the stock, write the order, the lines and the payment intent - one transaction.

    Stock is taken HERE rather than at payment, so two shoppers cannot both be told the last
    medium hoodie is theirs (DESIGN.md §4 rule 12).
    """
    if not 1 <= len(items) <= MAX_LINES:
        raise AppError(422, "VALIDATION_ERROR", f"An order takes between 1 and {MAX_LINES} lines")
    if len({str(item["variant_id"]) for item in items}) != len(items):
        raise AppError(422, "DUPLICATE_VARIANT", "Each variant may appear only once - raise its qty instead")
    for item in items:
        if not 1 <= item["qty"] <= MAX_QTY_PER_LINE:
            raise AppError(422, "VALIDATION_ERROR", f"qty must be between 1 and {MAX_QTY_PER_LINE}")

    if delivery_method == "campus_delivery":
        delivery_note = (delivery_note or "").strip()
        if len(delivery_note) < MIN_DELIVERY_NOTE:
            raise AppError(
                422,
                "DELIVERY_NOTE_REQUIRED",
                f"A campus delivery needs a block/room note ({MIN_DELIVERY_NOTE}+ characters)",
            )
    else:
        delivery_note = (delivery_note or "").strip() or None

    if idempotency_key:
        existing = db.scalar(
            select(Order).where(Order.idempotency_key == idempotency_key, Order.user_id == user.id)
        )
        if existing is not None:
            return existing, payments.latest_payment(db, existing.id)

    if settings.MERCH_MEMBERS_ONLY and not pricing.is_active_member(db, user):
        raise AppError(
            403,
            "MEMBERSHIP_REQUIRED",
            "Merch is for members: join or renew your membership to place an order",
            {"merch_members_only": True},
        )

    lines = []
    for item in items:
        variant = get_variant(db, item["variant_id"])
        if not variant.is_active or not variant.product.is_active:
            raise AppError(
                409,
                "PRODUCT_UNAVAILABLE",
                f"{variant.product.name} ({variant.size}) is no longer on sale",
                {"variant_id": str(variant.id), "product_name": variant.product.name, "size": variant.size},
            )
        unit_price, pct, source = pricing.resolve_merch_unit_price(db, user, variant.product)
        lines.append({"variant": variant, "qty": item["qty"], "unit_price": unit_price, "pct": pct, "source": source})

    subtotal = sum(line["variant"].product.base_price * line["qty"] for line in lines)
    total = sum(line["unit_price"] * line["qty"] for line in lines)
    if total <= 0:
        raise AppError(422, "VALIDATION_ERROR", "Order total must be greater than zero")

    order = Order(
        user_id=user.id,
        kind="merch",
        status="pending",
        subtotal=subtotal,
        discount=subtotal - total,
        total=total,
        currency="INR",
        meta={
            "delivery_method": delivery_method,
            "delivery_note": delivery_note,
            # The receipt line, frozen: a later price change never rewrites this order.
            "items": [
                {
                    "variant_id": str(line["variant"].id),
                    "product_name": line["variant"].product.name,
                    "size": line["variant"].size,
                    "color": line["variant"].color,
                    "qty": line["qty"],
                    "unit_price": line["unit_price"],
                    "base_price": line["variant"].product.base_price,
                    "discount_pct": line["pct"],
                    "discount_source": line["source"],
                    "line_total": line["unit_price"] * line["qty"],
                }
                for line in lines
            ],
        },
        idempotency_key=idempotency_key or uuid.uuid4().hex,
    )
    db.add(order)
    db.flush()

    for line in lines:
        db.add(
            OrderItem(
                order_id=order.id,
                item_type="variant",
                item_id=line["variant"].id,
                quantity=line["qty"],
                unit_price=line["unit_price"],
                line_total=line["unit_price"] * line["qty"],
            )
        )
    db.flush()

    try:
        reserve_stock(db, [(line["variant"], line["qty"]) for line in lines], user, order.id)
    except AppError:
        # All the lines or none: without this, the lines reserved before the failing one would be
        # held for 15 minutes by an order that never existed.
        db.rollback()
        raise

    payment = payments.create_mock_intent(db, order)
    db.commit()
    db.refresh(order)
    db.refresh(payment)
    return order, payment


def expires_at(order: Order) -> datetime:
    return order.created_at + timedelta(minutes=PENDING_ORDER_TTL_MINUTES)


def checkout_view(order: Order, payment: Payment | None) -> dict:
    meta = order.meta or {}
    return {
        "order_id": order.id,
        "payment_id": payment.id if payment else None,
        "amount": order.total,
        "subtotal": order.subtotal,
        "discount": order.discount,
        "items": meta.get("items", []),
        "delivery_method": meta.get("delivery_method", "pickup"),
        "provider": payment.provider if payment else "mock",
        "status": order.status,
        "expires_at": expires_at(order),
    }


# --- payment result, fulfilment ---------------------------------------------------------------


def fulfil_merch_order(db: Session, order: Order) -> MerchOrder:
    """Create the fulfilment row for a paid order. Idempotent: a replayed callback finds the row
    it already made (DESIGN.md §4 rule 13)."""
    existing = db.get(MerchOrder, order.id)
    if existing is not None:
        return existing
    meta = order.meta or {}
    fulfilment = MerchOrder(
        order_id=order.id,
        fulfilment_status="paid",
        delivery_method=meta.get("delivery_method", "pickup"),
        delivery_note=meta.get("delivery_note"),
    )
    db.add(fulfilment)
    db.flush()
    return fulfilment


def fulfilment_view(fulfilment: MerchOrder | None, order_id: UUID) -> dict | None:
    if fulfilment is None:
        return None
    return {
        "order_id": order_id,
        "fulfilment_status": fulfilment.fulfilment_status,
        "delivery_method": fulfilment.delivery_method,
        "delivery_note": fulfilment.delivery_note,
        "packed_at": fulfilment.packed_at,
        "handed_over_at": fulfilment.handed_over_at,
    }


def confirm_merch_payment(db: Session, order: Order, payment: Payment, outcome: str) -> dict:
    """The merch half of the gateway callback (reached via services.payments.confirm_mock_payment).

    Stock is NOT touched on success - it was reserved at checkout - so the whole job here is the
    fulfilment row and the ledger entry, once. The atomic pending->paid claim is what makes a
    second call change nothing.
    """
    if order.status == "cancelled":
        # The checkout expired and its stock went back on the shelf; taking the money now would
        # sell something we no longer hold.
        raise AppError(
            409,
            "ORDER_NOT_PAYABLE",
            "This order was cancelled because its checkout expired",
            {"order_id": str(order.id), "status": order.status},
        )

    if outcome == "fail":
        if order.status == "pending":
            order.status = "failed"
            payments.settle(db, payment, "fail")
            release_stock(db, order)
            db.commit()
        return merch_result(db, order, payment)

    order_id = order.id
    claimed = db.execute(
        update(Order).where(Order.id == order_id, Order.status == "pending").values(status="paid", updated_at=func.now())
    ).rowcount
    if not claimed:
        db.rollback()  # already settled - replay the stored result
        order = db.get(Order, order_id)
        return merch_result(db, order, payments.latest_payment(db, order_id))

    payments.settle(db, payment, "success")
    fulfil_merch_order(db, order)
    ledger.add_transaction(
        db,
        direction="in",
        amount=order.total,
        source="merch",
        ref_type="order",
        ref_id=order.id,
        note=f"Merch sale - {items_summary(db, order)}",
    )
    db.commit()
    db.refresh(order)
    return merch_result(db, order, payment)


def merch_result(db: Session, order: Order, payment: Payment | None) -> dict:
    return {
        "order_id": order.id,
        "payment_id": payment.id if payment else None,
        "order_status": order.status,
        "payment_status": payment.status if payment else None,
        "provider_ref": payment.provider_ref if payment else None,
        "membership": None,
        "tickets": None,
        "merch": fulfilment_view(db.get(MerchOrder, order.id), order.id),
    }


def update_fulfilment(db: Session, order_id: UUID, new_status: str, actor: User) -> MerchOrder:
    """paid -> packed -> handed_over, one step at a time (PRD FR-4.4)."""
    fulfilment = db.get(MerchOrder, order_id)
    if fulfilment is None:
        raise AppError(
            404,
            "MERCH_ORDER_NOT_FOUND",
            "No merch order with that id - an order gets one when its payment succeeds",
            {"order_id": str(order_id)},
        )
    allowed = NEXT_FULFILMENT[fulfilment.fulfilment_status]
    if new_status != allowed:
        raise AppError(
            409,
            "INVALID_TRANSITION",
            f"Cannot move a merch order from {fulfilment.fulfilment_status} to {new_status}",
            {"from": fulfilment.fulfilment_status, "to": new_status, "allowed": allowed},
        )
    now = datetime.now(UTC)
    fulfilment.fulfilment_status = new_status
    if new_status == "packed":
        fulfilment.packed_at = now
    else:
        fulfilment.handed_over_at = now
    fulfilment.handled_by = actor.id
    db.commit()
    db.refresh(fulfilment)
    return fulfilment


def release_expired_pending_merch_orders(
    db: Session, ttl_minutes: int = PENDING_ORDER_TTL_MINUTES, batch_size: int = ADMIN_PAGE
) -> dict:
    """Abandoned checkouts must not hold stock hostage (DESIGN.md §4 rule 12). Runs every 5
    minutes beside the ticket sweep; exposed so tests can drive it directly.

    Claimed with SKIP LOCKED, so two sweeps ticking together split the batch instead of fighting
    over it - and the release itself is idempotent, so a row seen twice still credits once.
    """
    cutoff = datetime.now(UTC) - timedelta(minutes=ttl_minutes)
    stale = list(
        db.scalars(
            select(Order)
            .where(Order.kind == "merch", Order.status == "pending", Order.created_at < cutoff)
            .order_by(Order.created_at)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
    )
    released = 0
    for order in stale:
        order.status = "cancelled"
        released += int(release_stock(db, order))
    db.commit()
    return {"cancelled": len(stale), "released": released}


# --- order history ----------------------------------------------------------------------------


def items_summary(db: Session, order: Order) -> str:
    """One readable packing list: "SSA Hoodie (M) x2, SSA T-Shirt (L) x1"."""
    parts = []
    for line, name in order_lines(db, order):
        parts.append(f"{name} x{line.quantity}")
    return ", ".join(parts) or "no items"


def order_lines(db: Session, order: Order) -> list[tuple[OrderItem, str]]:
    names = _item_names(db, [order])
    return [(item, names.get((item.item_type, item.item_id)) or item.item_type) for item in order.items]


def _item_names(db: Session, orders: list[Order]) -> dict[tuple[str, UUID], str]:
    """Item labels for a whole page of orders: one query per item type, never one per row."""
    ids: dict[str, set[UUID]] = {}
    for order in orders:
        for item in order.items:
            ids.setdefault(item.item_type, set()).add(item.item_id)

    names: dict[tuple[str, UUID], str] = {}
    if ids.get("plan"):
        for plan in db.scalars(select(MembershipPlan).where(MembershipPlan.id.in_(ids["plan"]))):
            names[("plan", plan.id)] = plan.name
    if ids.get("ticket_type"):
        for ticket_type in db.scalars(select(TicketType).where(TicketType.id.in_(ids["ticket_type"]))):
            names[("ticket_type", ticket_type.id)] = ticket_type.name
    if ids.get("variant"):
        for variant in db.scalars(select(ProductVariant).where(ProductVariant.id.in_(ids["variant"]))):
            names[("variant", variant.id)] = f"{variant.product.name} ({variant.size})"
    return names


def list_user_orders(
    db: Session, user: User, *, kind: str | None = None, page: int = 1, page_size: int = 20
) -> tuple[list[Order], int]:
    conditions = [Order.user_id == user.id]
    if kind:
        conditions.append(Order.kind == kind)
    total = db.scalar(select(func.count()).select_from(Order).where(*conditions)) or 0
    rows = db.scalars(
        select(Order)
        .where(*conditions)
        .order_by(Order.created_at.desc(), Order.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return list(rows), total


def orders_view(db: Session, orders: list[Order]) -> list[dict]:
    """The owner's view of a page of orders, whatever their kind. Batched: one query per relation
    for the whole page rather than a handful per order."""
    names = _item_names(db, orders)
    order_ids = [order.id for order in orders]
    if not order_ids:
        return []

    latest: dict[UUID, Payment] = {}
    for payment in db.scalars(
        select(Payment).where(Payment.order_id.in_(order_ids)).order_by(Payment.created_at)
    ):
        latest[payment.order_id] = payment
    fulfilments = {
        fulfilment.order_id: fulfilment
        for fulfilment in db.scalars(select(MerchOrder).where(MerchOrder.order_id.in_(order_ids)))
    }

    views = []
    for order in orders:
        fulfilment = fulfilments.get(order.id)
        meta = order.meta or {}
        views.append(
            {
                "id": order.id,
                "kind": order.kind,
                "status": order.status,
                "subtotal": order.subtotal,
                "discount": order.discount,
                "total": order.total,
                "currency": order.currency,
                "created_at": order.created_at,
                "items": [
                    {
                        "item_type": item.item_type,
                        "name": names.get((item.item_type, item.item_id)),
                        "quantity": item.quantity,
                        "unit_price": item.unit_price,
                        "line_total": item.line_total,
                    }
                    for item in order.items
                ],
                "payment_status": latest[order.id].status if order.id in latest else None,
                "fulfilment_status": fulfilment.fulfilment_status if fulfilment else None,
                "delivery_method": meta.get("delivery_method"),
                "delivery_note": meta.get("delivery_note"),
                "packed_at": fulfilment.packed_at if fulfilment else None,
                "handed_over_at": fulfilment.handed_over_at if fulfilment else None,
            }
        )
    return views


def get_user_order(db: Session, order_id: UUID, user: User) -> Order:
    order = db.get(Order, order_id)
    if order is None or (order.user_id != user.id and user.role != "admin"):
        # 404 for someone else's order: an order id is not a lookup key for other people's money.
        raise AppError(404, "ORDER_NOT_FOUND", "No order with that id", {"order_id": str(order_id)})
    return order


# --- admin board ------------------------------------------------------------------------------


def admin_orders(
    db: Session,
    *,
    fulfilment_status: str | None = None,
    product_id: UUID | None = None,
    size: str | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[tuple[Order, MerchOrder, User]], int, dict]:
    conditions = []
    if fulfilment_status:
        conditions.append(MerchOrder.fulfilment_status == fulfilment_status)
    if product_id or size:
        line_orders = select(OrderItem.order_id).join(
            ProductVariant, ProductVariant.id == OrderItem.item_id
        ).where(OrderItem.item_type == "variant")
        if product_id:
            line_orders = line_orders.where(ProductVariant.product_id == product_id)
        if size:
            line_orders = line_orders.where(ProductVariant.size == size)
        conditions.append(Order.id.in_(line_orders))
    if q:
        like = f"%{q}%"
        conditions.append(
            Order.user_id.in_(
                select(User.id).where(
                    or_(User.full_name.ilike(like), User.email.ilike(like), User.member_code.ilike(like))
                )
            )
        )

    total = (
        db.scalar(
            select(func.count())
            .select_from(MerchOrder)
            .join(Order, Order.id == MerchOrder.order_id)
            .where(*conditions)
        )
        or 0
    )
    rows = db.execute(
        select(Order, MerchOrder, User)
        .join(MerchOrder, MerchOrder.order_id == Order.id)
        .join(User, User.id == Order.user_id)
        .where(*conditions)
        .order_by(Order.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return list(rows), total, fulfilment_counts(db)


def admin_order(db: Session, order_id: UUID) -> dict:
    """One board row by id - the same shape as a row of the board itself."""
    row = db.execute(
        select(Order, MerchOrder, User)
        .join(MerchOrder, MerchOrder.order_id == Order.id)
        .join(User, User.id == Order.user_id)
        .where(Order.id == order_id)
    ).first()
    if row is None:
        raise AppError(
            404,
            "MERCH_ORDER_NOT_FOUND",
            "No merch order with that id - an order gets one when its payment succeeds",
            {"order_id": str(order_id)},
        )
    order, fulfilment, buyer = row
    return admin_order_view(order, fulfilment, buyer, admin_lines(db, [order])[order.id])


def fulfilment_counts(db: Session) -> dict:
    counts = {"paid": 0, "packed": 0, "handed_over": 0}
    for status, count in db.execute(
        select(MerchOrder.fulfilment_status, func.count()).group_by(MerchOrder.fulfilment_status)
    ):
        counts[status] = count
    return counts


def admin_order_view(order: Order, fulfilment: MerchOrder, buyer: User, lines: list[tuple[OrderItem, ProductVariant | None]]) -> dict:
    return {
        "order_id": order.id,
        "buyer": {
            "name": buyer.full_name,
            "email": buyer.email,
            "member_code": buyer.member_code,
            "phone": buyer.phone,
        },
        "items_summary": ", ".join(
            f"{_line_label(item, variant)} x{item.quantity}" for item, variant in lines
        )
        or "no items",
        "items": [
            {
                "variant_id": item.item_id,
                "product_name": variant.product.name if variant else None,
                "size": variant.size if variant else None,
                "color": variant.color if variant else None,
                "qty": item.quantity,
                "unit_price": item.unit_price,
                "line_total": item.line_total,
            }
            for item, variant in lines
        ],
        "total": order.total,
        "delivery_method": fulfilment.delivery_method,
        "delivery_note": fulfilment.delivery_note,
        "fulfilment_status": fulfilment.fulfilment_status,
        "created_at": order.created_at,
        "packed_at": fulfilment.packed_at,
        "handed_over_at": fulfilment.handed_over_at,
    }


def _line_label(item: OrderItem, variant: ProductVariant | None) -> str:
    return f"{variant.product.name} ({variant.size})" if variant else "deleted variant"


def admin_lines(db: Session, orders: list[Order]) -> dict[UUID, list[tuple[OrderItem, ProductVariant | None]]]:
    """Order lines with their variants, for a whole page in two queries."""
    items = [item for order in orders for item in order.items if item.item_type == "variant"]
    variants = {
        variant.id: variant
        for variant in db.scalars(select(ProductVariant).where(ProductVariant.id.in_({i.item_id for i in items})))
    }
    grouped: dict[UUID, list[tuple[OrderItem, ProductVariant | None]]] = {order.id: [] for order in orders}
    for item in items:
        grouped[item.order_id].append((item, variants.get(item.item_id)))
    return grouped


def stock_movements(db: Session, variant_id: UUID, *, page: int = 1, page_size: int = 20) -> tuple[list[dict], int]:
    """The audit trail, newest first, with whoever caused each change (DESIGN.md §5)."""
    get_variant(db, variant_id)  # 404 rather than an empty page for an unknown variant
    conditions = [StockMovement.variant_id == variant_id]
    total = db.scalar(select(func.count()).select_from(StockMovement).where(*conditions)) or 0
    rows = list(
        db.scalars(
            select(StockMovement)
            .where(*conditions)
            .order_by(StockMovement.created_at.desc(), StockMovement.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    names = {
        actor.id: actor.full_name
        for actor in db.scalars(
            select(User).where(User.id.in_({row.created_by for row in rows if row.created_by}))
        )
    }
    return (
        [
            {
                "id": row.id,
                "variant_id": row.variant_id,
                "delta": row.delta,
                "reason": row.reason,
                "order_id": row.order_id,
                "created_by": row.created_by,
                "created_by_name": names.get(row.created_by),
                "note": row.note,
                "created_at": row.created_at,
            }
            for row in rows
        ],
        total,
    )
