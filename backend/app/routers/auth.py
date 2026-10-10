from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.core.security import create_access_token
from app.models import User
from app.schemas import LoginIn, MeOut, MembershipSummary, RegisterIn, TokenOut
from app.services import accounts
from app.services.memberships import current_membership, summarize

router = APIRouter(prefix="/auth", tags=["auth"])


def _token(user: User) -> dict:
    return {"access_token": create_access_token(user.id), "token_type": "bearer", "user": user}


@router.post(
    "/register",
    response_model=TokenOut,
    status_code=201,
    summary="Register a student (role=guest until dues are paid)",
)
def register(payload: RegisterIn, db: Session = Depends(get_db)):
    return _token(accounts.register_user(db, payload))


@router.post("/login", response_model=TokenOut, summary="Log in with email + password")
def login(payload: LoginIn, db: Session = Depends(get_db)):
    return _token(accounts.authenticate(db, payload.email, payload.password))


@router.get("/me", response_model=MeOut, summary="Current user + membership summary")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    out = MeOut.model_validate(user)
    out.membership = MembershipSummary(**summarize(current_membership(db, user)))
    return out
