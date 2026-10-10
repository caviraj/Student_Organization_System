"""Daily expiry scan and renewals-due list (FR-1.5, DESIGN.md §4 rule 6)."""

from datetime import date, timedelta

from app.models import Membership, Reminder
from app.services.reminders import run_expiry_scan


def _membership(db, user, plan, status, end_offset_days):
    membership = Membership(
        user_id=user.id,
        plan_id=plan.id,
        status=status,
        start_date=date.today() - timedelta(days=365),
        end_date=date.today() + timedelta(days=end_offset_days),
    )
    db.add(membership)
    db.flush()
    return membership


def test_scan_expires_past_end_and_reminds_once_per_kind(db, make_user, make_plan):
    plan = make_plan()
    lapsed = _membership(db, make_user("lapsed@ssa.org"), plan, "active", -2)
    due_10 = _membership(db, make_user("due10@ssa.org"), plan, "active", 10)
    due_3 = _membership(db, make_user("due3@ssa.org"), plan, "active", 3)
    fresh = _membership(db, make_user("fresh@ssa.org"), plan, "active", 300)
    db.commit()

    result = run_expiry_scan(db)
    # 1 expired + expiry_30 (10 days) + expiry_30 and expiry_7 (3 days)
    assert result == {"scanned": 4, "expired": 1, "reminders_created": 4}

    db.expire_all()
    assert db.get(Membership, lapsed.id).status == "expired"
    assert db.get(Membership, due_10.id).status == "active"  # still valid until end_date

    kinds = lambda membership: {r.kind for r in db.query(Reminder).filter_by(membership_id=membership.id)}
    assert kinds(lapsed) == {"expired"}
    assert kinds(due_10) == {"expiry_30"}
    assert kinds(due_3) == {"expiry_30", "expiry_7"}
    assert kinds(fresh) == set()  # outside the 30-day window

    assert db.get(Membership, due_10.id).renewal_reminded_at is not None
    assert db.get(Membership, fresh.id).renewal_reminded_at is None

    # Running again the next day must not duplicate anything.
    second = run_expiry_scan(db)
    assert second["reminders_created"] == 0
    assert db.query(Reminder).count() == 4


def test_scan_is_boundary_correct_on_the_last_day(db, make_user, make_plan):
    plan = make_plan()
    last_day = _membership(db, make_user("last@ssa.org"), plan, "active", 0)
    edge_30 = _membership(db, make_user("edge@ssa.org"), plan, "active", 30)
    db.commit()

    result = run_expiry_scan(db)
    assert result["expired"] == 0  # the end_date itself is still covered
    db.expire_all()

    assert db.get(Membership, last_day.id).status == "active"
    kinds = {r.kind for r in db.query(Reminder).filter_by(membership_id=last_day.id)}
    assert kinds == {"expiry_30", "expiry_7"}
    assert {r.kind for r in db.query(Reminder).filter_by(membership_id=edge_30.id)} == {"expiry_30"}


def test_scan_leaves_non_active_memberships_alone(db, make_user, make_plan):
    plan = make_plan()
    cancelled = _membership(db, make_user("cancelled@ssa.org"), plan, "cancelled", -30)
    pending = _membership(db, make_user("pending@ssa.org"), plan, "pending", -1)
    already_expired = _membership(db, make_user("gone@ssa.org"), plan, "expired", -60)
    db.commit()

    result = run_expiry_scan(db)
    assert result == {"scanned": 0, "expired": 0, "reminders_created": 0}
    db.expire_all()
    assert db.get(Membership, cancelled.id).status == "cancelled"
    assert db.get(Membership, pending.id).status == "pending"
    assert db.get(Membership, already_expired.id).status == "expired"
    assert db.query(Reminder).count() == 0


def test_renewal_resets_the_reminder_cycle(db, make_user, make_plan, client, login, auth):
    """A renewed membership warns again for its new period (seen in test_membership_flow too)."""
    from tests.conftest import buy_membership

    plan = make_plan(duration_months=12)
    member = make_user("renew@ssa.org", role="member")
    membership = _membership(db, member, plan, "active", 9)
    db.commit()

    run_expiry_scan(db)
    db.expire_all()
    assert {r.kind for r in db.query(Reminder).filter_by(membership_id=membership.id)} == {"expiry_30"}

    buy_membership(client, auth, login("renew@ssa.org"), str(plan.id))

    db.expire_all()
    assert db.query(Reminder).filter_by(membership_id=membership.id).count() == 0
    assert db.get(Membership, membership.id).renewal_reminded_at is None
    assert run_expiry_scan(db)["reminders_created"] == 0  # renewed far from expiry
