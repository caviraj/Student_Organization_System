"""Real payments (M2-P1): the Razorpay provider, its webhook, and the guard that stops a
simulated outcome from settling an order on a live deployment.

No test here touches api.razorpay.com. `create_intent` is stubbed at the httpx call; everything
from the checkout transaction down is the real code path.
"""

import hashlib
import hmac
import json

import httpx
import pytest

from app.core.config import Settings, settings
from app.models import Membership, Order, Payment, Transaction, User
from app.services import payments

KEY_ID = "rzp_test_ssa_hub"
KEY_SECRET = "key-secret-only-for-tests"
WEBHOOK_SECRET = "webhook-secret-only-for-tests"
GATEWAY_ORDER_ID = "order_TESTorder123"
GATEWAY_PAYMENT_ID = "pay_TESTpayment123"


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


@pytest.fixture
def gateway(monkeypatch):
    """Razorpay configured, with the network call captured instead of sent."""
    monkeypatch.setattr(settings, "PAYMENTS_PROVIDER", "razorpay")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", KEY_ID)
    monkeypatch.setattr(settings, "RAZORPAY_KEY_SECRET", KEY_SECRET)
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", WEBHOOK_SECRET)
    calls = []

    def fake_post(url, json=None, auth=None, timeout=None):
        calls.append({"url": url, "json": json, "auth": auth})
        return _FakeResponse({"id": GATEWAY_ORDER_ID, "status": "created", "amount": json["amount"]})

    monkeypatch.setattr(payments.httpx, "post", fake_post)
    return calls


def _webhook_body(event: dict) -> bytes:
    return json.dumps(event).encode()


def _sign(body: bytes, secret: str = WEBHOOK_SECRET) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _post_webhook(client, event: dict, signature: str | None = None, body: bytes | None = None):
    """Signature defaults to a valid one; pass "" to send none at all."""
    raw = body if body is not None else _webhook_body(event)
    headers = {"Content-Type": "application/json"}
    if signature is None:
        signature = _sign(raw)
    if signature:
        headers["X-Razorpay-Signature"] = signature
    return client.post("/api/v1/payments/webhook", content=raw, headers=headers)


def _captured_event(order_id: str = GATEWAY_ORDER_ID, payment_id: str = GATEWAY_PAYMENT_ID, amount: int = 50000):
    return {
        "entity": "event",
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {"id": payment_id, "order_id": order_id, "amount": amount, "status": "captured"}
            }
        },
    }


def _checkout(client, auth, token: str, plan_id: str) -> dict:
    response = client.post("/api/v1/memberships/checkout", json={"plan_id": plan_id}, headers=auth(token))
    assert response.status_code == 201, response.text
    return response.json()


def _membership_order(client, gateway, make_user, make_plan, login, auth, price: int = 50000) -> tuple[dict, str]:
    make_user("buyer@ssa.org", role="guest")
    plan = make_plan(price=price)
    token = login("buyer@ssa.org")
    return _checkout(client, auth, token, str(plan.id)), token


# --- creating an order at the gateway ---------------------------------------------


def test_checkout_creates_a_gateway_order_and_stores_its_id(client, db, gateway, make_user, make_plan, login, auth):
    body, _ = _membership_order(client, gateway, make_user, make_plan, login, auth, price=90000)

    assert len(gateway) == 1
    sent = gateway[0]
    assert sent["url"] == "https://api.razorpay.com/v1/orders"
    assert sent["auth"] == (KEY_ID, KEY_SECRET)
    assert sent["json"]["amount"] == 90000  # paise, straight through - never a float
    assert sent["json"]["currency"] == "INR"
    assert sent["json"]["receipt"] == body["order_id"]  # the club's own order id, for their dashboard

    payment = db.query(Payment).one()
    assert payment.provider == "razorpay"
    assert payment.provider_ref == GATEWAY_ORDER_ID  # every webhook carries this, so it is the key
    assert payment.status == "created"


def test_the_checkout_page_can_rehydrate_the_gateway_details(client, db, gateway, make_user, make_plan, login, auth):
    body, token = _membership_order(client, gateway, make_user, make_plan, login, auth)

    intent = client.get(f"/api/v1/payments/{body['order_id']}", headers=auth(token))
    assert intent.status_code == 200, intent.text
    assert intent.json() == {
        "order_id": body["order_id"],
        "kind": "membership",
        "order_status": "pending",
        "amount": 50000,
        "currency": "INR",
        "provider": "razorpay",
        "payment_status": "created",
        "key_id": KEY_ID,
        "gateway_order_id": GATEWAY_ORDER_ID,
    }


def test_another_member_cannot_read_someone_elses_intent(client, db, gateway, make_user, make_plan, login, auth):
    body, _ = _membership_order(client, gateway, make_user, make_plan, login, auth)
    make_user("nosy@ssa.org", role="member")

    response = client.get(f"/api/v1/payments/{body['order_id']}", headers=auth(login("nosy@ssa.org")))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


# --- the webhook ------------------------------------------------------------------


def test_a_signed_webhook_settles_the_order(client, db, gateway, make_user, make_plan, login, auth):
    body, _ = _membership_order(client, gateway, make_user, make_plan, login, auth)

    response = _post_webhook(client, _captured_event(amount=50000))
    assert response.status_code == 200, response.text
    assert response.json() == {"status": "processed", "order_id": body["order_id"]}

    db.expire_all()
    assert db.get(Order, body["order_id"]).status == "paid"
    assert db.query(Membership).one().status == "active"
    assert db.query(User).filter(User.email == "buyer@ssa.org").one().role == "member"
    assert db.query(Transaction).count() == 1  # the dues row, written exactly once
    assert db.query(Payment).one().status == "succeeded"


def test_a_replayed_webhook_settles_once(client, db, gateway, make_user, make_plan, login, auth):
    """Razorpay retries until it gets a 2xx. The retry must not mint a second membership."""
    _membership_order(client, gateway, make_user, make_plan, login, auth)
    first = _post_webhook(client, _captured_event(amount=50000))
    replay = _post_webhook(client, _captured_event(amount=50000))

    assert (first.status_code, replay.status_code) == (200, 200)
    assert replay.json()["status"] == "processed"

    db.expire_all()
    assert db.query(Membership).count() == 1
    assert db.query(Transaction).count() == 1
    assert db.query(Order).count() == 1


def test_both_event_types_for_one_payment_settle_once(client, db, gateway, make_user, make_plan, login, auth):
    """`order.paid` and `payment.captured` describe the same money; the second is a replay."""
    _membership_order(client, gateway, make_user, make_plan, login, auth)
    captured = _captured_event(amount=50000)
    paid = {
        "entity": "event",
        "event": "order.paid",
        "payload": {"order": {"entity": {"id": GATEWAY_ORDER_ID, "amount": 50000, "status": "paid"}}},
    }

    assert _post_webhook(client, captured).status_code == 200
    assert _post_webhook(client, paid).status_code == 200

    db.expire_all()
    assert db.query(Membership).count() == 1
    assert db.query(Transaction).count() == 1


def test_a_bad_signature_is_refused_and_settles_nothing(client, db, gateway, make_user, make_plan, login, auth):
    body, _ = _membership_order(client, gateway, make_user, make_plan, login, auth)

    response = _post_webhook(client, _captured_event(amount=50000), signature="0" * 64)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_SIGNATURE"
    db.expire_all()
    assert db.get(Order, body["order_id"]).status == "pending"
    assert db.query(Transaction).count() == 0


def test_a_body_swapped_after_signing_is_refused(client, db, gateway, make_user, make_plan, login, auth):
    """The signature covers the exact bytes, so an attacker cannot keep the signature and edit the
    amount - which is the whole reason the raw body is read before anything parses it."""
    _membership_order(client, gateway, make_user, make_plan, login, auth)
    signed = _webhook_body(_captured_event(amount=50000))
    signature = _sign(signed)
    tampered = _webhook_body(_captured_event(amount=1))

    response = _post_webhook(client, {}, signature=signature, body=tampered)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_SIGNATURE"
    db.expire_all()
    assert db.query(Transaction).count() == 0


def test_an_unsigned_webhook_is_refused(client, db, gateway, make_user, make_plan, login, auth):
    _membership_order(client, gateway, make_user, make_plan, login, auth)

    response = _post_webhook(client, _captured_event(amount=50000), signature="")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_SIGNATURE"


def test_an_amount_that_does_not_match_is_refused(client, db, gateway, make_user, make_plan, login, auth):
    body, _ = _membership_order(client, gateway, make_user, make_plan, login, auth)

    response = _post_webhook(client, _captured_event(amount=100))

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "AMOUNT_MISMATCH"
    db.expire_all()
    assert db.get(Order, body["order_id"]).status == "pending"


def test_a_failed_payment_marks_the_order_failed(client, db, gateway, make_user, make_plan, login, auth):
    body, _ = _membership_order(client, gateway, make_user, make_plan, login, auth)
    failed = {
        "entity": "event",
        "event": "payment.failed",
        "payload": {
            "payment": {
                "entity": {
                    "id": GATEWAY_PAYMENT_ID,
                    "order_id": GATEWAY_ORDER_ID,
                    "amount": 50000,
                    "status": "failed",
                    "error_description": "card declined",
                }
            }
        },
    }

    assert _post_webhook(client, failed).status_code == 200

    db.expire_all()
    assert db.get(Order, body["order_id"]).status == "failed"
    assert db.query(Payment).one().status == "failed"
    assert db.query(Membership).count() == 0


def test_an_event_we_do_not_act_on_is_acknowledged(client, db, gateway, make_user, make_plan, login, auth):
    """A 4xx would have Razorpay retry a no-op until it gives up."""
    _membership_order(client, gateway, make_user, make_plan, login, auth)

    response = _post_webhook(client, {"event": "payment.authorized", "payload": {}})

    assert response.status_code == 200
    assert response.json() == {"status": "ignored", "order_id": None}


def test_a_webhook_for_an_unknown_gateway_order_is_a_404(client, db, gateway):
    response = _post_webhook(client, _captured_event(order_id="order_NOTours"))

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PAYMENT_NOT_FOUND"


def test_the_gateway_payment_id_is_recorded_for_reconciliation(client, db, gateway, make_user, make_plan, login, auth):
    """Two successful payments against one order is the case a refund has to be raised for, so
    every id the gateway reports is kept."""
    _membership_order(client, gateway, make_user, make_plan, login, auth)
    _post_webhook(client, _captured_event(amount=50000))

    db.expire_all()
    payment = db.query(Payment).one()
    assert [p["id"] for p in payment.raw["payments"]] == [GATEWAY_PAYMENT_ID]
    assert payment.raw["payments"][0]["status"] == "captured"


# --- the Checkout widget's success callback ---------------------------------------


def _checkout_signature(order_id: str, payment_id: str, secret: str = KEY_SECRET) -> str:
    return hmac.new(secret.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()


def test_a_verified_callback_settles_the_order(client, db, gateway, make_user, make_plan, login, auth):
    body, token = _membership_order(client, gateway, make_user, make_plan, login, auth)

    response = client.post(
        f"/api/v1/payments/{body['order_id']}/verify",
        json={
            "razorpay_order_id": GATEWAY_ORDER_ID,
            "razorpay_payment_id": GATEWAY_PAYMENT_ID,
            "razorpay_signature": _checkout_signature(GATEWAY_ORDER_ID, GATEWAY_PAYMENT_ID),
        },
        headers=auth(token),
    )

    assert response.status_code == 200, response.text
    assert response.json()["order_status"] == "paid"
    db.expire_all()
    assert db.query(Membership).count() == 1
    assert db.query(Transaction).count() == 1


def test_a_forged_callback_signature_settles_nothing(client, db, gateway, make_user, make_plan, login, auth):
    """The signature is computed with the API key secret, which the browser never sees."""
    body, token = _membership_order(client, gateway, make_user, make_plan, login, auth)

    response = client.post(
        f"/api/v1/payments/{body['order_id']}/verify",
        json={
            "razorpay_order_id": GATEWAY_ORDER_ID,
            "razorpay_payment_id": GATEWAY_PAYMENT_ID,
            "razorpay_signature": _checkout_signature(GATEWAY_ORDER_ID, GATEWAY_PAYMENT_ID, secret="guessed"),
        },
        headers=auth(token),
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_SIGNATURE"
    db.expire_all()
    assert db.get(Order, body["order_id"]).status == "pending"


def test_a_callback_naming_another_order_is_refused(client, db, gateway, make_user, make_plan, login, auth):
    body, token = _membership_order(client, gateway, make_user, make_plan, login, auth)

    response = client.post(
        f"/api/v1/payments/{body['order_id']}/verify",
        json={
            "razorpay_order_id": "order_SOMEONEelse",
            "razorpay_payment_id": GATEWAY_PAYMENT_ID,
            "razorpay_signature": _checkout_signature("order_SOMEONEelse", GATEWAY_PAYMENT_ID),
        },
        headers=auth(token),
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "ORDER_MISMATCH"


def test_callback_and_webhook_together_settle_once(client, db, gateway, make_user, make_plan, login, auth):
    """The customer's browser and the gateway's webhook race by design. Both land on the same
    conditional claim, so the club gets one membership and one ledger row."""
    body, token = _membership_order(client, gateway, make_user, make_plan, login, auth)
    payload = {
        "razorpay_order_id": GATEWAY_ORDER_ID,
        "razorpay_payment_id": GATEWAY_PAYMENT_ID,
        "razorpay_signature": _checkout_signature(GATEWAY_ORDER_ID, GATEWAY_PAYMENT_ID),
    }

    verified = client.post(f"/api/v1/payments/{body['order_id']}/verify", json=payload, headers=auth(token))
    webhooked = _post_webhook(client, _captured_event(amount=50000))

    assert (verified.status_code, webhooked.status_code) == (200, 200)
    db.expire_all()
    assert db.query(Membership).count() == 1
    assert db.query(Transaction).count() == 1


# --- the guard that removes the demo mode -----------------------------------------


def test_a_simulated_outcome_cannot_settle_a_real_order(client, db, gateway, make_user, make_plan, login, auth):
    """The M1 endpoint asserts its own outcome. On a deployment taking real money that is a
    free-money endpoint, so it is refused - this is what makes PAYMENTS_PROVIDER a real switch."""
    body, token = _membership_order(client, gateway, make_user, make_plan, login, auth)

    response = client.post(
        f"/api/v1/payments/{body['order_id']}/mock-confirm", json={"outcome": "success"}, headers=auth(token)
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SIMULATED_PAYMENT_DISABLED"
    db.expire_all()
    assert db.get(Order, body["order_id"]).status == "pending"
    assert db.query(Membership).count() == 0


def test_verify_is_refused_for_a_mock_order(client, db, make_user, make_plan, login, auth):
    """The default provider for this suite is mock; a razorpay callback must not touch its orders."""
    make_user("buyer@ssa.org", role="guest")
    plan = make_plan(price=50000)
    token = login("buyer@ssa.org")
    body = _checkout(client, auth, token, str(plan.id))

    response = client.post(
        f"/api/v1/payments/{body['order_id']}/verify",
        json={
            "razorpay_order_id": "order_whatever",
            "razorpay_payment_id": GATEWAY_PAYMENT_ID,
            "razorpay_signature": "0" * 64,
        },
        headers=auth(token),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "NOT_A_GATEWAY_PAYMENT"


def test_a_gateway_outage_fails_the_checkout_without_creating_an_order(
    client, db, gateway, make_user, make_plan, login, auth, monkeypatch
):
    make_user("buyer@ssa.org", role="guest")
    plan = make_plan(price=50000)
    token = login("buyer@ssa.org")

    def dead_post(*args, **kwargs):
        raise httpx.ConnectTimeout("api.razorpay.com did not answer")

    monkeypatch.setattr(payments.httpx, "post", dead_post)

    response = client.post("/api/v1/memberships/checkout", json={"plan_id": str(plan.id)}, headers=auth(token))

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "PAYMENT_GATEWAY_UNREACHABLE"
    # The test override hands `get_db` a bare session, so the rollback production's generator does
    # on the way out has to be done by hand here - then nothing half-created is left to pay for.
    db.rollback()
    assert db.query(Order).count() == 0


# --- configuration ------------------------------------------------------------------


def _production(**overrides) -> Settings:
    base = {
        "APP_ENV": "production",
        "DEBUG": False,
        "JWT_SECRET": "a-real-production-secret-of-sufficient-length",
        "CORS_ORIGINS": "https://ssa-hub.example",
        "PAYMENTS_PROVIDER": "razorpay",
        "RAZORPAY_KEY_ID": "rzp_live_abc123",
        "RAZORPAY_KEY_SECRET": "live-secret",
        "RAZORPAY_WEBHOOK_SECRET": "live-webhook-secret",
    }
    return Settings(**{**base, **overrides})


def test_a_complete_razorpay_config_is_production_ready():
    assert _production().startup_problems() == []


def test_production_refuses_a_test_key():
    """A test key in production takes no money while looking live - the demo mode this change
    exists to delete. It must not be possible to ship by accident."""
    problems = _production(RAZORPAY_KEY_ID="rzp_test_abc123").startup_problems()

    assert any("TEST key" in problem for problem in problems)


def test_a_live_key_outside_production_is_a_warning():
    problems = Settings(APP_ENV="development", PAYMENTS_PROVIDER="razorpay", RAZORPAY_KEY_ID="rzp_live_abc123").startup_problems()

    assert any("LIVE key" in problem for problem in problems)


def test_razorpay_without_keys_names_every_missing_one():
    problems = _production(
        RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET="", RAZORPAY_WEBHOOK_SECRET=""
    ).startup_problems()

    assert [problem for problem in problems if "razorpay but" in problem] == [
        "PAYMENTS_PROVIDER=razorpay but RAZORPAY_KEY_ID is unset",
        "PAYMENTS_PROVIDER=razorpay but RAZORPAY_KEY_SECRET is unset",
        "PAYMENTS_PROVIDER=razorpay but RAZORPAY_WEBHOOK_SECRET is unset",
    ]


def test_the_mock_provider_needs_no_gateway_keys():
    assert Settings(APP_ENV="development", PAYMENTS_PROVIDER="mock", JWT_SECRET="x" * 32).startup_problems() == []


def test_enforce_startup_config_refuses_to_boot_production():
    with pytest.raises(RuntimeError, match="refusing to start"):
        _production(RAZORPAY_KEY_ID="rzp_test_abc123").enforce_startup_config()
