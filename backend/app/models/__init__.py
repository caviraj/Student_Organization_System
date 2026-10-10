"""ORM models (DESIGN.md §4). Money is always integer paise; PKs are UUIDs.

Phase 1 tables: users, membership_plans, memberships, orders, order_items, payments,
transactions, reminders. Phase 2 adds events, ticket_types, tickets. Phase 3 adds
announcements, announcement_revisions, announcement_deliveries. Phase 4 adds products,
product_variants, stock_movements, merch_orders. Phase 5 adds fundraisers, tasks, task_activity,
and the fundraiser columns on transactions. Phase 6 adds expenses, expense_history,
finance_periods, and the reversal columns on transactions.
"""

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# JSONB on Postgres, plain JSON elsewhere (SQLite in tests/dev).
JSON_VARIANT = JSON().with_variant(JSONB(), "postgresql")

ROLES = ("admin", "treasurer", "organizer", "volunteer", "member", "guest")
MEMBERSHIP_STATUSES = ("pending", "active", "expired", "cancelled")
ORDER_KINDS = ("membership", "ticket", "merch")
ORDER_STATUSES = ("pending", "paid", "failed", "cancelled", "refunded")
ITEM_TYPES = ("plan", "ticket_type", "variant")
PAYMENT_PROVIDERS = ("mock", "razorpay")
PAYMENT_STATUSES = ("created", "succeeded", "failed")
LEDGER_DIRECTIONS = ("in", "out")
LEDGER_SOURCES = (
    "dues",
    "tickets",
    "merch",
    "fundraiser",
    "other_income",
    "other_expense",
    "expense_reimbursement",
)
REMINDER_KINDS = ("expiry_30", "expiry_7", "expired")
EVENT_STATUSES = ("draft", "published", "closed")
TICKET_STATUSES = ("valid", "used", "void")
ANNOUNCEMENT_CATEGORIES = ("meeting", "deadline", "change", "general")
ANNOUNCEMENT_AUDIENCES = ("all", "members", "event")
DELIVERY_CHANNELS = ("email", "inapp")
DELIVERY_STATUSES = ("queued", "sent", "failed")
FULFILMENT_STATUSES = ("paid", "packed", "handed_over")
DELIVERY_METHODS = ("pickup", "campus_delivery")
STOCK_REASONS = ("initial", "sale", "release", "restock", "adjustment")
FUNDRAISER_STATUSES = ("planning", "active", "done")
TASK_CATEGORIES = ("baking", "supplies", "table_duty", "promotion", "other")
TASK_STATUSES = ("todo", "doing", "done")
TASK_ACTIONS = ("created", "status_changed", "assigned", "edited", "due_changed")
EXPENSE_CATEGORIES = ("supplies", "food", "printing", "venue", "travel", "marketing", "equipment", "other")
EXPENSE_STATUSES = ("submitted", "approved", "rejected", "reimbursed", "withdrawn")
EXPENSE_ACTIONS = (
    "submitted",
    "edited",
    "receipt_attached",
    "approved",
    "rejected",
    "resubmitted",
    "reimbursed",
    "withdrawn",
)
REIMBURSEMENT_METHODS = ("cash", "upi", "bank_transfer")
FINANCE_PERIOD_STATUSES = ("closed", "reopened")


def _enum(*values: str, name: str) -> Enum:
    # native_enum=False -> portable VARCHAR, validated on bind; no PG type to migrate.
    return Enum(*values, name=name, native_enum=False, validate_strings=True)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(32))
    department: Mapped[str | None] = mapped_column(String(120))
    year: Mapped[int | None] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(_enum(*ROLES, name="user_role"), default="guest", index=True)
    member_code: Mapped[str | None] = mapped_column(String(32), unique=True, index=True)
    email_opt_in: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class MembershipPlan(TimestampMixin, Base):
    __tablename__ = "membership_plans"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    price: Mapped[int] = mapped_column(Integer)  # paise
    duration_months: Mapped[int] = mapped_column(Integer, default=12)
    ticket_discount_pct: Mapped[int] = mapped_column(Integer, default=0)
    merch_discount_pct: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class Order(TimestampMixin, Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(_enum(*ORDER_KINDS, name="order_kind"))
    status: Mapped[str] = mapped_column(_enum(*ORDER_STATUSES, name="order_status"), default="pending", index=True)
    subtotal: Mapped[int] = mapped_column(Integer)
    discount: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    meta: Mapped[dict | None] = mapped_column(JSON_VARIANT)
    idempotency_key: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)

    user: Mapped[User] = relationship()
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")
    payments: Mapped[list["Payment"]] = relationship(back_populates="order", cascade="all, delete-orphan")


class OrderItem(TimestampMixin, Base):
    __tablename__ = "order_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    item_type: Mapped[str] = mapped_column(_enum(*ITEM_TYPES, name="order_item_type"))
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid)  # no FK: points at plan / ticket_type / variant
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price: Mapped[int] = mapped_column(Integer)
    line_total: Mapped[int] = mapped_column(Integer)

    order: Mapped[Order] = relationship(back_populates="items")


class Payment(TimestampMixin, Base):
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(_enum(*PAYMENT_PROVIDERS, name="payment_provider"), default="mock")
    provider_ref: Mapped[str | None] = mapped_column(String(128), unique=True, index=True)
    status: Mapped[str] = mapped_column(_enum(*PAYMENT_STATUSES, name="payment_status"), default="created", index=True)
    amount: Mapped[int] = mapped_column(Integer)
    raw: Mapped[dict | None] = mapped_column(JSON_VARIANT)

    order: Mapped[Order] = relationship(back_populates="payments")


class Membership(TimestampMixin, Base):
    __tablename__ = "memberships"
    # One subscription row per user; renewals extend it and the order history keeps the trail.
    __table_args__ = (UniqueConstraint("user_id", name="uq_memberships_user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("membership_plans.id"))
    status: Mapped[str] = mapped_column(
        _enum(*MEMBERSHIP_STATUSES, name="membership_status"), default="pending", index=True
    )
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date, index=True)
    order_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("orders.id"))
    renewal_reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    plan: Mapped[MembershipPlan] = relationship(lazy="joined")
    user: Mapped[User] = relationship()
    reminders: Mapped[list["Reminder"]] = relationship(back_populates="membership", cascade="all, delete-orphan")


class Transaction(TimestampMixin, Base):
    """Ledger. Every successful payment writes exactly one `in` row (DESIGN.md §3)."""

    __tablename__ = "transactions"
    # Scoped to one fundraiser: two people may pick the same key on different fundraisers, and a
    # NULL key (every payment-driven row) is never a duplicate in Postgres.
    # `reverses_id` is UNIQUE, so a row can be reversed at most once - the DB, not the service,
    # is what makes a double-click on "reverse" a no-op (DESIGN.md §4 rule 14).
    # The partial index does the same for a hand-typed entry: Phase 5's key is scoped to a
    # fundraiser, so it cannot guard a row that has no fundraiser. Partial, so it stays out of the
    # way of Phase 5's per-fundraiser keys and of the NULL keys every payment-driven row carries.
    __table_args__ = (
        UniqueConstraint("fundraiser_id", "idempotency_key", name="uq_transactions_fundraiser_idem"),
        UniqueConstraint("reverses_id", name="uq_transactions_reverses_id"),
        CheckConstraint("amount > 0", name="ck_transactions_amount_positive"),
        Index(
            "uq_transactions_manual_idem",
            "idempotency_key",
            unique=True,
            postgresql_where=text("source IN ('other_income', 'other_expense')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    direction: Mapped[str] = mapped_column(_enum(*LEDGER_DIRECTIONS, name="ledger_direction"), index=True)
    amount: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(_enum(*LEDGER_SOURCES, name="ledger_source"), index=True)
    ref_type: Mapped[str | None] = mapped_column(String(32))
    ref_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id"), index=True)
    fundraiser_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("fundraisers.id", ondelete="SET NULL"), index=True
    )
    # Fundraiser income is logged by hand, so the row records who counted the cash and the key
    # that stops a double-click from counting it twice (DESIGN.md §4 rule 13).
    logged_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    idempotency_key: Mapped[str | None] = mapped_column(String(64))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    note: Mapped[str | None] = mapped_column(Text)
    # A reversal is a SECOND row that undoes the first; the row it undoes is left untouched, so the
    # ledger stays append-only. Signed totals subtract reversal rows from the side they came from
    # (see services/ledger.py), which is why `is_reversal` is indexed: every total reads it.
    is_reversal: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"), index=True)
    reverses_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("transactions.id"))


class Event(TimestampMixin, Base):
    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    venue: Mapped[str | None] = mapped_column(String(255))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    banner_url: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(_enum(*EVENT_STATUSES, name="event_status"), default="draft", index=True)
    department: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))

    # selectin: the events list needs every type's seats_left, and N+1 there is wasteful.
    ticket_types: Mapped[list["TicketType"]] = relationship(
        back_populates="event", cascade="all, delete-orphan", order_by="TicketType.name", lazy="selectin"
    )


class TicketType(TimestampMixin, Base):
    """A price tier for an event (DESIGN.md §4). `sold_count` is the live reservation counter."""

    __tablename__ = "ticket_types"
    # The seat invariants live in the DB so a bug in the service layer cannot oversell.
    __table_args__ = (
        CheckConstraint("capacity > 0", name="ck_ticket_types_capacity_positive"),
        CheckConstraint("sold_count >= 0", name="ck_ticket_types_sold_non_negative"),
        CheckConstraint("sold_count <= capacity", name="ck_ticket_types_sold_within_capacity"),
        CheckConstraint("member_price >= 0", name="ck_ticket_types_member_price_non_negative"),
        CheckConstraint("non_member_price >= 0", name="ck_ticket_types_non_member_price_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    member_price: Mapped[int] = mapped_column(Integer)  # paise
    non_member_price: Mapped[int] = mapped_column(Integer)  # paise
    capacity: Mapped[int] = mapped_column(Integer)
    sold_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    sale_starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sale_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    event: Mapped[Event] = relationship(back_populates="ticket_types")


class Ticket(TimestampMixin, Base):
    __tablename__ = "tickets"
    __table_args__ = (Index("ix_tickets_event_status", "event_id", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    ticket_type_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ticket_types.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(10), unique=True, index=True)
    status: Mapped[str] = mapped_column(_enum(*TICKET_STATUSES, name="ticket_status"), default="valid", index=True)
    price_paid: Mapped[int] = mapped_column(Integer)  # paise, frozen at purchase time
    is_member_price: Mapped[bool] = mapped_column(Boolean, default=False)
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checked_in_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))

    event: Mapped[Event] = relationship(lazy="joined")
    ticket_type: Mapped[TicketType] = relationship(lazy="joined")
    # Two FKs point at users (holder, checking-in staff), so name the one this means.
    user: Mapped[User] = relationship(foreign_keys="Ticket.user_id")


class Reminder(Base):
    __tablename__ = "reminders"
    # Enforces "once per kind per membership" (FR-1.5) in the database, not just in code.
    __table_args__ = (UniqueConstraint("membership_id", "kind", name="uq_reminders_membership_kind"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    membership_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("memberships.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(_enum(*REMINDER_KINDS, name="reminder_kind"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    delivered: Mapped[bool] = mapped_column(Boolean, default=False)

    membership: Mapped[Membership] = relationship(back_populates="reminders")


class Announcement(TimestampMixin, Base):
    """A post to the feed. There is no delete endpoint: the record of what was said, and when,
    is permanent (PRD FR-3.2). Edits keep the previous version in `announcement_revisions`."""

    __tablename__ = "announcements"
    # The feed is "pinned first, then newest", which is exactly this index read backwards.
    __table_args__ = (Index("ix_announcements_pinned_published", "is_pinned", "published_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(_enum(*ANNOUNCEMENT_CATEGORIES, name="announcement_category"), index=True)
    audience: Mapped[str] = mapped_column(_enum(*ANNOUNCEMENT_AUDIENCES, name="announcement_audience"), index=True)
    event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    author_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    # Set from Python, not `func.now()`: Postgres returns the *transaction* timestamp, so two
    # announcements posted in one transaction would be indistinguishable to "newest first".
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), server_default=func.now(), index=True
    )
    revision_note: Mapped[str | None] = mapped_column(Text)  # why the latest edit happened
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # null = never edited

    author: Mapped[User | None] = relationship(lazy="joined")  # every feed row shows the name
    event: Mapped[Event | None] = relationship()


class AnnouncementRevision(Base):
    """Immutable history. Each row holds the version that was REPLACED, so the feed can always
    answer "what did it say before, and who changed it?" (PRD FR-3.2). No updated_at: a revision
    is never edited."""

    __tablename__ = "announcement_revisions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    announcement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("announcements.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(_enum(*ANNOUNCEMENT_CATEGORIES, name="announcement_category"))
    audience: Mapped[str] = mapped_column(_enum(*ANNOUNCEMENT_AUDIENCES, name="announcement_audience"))
    edited_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    edited_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), server_default=func.now(), index=True
    )
    note: Mapped[str | None] = mapped_column(Text)


class AnnouncementDelivery(TimestampMixin, Base):
    """One row per recipient per channel - the mailing list of PRD FR-3.3. The unique constraint
    is the idempotency guard: a re-post can never queue the same person twice."""

    __tablename__ = "announcement_deliveries"
    __table_args__ = (
        UniqueConstraint("announcement_id", "user_id", "channel", name="uq_announcement_deliveries_target"),
        # The worker's claim query filters on exactly this pair.
        Index("ix_announcement_deliveries_status_channel", "status", "channel"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    announcement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("announcements.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(_enum(*DELIVERY_CHANNELS, name="delivery_channel"))
    status: Mapped[str] = mapped_column(
        _enum(*DELIVERY_STATUSES, name="delivery_status"), default="queued", server_default=text("'queued'")
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    error: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship()


class Product(TimestampMixin, Base):
    """Something the club sells (PRD FR-4.1). The image is a URL: no uploads in this phase."""

    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(80), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(String(512))
    base_price: Mapped[int] = mapped_column(Integer)  # paise
    member_discount_pct: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"), index=True)

    # selectin: the product list always shows its variants, and N+1 there would be 20 queries.
    variants: Mapped[list["ProductVariant"]] = relationship(
        back_populates="product", cascade="all, delete-orphan", order_by="ProductVariant.size", lazy="selectin"
    )


class ProductVariant(TimestampMixin, Base):
    """A size/colour of a product with its own stock (PRD FR-4.2). `size` is free text so a mug
    can say "350 ml"; the checkout schema validates the S-XXL set for apparel."""

    __tablename__ = "product_variants"
    __table_args__ = (
        UniqueConstraint("product_id", "size", "color", name="uq_product_variants_size_color"),
        # The stock floor lives in the DB too, so a bug in the service cannot oversell.
        CheckConstraint("stock >= 0", name="ck_product_variants_stock_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    size: Mapped[str] = mapped_column(String(20))
    color: Mapped[str | None] = mapped_column(String(40))
    sku: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    stock: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    low_stock_threshold: Mapped[int] = mapped_column(Integer, default=5, server_default=text("5"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))

    # joined: the stock error message and every admin row need the product name, and a lazy load
    # per variant would be a round trip each.
    product: Mapped[Product] = relationship(back_populates="variants", lazy="joined")


class StockMovement(Base):
    """Immutable audit of every stock change (PRD FR-4.3). Never updated, never deleted, so
    `SUM(delta)` reconstructs the current stock from zero. No updated_at, like a revision row."""

    __tablename__ = "stock_movements"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    variant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("product_variants.id", ondelete="CASCADE"), index=True)
    delta: Mapped[int] = mapped_column(Integer)  # negative = out of the door
    reason: Mapped[str] = mapped_column(_enum(*STOCK_REASONS, name="stock_reason"))
    order_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("orders.id"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class MerchOrder(TimestampMixin, Base):
    """Fulfilment side of a merch order (PRD FR-4.4). One row per paid order, created only when
    the payment succeeds - a cancelled checkout never reaches the packing table."""

    __tablename__ = "merch_orders"

    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), primary_key=True)
    fulfilment_status: Mapped[str] = mapped_column(
        _enum(*FULFILMENT_STATUSES, name="fulfilment_status"), default="paid", index=True
    )
    delivery_method: Mapped[str] = mapped_column(_enum(*DELIVERY_METHODS, name="delivery_method"), default="pickup")
    delivery_note: Mapped[str | None] = mapped_column(Text)
    packed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    handed_over_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    handled_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))

    order: Mapped[Order] = relationship()


class Fundraiser(TimestampMixin, Base):
    """A money-raising push with a goal and a date (PRD FR-5.1). Money raised is not stored here:
    it is the sum of the fundraiser's `in` ledger rows, so the total can never drift from the books.
    """

    __tablename__ = "fundraisers"
    __table_args__ = (CheckConstraint("goal_amount > 0", name="ck_fundraisers_goal_positive"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(100), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    goal_amount: Mapped[int] = mapped_column(Integer)  # paise
    event_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(
        _enum(*FUNDRAISER_STATUSES, name="fundraiser_status"), default="planning", index=True
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # joined: every fundraiser view names its owner, and a lazy load per row is a query per row.
    owner: Mapped[User] = relationship(lazy="joined")


class Task(TimestampMixin, Base):
    """One job on a board (PRD FR-5.2). It hangs off a fundraiser today and off an event later,
    which is why exactly one of the two must be set. `position` orders the task inside its column
    of that board, so the kanban needs no client-side sort.
    """

    __tablename__ = "tasks"
    __table_args__ = (
        # The DB refuses a task attached to nothing: a board-less task would be invisible.
        CheckConstraint("fundraiser_id IS NOT NULL OR event_id IS NOT NULL", name="ck_tasks_have_a_board"),
        Index("ix_tasks_fundraiser_status", "fundraiser_id", "status"),
        Index("ix_tasks_assignee_status", "assignee_id", "status"),
        Index("ix_tasks_due_date", "due_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    fundraiser_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("fundraisers.id", ondelete="CASCADE"))
    event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(_enum(*TASK_CATEGORIES, name="task_category"), default="other")
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(_enum(*TASK_STATUSES, name="task_status"), default="todo")
    position: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))

    # joined: every board row shows its assignee, and the task list groups by fundraiser.
    assignee: Mapped[User | None] = relationship(lazy="joined", foreign_keys=[assignee_id])
    fundraiser: Mapped[Fundraiser | None] = relationship(lazy="joined")


class TaskActivity(Base):
    """Immutable trail behind a task (PRD FR-5.2). No updated_at, like a revision row.

    `task_id` is nullable with ON DELETE SET NULL: deleting a task keeps every row it wrote, and
    the delete itself leaves the title in `to_value` so the trail still reads afterwards.
    """

    __tablename__ = "task_activity"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(_enum(*TASK_ACTIONS, name="task_action"))
    from_value: Mapped[str | None] = mapped_column(String(255))
    to_value: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    actor: Mapped[User | None] = relationship(lazy="joined")


class Expense(TimestampMixin, Base):
    """A volunteer's claim for money they already spent (PRD FR-6.1). The receipt lives in a
    PRIVATE storage bucket and only `receipt_path` is stored here - never a public URL, and the
    path is never returned by the API (DESIGN.md §4 rule 14). Money leaves the ledger exactly once,
    when `reimburse_expense` writes the `out` row and records its id in `ledger_transaction_id`.
    """

    __tablename__ = "expenses"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_expenses_amount_positive"),
        # A claim is charged to an event or to a fundraiser, never both: the two would double-count.
        CheckConstraint("NOT (event_id IS NOT NULL AND fundraiser_id IS NOT NULL)", name="ck_expenses_one_bucket"),
        Index("ix_expenses_claimant_status", "claimant_id", "status"),
        Index("ix_expenses_status_created", "status", "created_at"),
        Index("ix_expenses_event_id", "event_id"),
        Index("ix_expenses_fundraiser_id", "fundraiser_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    claimant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    amount: Mapped[int] = mapped_column(Integer)  # paise
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(
        _enum(*EXPENSE_CATEGORIES, name="expense_category"), default="other", index=True
    )
    incurred_on: Mapped[date] = mapped_column(Date, index=True)
    event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id"))
    fundraiser_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("fundraisers.id", ondelete="SET NULL"))
    receipt_path: Mapped[str | None] = mapped_column(String(512))  # bucket key, never a URL
    receipt_mime: Mapped[str | None] = mapped_column(String(100))
    receipt_size: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(
        _enum(*EXPENSE_STATUSES, name="expense_status"), default="submitted", server_default=text("'submitted'")
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(Text)
    reimbursed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reimbursed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reimbursement_method: Mapped[str | None] = mapped_column(_enum(*REIMBURSEMENT_METHODS, name="reimbursement_method"))
    reimbursement_reference: Mapped[str | None] = mapped_column(String(120))
    # Set in the same transaction that writes the `out` ledger row; UNIQUE-ish in effect because
    # `reimburse_expense` only ever fills it for a claim that is still `approved`.
    ledger_transaction_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("transactions.id"))

    # joined: every claim row in the treasurer's queue names its claimant and its reviewer.
    claimant: Mapped[User] = relationship(lazy="joined", foreign_keys=[claimant_id])
    reviewer: Mapped[User | None] = relationship(lazy="joined", foreign_keys=[reviewed_by])
    fundraiser: Mapped[Fundraiser | None] = relationship(lazy="joined")
    history: Mapped[list["ExpenseHistory"]] = relationship(
        back_populates="expense", cascade="all, delete-orphan", order_by="ExpenseHistory.created_at"
    )


class ExpenseHistory(Base):
    """Immutable trail behind a claim (DESIGN.md §4 rule 14). No updated_at, like a revision row."""

    __tablename__ = "expense_history"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    expense_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("expenses.id", ondelete="CASCADE"), index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(_enum(*EXPENSE_ACTIONS, name="expense_action"))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    expense: Mapped[Expense] = relationship(back_populates="history")
    actor: Mapped[User | None] = relationship(lazy="joined")


class FinancePeriod(Base):
    """A closed book (DESIGN.md §4 rule 14). Once closed, no ledger row may be dated inside it, so
    the numbers a treasurer signed off on cannot move under them. Reopening is admin-only and
    records why. The `snapshot` is the semester report as it stood at closing time."""

    __tablename__ = "finance_periods"
    __table_args__ = (CheckConstraint("end_date >= start_date", name="ck_finance_periods_dates_ordered"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    start_date: Mapped[date] = mapped_column(Date, index=True)
    end_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(
        _enum(*FINANCE_PERIOD_STATUSES, name="finance_period_status"), default="closed", server_default=text("'closed'")
    )
    closing_balance: Mapped[int] = mapped_column(Integer)  # paise, frozen at closing time
    snapshot: Mapped[dict | None] = mapped_column(JSON_VARIANT)
    closed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    closed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reopened_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reopened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reopen_reason: Mapped[str | None] = mapped_column(Text)

    closer: Mapped[User | None] = relationship(lazy="joined", foreign_keys=[closed_by])
