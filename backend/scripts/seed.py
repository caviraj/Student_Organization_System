"""Idempotent Phase 1 seed: staff, plans and 20 members in varied membership states.

    python scripts/seed.py

Running it twice changes nothing. Every member gets a paid order, a succeeded mock
payment and a matching ledger row, so the books reconcile from day one.
"""

import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from uuid import uuid4

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import (  # noqa: E402
    Membership,
    MembershipPlan,
    Order,
    OrderItem,
    Payment,
    Reminder,
    Transaction,
    User,
)
from app.services.memberships import add_months, ensure_member_code  # noqa: E402
from app.services.reminders import run_expiry_scan  # noqa: E402

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
                occurred_at=datetime.combine(start_date, time(10, 0), tzinfo=timezone.utc),
            )
        )
        db.commit()
        created += 1
    return created


def main() -> None:
    db = SessionLocal()
    try:
        staff = get_or_create_staff(db)
        plans = get_or_create_plans(db)
        members = seed_members(db, plans)
        scan = run_expiry_scan(db)  # same job the scheduler runs daily

        today = date.today()
        memberships = list(db.scalars(select(Membership)))
        active = [m for m in memberships if m.status == "active"]
        expiring = [m for m in active if m.end_date and (m.end_date - today).days <= 30]

        print("SSA Hub - Phase 1 seed")
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
        print("-" * 58)
        print(f"  login as staff: admin@ssa.org / treasurer@ssa.org / organizer@ssa.org / volunteer@ssa.org")
        print("  members: member01@ssa.org ... member20@ssa.org")
        print(f"  password for all seeded accounts: {PASSWORD}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
