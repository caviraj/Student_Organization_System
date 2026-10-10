"""Member pricing (DESIGN.md §4 rule 1)."""

from datetime import date

from sqlalchemy.orm import Session

from app.models import TicketType, User
from app.services.memberships import current_membership


def is_active_member(db: Session, user: User | None) -> bool:
    """Member pricing requires an ACTIVE membership as of today. Role alone never grants it —
    an organizer whose dues lapsed is a non-member at the door."""
    if user is None:
        return False
    membership = current_membership(db, user)
    return bool(
        membership
        and membership.status == "active"
        and membership.end_date
        and membership.end_date >= date.today()
    )


def price_for(ticket_type: TicketType, is_member: bool) -> int:
    return ticket_type.member_price if is_member else ticket_type.non_member_price


def resolve_ticket_price(db: Session, user: User, ticket_type: TicketType) -> tuple[int, bool]:
    """Returns (unit_price_in_paise, is_member_price), frozen onto the order at checkout."""
    member = is_active_member(db, user)
    return price_for(ticket_type, member), member
