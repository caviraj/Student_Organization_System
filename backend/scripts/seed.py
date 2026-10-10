"""Idempotent Phase 1-4 seed: staff, plans, 20 members, events with real sales, announcements
with real deliveries, and merch bought through the real checkout.

    python scripts/seed.py

Running it twice changes nothing. Every member gets a paid order, a succeeded mock payment
and a matching ledger row; every seeded ticket goes through the real checkout service, so
`ticket_types.sold_count` and the ledger reconcile from day one. Announcements go through the
real announcement service and the real delivery worker, so the mailing list has genuinely sent,
genuinely failed and genuinely opted-out rows. Merch orders are placed and paid through the real
merch checkout and the real payment dispatcher, so stock, the stock_movements audit trail and
the ledger all agree.
"""

import sys
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from uuid import uuid4

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import MigrationSessionLocal  # the DIRECT connection: seeding writes in bulk
from app.core.security import hash_password
from app.models import (
    Announcement,
    AnnouncementDelivery,
    AnnouncementRevision,
    Event,
    Membership,
    MembershipPlan,
    MerchOrder,
    Order,
    OrderItem,
    Payment,
    Product,
    ProductVariant,
    Reminder,
    StockMovement,
    Ticket,
    TicketType,
    Transaction,
    User,
)
from app.services import announcements as announcement_service
from app.services import merch as merch_service
from app.services import payments as payment_service
from app.services.checkin import check_in
from app.services.delivery_worker import process_queued_deliveries
from app.services.memberships import add_months, ensure_member_code
from app.services.pricing import is_active_member
from app.services.reminders import run_expiry_scan
from app.services.tickets import confirm_ticket_payment, create_ticket_checkout

# Also documented in .env.example.
PASSWORD = "Passw0rd!"
PASSWORD_HASH = hash_password(PASSWORD)  # hashed once; bcrypt is deliberately slow

# Any address at this domain fails to send (see app/services/mailer.py).
BOUNCE_EMAIL = "bouncing@fail.test"

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


# (title, body, category, audience, is_pinned, send_email)
POSTS = [
    (
        "Welcome to Spring Semester",
        ("The club desk in the Student Centre is open every weekday from 10 AM. Dues, events and "
        "merch all start here - come and say hello."),
        "general",
        "all",
        True,
        True,
    ),
    (
        "Members' AGM next Friday",
        ("The Annual General Meeting is next Friday at 4 PM in the Seminar Hall. Office-bearer "
        "elections are on the agenda, and only members may vote."),
        "deadline",
        "members",
        False,
        True,
    ),
    (
        "Spring Gala: doors open 6 PM",
        ("Doors open 6 PM - bring your QR ticket, entry is by scan only. See you in the Main "
        "Auditorium."),
        "change",
        "event",
        False,
        True,
    ),
    (
        "Dues deadline is 31 October",
        ("Memberships lapse on 31 October. Renew at the desk or online to keep member pricing for "
        "the Gala."),
        "deadline",
        "members",
        False,
        False,
    ),
    (
        "Blood donation drive on Tuesday",
        "The campus blood bank is on the lawn from 9 AM. Walk-ins welcome; bring your student ID.",
        "meeting",
        "all",
        False,
        False,
    ),
]


def seed_announcements(db: Session) -> dict:
    """Six posts, one of them edited twice, delivered by the real worker."""
    organizer = db.scalar(select(User).where(User.email == "organizer@ssa.org"))
    gala = db.scalar(select(Event).where(Event.title == "Spring Gala"))
    members = list(
        db.scalars(select(User).where(User.email.like("member%@ssa.org")).order_by(User.email))
    )

    # Three members have switched email off, and one more account has an address that always
    # bounces, so the mailing list has all three states (sent, failed, opted out) to show.
    # Nothing is broken to produce them.
    for member in members[:3]:
        member.email_opt_in = False
    if not db.scalar(select(User.id).where(User.email == BOUNCE_EMAIL)):
        db.add(
            User(
                email=BOUNCE_EMAIL,
                password_hash=PASSWORD_HASH,
                full_name="Bounce Test Account",
                role="member",
            )
        )
    db.commit()

    if db.scalar(select(Announcement.id)):
        return {"created": False}

    created: list[Announcement] = []
    for title, body, category, audience, is_pinned, send_email in POSTS:
        data = {
            "title": title,
            "body": body,
            "category": category,
            "audience": audience,
            "is_pinned": is_pinned,
            "send_email": send_email,
        }
        if audience == "event":
            data["event_id"] = gala.id
        created.append(announcement_service.create_announcement(db, organizer, data)["announcement"])

    # The one with history: two edits, so GET /revisions has something to show.
    auditions = announcement_service.create_announcement(
        db,
        organizer,
        {
            "title": "Auditions moved to Lab 3",
            "body": "Auditions for the annual play start at 4 PM in Lab 3.",
            "category": "change",
            "audience": "all",
        },
    )["announcement"]
    created.append(auditions)
    announcement_service.update_announcement(
        db,
        organizer,
        auditions.id,
        {
            "title": "Auditions moved to Lab 3",
            "body": "Auditions for the annual play start at 4 PM in Lab 3, not the Seminar Hall.",
            "revision_note": "Venue changed from the Seminar Hall to Lab 3",
        },
    )
    announcement_service.update_announcement(
        db,
        organizer,
        auditions.id,
        {
            "body": (
                "Auditions for the annual play start at 5 PM in Lab 3, not the Seminar Hall. "
                "Sign-up sheet is on the club desk."
            ),
            "revision_note": "Start moved to 5 PM to avoid the NCC drill",
        },
    )

    # Spread the dates: the feed reads newest first, and six posts written in the same second
    # would come out in an arbitrary order.
    base = datetime.now(UTC)
    for offset, announcement in enumerate(reversed(created)):
        announcement.published_at = base - timedelta(days=3 * offset)
    db.commit()

    # The worker, three times over: everything sends on the first pass except the bouncing
    # address, which needs all three attempts before it is marked failed.
    for _ in range(3):
        process_queued_deliveries(db)

    return {
        "created": True,
        "posts": len(created),
        "revisions": db.scalar(select(func.count()).select_from(AnnouncementRevision)),
    }


# --- merchandise (Phase 4) ----------------------------------------------------------------------

# (name, description, base price in paise, product-wide member discount, [(size, sku, opening stock)])
# The Hoodie's opening stock is deliberately uneven: S is gone, XXL is the last one, M is exactly
# at the low-stock threshold. A stock summary with everything comfortable shows nothing.
CATALOGUE = [
    (
        "SSA Hoodie",
        "Heavyweight fleece, embroidered club crest. Unisex fit.",
        99900,
        10,
        [("S", "SSA-HOOD-S", 0), ("M", "SSA-HOOD-M", 8), ("L", "SSA-HOOD-L", 10),
         ("XL", "SSA-HOOD-XL", 6), ("XXL", "SSA-HOOD-XXL", 1)],
    ),
    (
        "SSA T-Shirt",
        "Cotton tee with the club wordmark.",
        49900,
        15,
        [("S", "SSA-TEE-S", 10), ("M", "SSA-TEE-M", 15), ("L", "SSA-TEE-L", 15),
         ("XL", "SSA-TEE-XL", 10), ("XXL", "SSA-TEE-XXL", 5)],
    ),
    (
        "Old Mug",
        "Last year's design. No longer on sale.",
        29900,
        0,
        [("ONE", "SSA-MUG-ONE", 4)],
    ),
]

# ([(product, size, qty)], delivery_method, delivery_note, fulfilment steps after payment)
# Twelve orders, all genuinely paid: 6 still to pack, 4 packed, 2 handed over. Nothing is left
# pending - a pending order would be swept and its stock released on the next scheduler tick.
MERCH_ORDERS = [
    ([("SSA Hoodie", "M", 1)], "pickup", None, ()),
    ([("SSA Hoodie", "M", 2)], "pickup", None, ()),
    ([("SSA Hoodie", "L", 1)], "campus_delivery", "Hostel B, room 214", ()),
    ([("SSA Hoodie", "L", 1)], "pickup", None, ()),
    ([("SSA Hoodie", "XL", 1)], "pickup", None, ()),
    ([("SSA Hoodie", "XL", 1)], "campus_delivery", "Hostel A, room 108", ()),
    ([("SSA T-Shirt", "M", 1)], "pickup", None, ("packed",)),
    ([("SSA T-Shirt", "M", 2)], "pickup", None, ("packed",)),
    ([("SSA T-Shirt", "L", 1)], "campus_delivery", "Day scholar, main gate", ("packed",)),
    ([("SSA T-Shirt", "L", 1)], "pickup", None, ("packed",)),
    ([("SSA Hoodie", "XXL", 1), ("SSA T-Shirt", "S", 1)], "pickup", None, ("packed", "handed_over")),
    ([("SSA Hoodie", "M", 1), ("SSA T-Shirt", "XL", 1)], "pickup", None, ("packed", "handed_over")),
]


def seed_merch(db: Session) -> dict:
    """The shop, and twelve orders bought the way a real member buys them."""
    if db.scalar(select(Product.id).where(Product.name == "SSA Hoodie")):
        return {"created": False}

    admin = db.scalar(select(User).where(User.email == "admin@ssa.org"))
    variants: dict[tuple[str, str], ProductVariant] = {}
    for name, description, base_price, discount_pct, sizes in CATALOGUE:
        product = merch_service.create_product(
            db,
            {
                "name": name,
                "description": description,
                "base_price": base_price,
                "member_discount_pct": discount_pct,
                "is_active": name != "Old Mug",  # one retired product, so hiding is visible
            },
        )
        for size, sku, stock in sizes:
            variant = merch_service.create_variant(db, product, {"size": size, "sku": sku, "stock": stock}, admin)
            variants[(name, size)] = variant

    # Only members with a live membership may order (MERCH_MEMBERS_ONLY), so the lapsed and
    # expired seeded members are genuinely turned away at checkout - exactly as in production.
    buyers = [m for m in db.scalars(select(User).where(User.email.like("member%@ssa.org")).order_by(User.email))]
    buyers = [m for m in buyers if is_active_member(db, m)]
    for index, (lines, delivery_method, delivery_note, steps) in enumerate(MERCH_ORDERS):
        buyer = buyers[index % len(buyers)]
        order, _payment = merch_service.create_merch_checkout(
            db,
            buyer,
            [{"variant_id": variants[(product, size)].id, "qty": qty} for product, size, qty in lines],
            delivery_method,
            delivery_note,
        )
        payment_service.confirm_mock_payment(db, order.id, "success", buyer)
        for step in steps:
            merch_service.update_fulfilment(db, order.id, step, admin)

    return {"created": True, "products": len(CATALOGUE), "variants": len(variants), "orders": len(MERCH_ORDERS)}


def main() -> None:
    db = MigrationSessionLocal()
    try:
        staff = get_or_create_staff(db)
        plans = get_or_create_plans(db)
        members = seed_members(db, plans)
        events = seed_events(db)
        announcements = seed_announcements(db)
        merch = seed_merch(db)
        scan = run_expiry_scan(db)  # same job the scheduler runs daily

        today = date.today()
        memberships = list(db.scalars(select(Membership)))
        active = [m for m in memberships if m.status == "active"]
        expiring = [m for m in active if m.end_date and (m.end_date - today).days <= 30]

        print("SSA Hub - Phase 1-4 seed")
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

        deliveries = db.execute(
            select(AnnouncementDelivery.channel, AnnouncementDelivery.status, func.count())
            .group_by(AnnouncementDelivery.channel, AnnouncementDelivery.status)
            .order_by(AnnouncementDelivery.channel, AnnouncementDelivery.status)
        ).all()
        print(f"  announcements          {db.query(Announcement).count()} "
              f"({db.query(Announcement).filter(Announcement.is_pinned).count()} pinned) "
              f"({'new this run' if announcements['created'] else 'already seeded'}) | "
              f"{db.query(AnnouncementRevision).count()} revision rows")
        print("  deliveries             "
              + " | ".join(f"{channel} {status} {count}" for channel, status, count in deliveries))
        print(f"  opted out of email     "
              f"{db.query(User).filter(User.email_opt_in.is_(False)).count()} users "
              f"| bouncing@fail.test always fails")

        variant_count = db.query(ProductVariant).count()
        fulfilled = dict(
            db.execute(
                select(MerchOrder.fulfilment_status, func.count()).group_by(MerchOrder.fulfilment_status)
            ).all()
        )
        merch_paise = sum(
            t.amount for t in db.scalars(select(Transaction).where(Transaction.source == "merch"))
        )
        moved = (
            select(StockMovement.variant_id, func.sum(StockMovement.delta).label("delta"))
            .group_by(StockMovement.variant_id)
            .subquery()
        )
        drift = db.scalar(
            select(func.count())
            .select_from(ProductVariant)
            .outerjoin(moved, moved.c.variant_id == ProductVariant.id)
            .where(func.coalesce(moved.c.delta, 0) != ProductVariant.stock)
        )
        print(f"  products               {db.query(Product).count()} "
              f"({db.query(Product).filter(Product.is_active).count()} active, "
              f"{db.query(Product).filter(Product.is_active.is_(False)).count()} retired) | "
              f"{variant_count} variants "
              f"({'new this run' if merch['created'] else 'already seeded'})")
        print(f"  merch stock            "
              f"{db.query(func.coalesce(func.sum(ProductVariant.stock), 0)).scalar()} units | "
              f"{db.query(ProductVariant).filter(ProductVariant.stock <= 0).count()} out of stock | "
              f"{db.query(ProductVariant).filter(ProductVariant.stock > 0, ProductVariant.stock <= ProductVariant.low_stock_threshold).count()} low")
        print(f"  merch orders           {db.query(MerchOrder).count()} | "
              + ", ".join(f"{status} {fulfilled.get(status, 0)}" for status in ("paid", "packed", "handed_over")))
        print(f"  ledger rows (merch)    "
              f"{db.query(Transaction).filter(Transaction.source == 'merch').count()} | "
              f"Rs {merch_paise // 100:,} ({merch_paise} paise)")
        print(f"  stock movements        {db.query(StockMovement).count()} rows | "
              f"invariant SUM(delta) == stock for {variant_count - (drift or 0)}/{variant_count} variants")
        print("-" * 58)
        print("  login as staff: admin@ssa.org / treasurer@ssa.org / organizer@ssa.org / volunteer@ssa.org")
        print("  members: member01@ssa.org ... member20@ssa.org")
        print(f"  password for all seeded accounts: {PASSWORD}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
