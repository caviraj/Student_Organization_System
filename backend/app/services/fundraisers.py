"""Fundraisers: the plan, the board behind it, and how healthy it looks (PRD FR-5, DESIGN.md §4 rule 13).

Money is never stored on the fundraiser. `raised` and `spent` come from the ledger's signed
expressions (services/ledger.py), and `net_raised` is their difference, so the page and the books
can never disagree. `compute_progress` answers both the detail page (everything) and
the list page (the same numbers, batched for a whole page in two queries instead of two per row).
"""

from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.db import as_utc
from app.core.deps import ROLE_RANK
from app.core.errors import AppError
from app.models import FUNDRAISER_STATUSES, Fundraiser, Task, Transaction, User
from app.services import ledger

# One step forward only: planning -> active -> done (PRD FR-5.1). `None` is the end of the road.
NEXT_STATUS: dict[str, str | None] = {"planning": "active", "active": "done", "done": None}

# Income stays open for a week after the stall is shut down, then the books are closed.
INCOME_GRACE_DAYS = 7
DUE_SOON_DAYS = 3

# The health rule, named so the thresholds are reviewable in one place (DESIGN.md §5).
HEALTH_BEHIND_OVERDUE = 3
HEALTH_BEHIND_DAYS = 3
HEALTH_BEHIND_PERCENT = 70
HEALTH_AT_RISK_OVERDUE = 1
HEALTH_AT_RISK_UNASSIGNED = 2
HEALTH_AT_RISK_DAYS = 7
HEALTH_AT_RISK_PERCENT = 50

EMPTY_STATS = {"total": 0, "todo": 0, "doing": 0, "done": 0, "overdue": 0, "due_soon": 0, "unassigned": 0}


# --- health & progress ------------------------------------------------------------------------


def health_of(status: str, overdue: int, unassigned: int, days_to_event: int, percent_done: int) -> str:
    """behind > at_risk > on_track, first match wins; a finished fundraiser is simply completed."""
    if status == "done":
        return "completed"
    if (
        overdue >= HEALTH_BEHIND_OVERDUE
        # Its own date is close and most of the work is still ahead: too late to catch up.
        or (days_to_event <= HEALTH_BEHIND_DAYS and percent_done < HEALTH_BEHIND_PERCENT)
        # The date has passed and it is still open. `status != done` is already true here.
        or days_to_event < 0
    ):
        return "behind"
    if (
        overdue >= HEALTH_AT_RISK_OVERDUE
        or unassigned >= HEALTH_AT_RISK_UNASSIGNED
        or (days_to_event <= HEALTH_AT_RISK_DAYS and percent_done < HEALTH_AT_RISK_PERCENT)
    ):
        return "at_risk"
    return "on_track"


def _task_stats(db: Session, fundraiser_ids: list[UUID], today: date) -> dict[UUID, dict]:
    """Board counts for a whole page of fundraisers, one grouped query (never one per row)."""
    if not fundraiser_ids:
        return {}
    due_soon_by = today + timedelta(days=DUE_SOON_DAYS)
    still_open = Task.status != "done"
    rows = db.execute(
        select(
            Task.fundraiser_id,
            func.count().label("total"),
            func.count().filter(Task.status == "todo").label("todo"),
            func.count().filter(Task.status == "doing").label("doing"),
            func.count().filter(Task.status == "done").label("done"),
            func.count().filter(still_open, Task.due_date < today).label("overdue"),
            func.count().filter(still_open, Task.due_date >= today, Task.due_date <= due_soon_by).label("due_soon"),
            func.count().filter(still_open, Task.assignee_id.is_(None)).label("unassigned"),
        )
        .where(Task.fundraiser_id.in_(fundraiser_ids))
        .group_by(Task.fundraiser_id)
    ).all()
    return {
        row.fundraiser_id: {
            "total": row.total,
            "todo": row.todo,
            "doing": row.doing,
            "done": row.done,
            "overdue": row.overdue,
            "due_soon": row.due_soon,
            "unassigned": row.unassigned,
        }
        for row in rows
    }


def _money_by(db: Session, fundraiser_ids: list[UUID]) -> dict[UUID, dict[str, int]]:
    """`{fundraiser_id: {raised, spent}}` off the ledger in one grouped query.

    Both halves come from `services/ledger`'s signed expressions, so a reversed donation drops out
    of `raised` and a reimbursed claim counts against `spent` - the same arithmetic the finance
    dashboard uses, and the reason `net_raised` can never disagree with the books.
    """
    if not fundraiser_ids:
        return {}
    rows = db.execute(
        select(
            Transaction.fundraiser_id,
            ledger.total_in_expr().label("raised"),
            ledger.total_out_expr().label("spent"),
        )
        .where(Transaction.fundraiser_id.in_(fundraiser_ids))
        .group_by(Transaction.fundraiser_id)
    ).all()
    return {
        fundraiser_id: {"raised": int(raised), "spent": int(spent)} for fundraiser_id, raised, spent in rows
    }


def _progress_body(fundraiser, stats: dict, money: dict, today: date) -> dict:
    goal = fundraiser.goal_amount  # CHECK goal_amount > 0, so the division is always safe
    raised, spent = money["raised"], money["spent"]
    total = stats["total"]
    percent_done = round(stats["done"] * 100 / total) if total else 0  # an empty board is 0%, not a crash
    days_to_event = (fundraiser.event_date - today).days
    return {
        "tasks": {**stats, "percent_done": percent_done},
        # `raised` stays gross: money the stall took, before anything was spent on it (DESIGN.md §5).
        "raised": raised,
        "spent": spent,
        "net_raised": raised - spent,
        "goal": goal,
        "percent_of_goal": round(raised * 100 / goal),
        "days_to_event": days_to_event,
        "health": health_of(fundraiser.status, stats["overdue"], stats["unassigned"], days_to_event, percent_done),
        "by_category": [],
        "by_assignee": [],
    }


def compute_progress(db: Session, fundraiser, *, today: date | None = None) -> dict:
    """Everything the detail page shows: counts, money, and the breakdowns."""
    today = today or date.today()
    progress = _progress_body(
        fundraiser,
        _task_stats(db, [fundraiser.id], today).get(fundraiser.id, EMPTY_STATS),
        _money_by(db, [fundraiser.id]).get(fundraiser.id, {"raised": 0, "spent": 0}),
        today,
    )
    progress["by_category"] = _by_category(db, fundraiser.id)
    progress["by_assignee"] = _by_assignee(db, fundraiser.id)
    return progress


def progress_for(db: Session, fundraisers: list, *, today: date | None = None) -> dict[UUID, dict]:
    """The same numbers for a whole page, in two queries: what makes `GET /fundraisers` cheap."""
    today = today or date.today()
    ids = [fundraiser.id for fundraiser in fundraisers]
    stats = _task_stats(db, ids, today)
    money = _money_by(db, ids)
    return {
        fundraiser.id: _progress_body(
            fundraiser, stats.get(fundraiser.id, EMPTY_STATS), money.get(fundraiser.id, {"raised": 0, "spent": 0}), today
        )
        for fundraiser in fundraisers
    }


def _by_category(db: Session, fundraiser_id: UUID) -> list[dict]:
    rows = db.execute(
        select(Task.category, func.count(), func.count().filter(Task.status == "done"))
        .where(Task.fundraiser_id == fundraiser_id)
        .group_by(Task.category)
        .order_by(Task.category)
    ).all()
    return [{"category": category, "total": total, "done": done} for category, total, done in rows]


def _by_assignee(db: Session, fundraiser_id: UUID) -> list[dict]:
    """One row per assignee plus the unassigned bucket, so a lopsided board is visible."""
    rows = db.execute(
        select(Task.assignee_id, User.full_name, func.count(), func.count().filter(Task.status == "done"))
        .outerjoin(User, User.id == Task.assignee_id)
        .where(Task.fundraiser_id == fundraiser_id)
        .group_by(Task.assignee_id, User.full_name)
        .order_by(func.count().desc(), User.full_name)
    ).all()
    return [
        {"assignee_id": assignee_id, "name": name, "total": total, "done": done}
        for assignee_id, name, total, done in rows
    ]


# --- views ------------------------------------------------------------------------------------


def person_ref(user: User | None) -> dict | None:
    if user is None:
        return None
    return {"id": user.id, "full_name": user.full_name, "role": user.role}


def fundraiser_view(fundraiser, progress: dict) -> dict:
    return {
        "id": fundraiser.id,
        "title": fundraiser.title,
        "description": fundraiser.description,
        "goal_amount": fundraiser.goal_amount,
        "event_date": fundraiser.event_date,
        "status": fundraiser.status,
        "owner": person_ref(fundraiser.owner),
        "completed_at": fundraiser.completed_at,
        "created_at": fundraiser.created_at,
        "updated_at": fundraiser.updated_at,
        "progress": progress,
    }


def list_item_view(fundraiser, progress: dict) -> dict:
    """A list card: the same row with only the progress fields a card has space for."""
    return {
        "id": fundraiser.id,
        "title": fundraiser.title,
        "description": fundraiser.description,
        "goal_amount": fundraiser.goal_amount,
        "event_date": fundraiser.event_date,
        "status": fundraiser.status,
        "owner": person_ref(fundraiser.owner),
        "completed_at": fundraiser.completed_at,
        "created_at": fundraiser.created_at,
        "progress": {
            "tasks_total": progress["tasks"]["total"],
            "tasks_done": progress["tasks"]["done"],
            "overdue": progress["tasks"]["overdue"],
            "unassigned": progress["tasks"]["unassigned"],
            "percent_done": progress["tasks"]["percent_done"],
            "raised": progress["raised"],
            "spent": progress["spent"],
            "net_raised": progress["net_raised"],
            "goal": progress["goal"],
            "percent_of_goal": progress["percent_of_goal"],
            "days_to_event": progress["days_to_event"],
            "health": progress["health"],
        },
    }


# --- reads ------------------------------------------------------------------------------------


def get_fundraiser(db: Session, fundraiser_id: UUID) -> Fundraiser:
    fundraiser = db.get(Fundraiser, fundraiser_id)
    if fundraiser is None:
        raise AppError(404, "FUNDRAISER_NOT_FOUND", "No fundraiser with that id", {"fundraiser_id": str(fundraiser_id)})
    return fundraiser


def list_fundraisers(
    db: Session,
    *,
    status: str | None = None,
    q: str | None = None,
    owner_id: UUID | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list, int]:
    conditions = []
    if status:
        conditions.append(Fundraiser.status == status)
    if owner_id:
        conditions.append(Fundraiser.owner_id == owner_id)
    if q:
        like = f"%{q}%"
        conditions.append(or_(Fundraiser.title.ilike(like), Fundraiser.description.ilike(like)))

    total = db.scalar(select(func.count()).select_from(Fundraiser).where(*conditions)) or 0
    rows = db.scalars(
        select(Fundraiser)
        .where(*conditions)
        # Soonest date first: the one that needs attention now is the one at the top.
        .order_by(Fundraiser.event_date, Fundraiser.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return list(rows), total


def volunteers(db: Session, fundraiser_id: UUID) -> list[tuple[User, int, int]]:
    """Everyone with a card on this board, and how much of it is theirs."""
    rows = db.execute(
        select(User, func.count(), func.count().filter(Task.status == "done"))
        .join(Task, Task.assignee_id == User.id)
        .where(Task.fundraiser_id == fundraiser_id)
        .group_by(User.id)
        .order_by(func.count().desc(), User.full_name)
    ).all()
    return [(user, total, done) for user, total, done in rows]


# --- writes -----------------------------------------------------------------------------------


def _assert_owner(db: Session, owner_id: UUID | None, fallback: User) -> User:
    if owner_id is None or owner_id == fallback.id:
        return fallback
    owner = db.get(User, owner_id)
    if owner is None or not owner.is_active or ROLE_RANK.get(owner.role, 0) < ROLE_RANK["organizer"]:
        raise AppError(
            422,
            "INVALID_OWNER",
            "The owner must be an active organizer or above",
            {"owner_id": str(owner_id)},
        )
    return owner


def _assert_event_date(event_date: date, status: str) -> None:
    # A finished fundraiser is history and may be recorded with any date; a live one cannot be
    # planned for a day that has already gone.
    if status != "done" and event_date < date.today():
        raise AppError(
            422,
            "VALIDATION_ERROR",
            "event_date is in the past - only a fundraiser being recorded as done may have one",
            {"event_date": event_date.isoformat()},
        )


def create_fundraiser(db: Session, data: dict, actor: User) -> Fundraiser:
    status = data.get("status", "planning")
    if status not in FUNDRAISER_STATUSES:
        raise AppError(422, "VALIDATION_ERROR", "Unknown fundraiser status", {"status": status})
    _assert_event_date(data["event_date"], status)
    owner = _assert_owner(db, data.get("owner_id"), actor)

    fundraiser = Fundraiser(
        title=data["title"],
        description=data.get("description"),
        goal_amount=data["goal_amount"],
        event_date=data["event_date"],
        status=status,
        owner_id=owner.id,
        completed_at=datetime.now(UTC) if status == "done" else None,
    )
    db.add(fundraiser)
    db.commit()
    db.refresh(fundraiser)
    return fundraiser


def update_fundraiser(db: Session, fundraiser, data: dict, actor: User, *, force: bool = False) -> Fundraiser:
    """The owner (or an admin) edits it. Status only ever moves one step forward."""
    if fundraiser.owner_id != actor.id and actor.role != "admin":
        raise AppError(
            403,
            "NOT_OWNER",
            "Only the fundraiser's owner (or an admin) can change it",
            {"fundraiser_id": str(fundraiser.id), "owner_id": str(fundraiser.owner_id)},
        )

    new_status = data.get("status")
    if new_status is not None and new_status != fundraiser.status:
        allowed = NEXT_STATUS.get(fundraiser.status)
        if new_status != allowed:
            raise AppError(
                409,
                "INVALID_TRANSITION",
                f"Cannot move a fundraiser from {fundraiser.status} to {new_status}",
                {"from": fundraiser.status, "to": new_status, "allowed": allowed},
            )
        if new_status == "done":
            open_count = db.scalar(
                select(func.count()).select_from(Task).where(Task.fundraiser_id == fundraiser.id, Task.status != "done")
            ) or 0
            if open_count and not force:
                raise AppError(
                    409,
                    "OPEN_TASKS",
                    f"{open_count} task(s) are still open - finish them, or pass force=true to close anyway",
                    {"open_count": open_count},
                )
            fundraiser.completed_at = datetime.now(UTC)

    if "owner_id" in data:
        data = {**data, "owner_id": _assert_owner(db, data["owner_id"], actor).id}
    if "event_date" in data:
        _assert_event_date(data["event_date"], new_status or fundraiser.status)

    for key, value in data.items():
        setattr(fundraiser, key, value)
    db.commit()
    db.refresh(fundraiser)
    return fundraiser


# --- lifecycle gates --------------------------------------------------------------------------


def assert_open(fundraiser) -> None:
    """Tasks on a finished fundraiser are read-only, or the board and the books drift apart."""
    if fundraiser.status == "done":
        raise AppError(
            409,
            "FUNDRAISER_CLOSED",
            "This fundraiser is done - its tasks are read-only",
            {"fundraiser_id": str(fundraiser.id), "status": fundraiser.status},
        )


def income_grace_until(fundraiser) -> datetime | None:
    if fundraiser.status != "done" or fundraiser.completed_at is None:
        return None
    return as_utc(fundraiser.completed_at) + timedelta(days=INCOME_GRACE_DAYS)


def assert_income_open(fundraiser, now: datetime) -> None:
    """Cash counted on the day still arrives after the stall closes - for a week."""
    until = income_grace_until(fundraiser)
    if until is not None and now > until:
        raise AppError(
            409,
            "FUNDRAISER_CLOSED",
            f"Income for this fundraiser closed {INCOME_GRACE_DAYS} days after it was completed",
            {"fundraiser_id": str(fundraiser.id), "closed_at": until.isoformat()},
        )


def raised_total(db: Session, fundraiser_id: UUID) -> int:
    """What one fundraiser has taken, off the ledger (integer paise)."""
    return _money_by(db, [fundraiser_id]).get(fundraiser_id, {"raised": 0, "spent": 0})["raised"]


def volunteers_view(rows: list[tuple[User, int, int]]) -> list[dict]:
    """The same rows, shaped for the response."""
    return [
        {
            "user": person_ref(user),
            "tasks_total": total,
            "tasks_done": done,
            "open_tasks": total - done,
        }
        for user, total, done in rows
    ]
