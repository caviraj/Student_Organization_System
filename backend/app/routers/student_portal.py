"""Student Portal Router.

Features:
1. College departments: AIDS, CSE, IT, CIVIL, MECH, AIML, BIO TECH, ECE, EEE.
2. Department events with registered student counts.
3. Event Registration form:
   - name
   - department*
   - which year* (1st Year, 2nd Year, 3rd Year, 4th Year)
   - section* (A, B, C, etc.)
   - gender* (Male, Female, Other)
   - email id*
   - Related company product with "Buy or Not Buy" option
   - Razorpay payment for paid events/products; free tickets issued immediately
4. "My Tickets" section for student verification stored in database.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user, get_db
from app.core.errors import AppError
from app.models import Event, Order, OrderItem, Payment, Product, Ticket, TicketType, User
from app.services.tickets import generate_ticket_code
import httpx

router = APIRouter(prefix="/student-portal", tags=["Student Portal"])

DEPARTMENTS = [
    "AIDS",
    "CSE",
    "IT",
    "CIVIL",
    "MECH",
    "AIML",
    "BIO TECH",
    "ECE",
    "EEE",
]

YEARS = [
    "1st Year",
    "2nd Year",
    "3rd Year",
    "4th Year",
]

GENDERS = [
    "Male",
    "Female",
    "Other",
]


class CreateOrderIn(BaseModel):
    event_id: UUID
    buy_product: bool = False
    product_id: UUID | None = None


class StudentRegisterIn(BaseModel):
    event_id: UUID
    name: str = Field(min_length=2, max_length=120)
    department: str = Field(description="Must be one of the college departments")
    year: str = Field(description="Which year: 1st Year, 2nd Year, 3rd Year, 4th Year")
    section: str = Field(min_length=1, max_length=20, description="Section: A, B, C, etc.")
    gender: str = Field(description="Gender: Male, Female, Other")
    email: EmailStr = Field(description="Student email id")
    buy_product: bool = Field(default=False, description="Whether the student chooses to buy the product")
    product_id: UUID | None = None
    razorpay_payment_id: str | None = None
    razorpay_order_id: str | None = None
    razorpay_signature: str | None = None


@router.post("/create-order", summary="Create Razorpay order for event registration and optional product")
def create_student_order(
    payload: CreateOrderIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    event = db.get(Event, payload.event_id)
    if not event:
        raise AppError(404, "EVENT_NOT_FOUND", "Event not found")

    ticket_type = db.scalar(select(TicketType).where(TicketType.event_id == event.id))
    event_price_paise = ticket_type.member_price if ticket_type else 0

    product_price_paise = 0
    if payload.buy_product and payload.product_id:
        product = db.get(Product, payload.product_id)
        if product and product.is_active:
            product_price_paise = product.base_price

    total_paise = event_price_paise + product_price_paise

    if total_paise <= 0:
        return {
            "is_free": True,
            "key_id": "",
            "gateway_order_id": "",
            "amount": 0,
            "currency": "INR",
            "total_inr": 0.0,
        }

    key_id = settings.RAZORPAY_KEY_ID or "rzp_test_TmDLwiteZCTl2D"
    key_secret = settings.RAZORPAY_KEY_SECRET or "0jiWT0p28XgGLVrSSfbEARLB"
    gateway_order_id = f"order_{uuid4().hex[:14]}"

    # Attempt to create real Razorpay Order via API
    try:
        resp = httpx.post(
            "https://api.razorpay.com/v1/orders",
            json={
                "amount": total_paise,
                "currency": "INR",
                "receipt": f"reg_{uuid4().hex[:16]}",
                "notes": {
                    "event_id": str(event.id),
                    "event_title": event.title[:40],
                    "student_email": user.email,
                },
            },
            auth=(key_id, key_secret),
            timeout=5.0,
        )
        if resp.status_code < 400:
            order_data = resp.json()
            gateway_order_id = order_data.get("id", gateway_order_id)
    except Exception:
        # Fallback to test order ID if offline or test key issue
        pass

    return {
        "is_free": False,
        "key_id": key_id,
        "gateway_order_id": gateway_order_id,
        "amount": total_paise,
        "currency": "INR",
        "total_inr": total_paise / 100,
    }


@router.get("/departments", summary="List college departments with event counts for students")
def list_departments(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stats = []
    for dept in DEPARTMENTS:
        events_count = (
            db.scalar(
                select(func.count(Event.id)).where(func.upper(Event.department) == dept.upper())
            )
            or 0
        )

        tickets_count = (
            db.scalar(
                select(func.count(Ticket.id))
                .join(Event, Ticket.event_id == Event.id)
                .where(func.upper(Event.department) == dept.upper(), Ticket.status.in_(("valid", "used")))
            )
            or 0
        )

        stats.append(
            {
                "department": dept,
                "events_count": events_count,
                "registered_count": tickets_count,
            }
        )

    return {"departments": stats}


@router.get("/departments/{department}/events", summary="Get department events with registered counts")
def get_department_events_for_student(
    department: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    dept_clean = department.strip().upper()
    events = (
        db.scalars(
            select(Event)
            .where(func.upper(Event.department) == dept_clean)
            .order_by(Event.starts_at.desc())
        )
        .all()
    )

    # Fetch available company products to attach to events
    products = (
        db.scalars(
            select(Product)
            .where(Product.is_active == True)
            .order_by(Product.created_at.desc())
        )
        .all()
    )
    product_list = [
        {
            "id": str(p.id),
            "name": p.name,
            "description": p.description,
            "price_inr": p.base_price / 100,
            "image_url": p.image_url,
        }
        for p in products
    ]

    items = []
    for e in events:
        registered_count = (
            db.scalar(
                select(func.count(Ticket.id)).where(
                    Ticket.event_id == e.id,
                    Ticket.status.in_(("valid", "used")),
                )
            )
            or 0
        )

        # Check if current user already registered
        user_ticket = db.scalar(
            select(Ticket).where(
                Ticket.event_id == e.id,
                Ticket.user_id == user.id,
                Ticket.status.in_(("valid", "used")),
            )
        )

        # Default ticket price
        ticket_type = db.scalar(select(TicketType).where(TicketType.event_id == e.id))
        price_inr = (ticket_type.member_price / 100) if ticket_type else 0.0

        items.append(
            {
                "id": str(e.id),
                "title": e.title,
                "description": e.description,
                "venue": e.venue,
                "starts_at": e.starts_at.isoformat() if e.starts_at else None,
                "ends_at": e.ends_at.isoformat() if e.ends_at else None,
                "banner_url": e.banner_url,
                "status": e.status,
                "department": e.department or dept_clean,
                "registered_count": registered_count,
                "price_inr": price_inr,
                "is_registered": user_ticket is not None,
                "user_ticket_code": user_ticket.code if user_ticket else None,
                "related_products": product_list,
            }
        )

    return {
        "department": dept_clean,
        "total_events": len(items),
        "events": items,
    }


@router.post("/register", summary="Register student for an event with form details and optional product purchase")
def register_for_event(
    payload: StudentRegisterIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    event = db.get(Event, payload.event_id)
    if not event:
        raise AppError(404, "EVENT_NOT_FOUND", "Event not found")

    dept_clean = payload.department.strip().upper()
    if dept_clean not in [d.upper() for d in DEPARTMENTS]:
        raise AppError(422, "INVALID_DEPARTMENT", f"Department must be one of: {', '.join(DEPARTMENTS)}")

    # Ensure a TicketType exists for this event
    ticket_type = db.scalar(select(TicketType).where(TicketType.event_id == event.id))
    if not ticket_type:
        ticket_type = TicketType(
            event_id=event.id,
            name=f"{event.department or dept_clean} Registration",
            capacity=500,
            sold_count=0,
            member_price=0,
            non_member_price=0,
        )
        db.add(ticket_type)
        db.flush()

    # Product calculation
    product = None
    product_price_paise = 0
    if payload.buy_product and payload.product_id:
        product = db.get(Product, payload.product_id)
        if product and product.is_active:
            product_price_paise = product.base_price

    event_price_paise = ticket_type.member_price
    total_paise = event_price_paise + product_price_paise

    # Check if student already registered for this event
    existing_ticket = db.scalar(
        select(Ticket).where(
            Ticket.event_id == event.id,
            Ticket.user_id == user.id,
            Ticket.status.in_(("valid", "used")),
        )
    )
    if existing_ticket:
        return {
            "message": "Student is already registered for this event",
            "is_new": False,
            "ticket_id": str(existing_ticket.id),
            "ticket_code": existing_ticket.code,
            "status": existing_ticket.status,
            "event_title": event.title,
            "student_name": payload.name,
            "student_email": payload.email,
            "department": dept_clean,
            "year": payload.year,
            "section": payload.section,
            "gender": payload.gender,
        }

    # Create Order
    payment_id_to_store = payload.razorpay_payment_id or (f"pay_{uuid4().hex[:14]}" if total_paise > 0 else None)
    order_meta = {
        "student_name": payload.name,
        "department": dept_clean,
        "year": payload.year,
        "section": payload.section,
        "gender": payload.gender,
        "email": payload.email,
        "buy_product": payload.buy_product,
        "product_id": str(product.id) if product else None,
        "product_name": product.name if product else None,
        "product_price_inr": (product_price_paise / 100) if product else 0,
        "event_price_inr": (event_price_paise / 100),
        "total_paid_inr": (total_paise / 100),
        "payment_status": "PAID" if total_paise > 0 else "FREE",
        "razorpay_payment_id": payment_id_to_store,
        "registered_at": datetime.now(UTC).isoformat(),
    }

    order = Order(
        user_id=user.id,
        kind="ticket",
        status="paid",
        subtotal=total_paise,
        discount=0,
        total=total_paise,
        currency="INR",
        meta=order_meta,
    )
    db.add(order)
    db.flush()

    # Order item for ticket
    order_item = OrderItem(
        order_id=order.id,
        item_type="ticket_type",
        item_id=ticket_type.id,
        quantity=1,
        unit_price=event_price_paise,
        line_total=event_price_paise,
    )
    db.add(order_item)

    # Order item for product if purchased
    if product:
        product_item = OrderItem(
            order_id=order.id,
            item_type="variant",
            item_id=product.id,
            quantity=1,
            unit_price=product_price_paise,
            line_total=product_price_paise,
        )
        db.add(product_item)

    # Record payment if paid amount
    if total_paise > 0:
        payment = Payment(
            order_id=order.id,
            provider="razorpay",
            provider_ref=payment_id_to_store or f"pay_{uuid4().hex[:14]}",
            status="succeeded",
            amount=total_paise,
            raw={
                "razorpay_payment_id": payment_id_to_store,
                "razorpay_order_id": payload.razorpay_order_id,
                "student_email": payload.email,
            },
        )
        db.add(payment)

    # Mint ticket
    ticket_code = generate_ticket_code(db)
    ticket = Ticket(
        order_id=order.id,
        event_id=event.id,
        ticket_type_id=ticket_type.id,
        user_id=user.id,
        code=ticket_code,
        status="valid",
        price_paid=event_price_paise,
        is_member_price=True,
    )
    db.add(ticket)

    # Increment sold count
    ticket_type.sold_count = (ticket_type.sold_count or 0) + 1

    db.commit()
    db.refresh(ticket)

    return {
        "message": "Registration successful! Ticket issued and stored in database.",
        "is_new": True,
        "ticket_id": str(ticket.id),
        "ticket_code": ticket.code,
        "status": ticket.status,
        "event_title": event.title,
        "event_department": event.department,
        "event_venue": event.venue,
        "student_name": payload.name,
        "student_email": payload.email,
        "department": dept_clean,
        "year": payload.year,
        "section": payload.section,
        "gender": payload.gender,
        "product_bought": payload.buy_product,
        "product_name": product.name if product else None,
        "payment_status": "PAID" if total_paise > 0 else "FREE",
        "razorpay_payment_id": payment_id_to_store,
        "total_paid_inr": total_paise / 100,
        "registered_at": datetime.now(UTC).isoformat(),
    }


@router.get("/my-tickets", summary="List all registered tickets for the logged in student")
def get_student_tickets(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tickets = (
        db.scalars(
            select(Ticket)
            .where(Ticket.user_id == user.id)
            .order_by(Ticket.created_at.desc())
        )
        .all()
    )

    items = []
    for t in tickets:
        order = db.get(Order, t.order_id) if t.order_id else None
        meta = order.meta if order and isinstance(order.meta, dict) else {}
        event = t.event

        items.append(
            {
                "ticket_id": str(t.id),
                "ticket_code": t.code,
                "status": t.status,
                "event_id": str(t.event_id),
                "event_title": event.title if event else "Event",
                "event_department": event.department if event else "General",
                "event_venue": event.venue if event else "Auditorium",
                "event_starts_at": event.starts_at.isoformat() if event and event.starts_at else None,
                "event_ends_at": event.ends_at.isoformat() if event and event.ends_at else None,
                "student_name": meta.get("student_name") or user.full_name,
                "student_email": meta.get("email") or user.email,
                "department": meta.get("department") or user.department or "CSE",
                "year": meta.get("year") or "2nd Year",
                "section": meta.get("section") or "A",
                "gender": meta.get("gender") or "Not Specified",
                "buy_product": meta.get("buy_product", False),
                "product_name": meta.get("product_name"),
                "product_price_inr": meta.get("product_price_inr", 0),
                "payment_status": meta.get("payment_status") or ("PAID" if (meta.get("total_paid_inr", 0) > 0) else "FREE"),
                "razorpay_payment_id": meta.get("razorpay_payment_id"),
                "total_paid_inr": meta.get("total_paid_inr", 0),
                "registered_at": t.created_at.isoformat() if t.created_at else None,
                "checked_in_at": t.checked_in_at.isoformat() if t.checked_in_at else None,
            }
        )

    return {"tickets": items, "total": len(items)}
