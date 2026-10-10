"""Announcements (DESIGN.md §5).

There is no DELETE endpoint: the record of what was said, and when, is permanent (PRD FR-3.2).
"""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_optional_user, require_role
from app.jobs import scheduler
from app.models import User
from app.schemas import (
    AnnouncementCategory,
    AnnouncementCreatedOut,
    AnnouncementCreateIn,
    AnnouncementDeliveriesOut,
    AnnouncementDetail,
    AnnouncementOut,
    AnnouncementRevisionOut,
    AnnouncementUpdateIn,
    Page,
)
from app.services import announcements as service

router = APIRouter(prefix="/announcements", tags=["Announcements"])


@router.get(
    "",
    response_model=Page[AnnouncementOut],
    summary="Announcement feed (public; personalised when signed in)",
)
def list_announcements(
    category: AnnouncementCategory | None = Query(default=None, description="Filter by category"),
    q: str | None = Query(default=None, description="Search title and body"),
    pinned: bool | None = Query(default=None, description="true = pinned only, false = unpinned only"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """Pinned first, then newest. What comes back depends on who you are: guests see public posts,
    active members also see members-only ones, anyone holding a ticket for an event also sees that
    event's posts, and organizers see everything (PRD FR-3.2)."""
    rows, total = service.feed(
        db, user, category=category, q=q, pinned=pinned, page=page, page_size=page_size
    )
    return {
        "items": [service.announcement_summary(a) for a in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post(
    "",
    response_model=AnnouncementCreatedOut,
    status_code=201,
    summary="Post an announcement and queue its deliveries (organizer+)",
)
def create_announcement(
    payload: AnnouncementCreateIn,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_role("organizer")),
    db: Session = Depends(get_db),
):
    """The post, the audience it resolves to and the delivery rows are one transaction. Email goes
    only to members who have not opted out. The worker is kicked as soon as this response is sent,
    and again by the 60-second job, so `delivery_summary` is a queue count, not a receipt."""
    result = service.create_announcement(db, user, payload.model_dump())
    # Via the module, not the function: the tests point this at their own session.
    background_tasks.add_task(scheduler.run_deliveries_once)
    return service.announcement_detail(result["announcement"]) | {
        "delivery_summary": result["delivery_summary"]
    }


@router.get(
    "/{announcement_id}",
    response_model=AnnouncementDetail,
    summary="One announcement with the full body (public when you are in its audience)",
)
def get_announcement(
    announcement_id: UUID,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    # 404 for a post you may not see, exactly as for one that does not exist: the existence of a
    # members-only post is itself information.
    return service.announcement_detail(service.visible_to(db, user, announcement_id))


@router.patch(
    "/{announcement_id}",
    response_model=AnnouncementDetail,
    summary="Edit an announcement (organizer+)",
)
def update_announcement(
    announcement_id: UUID,
    payload: AnnouncementUpdateIn,
    user: User = Depends(require_role("organizer")),
    db: Session = Depends(get_db),
):
    """Any change to title, body or category requires `revision_note` (3+ characters) and stores
    the version being replaced in the revision history. `audience` and `event_id` are frozen once
    posted (422 AUDIENCE_LOCKED). Pinning needs no note, but still counts against the pin limit."""
    return service.announcement_detail(
        service.update_announcement(db, user, announcement_id, payload.model_dump(exclude_unset=True))
    )


@router.get(
    "/{announcement_id}/revisions",
    response_model=Page[AnnouncementRevisionOut],
    summary="Edit history, newest first (organizer+)",
)
def list_revisions(
    announcement_id: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(require_role("organizer")),
    db: Session = Depends(get_db),
):
    """Each row is the version that was replaced, who replaced it and why."""
    service.visible_to(db, user, announcement_id)  # 404 for an id that does not exist
    rows, total = service.list_revisions(db, announcement_id, page=page, page_size=page_size)
    return {
        "items": [service.revision_view(revision, editor) for revision, editor in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get(
    "/{announcement_id}/deliveries",
    response_model=AnnouncementDeliveriesOut,
    summary="Delivery status per recipient (admin)",
)
def list_deliveries(
    announcement_id: UUID,
    channel: Literal["email", "inapp"] | None = Query(default=None),
    status: Literal["queued", "sent", "failed"] | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """`summary` always counts the whole announcement; `items` is the filtered, paginated rows."""
    service.visible_to(db, user, announcement_id)
    rows, total = service.list_deliveries(
        db, announcement_id, channel=channel, status=status, page=page, page_size=page_size
    )
    return {
        "announcement_id": announcement_id,
        "summary": service.delivery_summary(db, announcement_id),
        "items": {
            "items": [service.delivery_view(delivery, recipient) for delivery, recipient in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    }
