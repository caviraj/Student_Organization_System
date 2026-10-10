"""The treasurer's dashboard, ledger controls, reports and closed periods (DESIGN.md §5, Finance).

Everything here needs treasurer and above, except reopening a closed period, which is admin-only —
and that is the whole point of the feature: the person who froze the books cannot quietly unfreeze
them. Nothing in this router moves money except `POST /finance/transactions` (a manual entry) and
`POST /finance/transactions/{id}/reverse`; reimbursements happen on the expense router.
"""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from app.core.authz import require_permission
from app.core.deps import get_db
from app.core.errors import AppError
from app.models import User
from app.schemas import (
    ClosePeriodIn,
    DimensionTotalOut,
    FinancePeriodOut,
    FinanceSummaryOut,
    ManualEntryIn,
    OutstandingReimbursementOut,
    Page,
    ReconcileOut,
    ReopenPeriodIn,
    ReverseIn,
    SemesterReportOut,
    TransactionOut,
)
from app.services import finance as finance_service

router = APIRouter(prefix="/finance", tags=["Finance"])
periods_router = APIRouter(prefix="/finance/periods", tags=["Finance Periods"])

TREASURER = "treasurer"
ADMIN = "admin"


@router.get("/summary", response_model=FinanceSummaryOut, summary="KPIs for the dashboard (treasurer+)")
def summary(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    _: User = Depends(require_permission("finance.view")),
    db: Session = Depends(get_db),
):
    return finance_service.summary(db, date_from, date_to)


@router.get("/transactions", response_model=Page[TransactionOut], summary="The ledger table (treasurer+)")
def list_transactions(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    source: str | None = Query(
        default=None,
        description="dues | tickets | merch | fundraiser | other_income | other_expense | expense_reimbursement",
    ),
    direction: str | None = Query(default=None, pattern="^(in|out)$"),
    event_id: UUID | None = Query(default=None),
    fundraiser_id: UUID | None = Query(default=None),
    q: str | None = Query(default=None, description="Search the note"),
    is_reversal: bool | None = Query(default=None),
    sort: str = Query(default="desc", pattern="^(asc|desc)$", description="`asc` also fills `running_balance`"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: User = Depends(require_permission("finance.view")),
    db: Session = Depends(get_db),
):
    items, total = finance_service.list_transactions(
        db,
        sort=sort,
        page=page,
        page_size=page_size,
        date_from=date_from,
        date_to=date_to,
        source=source,
        direction=direction,
        event_id=event_id,
        fundraiser_id=fundraiser_id,
        q=q,
        is_reversal=is_reversal,
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post(
    "/transactions", response_model=TransactionOut, status_code=201, summary="Manual ledger entry (treasurer+)"
)
def manual_entry(
    payload: ManualEntryIn,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=64),
    user: User = Depends(require_permission("finance.manage_entries")),
    db: Session = Depends(get_db),
):
    expected = "in" if payload.source == "other_income" else "out"
    if payload.direction is not None and payload.direction != expected:
        raise AppError(
            422,
            "VALIDATION_ERROR",
            f"A {payload.source} row moves money {expected}",
            {"source": payload.source, "direction": payload.direction, "expected_direction": expected},
        )
    data = payload.model_dump()
    data.pop("direction", None)
    # `model_dump()` runs the `UtcDateTime` serializer, so the dump holds an ISO string where the
    # service expects the datetime itself.
    data["occurred_at"] = payload.occurred_at
    entry, _ = finance_service.manual_entry(db, user, data, idempotency_key)
    return finance_service.transaction_view(entry, actor=user)


@router.post(
    "/transactions/{transaction_id}/reverse",
    response_model=TransactionOut,
    status_code=201,
    summary="Reverse a manual ledger row (treasurer+)",
)
def reverse_transaction(
    transaction_id: UUID,
    payload: ReverseIn,
    user: User = Depends(require_permission("finance.reverse")),
    db: Session = Depends(get_db),
):
    entry = finance_service.reverse_transaction(db, user, transaction_id, payload.reason)
    return finance_service.transaction_view(entry, actor=user)


@router.get("/by-event", response_model=list[DimensionTotalOut], summary="Income and spend per event (treasurer+)")
def by_event(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    _: User = Depends(require_permission("finance.view")),
    db: Session = Depends(get_db),
):
    return finance_service.by_event(db, date_from, date_to)


@router.get(
    "/by-fundraiser", response_model=list[DimensionTotalOut], summary="Income and spend per fundraiser (treasurer+)"
)
def by_fundraiser(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    _: User = Depends(require_permission("finance.view")),
    db: Session = Depends(get_db),
):
    return finance_service.by_fundraiser(db, date_from, date_to)


@router.get(
    "/outstanding-reimbursements",
    response_model=list[OutstandingReimbursementOut],
    summary="Who is waiting to be paid (treasurer+)",
)
def outstanding_reimbursements(
    _: User = Depends(require_permission("finance.view")),
    db: Session = Depends(get_db),
):
    return finance_service.outstanding_reimbursements(db)


@router.get("/reconcile", response_model=ReconcileOut, summary="Do the books add up? (treasurer+)")
def reconcile(
    _: User = Depends(require_permission("finance.view")),
    db: Session = Depends(get_db),
):
    return finance_service.reconcile(db)


@router.get("/report", response_model=SemesterReportOut, summary="Semester report for a date range (treasurer+)")
def report(
    from_: date = Query(alias="from", description="First day of the period"),
    to: date = Query(description="Last day of the period, inclusive"),
    _: User = Depends(require_permission("finance.view")),
    db: Session = Depends(get_db),
):
    return finance_service.semester_report(db, from_, to)


@periods_router.get("", response_model=list[FinancePeriodOut], summary="Closed and reopened periods (treasurer+)")
def list_periods(
    _: User = Depends(require_permission("finance.view")),
    db: Session = Depends(get_db),
):
    return [finance_service.period_view(period) for period in finance_service.list_periods(db)]


@periods_router.post("", response_model=FinancePeriodOut, status_code=201, summary="Close a period (treasurer+)")
def close_period(
    payload: ClosePeriodIn,
    user: User = Depends(require_permission("finance.close_period")),
    db: Session = Depends(get_db),
):
    period = finance_service.close_period(db, user, payload.name, payload.start_date, payload.end_date, payload.force)
    return finance_service.period_view(period)


@periods_router.post("/{period_id}/reopen", response_model=FinancePeriodOut, summary="Reopen a period (admin only)")
def reopen_period(
    period_id: UUID,
    payload: ReopenPeriodIn,
    user: User = Depends(require_permission("finance.reopen_period")),
    db: Session = Depends(get_db),
):
    period = finance_service.reopen_period(db, user, period_id, payload.reason)
    return finance_service.period_view(period)
