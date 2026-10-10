from collections.abc import Callable, Iterator
from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.core.errors import AppError
from app.core.security import decode_token
from app.models import User

# Hierarchy: admin > treasurer > organizer > volunteer > member > guest (PRD §3)
ROLE_RANK = {"guest": 0, "member": 1, "volunteer": 2, "organizer": 3, "treasurer": 4, "admin": 5}

bearer_scheme = HTTPBearer(auto_error=False, description="JWT from POST /auth/login")


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise AppError(401, "UNAUTHORIZED", "Missing bearer token")
    payload = decode_token(credentials.credentials)
    if not payload:
        raise AppError(401, "UNAUTHORIZED", "Invalid or expired token")
    try:
        user_id = UUID(str(payload.get("sub")))
    except (TypeError, ValueError):
        raise AppError(401, "UNAUTHORIZED", "Malformed token subject") from None
    # Role is read from the DB, never the token, so a promotion applies immediately.
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise AppError(401, "UNAUTHORIZED", "User not found or inactive")
    return user


def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    """For public endpoints that personalise when a token happens to be present
    (e.g. `price_for_you` on an event). A bad token is treated as anonymous, never a 401 —
    a stale token in a browser must not blank out the public events list."""
    if credentials is None:
        return None
    payload = decode_token(credentials.credentials)
    if not payload:
        return None
    try:
        user_id = UUID(str(payload.get("sub")))
    except (TypeError, ValueError):
        return None
    user = db.get(User, user_id)
    return user if user is not None and user.is_active else None


def require_role(*roles: str) -> Callable[..., User]:
    """Dependency factory; passes anyone at or above the lowest listed role."""
    min_rank = min(ROLE_RANK[role] for role in roles)

    def dependency(user: User = Depends(get_current_user)) -> User:
        if ROLE_RANK.get(user.role, 0) < min_rank:
            raise AppError(403, "FORBIDDEN", f"Requires role: {' or '.join(roles)}", {"your_role": user.role})
        return user

    # scripts/contract_check.py walks the dependency tree to compare each route's real minimum role
    # against the Role column in DESIGN.md §5. Nothing at runtime reads this.
    dependency.required_roles = roles  # type: ignore[attr-defined]
    return dependency
