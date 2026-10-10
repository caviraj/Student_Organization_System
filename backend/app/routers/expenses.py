"""Expense claims and their receipts (DESIGN.md §5, Expenses).

A volunteer submits; a treasurer decides; the treasurer pays. Guests get 401, members 403 —
claiming money back is a volunteer privilege (PRD FR-6.1).

The receipt endpoints are the only `async` routes in the backend, and only because multipart bodies
have to be awaited. The storage call inside them is blocking HTTP, so the service call is pushed to
a threadpool rather than stalling the event loop (DESIGN.md §4 rule 14).
"""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.core.authz import require_permission
from app.core.deps import get_db
from app.models import User
from app.schemas import (
    ExpenseDetailOut,
    ExpenseOut,
    ExpensePageOut,
    ExpensePatchIn,
    ExpenseReceiptOut,
    ExpenseReimburseIn,
    ExpenseReviewIn,
)
from app.services import expenses as expense_service
from app.services import storage

router = APIRouter(prefix="/expenses", tags=["Expenses"])

CLAIM = "volunteer"
TREASURER = "treasurer"


def _detail(db: Session, expense) -> dict:
    return {
        **expense_service.expense_view(expense),
        "history": [expense_service.history_view(row) for row in expense_service.history(db, expense.id)],
    }


@router.post("", response_model=ExpenseOut, status_code=201, summary="Submit an expense claim (volunteer+)")
async def create_expense(
    amount: int = Form(description="Integer paise, 1..5000000", examples=[45000]),
    description: str = Form(examples=["Auto fare to the printer"]),
    category: str = Form(examples=["printing"]),
    incurred_on: str = Form(description="YYYY-MM-DD, today or up to 90 days back", examples=["2026-10-04"]),
    event_id: UUID | None = Form(default=None),
    fundraiser_id: UUID | None = Form(default=None),
    receipt: UploadFile | None = File(
        default=None, description="JPEG/PNG/WebP/PDF, max 5 MB. Optional here, required to approve."
    ),
    user: User = Depends(require_permission("expenses.submit")),
    db: Session = Depends(get_db),
):
    blob = None
    if receipt is not None:
        data = await storage.read_upload(receipt)
        blob = (data, receipt.content_type or "")
    payload = {
        "amount": amount,
        "description": description,
        "category": category,
        "incurred_on": date.fromisoformat(incurred_on),
        "event_id": event_id,
        "fundraiser_id": fundraiser_id,
    }
    expense = await run_in_threadpool(expense_service.create_expense, db, payload, user, blob)
    return expense_service.expense_view(expense)


@router.get("/me", response_model=ExpensePageOut, summary="My claims (volunteer+)")
def my_expenses(
    status: str | None = Query(default=None, description="submitted | approved | rejected | reimbursed | withdrawn"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(require_permission("expenses.submit")),
    db: Session = Depends(get_db),
):
    rows, total = expense_service.list_expenses(db, claimant_id=user.id, status=status, page=page, page_size=page_size)
    return {
        "items": [expense_service.expense_view(row) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("", response_model=ExpensePageOut, summary="Every claim, for the review queue (treasurer+)")
def list_expenses(
    status: str | None = Query(default=None),
    claimant_id: UUID | None = Query(default=None),
    category: str | None = Query(default=None),
    event_id: UUID | None = Query(default=None),
    fundraiser_id: UUID | None = Query(default=None),
    date_from: str | None = Query(default=None, description="Incurred on or after (YYYY-MM-DD)"),
    date_to: str | None = Query(default=None, description="Incurred on or before (YYYY-MM-DD)"),
    q: str | None = Query(default=None, description="Search the description"),
    min_amount: int | None = Query(default=None, ge=0),
    max_amount: int | None = Query(default=None, ge=0),
    sort: str = Query(default="desc", pattern="^(asc|desc)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: User = Depends(require_permission("expenses.view_all")),
    db: Session = Depends(get_db),
):
    filters = {
        "status": status,
        "claimant_id": claimant_id,
        "category": category,
        "event_id": event_id,
        "fundraiser_id": fundraiser_id,
        "date_from": date.fromisoformat(date_from) if date_from else None,
        "date_to": date.fromisoformat(date_to) if date_to else None,
        "q": q,
        "min_amount": min_amount,
        "max_amount": max_amount,
    }
    rows, total = expense_service.list_expenses(db, sort=sort, page=page, page_size=page_size, **filters)
    # Counts come off the same filter minus the status, so the tabs always add up to `total`.
    counts = expense_service.status_counts(db, *expense_service.expense_conditions(**{**filters, "status": None}))
    return {
        "items": [expense_service.expense_view(row) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        **counts,
    }


@router.get("/{expense_id}", response_model=ExpenseDetailOut, summary="One claim, with its history")
def get_expense(
    expense_id: UUID,
    user: User = Depends(require_permission("expenses.submit")),
    db: Session = Depends(get_db),
):
    expense = expense_service.get_expense(db, expense_id)
    expense_service.assert_can_view(db, expense, user)
    return _detail(db, expense)


@router.patch("/{expense_id}", response_model=ExpenseOut, summary="Edit a claim (owner, while open)")
def update_expense(
    expense_id: UUID,
    payload: ExpensePatchIn,
    user: User = Depends(require_permission("expenses.submit")),
    db: Session = Depends(get_db),
):
    expense = expense_service.get_expense(db, expense_id)
    expense = expense_service.update_expense(db, expense, payload.model_dump(exclude_unset=True), user)
    return expense_service.expense_view(expense)


@router.put("/{expense_id}/receipt", response_model=ExpenseOut, summary="Attach or replace the receipt (owner)")
async def replace_receipt(
    expense_id: UUID,
    receipt: UploadFile = File(description="JPEG/PNG/WebP/PDF, max 5 MB"),
    user: User = Depends(require_permission("expenses.submit")),
    db: Session = Depends(get_db),
):
    data = await storage.read_upload(receipt)
    expense = expense_service.get_expense(db, expense_id)
    expense = await run_in_threadpool(
        expense_service.replace_receipt, db, expense, (data, receipt.content_type or ""), user
    )
    return expense_service.expense_view(expense)


@router.get("/{expense_id}/receipt", response_model=ExpenseReceiptOut, summary="A signed URL for the receipt")
def get_receipt(
    expense_id: UUID,
    user: User = Depends(require_permission("expenses.submit")),
    db: Session = Depends(get_db),
):
    expense = expense_service.get_expense(db, expense_id)
    expense_service.assert_can_view(db, expense, user)
    # The path stays on the server: this endpoint hands out a URL, and nothing else.
    return expense_service.receipt_url(expense)


@router.delete("/{expense_id}", response_model=ExpenseOut, summary="Withdraw a claim (owner, submitted only)")
def withdraw_expense(
    expense_id: UUID,
    user: User = Depends(require_permission("expenses.submit")),
    db: Session = Depends(get_db),
):
    expense = expense_service.get_expense(db, expense_id)
    expense = expense_service.withdraw_expense(db, expense, user)
    return expense_service.expense_view(expense)


@router.patch("/{expense_id}/review", response_model=ExpenseOut, summary="Approve or reject (treasurer+)")
def review_expense(
    expense_id: UUID,
    payload: ExpenseReviewIn,
    reviewer: User = Depends(require_permission("expenses.review")),
    db: Session = Depends(get_db),
):
    expense = expense_service.get_expense(db, expense_id)
    expense = expense_service.review_expense(db, expense, reviewer, payload.decision, payload.note)
    return expense_service.expense_view(expense)


@router.post("/{expense_id}/reimburse", response_model=ExpenseOut, summary="Pay an approved claim (treasurer+)")
def reimburse_expense(
    expense_id: UUID,
    payload: ExpenseReimburseIn,
    treasurer: User = Depends(require_permission("expenses.reimburse")),
    db: Session = Depends(get_db),
):
    expense = expense_service.get_expense(db, expense_id)
    expense, _ = expense_service.reimburse_expense(
        db, expense, treasurer, payload.method, payload.reference, payload.allow_negative
    )
    return expense_service.expense_view(expense)
