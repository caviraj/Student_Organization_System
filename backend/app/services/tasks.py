"""The task board: cards, columns, and the trail behind each card (PRD FR-5.2, DESIGN.md §4 rule 13).

Every route into a task change goes through `update_task` or `move_task`, so the activity row and
the `completed_at` stamp can never be forgotten. `position` orders a card inside its column of its
board and is rewritten densely whenever a card moves, which is what makes a drag-and-drop drop
land where the user let go.
"""

from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.core.authz import has_permission
from app.core.errors import AppError
from app.core.permissions import ROLE_PERMISSIONS
from app.models import ROLES, Event, Fundraiser, Task, TaskActivity, User
from app.services import fundraisers as fundraiser_service

MIN_TITLE = 3
MAX_TITLE = 120
STATUS_ORDER = {"todo": 0, "doing": 1, "done": 2}
BOARD_COLUMNS = ("todo", "doing", "done")

_status_rank = case(STATUS_ORDER, value=Task.status)


def is_organizer(db: Session, actor: User) -> bool:
    return has_permission(db, actor, "tasks.manage")


# --- helpers ----------------------------------------------------------------------------------


def board_filter(task: Task) -> list:
    """A card hangs off a fundraiser or an event; either way `position` is scoped to that board."""
    if task.fundraiser_id is not None:
        return [Task.fundraiser_id == task.fundraiser_id]
    return [Task.event_id == task.event_id]


def position_filter(fundraiser_id: UUID | None, event_id: UUID | None) -> list:
    return [Task.fundraiser_id == fundraiser_id] if fundraiser_id is not None else [Task.event_id == event_id]


def _column(db: Session, board: list, status: str) -> list[Task]:
    return list(
        db.scalars(select(Task).where(*board, Task.status == status).order_by(Task.position, Task.created_at, Task.id))
    )


def _write_positions(tasks: list[Task]) -> None:
    for index, task in enumerate(tasks):
        task.position = index


def _log(
    db: Session, task: Task, actor: User, action: str, from_value: str | None = None, to_value: str | None = None
) -> None:
    db.add(TaskActivity(task_id=task.id, actor_id=actor.id, action=action, from_value=from_value, to_value=to_value))


def _assert_may_edit(db: Session, task: Task, actor: User, *, fields: dict | None = None) -> None:
    """Organizer and above edit anything. The assignee owns one thing only: the column their own
    card sits in (PRD FR-5.2) - everything else about it belongs to the organizer."""
    if is_organizer(db, actor):
        return
    if task.assignee_id != actor.id:
        raise AppError(
            403,
            "FORBIDDEN",
            "Only the assignee or an organizer can change this task",
            {"task_id": str(task.id), "your_role": actor.role},
        )
    if fields:
        raise AppError(
            403,
            "FORBIDDEN",
            "An assignee may only move their own task between columns",
            {"fields": sorted(fields)},
        )


def _get_board(db: Session, data: dict) -> tuple[UUID | None, UUID | None, Fundraiser | None, Event | None]:
    """Exactly one board, and it must exist and still accept work."""
    fundraiser_id, event_id = data.get("fundraiser_id"), data.get("event_id")
    if (fundraiser_id is None) == (event_id is None):
        raise AppError(
            422, "VALIDATION_ERROR", "A task belongs to exactly one fundraiser or one event", {"data": {**data}}
        )
    if fundraiser_id is not None:
        fundraiser = fundraiser_service.get_fundraiser(db, fundraiser_id)
        fundraiser_service.assert_open(fundraiser)
        return fundraiser_id, None, fundraiser, None
    event = db.get(Event, event_id)
    if event is None:
        raise AppError(404, "EVENT_NOT_FOUND", "No event with that id", {"event_id": str(event_id)})
    return None, event_id, None, event


def _assert_assignee(db: Session, assignee_id: UUID | None) -> None:
    if assignee_id is None:
        return
    assignee = db.get(User, assignee_id)
    if assignee is None or not assignee.is_active or not has_permission(db, assignee, "tasks.update_own"):
        raise AppError(
            422,
            "INVALID_ASSIGNEE",
            "The assignee must be an active volunteer or above",
            {"assignee_id": str(assignee_id)},
        )


def _assert_due_date(due_date: date | None, fundraiser: Fundraiser | None, event: Event | None) -> None:
    last_day = fundraiser.event_date if fundraiser is not None else (event.starts_at.date() if event else None)
    if due_date is not None and last_day is not None and due_date > last_day:
        raise AppError(
            422,
            "DUE_AFTER_EVENT",
            "A task cannot be due after the day it is being prepared for",
            {"due_date": due_date.isoformat(), "event_date": last_day.isoformat()},
        )


# --- views ------------------------------------------------------------------------------------


def task_view(task: Task, *, today: date | None = None) -> dict:
    today = today or date.today()
    return {
        "id": task.id,
        "fundraiser_id": task.fundraiser_id,
        "event_id": task.event_id,
        "title": task.title,
        "description": task.description,
        "category": task.category,
        "assignee_id": task.assignee_id,
        "assignee": fundraiser_service.person_ref(task.assignee),
        "due_date": task.due_date,
        "status": task.status,
        "position": task.position,
        "is_overdue": task.status != "done" and task.due_date is not None and task.due_date < today,
        "completed_at": task.completed_at,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


def activity_view(row: TaskActivity) -> dict:
    return {
        "id": row.id,
        "task_id": row.task_id,
        "actor": fundraiser_service.person_ref(row.actor),
        "action": row.action,
        "from_value": row.from_value,
        "to_value": row.to_value,
        "created_at": row.created_at,
    }


# --- reads ------------------------------------------------------------------------------------


def get_task(db: Session, task_id: UUID) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise AppError(404, "TASK_NOT_FOUND", "No task with that id", {"task_id": str(task_id)})
    return task


def task_conditions(
    *,
    fundraiser_id: UUID | None = None,
    event_id: UUID | None = None,
    status: str | None = None,
    assignee_id: UUID | None = None,
    category: str | None = None,
    overdue: bool = False,
    q: str | None = None,
    today: date | None = None,
) -> list:
    today = today or date.today()
    conditions = []
    if fundraiser_id is not None:
        conditions.append(Task.fundraiser_id == fundraiser_id)
    if event_id is not None:
        conditions.append(Task.event_id == event_id)
    if status:
        conditions.append(Task.status == status)
    if assignee_id is not None:
        conditions.append(Task.assignee_id == assignee_id)
    if category:
        conditions.append(Task.category == category)
    if overdue:
        conditions.append(Task.status != "done")
        conditions.append(Task.due_date < today)
    if q:
        like = f"%{q}%"
        conditions.append(or_(Task.title.ilike(like), Task.description.ilike(like)))
    return conditions


def list_tasks(
    db: Session,
    *,
    fundraiser_id: UUID | None = None,
    event_id: UUID | None = None,
    status: str | None = None,
    assignee_id: UUID | None = None,
    category: str | None = None,
    overdue: bool = False,
    q: str | None = None,
    sort: str = "board",
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[Task], int]:
    conditions = task_conditions(
        fundraiser_id=fundraiser_id,
        event_id=event_id,
        status=status,
        assignee_id=assignee_id,
        category=category,
        overdue=overdue,
        q=q,
    )
    order = (
        (Task.due_date.is_(None), Task.due_date, Task.position, Task.created_at)
        if sort == "due_date"
        else (_status_rank, Task.position, Task.created_at)
    )
    total = db.scalar(select(func.count()).select_from(Task).where(*conditions)) or 0
    rows = db.scalars(
        select(Task).where(*conditions).order_by(*order).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return list(rows), total


def board(db: Session, **filters) -> tuple[list[Task], dict[str, list[Task]]]:
    """Every card of one board, flat in board order and bucketed by column. Not paginated: the
    kanban shows the whole board, and a fundraiser's board is a few dozen cards at most."""
    tasks, _ = list_tasks(db, page_size=1000, **filters)
    columns = {column: [task for task in tasks if task.status == column] for column in BOARD_COLUMNS}
    return tasks, columns


def my_tasks(
    db: Session, user: User, *, status: str | None = None, page: int = 1, page_size: int = 50
) -> tuple[list[Task], int]:
    """Overdue first: a card with no due date is not urgent, so it sorts last."""
    conditions = [Task.assignee_id == user.id]
    if status:
        conditions.append(Task.status == status)
    total = db.scalar(select(func.count()).select_from(Task).where(*conditions)) or 0
    rows = db.scalars(
        select(Task)
        .where(*conditions)
        .order_by(Task.due_date.is_(None), Task.due_date, Task.created_at)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return list(rows), total


def activity(db: Session, task_id: UUID, *, page: int = 1, page_size: int = 50) -> tuple[list[TaskActivity], int]:
    get_task(db, task_id)  # 404 rather than an empty page for an unknown task
    conditions = [TaskActivity.task_id == task_id]
    total = db.scalar(select(func.count()).select_from(TaskActivity).where(*conditions)) or 0
    rows = db.scalars(
        select(TaskActivity)
        .where(*conditions)
        .order_by(TaskActivity.created_at.desc(), TaskActivity.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return list(rows), total


def open_task_count(db: Session, fundraiser_id: UUID) -> int:
    return (
        db.scalar(
            select(func.count()).select_from(Task).where(Task.fundraiser_id == fundraiser_id, Task.status != "done")
        )
        or 0
    )


# --- writes -----------------------------------------------------------------------------------


def create_task(db: Session, data: dict, actor: User) -> Task:
    title = (data.get("title") or "").strip()
    if not MIN_TITLE <= len(title) <= MAX_TITLE:
        raise AppError(422, "VALIDATION_ERROR", f"title must be {MIN_TITLE}-{MAX_TITLE} characters")

    fundraiser_id, event_id, fundraiser, event = _get_board(db, data)
    _assert_assignee(db, data.get("assignee_id"))
    _assert_due_date(data.get("due_date"), fundraiser, event)

    status = data.get("status", "todo")
    last = db.scalar(
        select(func.max(Task.position)).where(*position_filter(fundraiser_id, event_id), Task.status == status)
    )
    task = Task(
        fundraiser_id=fundraiser_id,
        event_id=event_id,
        title=title,
        description=data.get("description"),
        category=data.get("category", "other"),
        assignee_id=data.get("assignee_id"),
        due_date=data.get("due_date"),
        status=status,
        created_by=actor.id,
        position=(last if last is not None else -1) + 1,  # new cards land at the bottom of the column
    )
    db.add(task)
    db.flush()
    if status == "done":
        task.completed_at = datetime.now(UTC)
    _log(db, task, actor, "created", None, task.title)
    db.commit()
    db.refresh(task)
    return task


def _apply_status(task: Task, new_status: str, actor: User, db: Session) -> bool:
    if new_status == task.status:
        return False
    previous, task.status = task.status, new_status
    task.completed_at = datetime.now(UTC) if new_status == "done" else None
    _log(db, task, actor, "status_changed", previous, new_status)
    return True


def update_task(db: Session, task: Task, data: dict, actor: User) -> Task:
    _assert_may_edit(db, task, actor, fields={k: v for k, v in data.items() if k != "status"} or None)
    if task.fundraiser_id is not None:
        fundraiser_service.assert_open(task.fundraiser)  # a finished board is read-only

    new_status = data.get("status")
    if new_status is not None and new_status != task.status:
        _apply_status(task, new_status, actor, db)

    if "assignee_id" in data and data["assignee_id"] != task.assignee_id:
        _assert_assignee(db, data["assignee_id"])
        _log(db, task, actor, "assigned", _user_label(task.assignee_id), _user_label(data["assignee_id"]))
        task.assignee_id = data["assignee_id"]

    if "due_date" in data and data["due_date"] != task.due_date:
        fundraiser = db.get(Fundraiser, task.fundraiser_id) if task.fundraiser_id else None
        event = db.get(Event, task.event_id) if task.event_id else None
        _assert_due_date(data["due_date"], fundraiser, event)
        _log(db, task, actor, "due_changed", _date_label(task.due_date), _date_label(data["due_date"]))
        task.due_date = data["due_date"]

    edited = sorted(
        key for key in data if key not in ("status", "assignee_id", "due_date") and getattr(task, key) != data[key]
    )
    for key in edited:
        setattr(task, key, data[key])
    if edited:
        _log(db, task, actor, "edited", ", ".join(edited), None)

    db.commit()
    db.refresh(task)
    return task


def move_task(db: Session, task: Task, new_status: str, position: int | None, actor: User) -> Task:
    """Drag and drop: land in a column, at a slot. Positions are rewritten densely in both the
    column left behind and the column landed in."""
    _assert_may_edit(db, task, actor)
    if task.fundraiser_id is not None:
        fundraiser_service.assert_open(task.fundraiser)  # a finished board is read-only

    board = board_filter(task)
    same_column = new_status == task.status
    source = [card for card in _column(db, board, task.status) if card.id != task.id]
    if not same_column:
        _write_positions(source)
    target = source if same_column else [card for card in _column(db, board, new_status) if card.id != task.id]

    index = len(target) if position is None else max(0, min(position, len(target)))
    target.insert(index, task)
    _apply_status(task, new_status, actor, db)
    _write_positions(target)
    db.commit()
    db.refresh(task)
    return task


def delete_task(db: Session, task: Task, actor: User) -> None:
    """Organizer and above. The trail outlives the card: `task_activity.task_id` is ON DELETE SET
    NULL, so the final row carries the title and nothing else is lost (DESIGN.md §4 rule 13)."""
    if not is_organizer(db, actor):
        raise AppError(403, "FORBIDDEN", "Only an organizer or above can delete a task", {"your_role": actor.role})
    board = board_filter(task)
    status = task.status
    task_id = task.id
    _log(db, task, actor, "edited", task.title, "deleted")
    db.flush()
    db.delete(task)
    db.flush()
    remaining = [card for card in _column(db, board, status) if card.id != task_id]
    _write_positions(remaining)
    db.commit()


def assignable_users(db: Session) -> list[User]:
    """The assignee picker: anyone who may move a card of their own, by permission rather than by a
    hard-coded ladder.

    shortcut: reads the permission catalog, not the `roles` tables, so a custom role created
    through Step 4's role API and granted `tasks.update_own` is missing from the picker until the
    next deploy. Upgrade when the role API can create roles the catalog does not know.

    Intersected with `ROLES`: `users.role` is a database enum of the ladder only, so a role like
    `event_lead` reaches a user through an assignment and never through this column.
    """
    roles = [key for key, perms in ROLE_PERMISSIONS.items() if "tasks.update_own" in perms and key in ROLES]
    return list(db.scalars(select(User).where(User.is_active.is_(True), User.role.in_(roles)).order_by(User.full_name)))


def _user_label(user_id: UUID | None) -> str | None:
    return str(user_id) if user_id else "unassigned"


def _date_label(value: date | None) -> str | None:
    return value.isoformat() if value else "none"
