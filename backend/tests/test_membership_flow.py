"""Checkout, mock payment, activation, renewal, ledger and verification (FR-1.3–1.6)."""

import re
from datetime import date, timedelta
from uuid import UUID

from app.models import Membership, Order, Payment, Reminder, Transaction, User
from tests.conftest import buy_membership


def plus_one_year(day: date) -> date:
    """Expected end date for a 12-month plan, without tripping over 29 Feb."""
    try:
        return day.replace(year=day.year + 1)
    except ValueError:
        return day.replace(year=day.year + 1, day=28)


def test_checkout_creates_pending_order_with_mock_payment(client, db, make_user, make_plan, login, auth):
    make_user("buyer@ssa.org", role="guest")
    plan = make_plan(price=90000)
    token = login("buyer@ssa.org")

    response = client.post("/api/v1/memberships/checkout", json={"plan_id": str(plan.id)}, headers=auth(token))
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["amount"] == 90000
    assert body["provider"] == "mock"
    assert body["status"] == "created"

    db.expire_all()
    order = db.query(Order).filter_by(id=UUID(body["order_id"])).one()
    assert (order.kind, order.status, order.total, order.currency) == ("membership", "pending", 90000, "INR")
    assert order.idempotency_key
    assert order.items[0].item_type == "plan"
    assert order.items[0].item_id == plan.id
    payment = db.query(Payment).filter_by(order_id=order.id).one()
    assert payment.status == "created"
    assert payment.provider_ref is None  # only set when the gateway settles


def test_checkout_rejects_inactive_plan(client, db, make_user, make_plan, login, auth):
    make_user("buyer@ssa.org", role="guest")
    plan = make_plan()
    plan.is_active = False
    db.commit()
    token = login("buyer@ssa.org")
    response = client.post("/api/v1/memberships/checkout", json={"plan_id": str(plan.id)}, headers=auth(token))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PLAN_NOT_FOUND"


def test_successful_payment_activates_membership_and_writes_one_ledger_row(
    client, db, make_user, make_plan, login, auth
):
    user = make_user("buyer@ssa.org", role="guest")
    plan = make_plan(name="Standard", price=90000, duration_months=12)
    token = login("buyer@ssa.org")

    result = buy_membership(client, auth, token, str(plan.id))

    assert result["order_status"] == "paid"
    assert result["payment_status"] == "succeeded"
    assert result["provider_ref"].startswith("mock_")
    assert result["membership"]["status"] == "active"
    assert result["membership"]["plan_name"] == "Standard"

    db.expire_all()
    user = db.get(User, user.id)
    assert user.role == "member"  # promoted from guest
    assert re.fullmatch(r"SSA-\d{4}-\d{4}", user.member_code)

    membership = db.query(Membership).filter_by(user_id=user.id).one()
    assert membership.status == "active"
    assert membership.start_date == date.today()
    assert membership.end_date == plus_one_year(date.today())  # +12 months
    assert membership.order_id == UUID(result["order_id"])

    ledger = db.query(Transaction).all()
    assert len(ledger) == 1
    assert (ledger[0].direction, ledger[0].source, ledger[0].amount) == ("in", "dues", 90000)
    assert ledger[0].ref_type == "order"
    assert ledger[0].ref_id == UUID(result["order_id"])

    payment = db.query(Payment).one()
    assert payment.status == "succeeded"


def test_mock_confirm_twice_changes_nothing(client, db, make_user, make_plan, login, auth):
    make_user("buyer@ssa.org", role="guest")
    plan = make_plan(price=90000)
    token = login("buyer@ssa.org")
    first = buy_membership(client, auth, token, str(plan.id))

    db.expire_all()
    before = db.query(Membership).one()

    replay = client.post(
        f"/api/v1/payments/{first['order_id']}/mock-confirm", json={"outcome": "success"}, headers=auth(token)
    )
    assert replay.status_code == 200
    assert replay.json()["order_status"] == "paid"
    assert replay.json()["membership"]["end_date"] == first["membership"]["end_date"]

    # Even a late "fail" must not undo a settled payment.
    late_fail = client.post(
        f"/api/v1/payments/{first['order_id']}/mock-confirm", json={"outcome": "fail"}, headers=auth(token)
    )
    assert late_fail.status_code == 200
    assert late_fail.json()["order_status"] == "paid"

    db.expire_all()
    assert db.query(Membership).one().end_date == before.end_date
    assert db.query(Transaction).count() == 1
    assert db.query(Payment).count() == 1
    assert db.query(Order).count() == 1


def test_failed_payment_changes_nothing(client, db, make_user, make_plan, login, auth):
    user = make_user("buyer@ssa.org", role="guest")
    plan = make_plan()
    token = login("buyer@ssa.org")

    result = buy_membership(client, auth, token, str(plan.id), outcome="fail")

    assert result["order_status"] == "failed"
    assert result["payment_status"] == "failed"
    assert result["membership"] is None

    db.expire_all()
    user = db.get(User, user.id)
    assert user.role == "guest"
    assert user.member_code is None
    assert db.query(Membership).count() == 0
    assert db.query(Transaction).count() == 0


def test_renewal_extends_from_previous_end_date(client, db, make_user, make_plan, login, auth):
    user = make_user("renew@ssa.org", role="member")
    plan = make_plan(name="Standard", price=90000, duration_months=12)
    old_end = date.today() + timedelta(days=25)
    membership = Membership(
        user_id=user.id,
        plan_id=plan.id,
        status="active",
        start_date=date.today() - timedelta(days=340),
        end_date=old_end,
    )
    db.add(membership)
    db.flush()
    db.add(Reminder(membership_id=membership.id, kind="expiry_30"))
    db.commit()

    token = login("renew@ssa.org")
    result = buy_membership(client, auth, token, str(plan.id))

    db.expire_all()
    renewed = db.query(Membership).filter_by(user_id=user.id).one()  # still a single row
    assert renewed.start_date == old_end  # no paid days lost
    assert renewed.end_date == plus_one_year(old_end)
    assert renewed.renewal_reminded_at is None  # new period, fresh reminder cycle
    assert result["membership"]["end_date"] == renewed.end_date.isoformat()
    assert db.query(Reminder).count() == 0  # last cycle's reminders cleared
    assert db.get(User, user.id).role == "member"  # never demoted or re-promoted


def test_ledger_and_membership_stay_consistent_across_two_purchases(client, db, make_user, make_plan, login, auth):
    """Money must reconcile: two paid orders == two ledger rows == two plans' worth."""
    user = make_user("twice@ssa.org", role="member")
    basic = make_plan(name="Basic", price=50000, duration_months=6)
    premium = make_plan(name="Premium", price=150000, duration_months=12)
    token = login("twice@ssa.org")

    buy_membership(client, auth, token, str(basic.id))
    db.expire_all()
    first_end = db.query(Membership).one().end_date
    buy_membership(client, auth, token, str(premium.id))

    db.expire_all()
    ledger = db.query(Transaction).order_by(Transaction.amount).all()
    assert [t.amount for t in ledger] == [50000, 150000]
    assert all(t.direction == "in" and t.source == "dues" for t in ledger)
    membership = db.query(Membership).filter_by(user_id=user.id).one()
    assert membership.start_date == first_end  # extended, not restarted
    assert membership.plan_id == premium.id


def test_confirm_requires_owner_or_admin(client, db, make_user, make_plan, login, auth):
    make_user("buyer@ssa.org", role="guest")
    make_user("nosy@ssa.org", role="member")
    make_user("admin@ssa.org", role="admin")
    plan = make_plan()
    order_id = client.post(
        "/api/v1/memberships/checkout", json={"plan_id": str(plan.id)}, headers=auth(login("buyer@ssa.org"))
    ).json()["order_id"]

    denied = client.post(
        f"/api/v1/payments/{order_id}/mock-confirm", json={"outcome": "success"}, headers=auth(login("nosy@ssa.org"))
    )
    assert denied.status_code == 403
    assert db.query(Transaction).count() == 0

    allowed = client.post(
        f"/api/v1/payments/{order_id}/mock-confirm", json={"outcome": "success"}, headers=auth(login("admin@ssa.org"))
    )
    assert allowed.status_code == 200
    assert allowed.json()["order_status"] == "paid"


def test_confirm_unknown_order_is_404(client, make_user, login, auth):
    make_user("buyer@ssa.org", role="guest")
    response = client.post(
        "/api/v1/payments/00000000-0000-0000-0000-000000000000/mock-confirm",
        json={"outcome": "success"},
        headers=auth(login("buyer@ssa.org")),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ORDER_NOT_FOUND"


# --- verification (FR-1.6) --------------------------------------------------------
def test_verify_active_member(client, db, make_user, make_plan, login, auth):
    make_user("vol@ssa.org", role="volunteer")  # exists so the volunteer can log in
    member = make_user("active@ssa.org", role="member")
    member.member_code = "SSA-2026-0001"
    plan = make_plan()
    db.add(
        Membership(
            user_id=member.id,
            plan_id=plan.id,
            status="active",
            start_date=date.today(),
            end_date=date.today() + timedelta(days=100),
        )
    )
    db.commit()

    response = client.get("/api/v1/members/verify?code=SSA-2026-0001", headers=auth(login("vol@ssa.org")))
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["status"] == "active"
    assert body["name"] == member.full_name
    assert body["member_code"] == "SSA-2026-0001"
    assert body["reason"] is None


def test_verify_expired_member(client, db, make_user, make_plan, login, auth):
    make_user("vol@ssa.org", role="volunteer")
    member = make_user("lapsed@ssa.org", role="member")
    member.member_code = "SSA-2026-0002"
    plan = make_plan()
    end = date.today() - timedelta(days=3)
    db.add(
        Membership(
            user_id=member.id, plan_id=plan.id, status="expired", start_date=end - timedelta(days=365), end_date=end
        )
    )
    db.commit()

    body = client.get("/api/v1/members/verify?code=SSA-2026-0002", headers=auth(login("vol@ssa.org"))).json()
    assert body["valid"] is False
    assert body["status"] == "expired"
    assert "expired" in body["reason"].lower()


def test_verify_unknown_code(client, make_user, login, auth):
    make_user("vol@ssa.org", role="volunteer")
    body = client.get("/api/v1/members/verify?code=SSA-2026-7777", headers=auth(login("vol@ssa.org"))).json()
    assert body["valid"] is False
    assert body["status"] == "none"
    assert body["reason"] == "No member found"


def test_verify_by_name_search(client, db, make_user, make_plan, login, auth):
    make_user("vol@ssa.org", role="volunteer")
    member = make_user("priya@ssa.org", role="member", full_name="Priya Sharma")
    member.member_code = "SSA-2026-0003"
    plan = make_plan()
    db.add(
        Membership(
            user_id=member.id,
            plan_id=plan.id,
            status="active",
            start_date=date.today(),
            end_date=date.today() + timedelta(days=10),
        )
    )
    db.commit()
    token = login("vol@ssa.org")

    found = client.get("/api/v1/members/verify?q=Sharma", headers=auth(token)).json()
    assert found["member_code"] == "SSA-2026-0003"
    assert found["valid"] is True

    make_user("priya.two@ssa.org", role="member", full_name="Priya Nair")
    ambiguous = client.get("/api/v1/members/verify?q=Priya", headers=auth(token))
    assert ambiguous.status_code == 409
    assert ambiguous.json()["error"]["code"] == "AMBIGUOUS_QUERY"


def test_verify_needs_a_query(client, make_user, login, auth):
    make_user("vol@ssa.org", role="volunteer")
    response = client.get("/api/v1/members/verify", headers=auth(login("vol@ssa.org")))
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "MISSING_QUERY"


def test_member_card(client, db, make_user, make_plan, login, auth):
    member = make_user("card@ssa.org", role="member", full_name="Card Holder")
    member.member_code = "SSA-2026-0004"
    plan = make_plan()
    end = date.today() + timedelta(days=200)
    db.add(Membership(user_id=member.id, plan_id=plan.id, status="active", start_date=date.today(), end_date=end))
    db.commit()

    token = login("card@ssa.org")
    card = client.get("/api/v1/members/me/card", headers=auth(token))
    assert card.status_code == 200
    assert card.json() == {
        "member_code": "SSA-2026-0004",
        "full_name": "Card Holder",
        "status": "active",
        "valid_until": end.isoformat(),
    }


def test_guest_cannot_get_member_card(client, make_user, login, auth):
    make_user("guest@ssa.org", role="guest")
    response = client.get("/api/v1/members/me/card", headers=auth(login("guest@ssa.org")))
    assert response.status_code == 403


# --- admin listings ---------------------------------------------------------------
def test_memberships_me_before_purchase_is_404(client, make_user, login, auth):
    make_user("nobody@ssa.org", role="member")
    response = client.get("/api/v1/memberships/me", headers=auth(login("nobody@ssa.org")))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "MEMBERSHIP_NOT_FOUND"


def test_memberships_me_after_purchase(client, db, make_user, make_plan, login, auth):
    make_user("buyer@ssa.org", role="guest")
    plan = make_plan(name="Premium", price=150000)
    token = login("buyer@ssa.org")
    buy_membership(client, auth, token, str(plan.id))

    body = client.get("/api/v1/memberships/me", headers=auth(token)).json()
    assert body["status"] == "active"
    assert body["plan_name"] == "Premium"
    assert date.fromisoformat(body["end_date"]) == plus_one_year(date.today())
    assert body["days_left"] == (plus_one_year(date.today()) - date.today()).days
    assert body["member_code"].startswith("SSA-")


def test_renewals_due_lists_only_the_next_30_days(client, db, make_user, make_plan, login, auth):
    make_user("admin@ssa.org", role="admin")
    plan = make_plan()
    soon = make_user("soon@ssa.org", role="member")
    later = make_user("later@ssa.org", role="member")
    db.add(
        Membership(
            user_id=soon.id,
            plan_id=plan.id,
            status="active",
            start_date=date.today(),
            end_date=date.today() + timedelta(days=10),
        )
    )
    db.add(
        Membership(
            user_id=later.id,
            plan_id=plan.id,
            status="active",
            start_date=date.today(),
            end_date=date.today() + timedelta(days=45),
        )
    )
    db.add(
        Membership(
            user_id=make_user("gone@ssa.org", role="member").id,
            plan_id=plan.id,
            status="expired",
            start_date=date.today() - timedelta(days=400),
            end_date=date.today() - timedelta(days=35),
        )
    )
    db.commit()

    body = client.get("/api/v1/memberships/renewals-due", headers=auth(login("admin@ssa.org"))).json()
    assert body["total"] == 1
    assert body["items"][0]["user_email"] == "soon@ssa.org"
    assert body["items"][0]["days_left"] == 10


def test_memberships_list_filters(client, db, make_user, make_plan, login, auth):
    make_user("admin@ssa.org", role="admin")
    plan = make_plan()
    for index, days in enumerate((10, 200)):
        user = make_user(f"m{index}@ssa.org", role="member")
        db.add(
            Membership(
                user_id=user.id,
                plan_id=plan.id,
                status="active",
                start_date=date.today(),
                end_date=date.today() + timedelta(days=days),
            )
        )
    db.commit()
    token = login("admin@ssa.org")

    assert client.get("/api/v1/memberships", headers=auth(token)).json()["total"] == 2
    filtered = client.get("/api/v1/memberships?expiring_within_days=30", headers=auth(token)).json()
    assert filtered["total"] == 1
    assert filtered["items"][0]["days_left"] == 10


def test_plans_public_list_shows_active_only(client, db, make_user, login, auth):
    make_user("admin@ssa.org", role="admin")
    token = login("admin@ssa.org")
    client.post("/api/v1/plans", json={"name": "Basic", "price": 50000, "duration_months": 12}, headers=auth(token))
    client.post(
        "/api/v1/plans",
        json={"name": "Retired", "price": 1000, "duration_months": 1, "is_active": False},
        headers=auth(token),
    )

    public = client.get("/api/v1/plans")  # no auth: public
    assert public.status_code == 200
    names = [plan["name"] for plan in public.json()["items"]]
    assert names == ["Basic"]
    assert public.json()["items"][0]["price"] == 50000

    duplicate = client.post("/api/v1/plans", json={"name": "Basic", "price": 1}, headers=auth(token))
    assert duplicate.status_code == 409

    plan_id = public.json()["items"][0]["id"]
    patched = client.patch(
        f"/api/v1/plans/{plan_id}", json={"price": 60000, "merch_discount_pct": 10}, headers=auth(token)
    )
    assert patched.status_code == 200
    assert patched.json()["price"] == 60000
    assert patched.json()["merch_discount_pct"] == 10
