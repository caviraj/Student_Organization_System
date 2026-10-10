"""The mailing-list worker (PRD FR-3.3).

Claim, then send. The rows are taken with `FOR UPDATE SKIP LOCKED` inside one transaction, so two
workers ticking at the same moment can never take the same row - and unlike an advisory lock, that
survives Supabase's transaction pooler, which may hand each statement to a different backend.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Announcement, AnnouncementDelivery, User
from app.services.mailer import get_provider, render

MAX_ATTEMPTS = 3
BATCH_SIZE = 100
ERROR_CHARS = 500


def process_queued_deliveries(db: Session, batch_size: int = BATCH_SIZE) -> dict:
    """Sends what it can, retries what it should, gives up after MAX_ATTEMPTS. Safe to run
    concurrently and safe to run twice: only rows still `queued` are ever claimed."""
    claimed = list(
        db.scalars(
            select(AnnouncementDelivery)
            .where(
                AnnouncementDelivery.status == "queued",
                AnnouncementDelivery.attempts < MAX_ATTEMPTS,
            )
            .order_by(AnnouncementDelivery.created_at)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
    )

    result = {"claimed": len(claimed), "sent": 0, "failed": 0, "retrying": 0}
    if not claimed:
        db.commit()  # close the empty transaction so the connection goes back to the pool
        return result

    # Two lookups for the whole batch instead of two per row: each statement is a round trip to
    # Supabase, and a 100-row batch of lazy loads would take minutes.
    users = {user.id: user for user in db.scalars(select(User).where(User.id.in_({d.user_id for d in claimed})))}
    announcements = {
        announcement.id: announcement
        for announcement in db.scalars(
            select(Announcement).where(Announcement.id.in_({d.announcement_id for d in claimed}))
        )
    }

    provider = get_provider()
    for delivery in claimed:
        if delivery.channel == "inapp":
            # Nothing to send: the row is the notification, and the feed already shows it.
            _mark_sent(delivery)
            result["sent"] += 1
            continue

        user = users.get(delivery.user_id)
        announcement = announcements.get(delivery.announcement_id)
        if user is None or announcement is None:
            _give_up(delivery, "recipient or announcement no longer exists")
            result["failed"] += 1
            continue
        if not user.email_opt_in:
            # Opting out takes effect now: mail queued before the click must not go out. Nothing
            # to retry, so it is terminal rather than a failed attempt.
            _give_up(delivery, "recipient unsubscribed before send")
            result["failed"] += 1
            continue

        try:
            subject, html, text = render(announcement, user)
            provider.send(user.email, subject, html, text)
        except Exception as exc:  # noqa: BLE001 - any provider failure is a retryable attempt
            delivery.attempts += 1
            delivery.error = str(exc)[:ERROR_CHARS]
            if delivery.attempts >= MAX_ATTEMPTS:
                delivery.status = "failed"
                result["failed"] += 1
            else:
                result["retrying"] += 1  # stays queued; the next tick picks it up
            continue

        _mark_sent(delivery)
        result["sent"] += 1

    db.commit()
    return result


def _mark_sent(delivery: AnnouncementDelivery) -> None:
    delivery.status = "sent"
    delivery.sent_at = datetime.now(UTC)
    delivery.error = None


def _give_up(delivery: AnnouncementDelivery, reason: str) -> None:
    delivery.status = "failed"
    delivery.error = reason
