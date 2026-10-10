from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

_connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(settings.DATABASE_URL, connect_args=_connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def as_utc(value: datetime) -> datetime:
    """SQLite stores `DateTime(timezone=True)` as naive UTC and hands it back naive, while
    Postgres returns it aware. Normalise before comparing, so both behave the same."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)
