"""Member pricing (DESIGN.md §4 rule 1)."""

from datetime import date

from sqlalchemy.orm import Session

from app.models import Product, TicketType, User
from app.services.memberships import current_membership


def is_active_member(db: Session, user: User | None) -> bool:
    """Member pricing requires an ACTIVE membership as of today. Role alone never grants it —
    an organizer whose dues lapsed is a non-member at the door."""
    if user is None:
        return False
    membership = current_membership(db, user)
    return bool(
        membership and membership.status == "active" and membership.end_date and membership.end_date >= date.today()
    )


def price_for(ticket_type: TicketType, is_member: bool) -> int:
    return ticket_type.member_price if is_member else ticket_type.non_member_price


def resolve_ticket_price(db: Session, user: User, ticket_type: TicketType) -> tuple[int, bool]:
    """Returns (unit_price_in_paise, is_member_price), frozen onto the order at checkout."""
    member = is_active_member(db, user)
    return price_for(ticket_type, member), member


def discounted(base_price: int, pct: int) -> int:
    """Integer paise, rounded half up. Never a float: 99900 at 15% is 84915, not 84914.99…"""
    return (base_price * (100 - pct) + 50) // 100


def merch_discount(db: Session, user: User | None, product: Product) -> tuple[int, str]:
    """The discount that applies to this product for this caller (PRD FR-4.1/4.3).

    A member gets the better of the product's own discount and their plan's merch perk; everyone
    else pays list price. Returns `(pct, source)` where source names where the pct came from and is
    "none" when nothing applied - so the order meta can always answer "why this price?".
    """
    if not is_active_member(db, user):
        return 0, "none"
    plan_pct = current_membership(db, user).plan.merch_discount_pct
    if plan_pct <= 0 and product.member_discount_pct <= 0:
        return 0, "none"
    # Ties go to the plan: it is the one the member paid for.
    if plan_pct >= product.member_discount_pct:
        return plan_pct, "plan"
    return product.member_discount_pct, "product"


def resolve_merch_unit_price(db: Session, user: User | None, product: Product) -> tuple[int, int, str]:
    """Returns (unit_price_in_paise, discount_pct_applied, source) for one product."""
    pct, source = merch_discount(db, user, product)
    return discounted(product.base_price, pct), pct, source
