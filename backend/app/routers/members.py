from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.authz import require_permission
from app.core.deps import get_db
from app.core.errors import AppError
from app.models import User
from app.schemas import CardOut, VerifyOut
from app.services.memberships import verification_state

router = APIRouter(prefix="/members", tags=["members"])


@router.get("/verify", response_model=VerifyOut, summary="Verify a member by code or name/email (volunteer+)")
def verify(
    code: str | None = Query(default=None, description="Member code, e.g. SSA-2026-0042"),
    q: str | None = Query(default=None, description="Name or email search"),
    _: User = Depends(require_permission("members.verify")),
    db: Session = Depends(get_db),
):
    if not code and not q:
        raise AppError(400, "MISSING_QUERY", "Provide ?code= (member code) or ?q= (name or email)")

    if code:
        user = db.scalar(select(User).where(User.member_code == code))
    else:
        needle = f"%{q}%"
        matches = db.scalars(
            select(User)
            .where(or_(User.full_name.ilike(needle), User.email.ilike(needle)))
            .order_by(User.full_name)
            .limit(10)
        ).all()
        if len(matches) > 1:
            raise AppError(
                409,
                "AMBIGUOUS_QUERY",
                "Several members match that search — scan or type the member code",
                {"count": len(matches), "member_codes": [m.member_code for m in matches]},
            )
        user = matches[0] if matches else None

    if user is None:
        return {
            "valid": False,
            "status": "none",
            "name": None,
            "member_code": None,
            "valid_until": None,
            "reason": "No member found",
        }

    state = verification_state(db, user)
    return {"name": user.full_name, "member_code": user.member_code, **state}


@router.get("/me/card", response_model=CardOut, summary="QR member card payload")
def my_card(user: User = Depends(require_permission("members.view")), db: Session = Depends(get_db)):
    state = verification_state(db, user)
    return {
        "full_name": user.full_name,
        "member_code": user.member_code,
        "status": state["status"],
        "valid_until": state["valid_until"],
    }
