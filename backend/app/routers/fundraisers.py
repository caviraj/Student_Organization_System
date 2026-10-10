"""Fundraisers, their boards, their income and their people (DESIGN.md §5, Fundraisers).

Reading needs volunteer and above; changing one needs organizer and above. There is no DELETE: a
fundraiser that happened is a fact, and its ledger rows have to keep a parent.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from app.core.authz import require_permission
from app.core.deps import get_db
from app.models import User
from app.schemas import (
    FundraiserCreateIn,
    FundraiserListItemOut,
    FundraiserOut,
    FundraiserUpdateIn,
    FundraiserVolunteerOut,
    IncomeCreateIn,
    IncomeListItemOut,
    IncomeOut,
    Page,
    TaskBoardOut,
    TaskCreateIn,
    TaskOut,
)
from app.services import fundraisers as fundraiser_service
from app.services import income as income_service
from app.services import tasks as task_service

router = APIRouter(prefix="/fundraisers", tags=["Fundraisers"])
income_router = APIRouter(prefix="/fundraisers", tags=["Fundraiser Income"])

READ = "volunteer"
WRITE = "organizer"


@router.get("", response_model=Page[FundraiserListItemOut], summary="List fundraisers (volunteer+)")
def list_fundraisers(
    status: str | None = Query(default=None, description="planning | active | done"),
    owner_id: UUID | None = Query(default=None),
    q: str | None = Query(default=None, description="Search title or description"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: User = Depends(require_permission("fundraisers.view")),
    db: Session = Depends(get_db),
):
    rows, total = fundraiser_service.list_fundraisers(
        db, status=status, q=q, owner_id=owner_id, page=page, page_size=page_size
    )
    # One batched progress pass for the page, not one per row.
    progress = fundraiser_service.progress_for(db, rows)
    return {
        "items": [fundraiser_service.list_item_view(row, progress[row.id]) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("", response_model=FundraiserOut, status_code=201, summary="Create a fundraiser (organizer+)")
def create_fundraiser(
    payload: FundraiserCreateIn,
    user: User = Depends(require_permission("fundraisers.manage")),
    db: Session = Depends(get_db),
):
    fundraiser = fundraiser_service.create_fundraiser(db, payload.model_dump(), user)
    return fundraiser_service.fundraiser_view(fundraiser, fundraiser_service.compute_progress(db, fundraiser))


@router.get("/{fundraiser_id}", response_model=FundraiserOut, summary="One fundraiser, with full progress (volunteer+)")
def get_fundraiser(
    fundraiser_id: UUID,
    _: User = Depends(require_permission("fundraisers.view")),
    db: Session = Depends(get_db),
):
    fundraiser = fundraiser_service.get_fundraiser(db, fundraiser_id)
    return fundraiser_service.fundraiser_view(fundraiser, fundraiser_service.compute_progress(db, fundraiser))


@router.patch(
    "/{fundraiser_id}",
    response_model=FundraiserOut,
    summary="Update a fundraiser - owner or admin (planning -> active -> done)",
)
def update_fundraiser(
    fundraiser_id: UUID,
    payload: FundraiserUpdateIn,
    force: bool = Query(default=False, description="Close with open tasks anyway"),
    user: User = Depends(require_permission("fundraisers.manage")),
    db: Session = Depends(get_db),
):
    fundraiser = fundraiser_service.get_fundraiser(db, fundraiser_id)
    updated = fundraiser_service.update_fundraiser(
        db, fundraiser, payload.model_dump(exclude_unset=True), user, force=force
    )
    return fundraiser_service.fundraiser_view(updated, fundraiser_service.compute_progress(db, updated))


@router.get("/{fundraiser_id}/tasks", response_model=TaskBoardOut, summary="The task board (volunteer+)")
def fundraiser_tasks(
    fundraiser_id: UUID,
    status: str | None = Query(default=None, description="Filter to one column"),
    assignee_id: UUID | None = Query(default=None),
    category: str | None = Query(default=None),
    q: str | None = Query(default=None),
    _: User = Depends(require_permission("fundraisers.view")),
    db: Session = Depends(get_db),
):
    fundraiser_service.get_fundraiser(db, fundraiser_id)
    cards, columns = task_service.board(
        db, fundraiser_id=fundraiser_id, status=status, assignee_id=assignee_id, category=category, q=q
    )
    return {
        "items": [task_service.task_view(card) for card in cards],
        "columns": {
            column: [task_service.task_view(card) for card in cards_in_column]
            for column, cards_in_column in columns.items()
        },
        "counts": {column: len(cards_in_column) for column, cards_in_column in columns.items()},
    }


@router.post(
    "/{fundraiser_id}/tasks",
    response_model=TaskOut,
    status_code=201,
    summary="Add a task to the board (organizer+)",
)
def create_task(
    fundraiser_id: UUID,
    payload: TaskCreateIn,
    user: User = Depends(require_permission("tasks.manage")),
    db: Session = Depends(get_db),
):
    task = task_service.create_task(db, {**payload.model_dump(), "fundraiser_id": fundraiser_id}, user)
    return task_service.task_view(task)


@router.get(
    "/{fundraiser_id}/volunteers",
    response_model=list[FundraiserVolunteerOut],
    summary="Who is on this board (volunteer+)",
)
def fundraiser_volunteers(
    fundraiser_id: UUID,
    _: User = Depends(require_permission("fundraisers.view")),
    db: Session = Depends(get_db),
):
    fundraiser_service.get_fundraiser(db, fundraiser_id)
    return fundraiser_service.volunteers_view(fundraiser_service.volunteers(db, fundraiser_id))


@income_router.post(
    "/{fundraiser_id}/income",
    response_model=IncomeOut,
    status_code=201,
    summary="Log cash taken (organizer+; Idempotency-Key honoured)",
)
def log_income(
    fundraiser_id: UUID,
    payload: IncomeCreateIn,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=64),
    user: User = Depends(require_permission("income.log")),
    db: Session = Depends(get_db),
):
    """Adds one `in` ledger row (source=fundraiser). Send the same `Idempotency-Key` twice - a
    double-click, a retry - and the second call replays the first row instead of counting the cash
    again. There is no PATCH and no DELETE: ledger rows are never rewritten."""
    entry, replayed = income_service.log_fundraiser_income(
        db,
        user,
        fundraiser_id,
        payload.amount,
        note=payload.note,
        source_label=payload.source_label,
        idempotency_key=idempotency_key,
        occurred_at=payload.occurred_at,
    )
    fundraiser = fundraiser_service.get_fundraiser(db, fundraiser_id)
    return income_service.income_view(db, entry, fundraiser, replayed=replayed)


@income_router.get(
    "/{fundraiser_id}/income",
    response_model=Page[IncomeListItemOut],
    summary="The cash book for one fundraiser (volunteer+)",
)
def list_income(
    fundraiser_id: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: User = Depends(require_permission("fundraisers.view")),
    db: Session = Depends(get_db),
):
    items, total = income_service.list_fundraiser_income(db, fundraiser_id, page=page, page_size=page_size)
    return {"items": items, "total": total, "page": page, "page_size": page_size}
