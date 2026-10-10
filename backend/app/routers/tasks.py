"""Tasks outside a fundraiser page: one card, the board move, the delete, my own list and a trail
(DESIGN.md §5, Tasks). Organizer and above change a card; its assignee may only move it between
columns, which the service enforces.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_role
from app.models import User
from app.schemas import Page, TaskActivityOut, TaskMoveIn, TaskOut, TaskUpdateIn
from app.services import tasks as task_service

router = APIRouter(prefix="/tasks", tags=["Tasks"])

READ = "volunteer"
WRITE = "organizer"


@router.get("", response_model=Page[TaskOut], summary="Search tasks across every board (volunteer+)")
def list_tasks(
    fundraiser_id: UUID | None = Query(default=None),
    event_id: UUID | None = Query(default=None),
    status: str | None = Query(default=None, description="todo | doing | done"),
    assignee_id: UUID | None = Query(default=None),
    category: str | None = Query(default=None, description="baking | supplies | table_duty | promotion | other"),
    overdue: bool = Query(default=False, description="Only past-due, unfinished cards"),
    q: str | None = Query(default=None, description="Search title or description"),
    sort: str = Query(default="board", pattern="^(board|due_date)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    _: User = Depends(require_role(READ)),
    db: Session = Depends(get_db),
):
    rows, total = task_service.list_tasks(
        db,
        fundraiser_id=fundraiser_id,
        event_id=event_id,
        status=status,
        assignee_id=assignee_id,
        category=category,
        overdue=overdue,
        q=q,
        sort=sort,
        page=page,
        page_size=page_size,
    )
    return {"items": [task_service.task_view(task) for task in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/me", response_model=Page[TaskOut], summary="My own cards, overdue first (volunteer+)")
def my_tasks(
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    user: User = Depends(require_role(READ)),
    db: Session = Depends(get_db),
):
    rows, total = task_service.my_tasks(db, user, status=status, page=page, page_size=page_size)
    return {"items": [task_service.task_view(task) for task in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/{task_id}", response_model=TaskOut, summary="One task (volunteer+)")
def get_task(task_id: UUID, _: User = Depends(require_role(READ)), db: Session = Depends(get_db)):
    return task_service.task_view(task_service.get_task(db, task_id))


@router.patch("/{task_id}", response_model=TaskOut, summary="Edit a task (organizer+; assignee may set status only)")
def update_task(
    task_id: UUID,
    payload: TaskUpdateIn,
    user: User = Depends(require_role(READ)),
    db: Session = Depends(get_db),
):
    task = task_service.get_task(db, task_id)
    return task_service.task_view(task_service.update_task(db, task, payload.model_dump(exclude_unset=True), user))


@router.post(
    "/{task_id}/move",
    response_model=TaskOut,
    summary="Move a card to a column and a slot (organizer+, or the assignee moving their own)",
)
def move_task(
    task_id: UUID,
    payload: TaskMoveIn,
    user: User = Depends(require_role(READ)),
    db: Session = Depends(get_db),
):
    task = task_service.get_task(db, task_id)
    return task_service.task_view(task_service.move_task(db, task, payload.status, payload.position, user))


@router.delete("/{task_id}", status_code=204, summary="Delete a task (organizer+; its activity log is kept)")
def delete_task(task_id: UUID, user: User = Depends(require_role(WRITE)), db: Session = Depends(get_db)):
    task_service.delete_task(db, task_service.get_task(db, task_id), user)


@router.get("/{task_id}/activity", response_model=Page[TaskActivityOut], summary="A task's trail, newest first (volunteer+)")
def task_activity(
    task_id: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    _: User = Depends(require_role(READ)),
    db: Session = Depends(get_db),
):
    rows, total = task_service.activity(db, task_id, page=page, page_size=page_size)
    return {"items": [task_service.activity_view(row) for row in rows], "total": total, "page": page, "page_size": page_size}
