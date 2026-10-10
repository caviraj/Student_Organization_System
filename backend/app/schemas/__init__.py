"""Pydantic v2 request/response models. Kept separate from the ORM models (AGENTS.md)."""

from datetime import date, datetime
from typing import Annotated, Generic, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, PlainSerializer

from app.core.db import as_utc

T = TypeVar("T")

Role = Literal["admin", "treasurer", "organizer", "volunteer", "member", "guest"]


def _iso_z(value: datetime) -> str:
    """Always emit `...Z`. Postgres hands back aware datetimes and SQLite naive ones, so
    without this the same API would describe the same event differently on dev and prod."""
    return as_utc(value).isoformat().replace("+00:00", "Z")


UtcDateTime = Annotated[datetime, PlainSerializer(_iso_z, return_type=str)]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    """DESIGN.md §5 list shape."""

    items: list[T]
    total: int
    page: int
    page_size: int


# --- users / auth -----------------------------------------------------------------
class UserOut(ORMModel):
    id: UUID
    email: EmailStr
    full_name: str
    phone: str | None = None
    department: str | None = None
    year: int | None = None
    role: str
    member_code: str | None = None
    email_opt_in: bool
    is_active: bool
    created_at: datetime


class RegisterIn(BaseModel):
    email: EmailStr = Field(examples=["student@ssa.org"])
    password: str = Field(min_length=8, max_length=72, examples=["Passw0rd!"])
    full_name: str = Field(min_length=1, max_length=255, examples=["Demo Student"])
    phone: str | None = Field(default=None, max_length=32, examples=["9876543210"])
    department: str | None = Field(default=None, max_length=120, examples=["CSE"])
    year: int | None = Field(default=None, ge=1, le=6, examples=[2])


class LoginIn(BaseModel):
    email: EmailStr = Field(examples=["admin@ssa.org"])
    password: str = Field(examples=["Passw0rd!"])


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class MembershipSummary(BaseModel):
    status: str
    plan_name: str | None = None
    end_date: date | None = None
    days_left: int | None = None


class MeOut(UserOut):
    membership: MembershipSummary | None = None


class RoleUpdateIn(BaseModel):
    role: Role


# --- plans ------------------------------------------------------------------------
class PlanOut(ORMModel):
    id: UUID
    name: str
    price: int = Field(description="Integer paise")
    duration_months: int
    ticket_discount_pct: int
    merch_discount_pct: int
    description: str | None = None
    is_active: bool


class PlanCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120, examples=["Standard"])
    price: int = Field(ge=0, examples=[90000], description="Integer paise")
    duration_months: int = Field(default=12, ge=1, le=60)
    ticket_discount_pct: int = Field(default=0, ge=0, le=100, examples=[20])
    merch_discount_pct: int = Field(default=0, ge=0, le=100, examples=[10])
    description: str | None = None
    is_active: bool = True


class PlanUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    price: int | None = Field(default=None, ge=0)
    duration_months: int | None = Field(default=None, ge=1, le=60)
    ticket_discount_pct: int | None = Field(default=None, ge=0, le=100)
    merch_discount_pct: int | None = Field(default=None, ge=0, le=100)
    description: str | None = None
    is_active: bool | None = None


# --- memberships & payments -------------------------------------------------------
class CheckoutIn(BaseModel):
    plan_id: UUID = Field(examples=["3f1a2b4c-0000-4000-8000-000000000001"])


class CheckoutOut(BaseModel):
    order_id: UUID
    payment_id: UUID
    amount: int = Field(description="Integer paise")
    provider: str
    status: str


class MockConfirmIn(BaseModel):
    outcome: Literal["success", "fail"] = Field(examples=["success"])


class PaymentResultOut(BaseModel):
    order_id: UUID
    payment_id: UUID | None = None
    order_status: str
    payment_status: str | None = None
    provider_ref: str | None = None
    membership: MembershipSummary | None = None
    tickets: list["TicketOut"] | None = None  # ticket orders only (Phase 2)


class MembershipOut(BaseModel):
    id: UUID
    user_id: UUID
    plan_id: UUID
    plan_name: str | None = None
    status: str
    start_date: date | None = None
    end_date: date | None = None
    days_left: int | None = None
    member_code: str | None = None
    user_name: str | None = None
    user_email: str | None = None


class VerifyOut(BaseModel):
    valid: bool
    status: str = Field(description="active | expired | pending | cancelled | none")
    name: str | None = None
    member_code: str | None = None
    valid_until: date | None = None
    reason: str | None = None


class CardOut(BaseModel):
    member_code: str | None = None
    full_name: str
    status: str
    valid_until: date | None = None


# --- events (Phase 2) -------------------------------------------------------------
class TicketTypeOut(BaseModel):
    id: UUID
    event_id: UUID
    name: str
    member_price: int = Field(description="Integer paise")
    non_member_price: int = Field(description="Integer paise")
    capacity: int
    sold_count: int
    seats_left: int
    is_on_sale: bool
    price_for_you: int | None = Field(default=None, description="Null when the caller is anonymous")
    sale_starts_at: UtcDateTime | None = None
    sale_ends_at: UtcDateTime | None = None


class EventListItem(BaseModel):
    id: UUID
    title: str
    venue: str | None = None
    starts_at: UtcDateTime
    ends_at: UtcDateTime
    banner_url: str | None = None
    status: str
    min_price: int | None = Field(default=None, description="Cheapest price that applies to the caller, in paise")
    seats_left: int


class EventDetail(BaseModel):
    id: UUID
    title: str
    description: str | None = None
    venue: str | None = None
    starts_at: UtcDateTime
    ends_at: UtcDateTime
    banner_url: str | None = None
    status: str
    created_by: UUID | None = None
    created_at: UtcDateTime
    seats_left: int
    ticket_types: list[TicketTypeOut] = []


class EventCreateIn(BaseModel):
    title: str = Field(min_length=1, max_length=255, examples=["Spring Gala"])
    description: str | None = Field(default=None, examples=["Live band, dinner and awards."])
    venue: str | None = Field(default=None, max_length=255, examples=["Main Auditorium"])
    starts_at: datetime = Field(examples=["2026-11-01T18:00:00Z"])
    ends_at: datetime = Field(examples=["2026-11-01T22:00:00Z"])
    banner_url: str | None = Field(default=None, max_length=512)


class EventUpdateIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    venue: str | None = Field(default=None, max_length=255)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    banner_url: str | None = Field(default=None, max_length=512)
    status: Literal["draft", "published", "closed"] | None = Field(
        default=None, description="draft -> published -> closed only"
    )


class TicketTypeCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120, examples=["General"])
    member_price: int = Field(ge=0, examples=[30000], description="Integer paise")
    non_member_price: int = Field(ge=0, examples=[50000], description="Integer paise")
    capacity: int = Field(gt=0, examples=[120])
    sale_starts_at: datetime | None = Field(default=None, examples=["2026-10-20T00:00:00Z"])
    sale_ends_at: datetime | None = Field(default=None, examples=["2026-11-01T17:00:00Z"])


class TicketTypeUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    member_price: int | None = Field(default=None, ge=0)
    non_member_price: int | None = Field(default=None, ge=0)
    capacity: int | None = Field(default=None, gt=0)
    sale_starts_at: datetime | None = None
    sale_ends_at: datetime | None = None


# --- tickets (Phase 2) ------------------------------------------------------------
class TicketOut(BaseModel):
    id: UUID
    code: str
    event_id: UUID
    event_title: str | None = None
    event_starts_at: UtcDateTime | None = None
    event_venue: str | None = None
    ticket_type_id: UUID
    ticket_type_name: str | None = None
    status: str
    price_paid: int = Field(description="Integer paise")
    is_member_price: bool
    checked_in_at: UtcDateTime | None = None


class TicketCheckoutIn(BaseModel):
    ticket_type_id: UUID = Field(examples=["3f1a2b4c-0000-4000-8000-000000000002"])
    quantity: int = Field(default=1, ge=1, le=10, examples=[2])


class TicketCheckoutOut(BaseModel):
    order_id: UUID
    payment_id: UUID | None = None
    amount: int = Field(description="Integer paise, total for the order")
    unit_price: int = Field(description="Integer paise, per ticket")
    is_member_price: bool
    quantity: int
    provider: str | None = None
    status: str
    tickets: list[TicketOut] = Field(default=[], description="Filled immediately for free tickets")


class CheckinIn(BaseModel):
    event_id: UUID = Field(examples=["3f1a2b4c-0000-4000-8000-000000000003"])
    code: str = Field(min_length=1, max_length=32, examples=["K7PQ2MX9RT"])


class CheckinOut(BaseModel):
    """Always HTTP 200: the door needs an answer, not an error page."""

    result: Literal["VALID", "ALREADY_USED", "INVALID", "WRONG_EVENT"]
    ticket: TicketOut | None = None
    holder_name: str | None = None
    ticket_type: str | None = None
    checked_in_at: UtcDateTime | None = None
    message: str
    checked_in: int = Field(description="Live counter for the scanner header")
    sold: int


class AttendeeOut(BaseModel):
    ticket_id: UUID
    code: str
    status: str
    holder_name: str | None = None
    holder_email: str | None = None
    ticket_type: str | None = None
    price_paid: int
    is_member_price: bool
    checked_in_at: UtcDateTime | None = None


class RevenueOut(BaseModel):
    member: int = Field(description="Integer paise")
    non_member: int = Field(description="Integer paise")
    total: int = Field(description="Integer paise")


class TicketTypeReportOut(BaseModel):
    ticket_type_id: UUID
    name: str
    capacity: int
    sold: int
    seats_left: int
    checked_in: int
    revenue: int = Field(description="Integer paise")


class EventReportOut(BaseModel):
    event_id: UUID
    title: str
    status: str
    tickets_sold: int = Field(description="Tickets issued (valid + used)")
    seats_total: int
    seats_left: int = Field(description="Live availability: capacity - reserved")
    checked_in: int
    no_shows: int
    attendance_rate: float = Field(description="Percent of sold tickets that showed up")
    revenue: RevenueOut
    by_ticket_type: list[TicketTypeReportOut] = []
