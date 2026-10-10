"""Unsubscribe links (PRD FR-3.3).

The link has to work from an email client, where there is no session - so it carries a signed
token instead. The `purpose` claim is what stops an ordinary access token from being replayed
here, and vice versa: a token minted for one job cannot do another.
"""

from datetime import UTC, datetime, timedelta

import jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError
from app.core.security import ALGORITHM, decode_token
from app.models import User

PURPOSE = "unsubscribe"


def create_unsubscribe_token(user: User) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": str(user.id),
            "purpose": PURPOSE,
            "iat": now,
            # Long: the link sits in an inbox for years, and one that has quietly expired turns a
            # member's unsubscribe click into an error page.
            "exp": now + timedelta(days=settings.UNSUBSCRIBE_TOKEN_DAYS),
        },
        settings.JWT_SECRET,
        algorithm=ALGORITHM,
    )


def apply_unsubscribe(db: Session, token: str) -> str:
    """Turns email off for the token's owner and returns their address."""
    payload = decode_token(token)
    if not payload or payload.get("purpose") != PURPOSE:
        raise AppError(400, "INVALID_TOKEN", "This unsubscribe link is invalid or has expired")

    user = db.get(User, _subject(payload))
    if user is None or not user.is_active:
        raise AppError(400, "INVALID_TOKEN", "This unsubscribe link is invalid or has expired")

    user.email_opt_in = False
    db.commit()
    return user.email


def mask_email(email: str) -> str:
    """Enough of the address to confirm which inbox was unsubscribed, without publishing it."""
    local, _, domain = email.partition("@")
    return f"{local[:1]}{'*' * max(len(local) - 1, 1)}@{domain}"


def _subject(payload: dict):
    from uuid import UUID

    try:
        return UUID(str(payload.get("sub")))
    except (TypeError, ValueError):
        raise AppError(400, "INVALID_TOKEN", "This unsubscribe link is invalid or has expired") from None
