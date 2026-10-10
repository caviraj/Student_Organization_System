"""Pydantic v2 request/response models. Kept separate from the ORM models (AGENTS.md)."""

from datetime import date, datetime
from typing import Generic, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

T = TypeVar("T")

Role = Literal["admin", "treasurer", "organizer", "volunteer", "member", "guest"]


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
    email: EmailStr
    password: str = Field(min_length=8, max_length=72, examples=["Passw0rd!"])
    full_name: str = Field(min_length=1, max_length=255, examples=["Demo Student"])
    phone: str | None = Field(default=None, max_length=32, examples=["9876543210"])
    department: str | None = Field(default=None, max_length=120, examples=["CSE"])
    year: int | None = Field(default=None, ge=1, le=6, examples=[2])


class LoginIn(BaseModel):
    email: EmailStr
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
    plan_id: UUID


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
    payment_id: UUID
    order_status: str
    payment_status: str
    provider_ref: str | None = None
    membership: MembershipSummary | None = None


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
