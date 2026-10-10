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
    merch: "MerchFulfilmentOut | None" = None  # merch orders only (Phase 4)


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


# --- announcements (Phase 3) ------------------------------------------------------
AnnouncementCategory = Literal["meeting", "deadline", "change", "general"]
AnnouncementAudience = Literal["all", "members", "event"]


class AnnouncementCreateIn(BaseModel):
    title: str = Field(min_length=3, max_length=120, examples=["Members' AGM next Friday"])
    body: str = Field(min_length=1, max_length=5000, examples=["Doors open 6 PM in the Main Auditorium."])
    category: AnnouncementCategory = Field(examples=["deadline"])
    audience: AnnouncementAudience = Field(default="all", examples=["members"])
    event_id: UUID | None = Field(
        default=None,
        description="Required when audience=event; must be omitted otherwise",
        examples=["3f1a2b4c-0000-4000-8000-000000000003"],
    )
    is_pinned: bool = Field(default=False, description="Pinned posts come first; at most 3 in total")
    send_email: bool = Field(
        default=False, description="Also email the audience. Opted-out members get in-app only."
    )


class AnnouncementUpdateIn(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=120)
    body: str | None = Field(default=None, min_length=1, max_length=5000)
    category: AnnouncementCategory | None = None
    is_pinned: bool | None = Field(default=None, description="Pinning is not an edit: no revision_note needed")
    revision_note: str | None = Field(
        default=None,
        max_length=500,
        description="Why it changed. Required (3+ chars) for any change to title, body or category.",
        examples=["Room changed to LH-2"],
    )
    # Accepted only so an attempt to change them is a clear 422 AUDIENCE_LOCKED rather than a
    # silent no-op: after posting, the delivery rows already exist.
    audience: AnnouncementAudience | None = Field(default=None, description="Immutable after posting")
    event_id: UUID | None = Field(default=None, description="Immutable after posting")


class AnnouncementBase(BaseModel):
    id: UUID
    title: str
    category: str
    audience: str
    event_id: UUID | None = None
    is_pinned: bool
    author_name: str | None = None
    published_at: UtcDateTime
    edited_at: UtcDateTime | None = Field(default=None, description="Null when never edited")


class AnnouncementOut(AnnouncementBase):
    body_preview: str = Field(description="First 200 characters; GET by id returns the whole body")


class AnnouncementDetail(AnnouncementBase):
    body: str
    revision_note: str | None = None


class DeliverySummary(BaseModel):
    inapp_queued: int
    email_queued: int
    skipped_opted_out: int = Field(description="Audience members with email switched off")


class AnnouncementCreatedOut(AnnouncementDetail):
    delivery_summary: DeliverySummary


class AnnouncementRevisionOut(BaseModel):
    id: UUID
    title: str
    body: str
    category: str
    audience: str
    edited_by: UUID | None = None
    edited_by_name: str | None = None
    edited_at: UtcDateTime
    note: str | None = None


class DeliveryOut(BaseModel):
    id: UUID
    user_id: UUID
    user_name: str | None = None
    user_email: str | None = None
    channel: str
    status: str
    attempts: int
    error: str | None = None
    sent_at: UtcDateTime | None = None


class ChannelCounts(BaseModel):
    queued: int
    sent: int
    failed: int


class DeliverySummaryOut(BaseModel):
    email: ChannelCounts
    inapp: ChannelCounts
    total_recipients: int


class AnnouncementDeliveriesOut(BaseModel):
    announcement_id: UUID
    summary: DeliverySummaryOut
    items: Page[DeliveryOut]


# --- email preferences (Phase 3) --------------------------------------------------
class EmailPreferencesOut(BaseModel):
    email: EmailStr
    email_opt_in: bool = Field(description="False = no announcement emails; in-app notices still appear")


class EmailPreferencesIn(BaseModel):
    email_opt_in: bool = Field(examples=[False])


class UnsubscribeOut(BaseModel):
    unsubscribed: bool
    email: str = Field(description="Masked address, so the page can confirm which inbox was updated")


# --- merchandise (Phase 4) ---------------------------------------------------------
StockStatus = Literal["in_stock", "low", "out_of_stock"]
DeliveryMethod = Literal["pickup", "campus_delivery"]
FulfilmentStatus = Literal["paid", "packed", "handed_over"]


class PriceRangeOut(BaseModel):
    min: int = Field(description="Integer paise, cheapest price that applies to the caller")
    max: int = Field(description="Integer paise; with one price level per product both ends are equal")


class VariantOut(BaseModel):
    id: UUID
    size: str
    color: str | None = None
    sku: str
    stock: int
    stock_status: StockStatus
    is_active: bool


class ProductOut(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    image_url: str | None = None
    base_price: int = Field(description="Integer paise")
    member_discount_pct: int
    is_active: bool
    price_range: PriceRangeOut
    total_stock: int
    variants: list[VariantOut] = []
    price_for_you: int | None = Field(
        default=None, description="Null for an anonymous caller; the price this caller would pay"
    )
    is_member_price: bool | None = Field(
        default=None, description="Null for an anonymous caller; true when a discount applied"
    )


class ProductCreateIn(BaseModel):
    name: str = Field(min_length=2, max_length=80, examples=["SSA Hoodie"])
    description: str | None = Field(default=None, examples=["Heavyweight fleece, club crest."])
    image_url: str | None = Field(default=None, max_length=512)
    base_price: int = Field(gt=0, examples=[99900], description="Integer paise")
    member_discount_pct: int = Field(default=0, ge=0, le=100, examples=[10])
    is_active: bool = True


class ProductUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    description: str | None = None
    image_url: str | None = Field(default=None, max_length=512)
    base_price: int | None = Field(default=None, gt=0)
    member_discount_pct: int | None = Field(default=None, ge=0, le=100)
    is_active: bool | None = None


class VariantCreateIn(BaseModel):
    size: str = Field(min_length=1, max_length=20, examples=["M"], description="S-XXL for apparel; free text otherwise")
    color: str | None = Field(default=None, max_length=40, examples=["Navy"])
    sku: str = Field(min_length=1, max_length=40, examples=["SSA-HOOD-M"])
    stock: int = Field(default=0, ge=0, examples=[10], description="Opening stock; written to the audit trail")
    low_stock_threshold: int = Field(default=5, ge=0)
    is_active: bool = True


class VariantUpdateIn(BaseModel):
    size: str | None = Field(default=None, min_length=1, max_length=20)
    color: str | None = Field(default=None, max_length=40)
    sku: str | None = Field(default=None, min_length=1, max_length=40)
    low_stock_threshold: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class StockAdjustIn(BaseModel):
    delta: int = Field(examples=[5], description="Signed; negative writes stock off")
    reason: Literal["restock", "adjustment"] = Field(examples=["restock"])
    note: str | None = Field(default=None, max_length=500, examples=["Restock from the supplier"])


class StockMovementOut(BaseModel):
    id: UUID
    variant_id: UUID
    delta: int
    reason: str
    order_id: UUID | None = None
    created_by: UUID | None = None
    created_by_name: str | None = None
    note: str | None = None
    created_at: UtcDateTime


class MerchLineIn(BaseModel):
    variant_id: UUID = Field(examples=["3f1a2b4c-0000-4000-8000-000000000004"])
    qty: int = Field(ge=1, le=5, examples=[1])


class MerchCheckoutIn(BaseModel):
    items: list[MerchLineIn] = Field(min_length=1, max_length=5)
    delivery_method: DeliveryMethod = Field(default="pickup", examples=["pickup"])
    delivery_note: str | None = Field(
        default=None, max_length=500, examples=["Hostel B, room 214"], description="Required for campus_delivery"
    )


class MerchLineOut(BaseModel):
    variant_id: UUID
    product_name: str | None = None
    size: str | None = None
    color: str | None = None
    qty: int
    unit_price: int = Field(description="Integer paise")
    line_total: int = Field(description="Integer paise")


class MerchCheckoutOut(BaseModel):
    order_id: UUID
    payment_id: UUID
    amount: int = Field(description="Integer paise, what the payment charges")
    subtotal: int = Field(description="Integer paise, before the member discount")
    discount: int = Field(description="Integer paise")
    items: list[MerchLineOut]
    delivery_method: str
    provider: str
    status: str
    expires_at: UtcDateTime = Field(description="Unpaid orders are cancelled and their stock released after this")


class MerchFulfilmentOut(BaseModel):
    order_id: UUID
    fulfilment_status: str
    delivery_method: str
    delivery_note: str | None = None
    packed_at: UtcDateTime | None = None
    handed_over_at: UtcDateTime | None = None


class OrderItemOut(BaseModel):
    item_type: str
    name: str | None = None
    quantity: int
    unit_price: int = Field(description="Integer paise")
    line_total: int = Field(description="Integer paise")


class OrderOut(BaseModel):
    """One order as its owner sees it, whichever kind it is (DESIGN.md §5)."""

    id: UUID
    kind: str
    status: str
    subtotal: int = Field(description="Integer paise")
    discount: int = Field(description="Integer paise")
    total: int = Field(description="Integer paise")
    currency: str
    created_at: UtcDateTime
    items: list[OrderItemOut] = []
    payment_status: str | None = None
    fulfilment_status: str | None = Field(default=None, description="Merch orders only")
    delivery_method: str | None = None
    delivery_note: str | None = None
    packed_at: UtcDateTime | None = None
    handed_over_at: UtcDateTime | None = None


class BuyerOut(BaseModel):
    name: str | None = None
    email: str | None = None
    member_code: str | None = None
    phone: str | None = None


class MerchAdminOrderOut(BaseModel):
    order_id: UUID
    buyer: BuyerOut
    items_summary: str = Field(description="Human-readable packing list, e.g. 'SSA Hoodie (M) x2'")
    items: list[MerchLineOut] = []
    total: int = Field(description="Integer paise")
    delivery_method: str
    delivery_note: str | None = None
    fulfilment_status: str
    created_at: UtcDateTime
    packed_at: UtcDateTime | None = None
    handed_over_at: UtcDateTime | None = None


class FulfilmentCounts(BaseModel):
    paid: int
    packed: int
    handed_over: int


class MerchAdminOrdersOut(BaseModel):
    counts: FulfilmentCounts = Field(description="Always counts the whole board, even when items are filtered")
    items: Page[MerchAdminOrderOut]


class FulfilmentUpdateIn(BaseModel):
    fulfilment_status: FulfilmentStatus = Field(examples=["packed"], description="paid -> packed -> handed_over")


class VariantStockOut(BaseModel):
    variant_id: UUID
    size: str
    color: str | None = None
    sku: str
    stock: int
    sold_units: int = Field(description="Units on paid merch orders")
    reserved_units: int = Field(description="Units on merch orders still awaiting payment")
    low_stock_threshold: int
    low_stock: bool
    out_of_stock: bool


class ProductStockOut(BaseModel):
    product_id: UUID
    name: str
    is_active: bool
    total_stock: int
    sold_units: int
    reserved_units: int
    low_stock_count: int
    out_of_stock_count: int
    variants: list[VariantStockOut] = []


class SizeDemandOut(BaseModel):
    size: str
    stock: int
    sold_units: int = Field(description="Units sold in this size across every product")
    reserved_units: int = Field(description="Units pending payment in this size - what to hold back")


class VariantStockTotals(BaseModel):
    stock: int
    sold_units: int
    reserved_units: int


class StockSummaryOut(BaseModel):
    products: list[ProductStockOut] = []
    demand_by_size: list[SizeDemandOut] = Field(
        default=[], description="Reorder view: what each size actually moves"
    )
    totals: VariantStockTotals
