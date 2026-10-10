"""Script to truncate all database tables (preserving schema & alembic_version)
and seed clean baseline accounts: Admin, Student, and Staff.
"""

import sys
from datetime import date
from pathlib import Path
from uuid import uuid4

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import text
from app.core.db import migration_engine, MigrationSessionLocal
from app.core.security import hash_password
from app.models import User, MembershipPlan, Membership
from app.services.memberships import add_months

PASSWORD = "Passw0rd!"

def clean_and_seed():
    print("1. Truncating all data from public tables (leaving alembic_version intact)...")
    with migration_engine.begin() as conn:
        tables = [
            row[0]
            for row in conn.execute(
                text(
                    "select tablename from pg_tables where schemaname = 'public' "
                    "and tablename <> 'alembic_version' order by tablename"
                )
            )
        ]
        if tables:
            stmt = f"truncate table {', '.join(tables)} restart identity cascade"
            conn.execute(text(stmt))
            print(f"   Truncated {len(tables)} tables: {', '.join(tables)}")
        else:
            print("   No tables found to truncate.")

    print("\n2. Seeding clean baseline accounts (Admin, Staff, Student) and Membership Plans...")
    password_hash = hash_password(PASSWORD)

    with MigrationSessionLocal() as db:
        # Create Plans
        basic_plan = MembershipPlan(
            id=uuid4(),
            name="Basic",
            price=50000,
            duration_months=12,
            ticket_discount_pct=10,
            merch_discount_pct=5,
            description="Basic student membership plan. 10% off tickets, 5% off merch.",
            is_active=True,
        )
        standard_plan = MembershipPlan(
            id=uuid4(),
            name="Standard",
            price=90000,
            duration_months=12,
            ticket_discount_pct=20,
            merch_discount_pct=10,
            description="Most popular student plan. 20% off tickets, 10% off merch.",
            is_active=True,
        )
        premium_plan = MembershipPlan(
            id=uuid4(),
            name="Premium",
            price=150000,
            duration_months=12,
            ticket_discount_pct=30,
            merch_discount_pct=15,
            description="Full-access membership plan. 30% off tickets, 15% off merch.",
            is_active=True,
        )
        db.add_all([basic_plan, standard_plan, premium_plan])
        db.flush()

        # 1. Admin
        admin_user = User(
            id=uuid4(),
            email="admin@ssa.org",
            password_hash=password_hash,
            full_name="System Administrator",
            phone="9876543210",
            department="Administration",
            year=4,
            role="admin",
            member_code="SSA-2026-0001",
            email_opt_in=True,
            is_active=True,
        )

        # 2. Staff
        staff_user = User(
            id=uuid4(),
            email="staff@ssa.org",
            password_hash=password_hash,
            full_name="Campus Staff Coordinator",
            phone="9876543211",
            department="Student Affairs",
            year=4,
            role="organizer",  # Full staff privileges (organizer / staff dashboard)
            member_code="SSA-2026-0002",
            email_opt_in=True,
            is_active=True,
        )

        # 3. Student
        student_user = User(
            id=uuid4(),
            email="student@ssa.org",
            password_hash=password_hash,
            full_name="Student Member",
            phone="9876543212",
            department="Computer Science",
            year=2,
            role="member",
            member_code="SSA-2026-0003",
            email_opt_in=True,
            is_active=True,
        )

        db.add_all([admin_user, staff_user, student_user])
        db.flush()

        # Give Student an active membership under Standard plan
        today = date.today()
        membership = Membership(
            id=uuid4(),
            user_id=student_user.id,
            plan_id=standard_plan.id,
            status="active",
            start_date=today,
            end_date=add_months(today, 12),
        )
        db.add(membership)

        db.commit()
        print("   Successfully seeded:")
        print("   - Admin: admin@ssa.org (Password: Passw0rd!)")
        print("   - Staff: staff@ssa.org (Password: Passw0rd!)")
        print("   - Student: student@ssa.org (Password: Passw0rd!)")
        print("   - Membership Plans: Basic, Standard, Premium")

if __name__ == "__main__":
    clean_and_seed()
