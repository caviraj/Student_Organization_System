"""Membership expiry scan (FR-1.5, DESIGN.md §4 rule 6).

Runs daily from jobs/scheduler.py; exposed here so tests can drive it directly.
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Membership, Reminder

REMINDER_WINDOW_DAYS = 30
EXPIRY_7_DAYS = 7


def run_expiry_scan(db: Session) -> dict:
    today = date.today()
    horizon = today + timedelta(days=REMINDER_WINDOW_DAYS)
    expired = created = 0

    memberships = db.scalars(select(Membership).where(Membership.status == "active")).all()
    for membership in memberships:
        if membership.end_date is None:
            continue

        days_left = (membership.end_date - today).days
        if days_left < 0:
            membership.status = "expired"
            expired += 1
            kinds = ["expired"]
        elif membership.end_date <= horizon:
            kinds = ["expiry_30"] if days_left <= REMINDER_WINDOW_DAYS else []
            if days_left <= EXPIRY_7_DAYS:
                kinds.append("expiry_7")
        else:
            continue

        raised = False
        for kind in kinds:
            exists = db.scalar(
                select(Reminder.id).where(Reminder.membership_id == membership.id, Reminder.kind == kind)
            )
            if exists is None:
                db.add(Reminder(membership_id=membership.id, kind=kind))
                created += 1
                raised = True
        if raised:
            membership.renewal_reminded_at = datetime.now(UTC)

    db.commit()
    return {"scanned": len(memberships), "expired": expired, "reminders_created": created}
