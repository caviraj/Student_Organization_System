"""Admin Portal router for College Department Events and Company Products.

Requirements:
1. Department selection: AIDS, CSE, IT, CIVIL, MECH, AIML, BIO TECH, ECE, EEE.
2. Clicking a department shows department events, count of registered students,
   and registered students' email IDs in the same portal.
3. Add company products for student needs (saved in DB, displayed in Student Portal, optional to buy).
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_optional_user, require_role
from app.core.errors import AppError
from app.core.security import verify_password
from app.models import (
    Event,
    Expense,
    Membership,
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

router = APIRouter(prefix="/admin-portal", tags=["Admin Portal"])

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


class CreateDepartmentEventIn(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    department: str = Field(description="Must be one of the college departments")
    description: str | None = None
    venue: str | None = Field(default="Campus Auditorium")
    starts_at: datetime
    ends_at: datetime
    banner_url: str | None = None
    capacity: int = Field(default=100, ge=1)
    price_inr: int = Field(default=0, ge=0, description="Ticket price in INR (0 for free registration)")


class CreateCompanyProductIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    company_name: str | None = Field(default=None, max_length=120)
    description: str | None = None
    price_inr: float = Field(gt=0, description="Price in INR")
    image_url: str | None = None
    stock: int = Field(default=50, ge=0)


@router.get("/departments", summary="List college departments with stats (admin)")
def get_departments_summary(
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    stats = []
    for dept in DEPARTMENTS:
        # Match case-insensitively or exact
        events_count = (
            db.scalar(
                select(func.count(Event.id)).where(func.upper(Event.department) == dept.upper())
            )
            or 0
        )

        # Count tickets for events in this department
        tickets_count = (
            db.scalar(
                select(func.count(Ticket.id))
                .join(Event, Ticket.event_id == Event.id)
                .where(func.upper(Event.department) == dept.upper(), Ticket.status.in_(("valid", "used")))
            )
            or 0
        )

        students_count = (
            db.scalar(
                select(func.count(User.id)).where(
                    func.upper(User.department) == dept.upper(),
                    User.role != "admin",
                )
            )
            or 0
        )

        stats.append(
            {
                "department": dept,
                "events_count": events_count,
                "registered_count": tickets_count,
                "students_count": students_count,
            }
        )

    return {"departments": stats}


@router.get("/departments/{department}/events", summary="Get department events and registered student emails (admin)")
def get_department_events(
    department: str,
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
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

    items = []
    for e in events:
        # Fetch attendees with user details
        tickets = (
            db.scalars(
                select(Ticket)
                .where(Ticket.event_id == e.id, Ticket.status.in_(("valid", "used")))
                .order_by(Ticket.created_at.desc())
            )
            .all()
        )

        registered_students = []
        for t in tickets:
            user = db.get(User, t.user_id) if t.user_id else None
            registered_students.append(
                {
                    "ticket_id": str(t.id),
                    "ticket_code": t.code,
                    "status": t.status,
                    "registered_at": t.created_at.isoformat() if t.created_at else None,
                    "ticket_type": t.ticket_type.name if t.ticket_type else "General Registration",
                    "student_name": user.full_name if user else "Unknown Student",
                    "student_email": user.email if user else None,
                    "student_department": user.department if user else None,
                }
            )

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
                "registered_count": len(registered_students),
                "registered_students": registered_students,
            }
        )

    return {
        "department": dept_clean,
        "total_events": len(items),
        "events": items,
    }


@router.post("/events", summary="Create event for a department (admin)")
def create_department_event(
    payload: CreateDepartmentEventIn,
    user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    dept = payload.department.strip().upper()
    if dept not in [d.upper() for d in DEPARTMENTS]:
        raise AppError(
            422,
            "INVALID_DEPARTMENT",
            f"Department must be one of: {', '.join(DEPARTMENTS)}",
        )

    if payload.ends_at <= payload.starts_at:
        raise AppError(422, "VALIDATION_ERROR", "ends_at must be after starts_at")

    event = Event(
        title=payload.title,
        description=payload.description,
        venue=payload.venue,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        banner_url=payload.banner_url,
        status="published",
        department=dept,
        created_by=user.id,
    )
    db.add(event)
    db.flush()

    price_paise = int(payload.price_inr * 100)
    ticket_type = TicketType(
        event_id=event.id,
        name=f"{dept} Registration",
        capacity=payload.capacity,
        sold_count=0,
        member_price=price_paise,
        non_member_price=price_paise,
    )
    db.add(ticket_type)
    db.commit()
    db.refresh(event)

    return {
        "message": f"Event created successfully for {dept}",
        "event_id": str(event.id),
        "title": event.title,
        "department": event.department,
        "status": event.status,
    }


@router.get("/products", summary="List company products (admin & student)")
def list_company_products(
    db: Session = Depends(get_db),
):
    products = (
        db.scalars(
            select(Product)
            .where(Product.is_active == True)
            .order_by(Product.created_at.desc())
        )
        .all()
    )

    items = []
    for p in products:
        variants = list(p.variants)
        total_stock = sum(v.stock for v in variants) if variants else 0
        primary_variant = variants[0] if variants else None
        items.append(
            {
                "id": str(p.id),
                "name": p.name,
                "description": p.description,
                "image_url": p.image_url,
                "price_inr": p.base_price / 100,
                "base_price_paise": p.base_price,
                "is_active": p.is_active,
                "stock": total_stock,
                "primary_variant_id": str(primary_variant.id) if primary_variant else None,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "is_optional": True,
                "note": "Optional purchase for students — only buy if needed",
            }
        )

    return {"products": items, "total": len(items)}


@router.post("/products", summary="Add company product for student needs (admin)")
def add_company_product(
    payload: CreateCompanyProductIn,
    user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    base_price_paise = int(round(payload.price_inr * 100))
    desc = payload.description or ""
    if payload.company_name:
        desc = f"Brand: {payload.company_name}. {desc}".strip()

    product = Product(
        name=payload.name,
        description=desc or None,
        image_url=payload.image_url,
        base_price=base_price_paise,
        member_discount_pct=0,
        is_active=True,
    )
    db.add(product)
    db.flush()

    # Create default variant with opening stock
    variant_sku = f"PROD-{uuid4().hex[:6].upper()}"
    variant = ProductVariant(
        product_id=product.id,
        size="Standard",
        color="Default",
        sku=variant_sku,
        stock=payload.stock,
        low_stock_threshold=5,
        is_active=True,
    )
    db.add(variant)
    db.commit()
    db.refresh(product)

    return {
        "message": "Company product added successfully!",
        "id": str(product.id),
        "name": product.name,
        "price_inr": payload.price_inr,
        "stock": payload.stock,
        "image_url": product.image_url,
    }


@router.delete("/products/{product_id}", summary="Delete or deactivate company product (admin)")
def delete_company_product(
    product_id: UUID,
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    product = db.get(Product, product_id)
    if product is None:
        raise AppError(404, "NOT_FOUND", "Product not found")

    product.is_active = False
    db.commit()
    return {"message": "Product deactivated successfully"}


class ResetDataIn(BaseModel):
    password: str = Field(min_length=1, description="Admin portal login password to confirm reset")


@router.post("/reset-data", summary="Reset portal registration and order data (requires admin password)")
def reset_portal_data(
    payload: ResetDataIn,
    current_admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    # Verify the provided password against current_admin's password_hash
    if not verify_password(payload.password, current_admin.password_hash):
        raise AppError(403, "INVALID_ADMIN_PASSWORD", "Incorrect admin password. Data reset aborted.")

    # 1. Clear cross-table foreign key references that prevent cascade
    db.query(Expense).filter(Expense.ledger_transaction_id != None).update({Expense.ledger_transaction_id: None})
    db.query(Membership).filter(Membership.order_id != None).update({Membership.order_id: None})
    db.query(Transaction).filter(Transaction.reverses_id != None).update({Transaction.reverses_id: None})
    db.flush()

    # 2. Delete tickets, merch orders, order items, payments, stock movements, reminders
    db.query(Ticket).delete()
    db.query(MerchOrder).delete()
    db.query(OrderItem).delete()
    db.query(Payment).delete()
    db.query(StockMovement).delete()
    db.query(Reminder).delete()
    db.flush()

    # 3. Delete orders and ledger transactions
    db.query(Order).delete()
    db.query(Transaction).delete()
    db.flush()

    # 4. Reset ticket sold counts back to 0
    db.query(TicketType).update({TicketType.sold_count: 0})

    # 5. Reset product variants back to default stock (50)
    db.query(ProductVariant).update({ProductVariant.stock: 50})
    db.flush()

    # 6. Delete student/guest accounts created during test registrations, preserving core accounts
    # Keep admin, organizers, and core default test accounts ('admin@ssa.org', 'staff@ssa.org', 'student@ssa.org')
    db.query(User).filter(
        User.id != current_admin.id,
        User.role.notin_(["admin", "organizer", "treasurer"]),
        User.email.notin_(["admin@ssa.org", "staff@ssa.org", "student@ssa.org"]),
    ).delete(synchronize_session=False)

    db.commit()

    return {
        "success": True,
        "message": "All registrations, orders, tickets, and attendee records have been reset successfully.",
    }

