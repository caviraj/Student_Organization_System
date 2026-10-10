"""ORM models (DESIGN.md §4). Money is always integer paise; PKs are UUIDs.

Phase 1 tables: users, membership_plans, memberships, orders, order_items, payments,
transactions, reminders. Phase 2 adds events, ticket_types, tickets. Merch arrives later.
"""

import uuid
from datetime import date, datetime

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
LEDGER_SOURCES = ("dues", "tickets", "merch", "fundraiser", "other_income", "expense_reimbursement")
REMINDER_KINDS = ("expiry_30", "expiry_7", "expired")
EVENT_STATUSES = ("draft", "published", "closed")
TICKET_STATUSES = ("valid", "used", "void")


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
    status: Mapped[str] = mapped_column(_enum(*MEMBERSHIP_STATUSES, name="membership_status"), default="pending", index=True)
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

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    direction: Mapped[str] = mapped_column(_enum(*LEDGER_DIRECTIONS, name="ledger_direction"), index=True)
    amount: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(_enum(*LEDGER_SOURCES, name="ledger_source"), index=True)
    ref_type: Mapped[str | None] = mapped_column(String(32))
    ref_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id"), index=True)
    fundraiser_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)  # FK lands in Phase 5
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    note: Mapped[str | None] = mapped_column(Text)


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
