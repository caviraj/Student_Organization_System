from datetime import UTC, datetime, timedelta
from uuid import UUID

import bcrypt
import jwt

from app.core.config import settings
from app.core.errors import AppError

ALGORITHM = "HS256"
_BCRYPT_MAX_BYTES = 72  # bcrypt silently ignores everything past this


def check_password_policy(password: str) -> str:
    """At least `PASSWORD_MIN_LENGTH` characters, with a letter and a digit.

    Enforced in the service, not the schema, so the answer is the API's own `WEAK_PASSWORD` (422)
    rather than a pydantic `VALIDATION_ERROR` - the frontend shows it next to the password field,
    and "your password is weak" is a rule of this club, not a malformed request. Length is free to
    check and does most of the work; the letter/digit rule only stops "aaaaaaaa"."""
    if len(password) < settings.PASSWORD_MIN_LENGTH:
        raise AppError(
            422,
            "WEAK_PASSWORD",
            f"Password must be at least {settings.PASSWORD_MIN_LENGTH} characters",
            {"min_length": settings.PASSWORD_MIN_LENGTH},
        )
    if not any(char.isalpha() for char in password) or not any(char.isdigit() for char in password):
        raise AppError(
            422,
            "WEAK_PASSWORD",
            "Password must contain at least one letter and one number",
            {"requirements": ["letter", "number"]},
        )
    return password


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode()[:_BCRYPT_MAX_BYTES], bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS)).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode()[:_BCRYPT_MAX_BYTES], password_hash.encode())
    except ValueError:
        return False


def create_access_token(user_id: UUID) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=ALGORITHM)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
