"""Announcement rules (DESIGN.md §4 rule 10, PRD FR-3.1/3.2/3.3).

Everything here is a service, not a route: who may see a post, who gets it, and what an edit is
allowed to change are rules of the club, not of HTTP.
"""

from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import Select, and_, func, or_, select, true
from sqlalchemy.orm import Session

from app.core.deps import ROLE_RANK
from app.core.errors import AppError
from app.models import (
    Announcement,
    AnnouncementDelivery,
    AnnouncementRevision,
    Event,
    Membership,
    Ticket,
    User,
)
from app.services.pricing import is_active_member

MAX_PINNED = 3
PREVIEW_CHARS = 200
MIN_REVISION_NOTE = 3


# --- visibility -------------------------------------------------------------------------------


def visibility_clause(db: Session, user: User | None):
    """The one place that decides who sees what (PRD FR-3.2, DESIGN.md §4 rule 10):

        guest              -> public posts only
        active member      -> public + members-only
        any signed-in user -> plus posts about events they actually hold a ticket for
        organizer and up   -> everything, including posts about events they never attended

    Returns a SQLAlchemy expression, so the feed, the detail endpoint and any future list all
    share it by construction rather than by discipline.
    """
    if user is None:
        return Announcement.audience == "all"
    if ROLE_RANK.get(user.role, 0) >= ROLE_RANK["organizer"]:
        return true()

    audiences = ["all"]
    if is_active_member(db, user):
        audiences.append("members")
    held_events = select(Ticket.event_id).where(
        Ticket.user_id == user.id, Ticket.status.in_(("valid", "used"))
    )
    return or_(
        Announcement.audience.in_(audiences),
        and_(Announcement.audience == "event", Announcement.event_id.in_(held_events)),
    )


def visible_to(db: Session, user: User | None, announcement_id: UUID) -> Announcement:
    announcement = db.get(Announcement, announcement_id)
    # A post you may not see is a 404, not a 403: the existence of a members-only post is itself
    # information (PRD FR-3.2).
    if announcement is None or db.scalar(
        select(Announcement.id).where(Announcement.id == announcement.id, visibility_clause(db, user))
    ) is None:
        raise AppError(404, "ANNOUNCEMENT_NOT_FOUND", "No such announcement")
    return announcement


# --- feed -------------------------------------------------------------------------------------


def _filters(db: Session, user: User | None, category: str | None, q: str | None, pinned: bool | None):
    conditions = [visibility_clause(db, user)]
    if category:
        conditions.append(Announcement.category == category)
    if q:
        like = f"%{q}%"
        conditions.append(or_(Announcement.title.ilike(like), Announcement.body.ilike(like)))
    if pinned is not None:
        conditions.append(Announcement.is_pinned.is_(pinned))
    return conditions


def feed(
    db: Session,
    user: User | None,
    *,
    category: str | None = None,
    q: str | None = None,
    pinned: bool | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Announcement], int]:
    conditions = _filters(db, user, category, q, pinned)
    total = db.scalar(select(func.count()).select_from(Announcement).where(*conditions)) or 0
    rows = db.scalars(
        _ordered(select(Announcement).where(*conditions)).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return list(rows), total


def _ordered(stmt: Select) -> Select:
    """Pinned first, then newest. `published_at` is set from Python, so two posts in the same
    transaction still order correctly."""
    return stmt.order_by(Announcement.is_pinned.desc(), Announcement.published_at.desc())


# --- recipients -------------------------------------------------------------------------------


def _audience_users(db: Session, announcement: Announcement) -> list[User]:
    base = select(User).where(User.is_active.is_(True))
    if announcement.audience == "members":
        base = base.join(Membership, Membership.user_id == User.id).where(
            Membership.status == "active", Membership.end_date >= date.today()
        )
    elif announcement.audience == "event":
        # Holders, not registrations: a void ticket is not an invitation.
        base = (
            base.join(Ticket, Ticket.user_id == User.id)
            .where(Ticket.event_id == announcement.event_id, Ticket.status.in_(("valid", "used")))
            .distinct()
        )
    return list(db.scalars(base))


def resolve_recipients(db: Session, announcement: Announcement, *, send_email: bool) -> dict:
    """Everyone in the audience gets an in-app row. Email is opt-in in both senses: the sender has
    to ask for it, and the member has to want it (FR-3.3)."""
    users = _audience_users(db, announcement)
    email_users = [u for u in users if u.email_opt_in] if send_email else []
    return {
        "inapp": users,
        "email": email_users,
        "skipped_opted_out": len(users) - len(email_users) if send_email else 0,
    }


def queue_deliveries(db: Session, announcement: Announcement, *, send_email: bool) -> dict:
    """Called inside the caller's transaction: a half-posted announcement that mailed half the
    club is worse than no announcement."""
    resolved = resolve_recipients(db, announcement, send_email=send_email)
    for user in resolved["inapp"]:
        db.add(
            AnnouncementDelivery(
                announcement_id=announcement.id, user_id=user.id, channel="inapp", status="queued"
            )
        )
    for user in resolved["email"]:
        db.add(
            AnnouncementDelivery(
                announcement_id=announcement.id, user_id=user.id, channel="email", status="queued"
            )
        )
    return {
        "inapp_queued": len(resolved["inapp"]),
        "email_queued": len(resolved["email"]),
        "skipped_opted_out": resolved["skipped_opted_out"],
    }


# --- writes -----------------------------------------------------------------------------------


def _assert_pin_room(db: Session) -> None:
    pinned = db.scalar(
        select(func.count()).select_from(Announcement).where(Announcement.is_pinned.is_(True))
    ) or 0
    if pinned >= MAX_PINNED:
        raise AppError(
            409,
            "PIN_LIMIT_REACHED",
            f"At most {MAX_PINNED} announcements can be pinned",
            {"pinned": pinned, "limit": MAX_PINNED},
        )


def create_announcement(db: Session, author: User, data: dict) -> dict:
    """Post, resolve the audience and queue the mail in one transaction."""
    audience = data["audience"]
    event_id = data.get("event_id")
    if audience == "event":
        if event_id is None:
            raise AppError(
                422, "EVENT_REQUIRED", "audience=event needs an event_id", {"audience": audience}
            )
        if db.get(Event, event_id) is None:
            raise AppError(404, "EVENT_NOT_FOUND", "No such event", {"event_id": str(event_id)})
    elif event_id is not None:
        raise AppError(
            422, "EVENT_NOT_ALLOWED", "event_id only applies when audience=event", {"audience": audience}
        )

    send_email = bool(data.get("send_email"))
    if data.get("is_pinned"):
        _assert_pin_room(db)

    announcement = Announcement(
        title=data["title"],
        body=data["body"],
        category=data["category"],
        audience=audience,
        event_id=event_id,
        is_pinned=bool(data.get("is_pinned")),
        author_id=author.id,
        published_at=datetime.now(UTC),
    )
    db.add(announcement)
    db.flush()  # the id the delivery rows need, still inside the transaction
    summary = queue_deliveries(db, announcement, send_email=send_email)
    db.commit()
    db.refresh(announcement)
    return {"announcement": announcement, "delivery_summary": summary}


def update_announcement(db: Session, editor: User, announcement_id: UUID, data: dict) -> Announcement:
    announcement = db.get(Announcement, announcement_id)
    if announcement is None:
        raise AppError(404, "ANNOUNCEMENT_NOT_FOUND", "No such announcement")

    # audience/event_id are frozen once posted: the delivery rows are already out, so widening or
    # narrowing the audience now would make those rows a lie (FR-3.2).
    for field in ("audience", "event_id"):
        if field in data and data[field] != getattr(announcement, field):
            raise AppError(
                422,
                "AUDIENCE_LOCKED",
                f"{field} cannot change after an announcement is posted; post a new one",
                {"field": field},
            )

    note = (data.get("revision_note") or "").strip()
    content_changed = any(
        field in data and data[field] != getattr(announcement, field)
        for field in ("title", "body", "category")
    )
    if content_changed:
        if len(note) < MIN_REVISION_NOTE:
            raise AppError(
                422,
                "REVISION_NOTE_REQUIRED",
                f"revision_note ({MIN_REVISION_NOTE}+ characters) is required when editing a posted announcement",
                {"field": "revision_note"},
            )
        # Store the version being REPLACED, then apply the new one.
        db.add(
            AnnouncementRevision(
                announcement_id=announcement.id,
                title=announcement.title,
                body=announcement.body,
                category=announcement.category,
                audience=announcement.audience,
                edited_by=editor.id,
                edited_at=datetime.now(UTC),
                note=note,
            )
        )
        for field in ("title", "body", "category"):
            if field in data:
                setattr(announcement, field, data[field])
        announcement.revision_note = note
        announcement.edited_at = datetime.now(UTC)

    # Pinning is not an edit to what was said, so it needs no revision row - but it still counts
    # against the pin limit.
    if "is_pinned" in data and bool(data["is_pinned"]) != announcement.is_pinned:
        if data["is_pinned"]:
            _assert_pin_room(db)
        announcement.is_pinned = bool(data["is_pinned"])

    db.commit()
    db.refresh(announcement)
    return announcement


def list_revisions(db: Session, announcement_id: UUID, *, page: int = 1, page_size: int = 20):
    """Newest first: history reads backwards from what the feed shows now."""
    total = db.scalar(
        select(func.count())
        .select_from(AnnouncementRevision)
        .where(AnnouncementRevision.announcement_id == announcement_id)
    ) or 0
    rows = db.execute(
        select(AnnouncementRevision, User.full_name)
        .outerjoin(User, User.id == AnnouncementRevision.edited_by)
        .where(AnnouncementRevision.announcement_id == announcement_id)
        .order_by(AnnouncementRevision.edited_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return rows, total


# --- delivery reporting -----------------------------------------------------------------------


def list_deliveries(
    db: Session,
    announcement_id: UUID,
    *,
    channel: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
):
    conditions = [AnnouncementDelivery.announcement_id == announcement_id]
    if channel:
        conditions.append(AnnouncementDelivery.channel == channel)
    if status:
        conditions.append(AnnouncementDelivery.status == status)

    total = db.scalar(select(func.count()).select_from(AnnouncementDelivery).where(*conditions)) or 0
    rows = db.execute(
        select(AnnouncementDelivery, User)
        .join(User, User.id == AnnouncementDelivery.user_id)
        .where(*conditions)
        .order_by(AnnouncementDelivery.channel, User.full_name)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return rows, total


def delivery_summary(db: Session, announcement_id: UUID) -> dict:
    counts = db.execute(
        select(AnnouncementDelivery.channel, AnnouncementDelivery.status, func.count())
        .where(AnnouncementDelivery.announcement_id == announcement_id)
        .group_by(AnnouncementDelivery.channel, AnnouncementDelivery.status)
    ).all()

    summary = {channel: {"queued": 0, "sent": 0, "failed": 0} for channel in ("email", "inapp")}
    for channel, status, count in counts:
        summary[channel][status] = count
    summary["total_recipients"] = sum(
        bucket["queued"] + bucket["sent"] + bucket["failed"] for bucket in summary.values()
    )
    return summary


def body_preview(body: str) -> str:
    return body if len(body) <= PREVIEW_CHARS else body[:PREVIEW_CHARS]


# --- views ------------------------------------------------------------------------------------


def _view(announcement: Announcement) -> dict:
    return {
        "id": announcement.id,
        "title": announcement.title,
        "category": announcement.category,
        "audience": announcement.audience,
        "event_id": announcement.event_id,
        "is_pinned": announcement.is_pinned,
        "author_name": announcement.author.full_name if announcement.author else None,
        "published_at": announcement.published_at,
        "edited_at": announcement.edited_at,
    }


def announcement_summary(announcement: Announcement) -> dict:
    """Feed row: the preview, not the whole post - a feed of 5,000-character bodies is unusable."""
    return _view(announcement) | {"body_preview": body_preview(announcement.body)}


def announcement_detail(announcement: Announcement) -> dict:
    return _view(announcement) | {"body": announcement.body, "revision_note": announcement.revision_note}


def revision_view(revision: AnnouncementRevision, editor_name: str | None) -> dict:
    return {
        "id": revision.id,
        "title": revision.title,
        "body": revision.body,
        "category": revision.category,
        "audience": revision.audience,
        "edited_by": revision.edited_by,
        "edited_by_name": editor_name,
        "edited_at": revision.edited_at,
        "note": revision.note,
    }


def delivery_view(delivery: AnnouncementDelivery, user: User) -> dict:
    return {
        "id": delivery.id,
        "user_id": delivery.user_id,
        "user_name": user.full_name,
        "user_email": user.email,
        "channel": delivery.channel,
        "status": delivery.status,
        "attempts": delivery.attempts,
        "error": delivery.error,
        "sent_at": delivery.sent_at,
    }
