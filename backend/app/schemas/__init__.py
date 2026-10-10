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
    # No `min_length` here on purpose: the length rule belongs to `check_password_policy`, which
    # answers `422 WEAK_PASSWORD`. A pydantic minimum would answer `VALIDATION_ERROR` first, so the
    # frontend would have to map two codes onto one password field. `max_length` stays because
    # bcrypt silently ignores everything past 72 bytes.
    password: str = Field(max_length=72, examples=["Passw0rd!"])
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


class RazorpayVerifyIn(BaseModel):
    """The trio the Checkout widget hands back on success. Verified server-side; a client that
    makes these up gains nothing, because the signature is computed with the key secret."""

    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class PaymentIntentOut(BaseModel):
    """What the checkout page needs to open the gateway - and to redraw itself after a reload or
    a redirect back from a bank page, where the router state is gone."""

    order_id: UUID
    kind: str
    order_status: str
    amount: int = Field(description="Integer paise")
    currency: str
    provider: str
    payment_status: str | None = None
    # Razorpay Checkout opens with these two together; both are null under the mock provider.
    key_id: str | None = None
    gateway_order_id: str | None = None


class WebhookAckOut(BaseModel):
    status: Literal["processed", "ignored"]
    order_id: UUID | None = None


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
    send_email: bool = Field(default=False, description="Also email the audience. Opted-out members get in-app only.")


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
    demand_by_size: list[SizeDemandOut] = Field(default=[], description="Reorder view: what each size actually moves")
    totals: VariantStockTotals


# --- fundraisers & tasks (Phase 5) -------------------------------------------------
FundraiserStatus = Literal["planning", "active", "done"]
TaskStatus = Literal["todo", "doing", "done"]
TaskCategory = Literal["baking", "supplies", "table_duty", "promotion", "other"]
FundraiserHealth = Literal["on_track", "at_risk", "behind", "completed"]


class PersonRef(BaseModel):
    """The smallest useful description of a person, for assignee/owner/logged_by fields."""

    id: UUID
    full_name: str
    role: str


class FundraiserCreateIn(BaseModel):
    title: str = Field(min_length=3, max_length=100, examples=["Spring Bake Sale"])
    description: str | None = Field(default=None, examples=["Cakes, cookies and cold coffee on the quad."])
    goal_amount: int = Field(gt=0, examples=[500000], description="Integer paise")
    event_date: date = Field(examples=["2026-10-20"], description="Cannot be in the past unless status is done")
    owner_id: UUID | None = Field(default=None, description="Defaults to you; must be an organizer or above")
    status: FundraiserStatus = Field(default="planning")


class FundraiserUpdateIn(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=100)
    description: str | None = None
    goal_amount: int | None = Field(default=None, gt=0, description="Integer paise")
    event_date: date | None = None
    status: FundraiserStatus | None = Field(default=None, description="planning -> active -> done, one step at a time")
    owner_id: UUID | None = None


class FundraiserTaskCounts(BaseModel):
    total: int
    todo: int
    doing: int
    done: int
    overdue: int = Field(description="Past due_date and not done")
    due_soon: int = Field(description="Due within 3 days and not done")
    unassigned: int = Field(description="Not done and nobody's name on it")
    percent_done: int = Field(description="0-100, whole percent; 0 when the board is empty")


class CategoryProgressOut(BaseModel):
    category: str
    total: int
    done: int


class AssigneeProgressOut(BaseModel):
    assignee_id: UUID | None = None
    name: str | None = Field(default=None, description="Null for the unassigned bucket")
    total: int
    done: int


class FundraiserProgressOut(BaseModel):
    """Full progress, for the fundraiser detail page (DESIGN.md §5)."""

    tasks: FundraiserTaskCounts
    raised: int = Field(description="Integer paise, GROSS: the sum of this fundraiser's `in` ledger rows")
    spent: int = Field(default=0, description="Integer paise, reimbursed claims charged to this fundraiser (Phase 6)")
    net_raised: int = Field(default=0, description="Integer paise, `raised - spent` (Phase 6)")
    goal: int = Field(description="Integer paise")
    percent_of_goal: int = Field(description="Whole percent; can exceed 100 when the goal is beaten")
    days_to_event: int = Field(description="Negative once the date has passed")
    health: FundraiserHealth
    by_category: list[CategoryProgressOut] = []
    by_assignee: list[AssigneeProgressOut] = []


class FundraiserProgressSummary(BaseModel):
    """The slice of progress a list card shows - same numbers, fewer of them."""

    tasks_total: int
    tasks_done: int
    overdue: int
    unassigned: int
    percent_done: int
    raised: int = Field(description="Integer paise, gross")
    spent: int = Field(default=0, description="Integer paise, reimbursed claims charged to this fundraiser")
    net_raised: int = Field(default=0, description="Integer paise, `raised - spent`")
    goal: int = Field(description="Integer paise")
    percent_of_goal: int
    days_to_event: int
    health: FundraiserHealth


class FundraiserOut(BaseModel):
    id: UUID
    title: str
    description: str | None = None
    goal_amount: int = Field(description="Integer paise")
    event_date: date
    status: str
    owner: PersonRef
    completed_at: UtcDateTime | None = None
    created_at: UtcDateTime
    updated_at: UtcDateTime
    progress: FundraiserProgressOut


class FundraiserListItemOut(BaseModel):
    id: UUID
    title: str
    description: str | None = None
    goal_amount: int = Field(description="Integer paise")
    event_date: date
    status: str
    owner: PersonRef
    completed_at: UtcDateTime | None = None
    created_at: UtcDateTime
    progress: FundraiserProgressSummary


class TaskCreateIn(BaseModel):
    title: str = Field(min_length=3, max_length=120, examples=["Bake 200 cookies"])
    description: str | None = None
    category: TaskCategory = Field(default="other", examples=["baking"])
    assignee_id: UUID | None = Field(default=None, examples=["3f1a2b4c-0000-4000-8000-000000000009"])
    due_date: date | None = Field(default=None, description="Must not be after the fundraiser's event_date")
    status: TaskStatus = Field(default="todo")


class TaskUpdateIn(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=120)
    description: str | None = None
    category: TaskCategory | None = None
    assignee_id: UUID | None = None
    due_date: date | None = None
    status: TaskStatus | None = None


class TaskMoveIn(BaseModel):
    status: TaskStatus = Field(examples=["doing"], description="Which column the card lands in")
    position: int | None = Field(
        default=None, ge=0, description="0-based slot; clamped to the column, defaults to last"
    )


class TaskOut(BaseModel):
    id: UUID
    fundraiser_id: UUID | None = None
    event_id: UUID | None = None
    title: str
    description: str | None = None
    category: str
    assignee_id: UUID | None = None
    assignee: PersonRef | None = None
    due_date: date | None = None
    status: str
    position: int
    is_overdue: bool
    completed_at: UtcDateTime | None = None
    created_at: UtcDateTime
    updated_at: UtcDateTime


class TaskColumnsOut(BaseModel):
    todo: list[TaskOut] = []
    doing: list[TaskOut] = []
    done: list[TaskOut] = []


class TaskBoardOut(BaseModel):
    """The kanban: the same cards twice, flat and bucketed, so a client can render either."""

    items: list[TaskOut]
    columns: TaskColumnsOut
    counts: dict[str, int] = Field(description="Card count per column")


class TaskActivityOut(BaseModel):
    id: UUID
    task_id: UUID | None = Field(default=None, description="Null once the task has been deleted")
    actor: PersonRef | None = None
    action: str
    from_value: str | None = None
    to_value: str | None = None
    created_at: UtcDateTime


class FundraiserVolunteerOut(BaseModel):
    user: PersonRef
    tasks_total: int
    tasks_done: int
    open_tasks: int


class AssignableUserOut(BaseModel):
    """A candidate assignee. Only volunteer and above: a member cannot be handed club work."""

    id: UUID
    full_name: str
    email: EmailStr
    role: str


class IncomeCreateIn(BaseModel):
    amount: int = Field(gt=0, le=10_000_000, examples=[150000], description="Integer paise, max Rs 1,00,000")
    note: str | None = Field(default=None, max_length=255, examples=["Coffee stall, day 2"])
    source_label: str | None = Field(
        default=None, max_length=80, examples=["Cash box"], description="Optional label prefixed to the ledger note"
    )
    occurred_at: datetime | None = Field(
        default=None, description="When the money was taken. Defaults to now; backdating is allowed up to 30 days"
    )


class IncomeOut(BaseModel):
    id: UUID
    amount: int = Field(description="Integer paise")
    note: str | None = None
    occurred_at: UtcDateTime
    raised_total: int = Field(description="Integer paise, this fundraiser's total after this entry")
    percent_of_goal: int
    replayed: bool = Field(
        default=False, description="True when this Idempotency-Key had already been used and nothing new was written"
    )


class IncomeListItemOut(BaseModel):
    id: UUID
    amount: int = Field(description="Integer paise")
    note: str | None = None
    occurred_at: UtcDateTime
    logged_by: PersonRef | None = None
    created_at: UtcDateTime


# --- Phase 6: expenses ------------------------------------------------------------
ExpenseCategory = Literal["supplies", "food", "printing", "venue", "travel", "marketing", "equipment", "other"]
ReimbursementMethod = Literal["cash", "upi", "bank_transfer"]


class ExpenseFundraiserRef(BaseModel):
    """Just enough to render "Spring Bake Sale" next to a claim."""

    id: UUID
    title: str


class ExpenseOut(BaseModel):
    """A claim. There is no `receipt_path` here and there never will be: receipts leave through
    `GET /expenses/{id}/receipt`, which mints a signed URL that expires (DESIGN.md §4 rule 14)."""

    id: UUID
    claimant: PersonRef
    amount: int = Field(description="Integer paise")
    description: str
    category: str
    incurred_on: date
    event_id: UUID | None = None
    fundraiser_id: UUID | None = None
    fundraiser: ExpenseFundraiserRef | None = None
    status: Literal["submitted", "approved", "rejected", "reimbursed", "withdrawn"]
    has_receipt: bool
    receipt_mime: str | None = None
    receipt_size: int | None = None
    reviewed_by: PersonRef | None = None
    reviewed_at: UtcDateTime | None = None
    review_note: str | None = None
    reimbursed_by: UUID | None = None
    reimbursed_at: UtcDateTime | None = None
    reimbursement_method: ReimbursementMethod | None = None
    reimbursement_reference: str | None = None
    ledger_transaction_id: UUID | None = Field(
        default=None, description="The `out` ledger row that paid this claim; null until reimbursed"
    )
    created_at: UtcDateTime
    updated_at: UtcDateTime


class ExpenseHistoryOut(BaseModel):
    id: UUID
    action: str
    note: str | None = None
    actor: PersonRef | None = None
    created_at: UtcDateTime


class ExpenseDetailOut(ExpenseOut):
    history: list[ExpenseHistoryOut] = []


class ExpensePatchIn(BaseModel):
    amount: int | None = Field(default=None, ge=1, le=5_000_000, examples=[45000])
    description: str | None = Field(default=None, min_length=5, max_length=300)
    category: ExpenseCategory | None = None
    incurred_on: date | None = None
    event_id: UUID | None = None
    fundraiser_id: UUID | None = None


class ExpenseReviewIn(BaseModel):
    decision: Literal["approve", "reject"]
    note: str | None = Field(default=None, description="Required (min 5 chars) when rejecting", max_length=1000)


class ExpenseReimburseIn(BaseModel):
    method: ReimbursementMethod
    reference: str | None = Field(default=None, max_length=120, examples=["UPI/2026/8891"])
    allow_negative: bool = Field(
        default=False, description="Admin only: pay even if it pushes the club balance below zero"
    )


class ExpenseReceiptOut(BaseModel):
    url: str = Field(description="Short-lived signed URL. The storage path is never returned.")
    expires_in: int = Field(description="Seconds until the URL stops working", examples=[600])
    mime: str | None = None
    size: int | None = None


class ExpensePageOut(BaseModel):
    items: list[ExpenseOut]
    total: int
    page: int
    page_size: int
    counts: dict[str, int] = Field(
        default={}, description="`{submitted, approved, rejected, reimbursed, withdrawn}` over the same filter"
    )
    submitted_amount: int = Field(default=0, description="Integer paise waiting for a decision")
    approved_unpaid_amount: int = Field(default=0, description="Integer paise approved but not yet paid out")


# --- Phase 6: finance -------------------------------------------------------------
class ReconcileCheckOut(BaseModel):
    name: str
    ledger_total: int = Field(description="Integer paise; the count of violations for the boolean checks")
    source_total: int = Field(description="Integer paise recomputed from the table that caused the stream")
    difference: int = Field(description="`ledger_total - source_total`; anything but zero is a problem")
    ok: bool


class ReconcileOut(BaseModel):
    ok: bool
    checks: list[ReconcileCheckOut]


class SourceTotalOut(BaseModel):
    source: str
    in_: int = Field(alias="in", description="Integer paise")
    out: int = Field(description="Integer paise")
    net: int = Field(description="Integer paise, `in - out`")

    model_config = ConfigDict(populate_by_name=True)


class CategoryTotalOut(BaseModel):
    category: str
    amount: int = Field(description="Integer paise, reimbursed in the window")


class MonthTotalOut(BaseModel):
    month: str = Field(description="`YYYY-MM`", examples=["2026-08"])
    in_: int = Field(alias="in")
    out: int

    model_config = ConfigDict(populate_by_name=True)


class PendingReimbursementsOut(BaseModel):
    submitted_count: int
    submitted_amount: int = Field(description="Integer paise")
    approved_unpaid_count: int
    approved_unpaid_amount: int = Field(description="Integer paise")


class FinanceSummaryOut(BaseModel):
    date_from: date | None = None
    date_to: date | None = None
    total_in: int = Field(description="Integer paise in the window")
    total_out: int = Field(description="Integer paise out in the window")
    balance: int = Field(description="Integer paise, `total_in - total_out` for the window")
    by_source: list[SourceTotalOut] = []
    by_category: list[CategoryTotalOut] = []
    pending_reimbursements: PendingReimbursementsOut
    by_month: list[MonthTotalOut] = []
    counts: dict[str, int] = Field(default={}, description="`{transactions, expenses_reimbursed}`")


class TransactionOut(BaseModel):
    id: UUID
    occurred_at: UtcDateTime
    direction: Literal["in", "out"]
    amount: int = Field(description="Integer paise, always positive")
    signed_amount: int = Field(description="Integer paise, negative for money out")
    source: str
    label: str = Field(description="Human line for the ledger table", examples=["Ticket sales - Spring Gala (VIP x2)"])
    note: str | None = None
    ref_type: str | None = None
    ref_id: UUID | None = None
    event_id: UUID | None = None
    event_title: str | None = None
    fundraiser_id: UUID | None = None
    fundraiser_title: str | None = None
    actor: PersonRef | None = None
    is_reversal: bool = False
    reverses_id: UUID | None = None
    running_balance: int | None = Field(
        default=None, description="Integer paise; only filled when sorting `occurred_at` ascending"
    )
    created_at: UtcDateTime


class DimensionTotalOut(BaseModel):
    id: UUID
    title: str
    total_in: int = Field(description="Integer paise")
    total_out: int = Field(description="Integer paise")
    net: int = Field(description="Integer paise")
    goal_amount: int | None = Field(default=None, description="Fundraisers only")


class OutstandingReimbursementOut(BaseModel):
    user: PersonRef
    submitted_amount: int = Field(description="Integer paise")
    approved_unpaid_amount: int = Field(description="Integer paise")
    oldest_pending_date: date | None = None


class TopExpenseOut(BaseModel):
    id: UUID
    claimant: PersonRef
    amount: int
    category: str
    description: str
    incurred_on: date
    reimbursed_at: UtcDateTime | None = None


class SemesterReportOut(BaseModel):
    period: dict[str, date]
    opening_balance: int = Field(description="Integer paise, balance before `from`")
    income: dict
    expenses: dict
    closing_balance: int = Field(description="Integer paise, always `opening_balance + net_movement`")
    net_movement: int = Field(description="Integer paise")
    by_event: list[DimensionTotalOut] = []
    by_fundraiser: list[DimensionTotalOut] = []
    outstanding_reimbursements: list[OutstandingReimbursementOut] = []
    top_expenses: list[TopExpenseOut] = []
    reconciliation: ReconcileOut
    generated_at: UtcDateTime


class ManualEntryIn(BaseModel):
    direction: Literal["in", "out"] | None = Field(
        default=None, description="Optional; must agree with `source` when given"
    )
    amount: int = Field(gt=0, examples=[500000], description="Integer paise")
    source: Literal["other_income", "other_expense"]
    note: str = Field(min_length=5, max_length=300, examples=["Sponsor - campus bookstore"])
    event_id: UUID | None = None
    fundraiser_id: UUID | None = None
    occurred_at: UtcDateTime | None = Field(
        default=None, description="Backdatable up to 60 days; never the future, never a closed period"
    )
    allow_negative: bool = Field(default=False, description="Admin only, for `other_expense`")


class ReverseIn(BaseModel):
    reason: str = Field(min_length=5, max_length=300, examples=["Double-counted the second cash box"])


class FinancePeriodOut(BaseModel):
    id: UUID
    name: str
    start_date: date
    end_date: date
    status: Literal["closed", "reopened"]
    closing_balance: int = Field(description="Integer paise, frozen at closing time")
    closed_by: PersonRef | None = None
    closed_at: UtcDateTime | None = None
    reopened_by: UUID | None = None
    reopened_at: UtcDateTime | None = None
    reopen_reason: str | None = None


class ClosePeriodIn(BaseModel):
    name: str = Field(min_length=3, max_length=120, examples=["Semester 1 2026"])
    start_date: date
    end_date: date = Field(description="Must be in the past")
    force: bool = Field(default=False, description="Admin only: close despite reconciliation or pending claims")


class ReopenPeriodIn(BaseModel):
    reason: str = Field(min_length=10, max_length=1000, examples=["Missed the printer invoice for October"])


# --- RBAC -------------------------------------------------------------------------
class PermissionOut(BaseModel):
    key: str
    category: str
    description: str
    is_privileged: bool = Field(description="Granting a role that carries this needs a second approver")


class MyPermissionsOut(BaseModel):
    """What the caller may do, so the frontend can hide a button instead of collecting a 403."""

    role: str = Field(description="The primary role on the account, from `users.role`")
    roles: list[str] = Field(description="Every role held right now, including scoped assignments")
    permissions: list[str]


class RoleOut(BaseModel):
    key: str
    name: str
    description: str
    inherits: str | None = None
    is_privileged: bool
    permissions: list[str] = Field(description="Effective: this role's grants plus every ancestor's")


class RoleMatrixOut(BaseModel):
    """Roles down, permissions across. The admin UI's access-control screen, in one call."""

    permissions: list[PermissionOut]
    roles: list[RoleOut]
