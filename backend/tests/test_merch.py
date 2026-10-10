"""Merchandise: pricing, stock, checkout, fulfilment and the money trail (DESIGN.md §4 rules 1, 12-13)."""

import threading
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import func, select, text

from app.core.config import settings
from app.core.errors import AppError
from app.models import (
    MembershipPlan,
    MerchOrder,
    Order,
    ProductVariant,
    StockMovement,
    Transaction,
    User,
)
from app.services import merch as merch_service
from app.services.pricing import discounted, resolve_merch_unit_price
from tests.conftest import TestingSession

HOODIE = 99900  # base price in paise, as seeded
TSHIRT = 49900


# --- helpers ----------------------------------------------------------------------
def make_product(db, actor, *, name="SSA Hoodie", base_price=HOODIE, pct=10, sizes=(("M", 10),), active=True):
    product = merch_service.create_product(
        db, {"name": name, "base_price": base_price, "member_discount_pct": pct, "is_active": active}
    )
    slug = name.upper().replace(" ", "-")
    variants = {
        size: merch_service.create_variant(
            db, product, {"size": size, "sku": f"{slug}-{size}", "stock": stock}, actor
        )
        for size, stock in sizes
    }
    return product, variants


@pytest.fixture
def admin_user(make_user):
    return make_user("admin@ssa.org", role="admin")


@pytest.fixture
def admin_headers(admin_user, login, auth):
    return auth(login(admin_user.email))


@pytest.fixture
def shop(db, admin_user):
    """One hoodie in three states: 10 in stock, 2 low, 0 gone."""
    product, variants = make_product(db, admin_user, sizes=(("S", 2), ("M", 10), ("L", 0)))
    return product, variants


@pytest.fixture
def buyer(db, make_user, make_membership):
    def _make(email="buyer@ssa.org", *, member=True):
        user = make_user(email)
        if member:
            make_membership(user)
        return user

    return _make


def _checkout(client, auth, token, variant_ids, qtys=None, **extra):
    qtys = qtys or [1] * len(variant_ids)
    headers = auth(token)
    if extra.get("idempotency_key"):
        headers["Idempotency-Key"] = extra.pop("idempotency_key")
    body = {"items": [{"variant_id": str(v), "qty": q} for v, q in zip(variant_ids, qtys, strict=True)]}
    body.update(extra)
    return client.post("/api/v1/orders/merch/checkout", json=body, headers=headers)


def _stock(db, variant_id) -> int:
    db.expire_all()
    return db.get(ProductVariant, variant_id).stock


def _movements(db, variant_id) -> list[StockMovement]:
    db.expire_all()
    return list(
        db.scalars(
            select(StockMovement)
            .where(StockMovement.variant_id == variant_id)
            .order_by(StockMovement.created_at, StockMovement.id)
        )
    )


def _confirm(client, auth, token, order_id, outcome="success"):
    return client.post(f"/api/v1/payments/{order_id}/mock-confirm", json={"outcome": outcome}, headers=auth(token))


def _assert_invariant(db, *variant_ids):
    """initial + every delta == stock, rebuilt from the audit trail alone (DESIGN.md §4 rule 12)."""
    for variant_id in variant_ids:
        moved = db.scalar(
            select(func.coalesce(func.sum(StockMovement.delta), 0)).where(StockMovement.variant_id == variant_id)
        )
        assert moved == _stock(db, variant_id)


def _product_row(client, name, headers=None) -> dict:
    listing = client.get("/api/v1/products", headers=headers).json()["items"]
    return next(p for p in listing if p["name"] == name)


# --- 1. pricing -------------------------------------------------------------------
def test_rounding_is_half_up_on_integer_paise():
    assert discounted(HOODIE, 10) == 89910  # 99900 - 9990, exact
    assert discounted(HOODIE, 15) == 84915
    assert discounted(TSHIRT, 15) == 42415
    assert discounted(101, 50) == 51, "50.5 paise rounds up, never down"
    assert isinstance(discounted(HOODIE, 15), int)


def test_the_better_of_product_and_plan_discount_wins(db, admin_user, make_user, make_membership):
    product, _ = make_product(db, admin_user, pct=10)
    member = make_user("member@ssa.org")
    make_membership(member)

    db.scalar(select(MembershipPlan)).merch_discount_pct = 15  # the plan beats the product
    db.commit()
    assert resolve_merch_unit_price(db, member, product) == (discounted(HOODIE, 15), 15, "plan")

    product.member_discount_pct = 25  # and now the product beats the plan
    db.commit()
    assert resolve_merch_unit_price(db, member, product) == (discounted(HOODIE, 25), 25, "product")


def test_lapsed_member_and_staff_role_pay_list_price(db, admin_user, make_user, make_membership):
    product, _ = make_product(db, admin_user, pct=10)
    lapsed = make_user("lapsed@ssa.org")
    make_membership(lapsed, status="expired", days_left=-10)
    organizer = make_user("organizer@ssa.org", role="organizer")
    make_membership(organizer, days_left=-1)  # still "active" in the row, but the end date is past

    for user in (lapsed, organizer, make_user("plain@ssa.org")):
        assert resolve_merch_unit_price(db, user, product) == (HOODIE, 0, "none")


def test_no_discount_anywhere_still_prices_at_base(db, admin_user, make_user, make_membership):
    product, _ = make_product(db, admin_user, pct=0)
    member = make_user("member@ssa.org")
    make_membership(member)

    assert resolve_merch_unit_price(db, member, product) == (HOODIE, 0, "none")


def test_price_for_you_matches_what_checkout_charges(client, auth, login, db, shop, buyer):
    _product, variants = shop
    member = buyer()
    token = login(member.email)

    listing = _product_row(client, "SSA Hoodie", auth(token))
    assert listing["price_for_you"] == discounted(HOODIE, 10)
    assert listing["is_member_price"] is True
    assert listing["price_range"] == {"min": discounted(HOODIE, 10), "max": discounted(HOODIE, 10)}

    checkout = _checkout(client, auth, token, [variants["M"].id]).json()
    assert checkout["items"][0]["unit_price"] == listing["price_for_you"]
    assert checkout["amount"] == listing["price_for_you"]
    assert checkout["subtotal"] == HOODIE
    assert checkout["discount"] == HOODIE - listing["price_for_you"]
    assert checkout["status"] == "pending" and checkout["expires_at"].endswith("Z")


# --- 2. oversell ------------------------------------------------------------------
def test_six_concurrent_buyers_never_oversell_three_units(db, admin_user, make_user, make_membership):
    """The conditional UPDATE is the lock: six real connections, one row, three units."""
    _product, variants = make_product(db, admin_user, sizes=(("M", 3),))
    variant_id = variants["M"].id
    buyers = [make_user(f"buyer{index}@ssa.org") for index in range(6)]
    for person in buyers:
        make_membership(person)

    results: list[str] = []
    lock = threading.Lock()

    def buy(person: User) -> None:
        session = TestingSession()
        try:
            order, _payment = merch_service.create_merch_checkout(
                session, session.get(User, person.id), [{"variant_id": variant_id, "qty": 1}]
            )
            with lock:
                results.append(f"ok:{order.id}")
        except AppError as exc:
            with lock:
                results.append(exc.code)
        finally:
            session.close()

    threads = [threading.Thread(target=buy, args=(person,)) for person in buyers]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert len(results) == 6
    assert sum(1 for result in results if result.startswith("ok:")) == 3
    assert results.count("OUT_OF_STOCK") == 3
    assert _stock(db, variant_id) == 0
    assert db.scalar(select(func.count()).select_from(Order)) == 3
    _assert_invariant(db, variant_id)


def test_a_line_bigger_than_stock_is_rejected(client, auth, login, db, shop, buyer):
    _product, variants = shop
    token = login(buyer().email)

    response = _checkout(client, auth, token, [variants["S"].id], [3])  # S holds 2

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "OUT_OF_STOCK"
    assert response.json()["error"]["details"] == {
        "variant_id": str(variants["S"].id),
        "product_name": "SSA Hoodie",
        "size": "S",
        "available": 2,
        "requested": 3,
    }
    assert _stock(db, variants["S"].id) == 2
    assert db.scalar(select(func.count()).select_from(Order)) == 0


# --- 3. multi-line atomicity ------------------------------------------------------
def test_one_bad_line_rolls_back_the_whole_order(client, auth, login, db, shop, buyer):
    _product, variants = shop
    token = login(buyer().email)

    response = _checkout(client, auth, token, [variants["M"].id, variants["L"].id], [2, 1])

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "OUT_OF_STOCK"
    assert _stock(db, variants["M"].id) == 10, "the good line's stock came back with the bad one"
    assert db.scalar(select(func.count()).select_from(Order)) == 0
    assert db.scalar(select(func.count()).select_from(StockMovement).where(StockMovement.reason == "sale")) == 0
    _assert_invariant(db, variants["M"].id, variants["L"].id)


# --- 4. checkout validation -------------------------------------------------------
def test_quantity_and_line_limits(client, auth, login, db, shop, buyer):
    _product, variants = shop
    token = login(buyer().email)

    assert _checkout(client, auth, token, [variants["M"].id], [0]).status_code == 422
    assert _checkout(client, auth, token, [variants["M"].id], [6]).status_code == 422
    duplicated = _checkout(client, auth, token, [variants["M"].id, variants["M"].id], [1, 1])
    assert duplicated.status_code == 422
    assert duplicated.json()["error"]["code"] == "DUPLICATE_VARIANT"

    six_lines = _checkout(client, auth, token, [variants["M"].id] * 6, [1] * 6)
    assert six_lines.status_code == 422, "six lines is over the limit whatever the variants are"

    assert db.scalar(select(func.count()).select_from(Order)) == 0
    assert _stock(db, variants["M"].id) == 10


def test_unknown_and_unavailable_variants(client, auth, login, db, admin_user, buyer):
    _product, active_variants = make_product(db, admin_user, name="SSA Hoodie")
    _retired, retired_variants = make_product(db, admin_user, name="Old Mug", sizes=(("ONE", 3),), active=False)
    hidden = make_product(db, admin_user, name="SSA Cap", sizes=(("M", 3),))[1]["M"]
    merch_service.update_variant(db, hidden, {"is_active": False})
    token = login(buyer().email)

    missing = _checkout(client, auth, token, ["3f1a2b4c-0000-4000-8000-000000000004"])
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "VARIANT_NOT_FOUND"

    for variant in (retired_variants["ONE"], hidden):
        response = _checkout(client, auth, token, [variant.id])
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "PRODUCT_UNAVAILABLE"

    assert _checkout(client, auth, token, [active_variants["M"].id]).status_code == 201


def test_delivery_rules(client, auth, login, shop, buyer):
    _product, variants = shop
    token = login(buyer().email)

    missing_note = _checkout(client, auth, token, [variants["M"].id], delivery_method="campus_delivery")
    assert missing_note.status_code == 422
    assert missing_note.json()["error"]["code"] == "DELIVERY_NOTE_REQUIRED"

    short_note = _checkout(
        client, auth, token, [variants["M"].id], delivery_method="campus_delivery", delivery_note="B-2"
    )
    assert short_note.status_code == 422

    delivered = _checkout(
        client,
        auth,
        token,
        [variants["M"].id],
        delivery_method="campus_delivery",
        delivery_note="Hostel B, room 214",
    )
    assert delivered.status_code == 201
    assert delivered.json()["delivery_method"] == "campus_delivery"
    assert _checkout(client, auth, token, [variants["M"].id]).json()["delivery_method"] == "pickup"


def test_checkout_needs_a_token_and_a_membership(client, auth, login, db, shop, buyer, monkeypatch):
    _product, variants = shop
    body = {"items": [{"variant_id": str(variants["M"].id), "qty": 1}]}

    assert client.post("/api/v1/orders/merch/checkout", json=body).status_code == 401

    outsider = buyer("outsider@ssa.org", member=False)
    token = login(outsider.email)
    refused = _checkout(client, auth, token, [variants["M"].id])
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "MEMBERSHIP_REQUIRED"
    assert _stock(db, variants["M"].id) == 10

    monkeypatch.setattr(settings, "MERCH_MEMBERS_ONLY", False)  # the same outsider now buys at list price
    allowed = _checkout(client, auth, token, [variants["M"].id])
    assert allowed.status_code == 201
    assert allowed.json()["amount"] == HOODIE
    assert allowed.json()["discount"] == 0


# --- 5. idempotency ---------------------------------------------------------------
def test_same_idempotency_key_reserves_stock_once(client, auth, login, db, shop, buyer):
    _product, variants = shop
    token = login(buyer().email)

    first = _checkout(client, auth, token, [variants["M"].id], [2], idempotency_key="cap-key-1")
    second = _checkout(client, auth, token, [variants["M"].id], [2], idempotency_key="cap-key-1")

    assert first.status_code == second.status_code == 201
    assert first.json()["order_id"] == second.json()["order_id"]
    assert db.scalar(select(func.count()).select_from(Order)) == 1
    assert _stock(db, variants["M"].id) == 8, "the replay must not reserve a second time"
    assert db.scalar(select(func.count()).select_from(StockMovement).where(StockMovement.reason == "sale")) == 1


# --- 6. payment success -----------------------------------------------------------
def test_payment_success_writes_one_fulfilment_row_and_one_ledger_row(client, auth, login, db, shop, buyer):
    _product, variants = shop
    member = buyer()
    token = login(member.email)
    order_id = _checkout(client, auth, token, [variants["M"].id], [2]).json()["order_id"]

    body = _confirm(client, auth, token, order_id).json()

    assert (body["order_status"], body["payment_status"]) == ("paid", "succeeded")
    assert body["merch"]["fulfilment_status"] == "paid"
    assert body["merch"]["delivery_method"] == "pickup"
    fulfilment = db.get(MerchOrder, UUID(order_id))
    assert (fulfilment.fulfilment_status, fulfilment.packed_at, fulfilment.handed_over_at) == ("paid", None, None)

    order = db.get(Order, UUID(order_id))
    ledger_rows = list(db.scalars(select(Transaction).where(Transaction.source == "merch")))
    assert len(ledger_rows) == 1
    assert (ledger_rows[0].direction, ledger_rows[0].amount) == ("in", order.total)
    assert (ledger_rows[0].ref_type, ledger_rows[0].ref_id) == ("order", order.id)
    assert _stock(db, variants["M"].id) == 8, "stock was reserved at checkout, not at payment"

    again = _confirm(client, auth, token, order_id)
    assert again.status_code == 200
    assert again.json()["order_status"] == "paid"
    assert db.scalar(select(func.count()).select_from(MerchOrder)) == 1
    assert db.scalar(select(func.count()).select_from(Transaction).where(Transaction.source == "merch")) == 1
    assert _stock(db, variants["M"].id) == 8
    _assert_invariant(db, variants["M"].id)


# --- 7. failure and expiry --------------------------------------------------------
def test_failed_payment_releases_stock_once(client, auth, login, db, shop, buyer):
    _product, variants = shop
    token = login(buyer().email)
    order_id = _checkout(client, auth, token, [variants["M"].id], [3]).json()["order_id"]
    assert _stock(db, variants["M"].id) == 7

    body = _confirm(client, auth, token, order_id, outcome="fail").json()

    assert (body["order_status"], body["payment_status"]) == ("failed", "failed")
    assert body["merch"] is None, "no fulfilment row for an order that was never paid"
    assert _stock(db, variants["M"].id) == 10

    _confirm(client, auth, token, order_id, outcome="fail")
    assert _stock(db, variants["M"].id) == 10, "a repeated failure releases nothing further"
    assert db.scalar(select(func.count()).select_from(StockMovement).where(StockMovement.reason == "release")) == 1
    _assert_invariant(db, variants["M"].id)


def test_expired_checkout_is_cancelled_and_its_stock_returns(client, auth, login, db, shop, buyer):
    _product, variants = shop
    token = login(buyer().email)
    order_id = _checkout(client, auth, token, [variants["M"].id], [4]).json()["order_id"]
    assert _stock(db, variants["M"].id) == 6

    db.get(Order, UUID(order_id)).created_at = datetime.now(UTC) - timedelta(minutes=20)
    db.commit()

    assert merch_service.release_expired_pending_merch_orders(db) == {"cancelled": 1, "released": 1}
    assert db.get(Order, UUID(order_id)).status == "cancelled"
    assert _stock(db, variants["M"].id) == 10
    _assert_invariant(db, variants["M"].id)

    assert merch_service.release_expired_pending_merch_orders(db) == {"cancelled": 0, "released": 0}, "never twice"
    assert _stock(db, variants["M"].id) == 10

    refused = _confirm(client, auth, token, order_id)
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "ORDER_NOT_PAYABLE"
    assert _stock(db, variants["M"].id) == 10


def test_a_fresh_checkout_is_not_swept(client, auth, login, db, shop, buyer):
    _product, variants = shop
    token = login(buyer().email)
    _checkout(client, auth, token, [variants["M"].id])

    assert merch_service.release_expired_pending_merch_orders(db) == {"cancelled": 0, "released": 0}
    assert _stock(db, variants["M"].id) == 9


# --- 8. the stock invariant -------------------------------------------------------
def test_invariant_holds_through_a_mixed_scenario(client, auth, login, db, shop, buyer, admin_headers):
    _product, variants = shop
    hoodie = variants["M"].id
    buyer_a, buyer_b = buyer("a@ssa.org"), buyer("b@ssa.org")
    token_a, token_b = login(buyer_a.email), login(buyer_b.email)

    # Every movement reason but initial: a sale, a failed payment, an expiry, a restock, a write-off.
    _checkout(client, auth, token_a, [hoodie], [2])
    paid = _checkout(client, auth, token_b, [hoodie], [1]).json()["order_id"]
    _confirm(client, auth, token_b, paid)
    failed = _checkout(client, auth, token_a, [hoodie], [3]).json()["order_id"]
    _confirm(client, auth, token_a, failed, outcome="fail")
    stranded = _checkout(client, auth, token_b, [hoodie], [1]).json()["order_id"]
    db.get(Order, UUID(stranded)).created_at = datetime.now(UTC) - timedelta(minutes=20)
    db.commit()
    merch_service.release_expired_pending_merch_orders(db)

    restocked = client.post(
        f"/api/v1/variants/{hoodie}/stock-adjust",
        json={"delta": 20, "reason": "restock", "note": "Supplier delivery"},
        headers=admin_headers,
    )
    assert restocked.json()["stock"] == 27

    refused = client.post(
        f"/api/v1/variants/{hoodie}/stock-adjust",
        json={"delta": -100, "reason": "adjustment", "note": "Stock take"},
        headers=admin_headers,
    )
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "NEGATIVE_STOCK"
    assert refused.json()["error"]["details"] == {"variant_id": str(hoodie), "stock": 27, "delta": -100}

    written_off = client.post(
        f"/api/v1/variants/{hoodie}/stock-adjust",
        json={"delta": -3, "reason": "adjustment", "note": "Damaged in the store room"},
        headers=admin_headers,
    )
    assert written_off.json()["stock"] == 24

    assert _stock(db, hoodie) == 24
    assert {row.reason for row in _movements(db, hoodie)} == {
        "initial",
        "sale",
        "release",
        "restock",
        "adjustment",
    }
    _assert_invariant(db, hoodie)


# --- 9. fulfilment transitions ----------------------------------------------------
def test_fulfilment_moves_one_step_and_records_who(client, auth, login, db, shop, buyer, admin_headers):
    _product, variants = shop
    token = login(buyer().email)
    order_id = _checkout(client, auth, token, [variants["M"].id]).json()["order_id"]
    _confirm(client, auth, token, order_id)

    def move(status):
        return client.patch(
            f"/api/v1/admin/merch/orders/{order_id}", json={"fulfilment_status": status}, headers=admin_headers
        )

    skipped = move("handed_over")
    assert skipped.status_code == 409
    assert skipped.json()["error"]["code"] == "INVALID_TRANSITION"
    assert skipped.json()["error"]["details"] == {"from": "paid", "to": "handed_over", "allowed": "packed"}

    packed = move("packed")
    assert packed.status_code == 200
    assert packed.json()["fulfilment_status"] == "packed"
    assert packed.json()["packed_at"] and packed.json()["handed_over_at"] is None

    assert move("paid").status_code == 409, "no going back"

    handed = move("handed_over")
    assert handed.status_code == 200 and handed.json()["handed_over_at"]
    assert move("handed_over").status_code == 409, "and no moving on from the last step"

    fulfilment = db.get(MerchOrder, UUID(order_id))
    assert fulfilment.handled_by == db.scalar(select(User.id).where(User.email == "admin@ssa.org"))
    assert fulfilment.packed_at <= fulfilment.handed_over_at


def test_unpaid_orders_have_no_fulfilment_row(client, auth, login, db, shop, buyer, admin_headers):
    _product, variants = shop
    token = login(buyer().email)
    order_id = _checkout(client, auth, token, [variants["M"].id]).json()["order_id"]

    response = client.patch(
        f"/api/v1/admin/merch/orders/{order_id}", json={"fulfilment_status": "packed"}, headers=admin_headers
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "MERCH_ORDER_NOT_FOUND"


# --- 10. visibility and role guards ----------------------------------------------
def test_shop_reads_are_public_and_retired_products_are_hidden(client, auth, login, db, admin_user, shop, buyer):
    _product, _variants = shop
    retired, _retired_variants = make_product(db, admin_user, name="Old Mug", sizes=(("ONE", 3),), active=False)

    guest = client.get("/api/v1/products").json()
    member = client.get("/api/v1/products", headers=auth(login(buyer().email))).json()
    staff = client.get("/api/v1/products?include_inactive=true", headers=auth(login(admin_user.email))).json()

    assert [p["name"] for p in guest["items"]] == ["SSA Hoodie"]
    assert guest["items"][0]["price_for_you"] is None, "no token, no price for you"
    assert guest["items"][0]["is_member_price"] is None
    assert member["items"][0]["price_for_you"] == discounted(HOODIE, 10)
    assert {p["name"] for p in staff["items"]} == {"SSA Hoodie", "Old Mug"}

    assert client.get(f"/api/v1/products/{retired.id}").status_code == 404
    assert client.get(f"/api/v1/products/{retired.id}", headers=auth(login(buyer("other@ssa.org").email))).status_code == 404
    assert client.get(
        f"/api/v1/products/{retired.id}", headers=auth(login(admin_user.email))
    ).status_code == 200


def test_stock_status_reflects_the_threshold(client, shop):
    _product, variants = shop

    listing = {v["size"]: v["stock_status"] for v in _product_row(client, "SSA Hoodie")["variants"]}
    assert listing == {"S": "low", "M": "in_stock", "L": "out_of_stock"}, "S holds 2 of a threshold of 5"
    assert client.get(f"/api/v1/products/{variants['M'].product_id}").json()["total_stock"] == 12


def test_staff_writes_need_admin(client, auth, login, db, shop, buyer, admin_headers):
    product, variants = shop
    member = auth(login(buyer().email))

    assert client.post("/api/v1/products", json={"name": "SSA Cap", "base_price": 39900}, headers=member).status_code == 403
    assert client.post(
        f"/api/v1/products/{product.id}/variants", json={"size": "XL", "sku": "SSA-HOOD-XL"}, headers=member
    ).status_code == 403
    assert client.post(
        f"/api/v1/variants/{variants['M'].id}/stock-adjust", json={"delta": 5, "reason": "restock"}, headers=member
    ).status_code == 403
    assert client.patch(f"/api/v1/variants/{variants['M'].id}", json={"sku": "X"}, headers=member).status_code == 403
    assert client.get("/api/v1/admin/merch/orders", headers=member).status_code == 403
    assert client.get("/api/v1/admin/merch/stock-summary", headers=member).status_code == 403
    assert client.get(f"/api/v1/variants/{variants['M'].id}/stock-movements", headers=member).status_code == 403
    assert client.get("/api/v1/products?include_inactive=true", headers=member).status_code == 403

    created = client.post(
        "/api/v1/products",
        json={"name": "SSA Cap", "base_price": 39900, "member_discount_pct": 5},
        headers=admin_headers,
    )
    assert created.status_code == 201
    variant = client.post(
        f"/api/v1/products/{created.json()['id']}/variants",
        json={"size": "M", "sku": "SSA-CAP-M", "stock": 4},
        headers=admin_headers,
    )
    assert variant.status_code == 201 and variant.json()["stock_status"] == "low"
    assert client.patch(
        f"/api/v1/variants/{variant.json()['id']}", json={"sku": "SSA-CAP-M2"}, headers=admin_headers
    ).status_code == 200

    taken = client.post(
        f"/api/v1/products/{created.json()['id']}/variants",
        json={"size": "M", "sku": "SSA-CAP-M3"},
        headers=admin_headers,
    )
    assert taken.status_code == 409 and taken.json()["error"]["code"] == "VARIANT_TAKEN"
    duplicate_sku = client.post(
        f"/api/v1/products/{created.json()['id']}/variants",
        json={"size": "L", "sku": "SSA-CAP-M2"},
        headers=admin_headers,
    )
    assert duplicate_sku.status_code == 409 and duplicate_sku.json()["error"]["code"] == "SKU_TAKEN"


def test_variant_creation_writes_the_opening_movement(client, db, admin_user, admin_headers):
    _product, variants = make_product(db, admin_user, name="SSA Cap", sizes=(("M", 7),))

    movements = client.get(f"/api/v1/variants/{variants['M'].id}/stock-movements", headers=admin_headers).json()
    assert movements["total"] == 1
    assert movements["items"][0]["reason"] == "initial"
    assert movements["items"][0]["delta"] == 7
    assert movements["items"][0]["created_by_name"] == "Admin"
    assert movements["items"][0]["order_id"] is None
    _assert_invariant(db, variants["M"].id)


# --- 11. the admin board and the stock summary -----------------------------------
def test_admin_board_filters_and_counts(client, auth, login, shop, buyer, admin_headers):
    product, variants = shop
    first, second = buyer("a@ssa.org"), buyer("b@ssa.org")
    first_order = _checkout(client, auth, login(first.email), [variants["M"].id]).json()["order_id"]
    _confirm(client, auth, login(first.email), first_order)
    second_order = _checkout(client, auth, login(second.email), [variants["M"].id], [2]).json()["order_id"]
    _confirm(client, auth, login(second.email), second_order)
    for step in ("packed", "handed_over"):
        client.patch(f"/api/v1/admin/merch/orders/{second_order}", json={"fulfilment_status": step}, headers=admin_headers)

    board = client.get("/api/v1/admin/merch/orders", headers=admin_headers).json()
    assert board["counts"] == {"paid": 1, "packed": 0, "handed_over": 1}
    assert board["items"]["total"] == 2
    newest = board["items"]["items"][0]
    assert newest["order_id"] == second_order, "newest first"
    assert newest["buyer"] == {"name": "B", "email": "b@ssa.org", "member_code": None, "phone": None}
    assert newest["items_summary"] == "SSA Hoodie (M) x2"
    assert newest["total"] == 2 * discounted(HOODIE, 10)
    assert newest["packed_at"] and newest["handed_over_at"] and newest["fulfilment_status"] == "handed_over"

    paid_only = client.get("/api/v1/admin/merch/orders?fulfilment_status=paid", headers=admin_headers).json()
    assert paid_only["items"]["total"] == 1
    assert paid_only["counts"]["handed_over"] == 1, "counts cover the whole board, not the filter"

    by_product = client.get(f"/api/v1/admin/merch/orders?product_id={product.id}", headers=admin_headers).json()
    assert by_product["items"]["total"] == 2
    assert client.get("/api/v1/admin/merch/orders?size=L", headers=admin_headers).json()["items"]["total"] == 0
    by_buyer = client.get("/api/v1/admin/merch/orders?q=a@ssa.org", headers=admin_headers).json()
    assert by_buyer["items"]["total"] == 1 and by_buyer["items"]["items"][0]["order_id"] == first_order


def test_stock_summary_counts_sales_and_reservations(client, auth, login, shop, buyer, admin_headers):
    _product, variants = shop
    token = login(buyer().email)
    paid = _checkout(client, auth, token, [variants["M"].id], [3]).json()["order_id"]
    _confirm(client, auth, token, paid)
    _checkout(client, auth, token, [variants["M"].id], [2])  # still pending: reserved, not sold

    summary = client.get("/api/v1/admin/merch/stock-summary", headers=admin_headers).json()

    hoodie = summary["products"][0]
    assert hoodie["name"] == "SSA Hoodie" and hoodie["is_active"] is True
    assert (hoodie["total_stock"], hoodie["sold_units"], hoodie["reserved_units"]) == (7, 3, 2)
    assert (hoodie["low_stock_count"], hoodie["out_of_stock_count"]) == (3, 1)

    by_size = {v["size"]: v for v in hoodie["variants"]}
    assert by_size["M"] == {
        "variant_id": str(variants["M"].id),
        "size": "M",
        "color": None,
        "sku": "SSA-HOODIE-M",
        "stock": 5,
        "sold_units": 3,
        "reserved_units": 2,
        "low_stock_threshold": 5,
        "low_stock": True,
        "out_of_stock": False,
    }
    assert by_size["L"]["out_of_stock"] is True and by_size["L"]["low_stock"] is True
    assert by_size["S"]["stock"] == 2 and (by_size["S"]["sold_units"], by_size["S"]["reserved_units"]) == (0, 0)

    demand = {d["size"]: d for d in summary["demand_by_size"]}
    assert demand["M"] == {"size": "M", "stock": 5, "sold_units": 3, "reserved_units": 2}
    assert [d["size"] for d in summary["demand_by_size"]] == ["S", "M", "L"], "apparel sizes come out in wear order"
    assert summary["totals"] == {"stock": 7, "sold_units": 3, "reserved_units": 2}


def test_order_history_shows_items_payment_and_fulfilment(client, auth, login, db, shop, buyer, admin_headers):
    _product, variants = shop
    member = buyer()
    token = login(member.email)
    order_id = _checkout(client, auth, token, [variants["M"].id], [2]).json()["order_id"]
    _confirm(client, auth, token, order_id)

    one = client.get(f"/api/v1/orders/{order_id}", headers=auth(token)).json()
    assert (one["kind"], one["status"], one["payment_status"], one["fulfilment_status"]) == (
        "merch",
        "paid",
        "succeeded",
        "paid",
    )
    assert one["items"] == [
        {
            "item_type": "variant",
            "name": "SSA Hoodie (M)",
            "quantity": 2,
            "unit_price": discounted(HOODIE, 10),
            "line_total": 2 * discounted(HOODIE, 10),
        }
    ]

    listing = client.get("/api/v1/orders/me", headers=auth(token)).json()
    assert [row["id"] for row in listing["items"]] == [order_id]
    assert client.get("/api/v1/orders/me?kind=ticket", headers=auth(token)).json()["total"] == 0
    assert client.get(f"/api/v1/orders/{order_id}", headers=admin_headers).status_code == 200

    outsider = _checkout(client, auth, login(buyer("other@ssa.org").email), [variants["M"].id]).json()["order_id"]
    assert client.get(f"/api/v1/orders/{outsider}", headers=auth(token)).status_code == 404
    assert client.get(f"/api/v1/orders/{order_id}").status_code == 401


def test_a_membership_or_ticket_order_still_reads_back(client, auth, login, make_user, make_plan):
    """Phase 4 owns the order history, so the earlier phases' orders must still show up in it."""
    plan = make_plan()
    token = login(make_user("joiner@ssa.org").email)
    checkout = client.post("/api/v1/memberships/checkout", json={"plan_id": str(plan.id)}, headers=auth(token))
    order_id = checkout.json()["order_id"]
    client.post(f"/api/v1/payments/{order_id}/mock-confirm", json={"outcome": "success"}, headers=auth(token))

    rows = client.get("/api/v1/orders/me", headers=auth(token)).json()["items"]
    assert [row["kind"] for row in rows] == ["membership"]
    assert rows[0]["items"][0]["name"] == plan.name
    assert rows[0]["fulfilment_status"] is None, "memberships have no fulfilment"


# --- 12. RLS ----------------------------------------------------------------------
def test_every_new_table_has_rls_enabled(db):
    rows = db.execute(
        text(
            "select tablename, rowsecurity from pg_tables "
            "where schemaname = 'public' and tablename in "
            "('products', 'product_variants', 'stock_movements', 'merch_orders')"
        )
    ).all()
    assert len(rows) == 4
    assert all(enabled for _table, enabled in rows), "Supabase would publish these over REST without RLS"
