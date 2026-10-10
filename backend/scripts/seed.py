"""Idempotent Phase 1 + 2 seed: staff, plans, 20 members and a set of events with real sales.

    python scripts/seed.py

Running it twice changes nothing. Every member gets a paid order, a succeeded mock payment
and a matching ledger row; every seeded ticket goes through the real checkout service, so
`ticket_types.sold_count` and the ledger reconcile from day one.
"""

import sys
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from uuid import uuid4

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models import (
    Event,
    Membership,
    MembershipPlan,
    Order,
    OrderItem,
    Payment,
    Reminder,
    Ticket,
    TicketType,
    Transaction,
    User,
)
from app.services.checkin import check_in
from app.services.memberships import add_months, ensure_member_code
from app.services.reminders import run_expiry_scan
from app.services.tickets import confirm_ticket_payment, create_ticket_checkout

# Also documented in .env.example.
PASSWORD = "Passw0rd!"
PASSWORD_HASH = hash_password(PASSWORD)  # hashed once; bcrypt is deliberately slow

STAFF = [
    ("admin@ssa.org", "Aarav Menon", "admin"),
    ("treasurer@ssa.org", "Tara Iyer", "treasurer"),
    ("organizer@ssa.org", "Om Prakash", "organizer"),
    ("volunteer@ssa.org", "Vidya Nair", "volunteer"),
]

# (name, price in paise, duration_months, ticket_discount_pct, merch_discount_pct, description)
PLANS = [
    ("Basic", 50000, 12, 10, 5, "Dues + member pricing. 10% off tickets, 5% off merch."),
    ("Standard", 90000, 12, 20, 10, "Most popular. 20% off tickets, 10% off merch."),
    ("Premium", 150000, 12, 30, 15, "Best value. 30% off tickets, 15% off merch."),
]

MEMBER_NAMES = [
    "Aditi Rao", "Bhavya Shetty", "Chirag Patel", "Divya Menon", "Eshan Gupta",
    "Farah Khan", "Gaurav Singh", "Harini Prasad", "Ishaan Bose", "Jaya Krishnan",
    "Kabir Malhotra", "Lakshmi Reddy", "Manav Joshi", "Nisha Pillai", "Ojas Desai",
    "Pooja Bhat", "Rahul Verma", "Sneha Kulkarni", "Tarun Nambiar", "Uma Sharma",
]
DEPARTMENTS = ["CSE", "ECE", "Mechanical", "Civil", "Business"]

# (days until end_date, seeded status) — 8 healthy, 6 expiring, 1 the job must expire, 5 long expired
MEMBER_STATES = [
    (240, "active"), (200, "active"), (300, "active"), (180, "active"),
    (150, "active"), (120, "active"), (275, "active"),
    (5, "active"),  # inside the 7-day window, so both expiry_30 and expiry_7 fire
    (10, "active"), (10, "active"), (10, "active"),
    (25, "active"), (25, "active"), (25, "active"),
    (-1, "active"),  # left for the daily scan: it flips to expired and raises the 'expired' reminder
    (-20, "expired"), (-45, "expired"), (-70, "expired"), (-100, "expired"), (-150, "expired"),
]


def get_or_create_staff(db: Session) -> int:
    created = 0
    for email, full_name, role in STAFF:
        if db.scalar(select(User.id).where(User.email == email)):
            continue
        db.add(User(email=email, password_hash=PASSWORD_HASH, full_name=full_name, role=role))
        created += 1
    db.commit()
    return created


def get_or_create_plans(db: Session) -> list[MembershipPlan]:
    for name, price, duration, ticket_pct, merch_pct, description in PLANS:
        if db.scalar(select(MembershipPlan.id).where(MembershipPlan.name == name)):
            continue
        db.add(
            MembershipPlan(
                name=name,
                price=price,
                duration_months=duration,
                ticket_discount_pct=ticket_pct,
                merch_discount_pct=merch_pct,
                description=description,
            )
        )
    db.commit()
    return list(db.scalars(select(MembershipPlan).order_by(MembershipPlan.price)))


def seed_members(db: Session, plans: list[MembershipPlan]) -> int:
    created = 0
    for index, (end_offset, seeded_status) in enumerate(MEMBER_STATES, start=1):
        email = f"member{index:02d}@ssa.org"
        if db.scalar(select(User.id).where(User.email == email)):
            continue

        plan = plans[(index - 1) % len(plans)]
        user = User(
            email=email,
            password_hash=PASSWORD_HASH,
            full_name=MEMBER_NAMES[index - 1],
            phone=f"98765{index:05d}",
            department=DEPARTMENTS[(index - 1) % len(DEPARTMENTS)],
            year=(index - 1) % 4 + 1,
            role="member",
        )
        db.add(user)
        db.flush()
        ensure_member_code(db, user)

        end_date = date.today() + timedelta(days=end_offset)
        start_date = add_months(end_date, -plan.duration_months)

        order = Order(
            user_id=user.id,
            kind="membership",
            status="paid",
            subtotal=plan.price,
            discount=0,
            total=plan.price,
            currency="INR",
            meta={"plan_id": str(plan.id), "plan_name": plan.name, "seeded": True},
            idempotency_key=uuid4().hex,
        )
        db.add(order)
        db.flush()
        db.add(
            OrderItem(
                order_id=order.id,
                item_type="plan",
                item_id=plan.id,
                quantity=1,
                unit_price=plan.price,
                line_total=plan.price,
            )
        )
        db.add(
            Payment(
                order_id=order.id,
                provider="mock",
                provider_ref=f"mock_seed_{index:04d}",
                status="succeeded",
                amount=plan.price,
                raw={"seeded": True},
            )
        )
        db.add(
            Membership(
                user_id=user.id,
                plan_id=plan.id,
                status=seeded_status,
                start_date=start_date,
                end_date=end_date,
                order_id=order.id,
            )
        )
        db.add(
            Transaction(
                direction="in",
                amount=plan.price,
                source="dues",
                ref_type="order",
                ref_id=order.id,
                note=f"Membership dues - {plan.name}",
                occurred_at=datetime.combine(start_date, time(10, 0), tzinfo=UTC),
            )
        )
        db.commit()
        created += 1
    return created


def _sell(db: Session, buyer: User, ticket_type: TicketType, quantity: int = 1) -> list[str]:
    """A real sale, through the same service the API uses, so seats and ledger agree."""
    order, payment, _ = create_ticket_checkout(db, buyer, ticket_type.id, quantity)
    return [ticket["code"] for ticket in confirm_ticket_payment(db, order, payment, "success")["tickets"]]


def _event(db: Session, organizer: User, **fields) -> Event:
    event = Event(created_by=organizer.id, **fields)
    db.add(event)
    db.flush()
    return event


def seed_events(db: Session) -> dict:
    """Spring Gala (nearly sold out), a free workshop, a draft and a past event."""
    if db.scalar(select(Event.id).where(Event.title == "Spring Gala")):
        return {"created": False}

    organizer = db.scalar(select(User).where(User.email == "organizer@ssa.org"))
    volunteer = db.scalar(select(User).where(User.email == "volunteer@ssa.org"))
    # The seeded members are a mix of active and lapsed, so the sales produce both
    # member-priced and non-member-priced tickets without inventing more users.
    buyers = list(db.scalars(select(User).where(User.email.like("member%@ssa.org")).order_by(User.email)))
    now = datetime.now(UTC)

    gala = _event(
        db,
        organizer,
        title="Spring Gala",
        description="Live band, dinner and the annual awards.",
        venue="Main Auditorium",
        starts_at=now + timedelta(days=14),
        ends_at=now + timedelta(days=14, hours=4),
        status="published",
    )
    general = TicketType(event_id=gala.id, name="General", member_price=30000, non_member_price=50000, capacity=120)
    vip = TicketType(event_id=gala.id, name="VIP", member_price=100000, non_member_price=150000, capacity=20)
    workshop = _event(
        db,
        organizer,
        title="Coding Workshop",
        description="Hands-on intro to FastAPI and SQL.",
        venue="Lab 3",
        starts_at=now + timedelta(days=21),
        ends_at=now + timedelta(days=21, hours=3),
        status="published",
    )
    free = TicketType(event_id=workshop.id, name="General", member_price=0, non_member_price=0, capacity=40)
    meet = _event(
        db,
        organizer,
        title="Annual Meet",
        description="AGM and office-bearer elections.",
        venue="Seminar Hall",
        starts_at=now + timedelta(days=30),
        ends_at=now + timedelta(days=30, hours=3),
        status="draft",
    )
    db.add(TicketType(event_id=meet.id, name="General", member_price=0, non_member_price=0, capacity=200))
    farewell = _event(
        db,
        organizer,
        title="Farewell 2025",
        description="Farewell for the outgoing batch.",
        venue="Open Air Theatre",
        starts_at=now - timedelta(days=30),
        ends_at=now - timedelta(days=30) + timedelta(hours=3),
        status="published",  # sold while it was on sale; closed below, the way a real event ages
    )
    past = TicketType(event_id=farewell.id, name="General", member_price=20000, non_member_price=35000, capacity=50)
    db.add_all([general, vip, free, past])
    db.commit()

    gala_codes: list[str] = []
    for index in range(85):  # General: 85 of 120
        gala_codes += _sell(db, buyers[index % len(buyers)], general)
    for index in range(19):  # VIP: 19 of 20, deliberately nearly gone
        _sell(db, buyers[index % len(buyers)], vip)
    for code in gala_codes[:60]:  # already through the door
        check_in(db, volunteer, gala.id, code)

    for index in range(10):
        _sell(db, buyers[index % len(buyers)], free)

    past_codes: list[str] = []
    for index in range(5):
        past_codes += _sell(db, buyers[index % len(buyers)], past)
    for code in past_codes[:4]:
        check_in(db, volunteer, farewell.id, code)
    farewell.status = "closed"
    db.commit()

    return {"created": True, "events": 4, "tickets": 85 + 19 + 10 + 5, "checked_in": 64}


def main() -> None:
    db = SessionLocal()
    try:
        staff = get_or_create_staff(db)
        plans = get_or_create_plans(db)
        members = seed_members(db, plans)
        events = seed_events(db)
        scan = run_expiry_scan(db)  # same job the scheduler runs daily

        today = date.today()
        memberships = list(db.scalars(select(Membership)))
        active = [m for m in memberships if m.status == "active"]
        expiring = [m for m in active if m.end_date and (m.end_date - today).days <= 30]

        print("SSA Hub - Phase 1 + 2 seed")
        print("-" * 58)
        print(f"  staff created          {staff} (of {len(STAFF)})")
        print(f"  plans                  {len(plans)}: {', '.join(p.name for p in plans)}")
        print(f"  members created        {members} (of {len(MEMBER_STATES)})")
        print(f"  memberships            {len(memberships)} total | {len(active)} active | "
              f"{len(expiring)} expiring <=30d | {len(memberships) - len(active)} expired")
        print(f"  paid orders            {db.query(Order).filter(Order.status == 'paid').count()}")
        print(f"  succeeded payments     {db.query(Payment).filter(Payment.status == 'succeeded').count()}")
        print(f"  ledger rows (dues)     {db.query(Transaction).filter(Transaction.source == 'dues').count()}")
        print(f"  reminders              {db.query(Reminder).count()} (expiry_30/expiry_7/expired)")
        print(f"  expiry scan            {scan}")

        tickets = db.query(Ticket).count()
        checked_in = db.query(Ticket).filter(Ticket.status == "used").count()
        ledger_paise = sum(t.amount for t in db.scalars(select(Transaction).where(Transaction.source == "tickets")))
        print(f"  events                 {db.query(Event).count()} "
              f"({'new this run' if events['created'] else 'already seeded'})")
        print(f"  ticket types           {db.query(TicketType).count()}")
        print(f"  tickets issued         {tickets} | {checked_in} checked in | "
              f"{db.query(Ticket).filter(Ticket.status == 'valid').count()} still valid")
        print(f"  ledger rows (tickets)  "
              f"{db.query(Transaction).filter(Transaction.source == 'tickets').count()} | "
              f"Rs {ledger_paise // 100:,} ({ledger_paise} paise)")
        print("-" * 58)
        print("  login as staff: admin@ssa.org / treasurer@ssa.org / organizer@ssa.org / volunteer@ssa.org")
        print("  members: member01@ssa.org ... member20@ssa.org")
        print(f"  password for all seeded accounts: {PASSWORD}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
