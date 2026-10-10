from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.security import check_password_policy, hash_password, verify_password
from app.models import User
from app.schemas import RegisterIn


def register_user(db: Session, payload: RegisterIn) -> User:
    email = payload.email.lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise AppError(409, "EMAIL_TAKEN", "Email is already registered", {"email": email})
    check_password_policy(payload.password)
    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        phone=payload.phone,
        department=payload.department,
        year=payload.year,
        role="guest",  # promoted to member when dues are paid (DESIGN.md §5)
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate(db: Session, email: str, password: str) -> User:
    user = db.scalar(select(User).where(User.email == email.lower()))
    # Same error for unknown email and wrong password: no account enumeration.
    if user is None or not verify_password(password, user.password_hash):
        raise AppError(401, "INVALID_CREDENTIALS", "Email or password is incorrect")
    if not user.is_active:
        raise AppError(403, "ACCOUNT_DISABLED", "This account is disabled")
    return user
