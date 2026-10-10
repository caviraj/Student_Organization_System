import time

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core import ratelimit
from app.core.config import settings
from app.core.deps import get_current_user, get_db
from app.core.errors import AppError
from app.core.security import create_access_token
from app.models import User
from app.schemas import LoginIn, MembershipSummary, MeOut, RegisterIn, TokenOut
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
    dependencies=[
        Depends(
            ratelimit.limit_by_ip(
                "register",
                settings.REGISTER_PER_MINUTE,
                "Too many accounts created from here; try again shortly",
            )
        )
    ],
)
def register(payload: RegisterIn, db: Session = Depends(get_db)):
    return _token(accounts.register_user(db, payload))


@router.post(
    "/login",
    response_model=TokenOut,
    summary="Log in with email + password",
    dependencies=[
        Depends(ratelimit.limit_by_ip("login", settings.LOGIN_PER_MINUTE, "Too many login attempts; try again shortly"))
    ],
)
def login(payload: LoginIn, db: Session = Depends(get_db)):
    """Two separate guards: a per-IP sliding window for volume, and a per-email lockout after
    `LOGIN_FAILURES_BEFORE_LOCKOUT` consecutive failures. The lockout is what makes a slow
    password-guessing run against one known email pointless.

    Both refuse without saying whether the account exists - the message names no email, and a
    locked account and a rate-limited one look the same from outside."""
    email = payload.email.lower()
    remaining = ratelimit.lockouts.locked_for(email, time.monotonic())
    if remaining:
        raise AppError(
            429,
            "TOO_MANY_REQUESTS",
            "Too many failed logins for this account; try again later",
            {"retry_after": remaining},
            headers={"Retry-After": str(remaining)},
        )
    try:
        user = accounts.authenticate(db, payload.email, payload.password)
    except AppError:
        ratelimit.lockouts.record_failure(email, time.monotonic())
        raise
    ratelimit.lockouts.clear(email)
    return _token(user)


@router.get("/me", response_model=MeOut, summary="Current user + membership summary")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    out = MeOut.model_validate(user)
    out.membership = MembershipSummary(**summarize(current_membership(db, user)))
    return out
