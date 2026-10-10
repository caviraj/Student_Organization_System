"""Membership purchase, renewal and payment settlement (FR-1.3, DESIGN.md §4 rules 1–3)."""

import calendar
import uuid
from datetime import date

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import (
    Membership,
    MembershipPlan,
    Order,
    OrderItem,
    Payment,
    Reminder,
    User,
)
from app.services import ledger, payments


def add_months(start: date, months: int) -> date:
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


def ensure_member_code(db: Session, user: User) -> str:
    if user.member_code:
        return user.member_code
    prefix = f"SSA-{date.today().year}-"
    # shortcut: sequence is max+1 for the year — safe for a single writer; switch to a DB
    # sequence if concurrent first-time signups start colliding on uq users.member_code.
    latest = db.scalar(select(func.max(User.member_code)).where(User.member_code.like(f"{prefix}%")))
    sequence = int(latest.rsplit("-", 1)[1]) + 1 if latest else 1
    user.member_code = f"{prefix}{sequence:04d}"
    return user.member_code


def current_membership(db: Session, user: User) -> Membership | None:
    return db.scalar(
        select(Membership).where(Membership.user_id == user.id).order_by(Membership.created_at.desc()).limit(1)
    )


def summarize(membership: Membership | None) -> dict:
    if membership is None:
        return {"status": "none", "plan_name": None, "end_date": None, "days_left": None}
    return {
        "status": membership.status,
        "plan_name": membership.plan.name if membership.plan else None,
        "end_date": membership.end_date,
        "days_left": (membership.end_date - date.today()).days if membership.end_date else None,
    }


def verification_state(db: Session, user: User) -> dict:
    """{status, valid, valid_until, reason} — backs /members/verify and /members/me/card."""
    membership = current_membership(db, user)
    if membership is None:
        return {"status": "none", "valid": False, "valid_until": None, "reason": "Not a member"}
    if membership.status == "active" and membership.end_date and membership.end_date >= date.today():
        return {"status": "active", "valid": True, "valid_until": membership.end_date, "reason": None}
    # An active row whose end_date has passed means the daily scan has not run yet.
    status = "expired" if membership.status == "active" else membership.status
    reasons = {
        "expired": f"Membership expired on {membership.end_date}" if membership.end_date else "Membership expired",
        "pending": "Membership payment is pending",
        "cancelled": "Membership was cancelled",
    }
    return {
        "status": status,
        "valid": False,
        "valid_until": membership.end_date,
        "reason": reasons.get(status, "Membership is not active"),
    }


def membership_view(membership: Membership, user: User | None = None) -> dict:
    user = user or membership.user
    return {
        "id": membership.id,
        "user_id": membership.user_id,
        "plan_id": membership.plan_id,
        "plan_name": membership.plan.name if membership.plan else None,
        "status": membership.status,
        "start_date": membership.start_date,
        "end_date": membership.end_date,
        "days_left": (membership.end_date - date.today()).days if membership.end_date else None,
        "member_code": user.member_code if user else None,
        "user_name": user.full_name if user else None,
        "user_email": user.email if user else None,
    }


def checkout(db: Session, user: User, plan_id: uuid.UUID) -> tuple[Order, Payment]:
    plan = db.get(MembershipPlan, plan_id)
    if plan is None or not plan.is_active:
        raise AppError(404, "PLAN_NOT_FOUND", "No active plan with that id", {"plan_id": str(plan_id)})

    order = Order(
        user_id=user.id,
        kind="membership",
        status="pending",
        subtotal=plan.price,
        discount=0,
        total=plan.price,
        currency="INR",
        meta={"plan_id": str(plan.id), "plan_name": plan.name},
        idempotency_key=uuid.uuid4().hex,
    )
    db.add(order)
    db.flush()
    db.add(
        OrderItem(
            order_id=order.id,
            item_type="plan",
            item_id=plan.id,
            quantity=1,
            unit_price=plan.price,
            line_total=plan.price,
        )
    )
    payment = payments.create_mock_intent(db, order)
    db.commit()
    db.refresh(order)
    db.refresh(payment)
    return order, payment


def activate(db: Session, order: Order) -> Membership:
    """Activate or extend the member's single membership row. Caller owns the transaction."""
    item = db.scalar(select(OrderItem).where(OrderItem.order_id == order.id, OrderItem.item_type == "plan"))
    if item is None:
        raise AppError(409, "NOT_A_MEMBERSHIP_ORDER", "Order has no membership plan")
    plan = db.get(MembershipPlan, item.item_id)
    if plan is None:
        raise AppError(409, "PLAN_NOT_FOUND", "The plan on this order no longer exists")

    today = date.today()
    membership = db.scalar(select(Membership).where(Membership.user_id == order.user_id))
    # Renewal runs from the old end_date so no paid days are lost (FR-1.3).
    extends = bool(
        membership and membership.status == "active" and membership.end_date and membership.end_date >= today
    )
    if membership is None:
        membership = Membership(user_id=order.user_id, plan_id=plan.id, status="active")
        db.add(membership)
    else:
        # A renewed period gets a fresh reminder cycle.
        db.execute(delete(Reminder).where(Reminder.membership_id == membership.id))

    start = membership.end_date if extends else today
    membership.plan_id = plan.id
    membership.status = "active"
    membership.start_date = start
    membership.end_date = add_months(start, plan.duration_months)
    membership.order_id = order.id
    membership.renewal_reminded_at = None
    db.flush()

    user = db.get(User, order.user_id)
    ensure_member_code(db, user)
    if user.role == "guest":  # never demote a volunteer/organizer/treasurer/admin
        user.role = "member"
    return membership


def confirm_membership_payment(db: Session, order: Order, payment: Payment, outcome: str) -> dict:
    """Membership half of the gateway callback (reached via services.payments.confirm_mock_payment).
    Idempotent: the atomic pending→paid claim below decides who does the work, so a repeat
    call changes nothing."""
    if outcome == "fail":
        if order.status == "pending":
            order.status = "failed"
            payments.settle(db, payment, "fail")
            db.commit()
        db.refresh(order)
        db.refresh(payment)
        return _result(db, order, payment)

    order_id = order.id
    claimed = db.execute(
        update(Order)
        .where(Order.id == order_id, Order.status == "pending")
        .values(status="paid", updated_at=func.now())
    ).rowcount
    if not claimed:
        db.rollback()  # already settled — replay the stored result
        order = db.get(Order, order_id)
        return _result(db, order, payments.latest_payment(db, order_id))

    payments.settle(db, payment, "success")
    membership = activate(db, order)
    ledger.add_transaction(
        db,
        direction="in",
        amount=order.total,
        source="dues",
        ref_type="order",
        ref_id=order.id,
        note=f"Membership dues - {membership.plan.name if membership.plan else order.meta.get('plan_name', 'plan')}",
    )
    db.commit()
    db.refresh(order)
    db.refresh(payment)
    return _result(db, order, payment, membership)


def _result(db: Session, order: Order, payment: Payment, membership: Membership | None = None) -> dict:
    if membership is None and order.status == "paid":
        membership = db.scalar(select(Membership).where(Membership.user_id == order.user_id))
    return {
        "order_id": order.id,
        "payment_id": payment.id,
        "order_status": order.status,
        "payment_status": payment.status,
        "provider_ref": payment.provider_ref,
        "membership": summarize(membership) if membership else None,
    }
