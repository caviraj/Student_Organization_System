"""Staff Portal Router.

Features:
Only two options as required:
1. Option 1: Ticket Scanning (Real or Fake check)
   - Scans QR code or code input.
   - Checks whether the ticket is REAL or FAKE against the database.
   - If REAL: displays Student Email ID and Name prominently on screen (along with event & registration info).
   - If FAKE: displays bright red alert that no record exists in database.
   - Automatically marks valid ticket as checked in.
2. Option 2: Student Event Registered
   - Lists college departments: AIDS, CSE, IT, CIVIL, MECH, AIML, BIO TECH, ECE, EEE.
   - When staff clicks a department, shows all events and registered students from that department
     with student Name, Email ID, Year, Section, Gender, Ticket Code, and Status.
"""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_role
from app.core.errors import AppError
from app.models import Event, Order, Ticket, User
from app.services.tickets import normalise_code

router = APIRouter(prefix="/staff-portal", tags=["Staff Portal"])

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


class VerifyTicketIn(BaseModel):
    code: str = Field(min_length=1, max_length=100, description="Ticket code to verify")
    auto_checkin: bool = Field(default=True, description="Automatically mark valid ticket as checked in")


@router.post("/verify-ticket", summary="Verify whether a ticket is REAL or FAKE (staff/volunteer+)")
def verify_ticket(
    payload: VerifyTicketIn,
    staff: User = Depends(require_role("volunteer")),
    db: Session = Depends(get_db),
):
    raw_code = payload.code.strip()
    norm_code = normalise_code(raw_code)

    # Search for ticket in database by normalized code or raw code
    ticket = db.scalar(
        select(Ticket).where(
            or_(
                Ticket.code == norm_code,
                Ticket.code == raw_code.upper(),
            )
        )
    )

    # If ticket does not exist in the database -> FAKE TICKET
    if not ticket:
        return {
            "is_real": False,
            "status": "FAKE",
            "message": "FAKE TICKET! No record found in database.",
            "scanned_code": raw_code,
            "verified_at": datetime.now(UTC).isoformat(),
        }

    # Ticket exists -> REAL TICKET!
    event = ticket.event
    user = ticket.user
    order = db.get(Order, ticket.order_id) if ticket.order_id else None
    meta = order.meta if order and isinstance(order.meta, dict) else {}

    # Extract student details
    student_name = meta.get("student_name") or (user.full_name if user else "Unknown Student")
    student_email = meta.get("email") or (user.email if user else "No Email")
    student_department = meta.get("department") or (user.department if user else (event.department if event else "General"))
    student_year = meta.get("year") or "2nd Year"
    student_section = meta.get("section") or "A"
    student_gender = meta.get("gender") or "Not Specified"

    # Status check
    current_status = ticket.status
    if current_status == "used":
        result_status = "ALREADY_USED"
        checkin_message = f"REAL TICKET - Already scanned earlier at {ticket.checked_in_at.strftime('%I:%M %p') if ticket.checked_in_at else 'earlier'}"
    else:
        result_status = "VALID"
        checkin_message = "REAL TICKET - Verified & Admitted successfully!"
        if payload.auto_checkin:
            ticket.status = "used"
            ticket.checked_in_at = datetime.now(UTC)
            ticket.checked_in_by = staff.id
            db.commit()
            db.refresh(ticket)

    return {
        "is_real": True,
        "status": result_status,
        "message": checkin_message,
        "ticket_id": str(ticket.id),
        "ticket_code": ticket.code,
        "student_name": student_name,
        "student_email": student_email,
        "department": student_department,
        "year": student_year,
        "section": student_section,
        "gender": student_gender,
        "event_id": str(ticket.event_id),
        "event_title": event.title if event else "College Event",
        "event_department": event.department if event else "General",
        "event_venue": event.venue if event else "Campus Venue",
        "event_starts_at": event.starts_at.isoformat() if event and event.starts_at else None,
        "checked_in_at": ticket.checked_in_at.isoformat() if ticket.checked_in_at else None,
        "registered_at": ticket.created_at.isoformat() if ticket.created_at else None,
        "product_bought": meta.get("buy_product", False),
        "product_name": meta.get("product_name"),
        "payment_status": meta.get("payment_status") or ("PAID" if (meta.get("total_paid_inr", 0) > 0) else "FREE"),
        "razorpay_payment_id": meta.get("razorpay_payment_id"),
        "total_paid_inr": meta.get("total_paid_inr", 0),
    }


@router.get("/departments", summary="List departments for staff view")
def get_staff_departments(
    staff: User = Depends(require_role("volunteer")),
    db: Session = Depends(get_db),
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
                "registered_students_count": tickets_count,
            }
        )

    return {"departments": stats}


@router.get("/departments/{department}/students", summary="Get registered students in department (staff)")
def get_department_registered_students(
    department: str,
    staff: User = Depends(require_role("volunteer")),
    db: Session = Depends(get_db),
):
    dept_clean = department.strip().upper()

    # Find events in this department
    events = (
        db.scalars(
            select(Event)
            .where(func.upper(Event.department) == dept_clean)
            .order_by(Event.starts_at.desc())
        )
        .all()
    )

    event_ids = [e.id for e in events]

    # Find all tickets for these events
    tickets = []
    if event_ids:
        tickets = (
            db.scalars(
                select(Ticket)
                .where(
                    Ticket.event_id.in_(event_ids),
                    Ticket.status.in_(("valid", "used")),
                )
                .order_by(Ticket.created_at.desc())
            )
            .all()
        )

    registered_students = []
    for t in tickets:
        order = db.get(Order, t.order_id) if t.order_id else None
        meta = order.meta if order and isinstance(order.meta, dict) else {}
        user = t.user
        event = t.event

        registered_students.append(
            {
                "ticket_id": str(t.id),
                "ticket_code": t.code,
                "status": t.status,
                "student_name": meta.get("student_name") or (user.full_name if user else "Student"),
                "student_email": meta.get("email") or (user.email if user else "N/A"),
                "department": meta.get("department") or dept_clean,
                "year": meta.get("year") or "2nd Year",
                "section": meta.get("section") or "A",
                "gender": meta.get("gender") or "Not Specified",
                "event_title": event.title if event else "Event",
                "event_id": str(t.event_id),
                "product_bought": meta.get("buy_product", False),
                "product_name": meta.get("product_name"),
                "payment_status": meta.get("payment_status") or ("PAID" if (meta.get("total_paid_inr", 0) > 0) else "FREE"),
                "razorpay_payment_id": meta.get("razorpay_payment_id"),
                "total_paid_inr": meta.get("total_paid_inr", 0),
                "registered_at": t.created_at.isoformat() if t.created_at else None,
                "checked_in_at": t.checked_in_at.isoformat() if t.checked_in_at else None,
            }
        )

    return {
        "department": dept_clean,
        "total_registered": len(registered_students),
        "total_events": len(events),
        "events": [
            {
                "id": str(e.id),
                "title": e.title,
                "venue": e.venue,
                "starts_at": e.starts_at.isoformat() if e.starts_at else None,
            }
            for e in events
        ],
        "students": registered_students,
    }
