from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_role
from app.core.errors import AppError
from app.models import MembershipPlan, User
from app.schemas import Page, PlanCreate, PlanOut, PlanUpdate

router = APIRouter(prefix="/plans", tags=["plans"])


@router.get("", response_model=Page[PlanOut], summary="Active membership plans (public)")
def list_plans(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    filters = [MembershipPlan.is_active.is_(True)]
    total = db.scalar(select(func.count()).select_from(MembershipPlan).where(*filters)) or 0
    rows = db.scalars(
        select(MembershipPlan)
        .where(*filters)
        .order_by(MembershipPlan.price)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {"items": rows, "total": total, "page": page, "page_size": page_size}


@router.post("", response_model=PlanOut, status_code=201, summary="Create a plan (admin)")
def create_plan(
    payload: PlanCreate,
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    if db.scalar(select(MembershipPlan.id).where(MembershipPlan.name == payload.name)):
        raise AppError(409, "PLAN_NAME_TAKEN", "A plan with that name already exists", {"name": payload.name})
    plan = MembershipPlan(**payload.model_dump())
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


@router.patch("/{plan_id}", response_model=PlanOut, summary="Update a plan (admin)")
def update_plan(
    plan_id: UUID,
    payload: PlanUpdate,
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    plan = db.get(MembershipPlan, plan_id)
    if plan is None:
        raise AppError(404, "PLAN_NOT_FOUND", "Plan not found", {"plan_id": str(plan_id)})
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(plan, field, value)
    db.commit()
    db.refresh(plan)
    return plan
