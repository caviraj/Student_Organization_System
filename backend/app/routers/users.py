from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_role
from app.core.errors import AppError
from app.models import User
from app.schemas import AssignableUserOut, Page, RoleUpdateIn, UserOut
from app.services import tasks as task_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=Page[UserOut], summary="Member directory (admin)")
def list_users(
    q: str | None = Query(default=None, description="Search name, email or member code"),
    role: str | None = Query(default=None),
    status: str | None = Query(default=None, description="active | inactive"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    filters = []
    if q:
        needle = f"%{q}%"
        filters.append(or_(User.full_name.ilike(needle), User.email.ilike(needle), User.member_code.ilike(needle)))
    if role:
        filters.append(User.role == role)
    if status == "active":
        filters.append(User.is_active.is_(True))
    elif status == "inactive":
        filters.append(User.is_active.is_(False))

    total = db.scalar(select(func.count()).select_from(User).where(*filters)) or 0
    rows = db.scalars(
        select(User).where(*filters).order_by(User.full_name).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {"items": rows, "total": total, "page": page, "page_size": page_size}


@router.get(
    "/assignable",
    response_model=list[AssignableUserOut],
    summary="Who can be handed a task: active volunteer and above (organizer+)",
)
def assignable(
    _: User = Depends(require_role("organizer")),
    db: Session = Depends(get_db),
):
    """The assignee picker. Not paginated: the club's volunteers and staff are a short list, and a
    picker needs all of them at once."""
    return task_service.assignable_users(db)


@router.patch("/{user_id}/role", response_model=UserOut, summary="Change a user's role (admin)")
def set_role(
    user_id: UUID,
    payload: RoleUpdateIn,
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None:
        raise AppError(404, "USER_NOT_FOUND", "User not found", {"user_id": str(user_id)})
    user.role = payload.role
    db.commit()
    db.refresh(user)
    return user
