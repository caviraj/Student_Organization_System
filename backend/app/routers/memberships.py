from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db, require_role
from app.core.errors import AppError
from app.models import Membership, User
from app.schemas import CheckoutIn, CheckoutOut, MembershipOut, Page
from app.services import memberships as membership_service

router = APIRouter(prefix="/memberships", tags=["memberships"])


@router.post("/checkout", response_model=CheckoutOut, status_code=201, summary="Start a membership purchase (auth)")
def checkout(payload: CheckoutIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order, payment = membership_service.checkout(db, user, payload.plan_id)
    return {
        "order_id": order.id,
        "payment_id": payment.id,
        "amount": order.total,
        "provider": payment.provider,
        "status": payment.status,
    }


@router.get("/me", response_model=MembershipOut, summary="My membership")
def my_membership(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    membership = membership_service.current_membership(db, user)
    if membership is None:
        raise AppError(404, "MEMBERSHIP_NOT_FOUND", "You do not have a membership yet")
    return membership_service.membership_view(membership, user)


@router.get("", response_model=Page[MembershipOut], summary="All memberships (admin)")
def list_memberships(
    status: str | None = Query(default=None),
    expiring_within_days: int | None = Query(default=None, ge=0, le=365),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    filters = []
    if status:
        filters.append(Membership.status == status)
    if expiring_within_days is not None:
        filters.append(Membership.end_date <= date.today() + timedelta(days=expiring_within_days))

    total = db.scalar(select(func.count()).select_from(Membership).where(*filters)) or 0
    rows = db.scalars(
        select(Membership).where(*filters).order_by(Membership.end_date).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {
        "items": [membership_service.membership_view(m) for m in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get(
    "/renewals-due", response_model=Page[MembershipOut], summary="Active memberships ending within 30 days (admin)"
)
def renewals_due(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    horizon = date.today() + timedelta(days=30)
    filters = [Membership.status == "active", Membership.end_date <= horizon]
    total = db.scalar(select(func.count()).select_from(Membership).where(*filters)) or 0
    rows = db.scalars(
        select(Membership).where(*filters).order_by(Membership.end_date).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {
        "items": [membership_service.membership_view(m) for m in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
