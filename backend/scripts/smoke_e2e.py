"""Drive a running SSA Hub server through one semester and print a PASS/FAIL table.

    uvicorn app.main:app &          # or the docker/uvicorn command of your choice
    python scripts/seed.py          # the demo accounts this script logs in as
    python scripts/smoke_e2e.py     # BASE_URL=http://localhost:8000 by default

`tests/test_e2e_semester.py` proves the same story in-process, where it can reach into the
database and compute its own expected numbers. This one proves a different thing: that the story
works over a real socket, against a server someone else started, through nothing but the documented
HTTP API. Between them, a failure is either a bug in the code or a bug in the contract - not an
artifact of the harness.

What it needs and what it leaves behind:

  * A reachable server and **seeded demo accounts** (`admin@`, `organizer@`, `treasurer@`,
    `volunteer@ssa.org`, password `Passw0rd!`). It logs in as those; it never touches the
    database, and it does not read any seeded row other than those four logins.
  * It creates its own uniquely-suffixed event, product, fundraiser and users, so running it twice
    does not collide with the first run - and does not disturb the demo data you seeded.

Exit code is 0 only when every step passed. The run stops at the first failure: later steps depend
on earlier ones (there is no check-in without a ticket), so continuing would report noise.
"""

import os
import time
from datetime import UTC, date, datetime, timedelta

import httpx

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000").rstrip("/")
PASSWORD = os.environ.get("DEMO_PASSWORD", "Passw0rd!")
API = "/api/v1"
TIMEOUT = 30.0

PLAN_PRICE = 90_000
MEMBER_TICKET = 100_000
NON_MEMBER_TICKET = 150_000
GALA_CAPACITY = 3
HOODIE_PRICE = 80_000
HOODIE_DISCOUNT_PCT = 10
MEMBER_HOODIE = HOODIE_PRICE * (100 - HOODIE_DISCOUNT_PCT) // 100
FUNDRAISER_GOAL = 500_000
FUNDRAISER_INCOME = 100_000
CLAIM_AMOUNT = 50_000

TODAY = date.today()
RUN = str(int(time.time()))


class Failed(Exception):
    """One step did not hold. Carries the line the table shows."""


def check(condition: bool, detail: str) -> None:
    if not condition:
        raise Failed(detail)


class Api:
    """A thin wrapper that refuses to return a body it did not expect.

    Every call names the status it wants. `expect=201` that returns 500 prints the server's error
    envelope instead of a KeyError three lines later, which is the difference between a five-second
    diagnosis and a ten-minute one.
    """

    def __init__(self, base: str) -> None:
        self.base = base

    def call(self, method: str, path: str, expect, token: str | None = None, **kw) -> dict:
        headers = dict(kw.pop("headers", {}))
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            response = httpx.request(method, f"{self.base}{path}", headers=headers, timeout=TIMEOUT, **kw)
        except httpx.HTTPError as error:
            raise Failed(f"cannot reach {self.base}: {error}") from error
        wanted = (expect,) if isinstance(expect, int) else tuple(expect)
        if response.status_code not in wanted:
            raise Failed(f"{method} {path} -> {response.status_code} (wanted {wanted}): {response.text[:300]}")
        return response.json() if response.content else {}

    def login(self, email: str) -> str:
        body = self.call("POST", f"{API}/auth/login", 200, json={"email": email, "password": PASSWORD})
        return body["access_token"]

    def register(self, email: str, full_name: str) -> str:
        body = self.call(
            "POST",
            f"{API}/auth/register",
            201,
            json={
                "email": email,
                "password": PASSWORD,
                "full_name": full_name,
                "phone": "9876500000",
                "department": "CSE",
                "year": 2,
            },
        )
        check(body["user"]["role"] == "guest", f"a new account should be a guest, got {body['user']['role']}")
        return body["access_token"]

    def confirm(self, order_id: str, token: str, outcome: str = "success") -> dict:
        return self.call("POST", f"{API}/payments/{order_id}/mock-confirm", 200, token, json={"outcome": outcome})


def png() -> bytes:
    """A 1x1 PNG: the receipt check reads the magic bytes."""
    return bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000a49444154789c6300010000050001a5f645400000000049454e44ae426082"
    )


def step_one(api: Api, ctx: dict) -> str:
    """A student joins and pays their dues."""
    member = api.register(f"smoke.member.{RUN}@ssa.org", "Smoke Member")
    me = api.call("GET", f"{API}/auth/me", 200, member)
    check(me["member_code"] is None, "a guest should not have a member code yet")
    check(me["membership"]["status"] == "none", f"a guest's membership should be none, got {me['membership']}")

    plans = api.call("GET", f"{API}/plans", 200)
    check(plans["items"], "the seed should have published at least one membership plan")
    plan = plans["items"][0]
    checkout = api.call("POST", f"{API}/memberships/checkout", 201, member, json={"plan_id": plan["id"]})
    check(checkout["amount"] == plan["price"], f"checkout charged {checkout['amount']}, plan costs {plan['price']}")

    done = api.confirm(checkout["order_id"], member)
    check(done["order_status"] == "paid", f"the order should be paid, got {done['order_status']}")
    check(done["membership"]["status"] == "active", "the membership should be active after payment")

    me = api.call("GET", f"{API}/auth/me", 200, member)
    check(me["role"] == "member", f"paying dues should promote a guest, role is {me['role']}")
    check(bool(me["member_code"]), "the member code should be issued on activation")

    ctx["member"] = member
    return f"{me['member_code']} on plan {plan['name']} ({plan['price'] // 100} INR)"


def step_two(api: Api, ctx: dict) -> str:
    """The organizer posts the event and announces it to the members."""
    organizer = api.login("organizer@ssa.org")
    now = datetime.now(UTC).replace(microsecond=0)
    event = api.call(
        "POST",
        f"{API}/events",
        201,
        organizer,
        json={
            "title": f"Gala Smoke {RUN}",
            "venue": "Main Auditorium",
            "starts_at": now.isoformat(),
            "ends_at": (now + timedelta(hours=4)).isoformat(),
        },
    )
    check(event["status"] == "draft", f"a new event is a draft, got {event['status']}")
    event_id = event["id"]

    published = api.call("PATCH", f"{API}/events/{event_id}", 200, organizer, json={"status": "published"})
    check(published["status"] == "published", "the event should be published")

    ticket_type = api.call(
        "POST",
        f"{API}/events/{event_id}/ticket-types",
        201,
        organizer,
        json={
            "name": "Balcony",
            "member_price": MEMBER_TICKET,
            "non_member_price": NON_MEMBER_TICKET,
            "capacity": GALA_CAPACITY,
        },
    )
    check(
        ticket_type["seats_left"] == GALA_CAPACITY, f"expected {GALA_CAPACITY} seats, got {ticket_type['seats_left']}"
    )

    announcement = api.call(
        "POST",
        f"{API}/announcements",
        201,
        organizer,
        json={
            "title": f"Gala tickets are live {RUN}",
            "body": "Three seats. Member price first, then it is everyone for themselves.",
            "category": "general",
            "audience": "members",
            "send_email": True,
        },
    )
    summary = announcement["delivery_summary"]
    check(summary["inapp_queued"] >= 1, f"nobody was queued for the in-app notice: {summary}")

    inbox = api.call("GET", f"{API}/announcements/{announcement['id']}/deliveries", 200, api.login("admin@ssa.org"))
    check(inbox["summary"]["inapp"]["sent"] >= 1, f"nothing was delivered in-app: {inbox['summary']}")
    check(inbox["summary"]["email"]["failed"] == 0, f"some announcement emails failed: {inbox['summary']['email']}")

    ctx.update(
        organizer=organizer,
        event_id=event_id,
        ticket_type_id=ticket_type["id"],
        announcement_id=announcement["id"],
    )
    return (
        f"Gala Smoke {RUN} published with {GALA_CAPACITY} seats; announcement queued "
        f"in-app {summary['inapp_queued']}, email {summary['email_queued']}, nothing failed"
    )


def step_three(api: Api, ctx: dict) -> dict:
    """Three seats, four buyers."""

    def buy(token: str, quantity: int = 1) -> dict:
        body = api.call(
            "POST",
            f"{API}/tickets/checkout",
            201,
            token,
            json={"ticket_type_id": ctx["ticket_type_id"], "quantity": quantity},
        )
        check(body["status"] == "pending", f"a paid ticket type should open a pending order, got {body['status']}")
        return api.confirm(body["order_id"], token)

    member_sale = buy(ctx["member"])
    (member_ticket,) = member_sale["tickets"]
    check(
        member_ticket["price_paid"] == MEMBER_TICKET,
        f"an active member should pay {MEMBER_TICKET}, paid {member_ticket['price_paid']}",
    )

    guest_a = api.register(f"smoke.guest.a.{RUN}@ssa.org", "Smoke Guest A")
    guest_a_sale = buy(guest_a)
    check(
        guest_a_sale["tickets"][0]["price_paid"] == NON_MEMBER_TICKET,
        f"without a membership the price is {NON_MEMBER_TICKET}, paid {guest_a_sale['tickets'][0]['price_paid']}",
    )

    guest_b = api.register(f"smoke.guest.b.{RUN}@ssa.org", "Smoke Guest B")
    buy(guest_b)

    guest_c = api.register(f"smoke.guest.c.{RUN}@ssa.org", "Smoke Guest C")
    refused = api.call(
        "POST",
        f"{API}/tickets/checkout",
        409,
        guest_c,
        json={"ticket_type_id": ctx["ticket_type_id"], "quantity": 1},
    )
    check(refused["error"]["code"] == "SOLD_OUT", f"the fourth buyer should be turned away, got {refused['error']}")
    check(refused["error"]["details"]["seats_left"] == 0, f"seats_left should be 0: {refused['error']['details']}")

    event = api.call("GET", f"{API}/events/{ctx['event_id']}", 200)
    (only_type,) = event["ticket_types"]
    check(
        only_type["sold_count"] == GALA_CAPACITY, f"sold_count is {only_type['sold_count']}, expected {GALA_CAPACITY}"
    )
    check(only_type["seats_left"] == 0, "the event should be full")

    ctx["ticket_code"] = member_ticket["code"]
    ctx["guest_a"] = guest_a
    return (
        f"sold {GALA_CAPACITY}/{GALA_CAPACITY}, member paid {MEMBER_TICKET // 100}, guests {NON_MEMBER_TICKET // 100}"
    )


def step_four(api: Api, ctx: dict) -> str:
    """The door: four outcomes and the event report."""
    volunteer = api.login("volunteer@ssa.org")

    def scan(code: str, event_id: str | None = None) -> dict:
        return api.call(
            "POST",
            f"{API}/checkin",
            200,
            volunteer,
            json={"event_id": event_id or ctx["event_id"], "code": code},
        )

    first = scan(ctx["ticket_code"])
    check(first["result"] == "VALID", f"a valid ticket should scan VALID, got {first['result']}: {first['message']}")
    check(first["holder_name"] == "Smoke Member", f"the scanner should name the holder, got {first['holder_name']}")
    check(first["checked_in"] == 1, f"the live counter should read 1, got {first['checked_in']}")
    check(first["sold"] == GALA_CAPACITY, f"the scanner header should read {GALA_CAPACITY} sold, got {first['sold']}")

    check(scan(ctx["ticket_code"])["result"] == "ALREADY_USED", "a second scan of the same ticket is not VALID")
    check(scan("NOT-A-REAL-CODE")["result"] == "INVALID", "a made-up code should be INVALID")

    organizer = ctx["organizer"]
    other = api.call(
        "POST",
        f"{API}/events",
        201,
        organizer,
        json={
            "title": f"Freshers Mixer Smoke {RUN}",
            "venue": "Quad",
            "starts_at": (datetime.now(UTC) + timedelta(days=20)).replace(microsecond=0).isoformat(),
            "ends_at": (datetime.now(UTC) + timedelta(days=20, hours=4)).replace(microsecond=0).isoformat(),
        },
    )
    api.call("PATCH", f"{API}/events/{other['id']}", 200, organizer, json={"status": "published"})
    wrong = scan(ctx["ticket_code"], other["id"])
    check(wrong["result"] == "WRONG_EVENT", f"a Gala ticket at the Mixer should be WRONG_EVENT, got {wrong['result']}")
    check(f"Gala Smoke {RUN}" in wrong["message"], f"the message should name the real event: {wrong['message']}")

    report = api.call("GET", f"{API}/events/{ctx['event_id']}/report", 200, organizer)
    check(report["tickets_sold"] == GALA_CAPACITY, f"tickets_sold is {report['tickets_sold']}")
    check(report["checked_in"] == 1, f"checked_in is {report['checked_in']}, expected 1")
    check(report["no_shows"] == GALA_CAPACITY - 1, f"no_shows is {report['no_shows']}, expected {GALA_CAPACITY - 1}")
    check(report["seats_left"] == 0, "the report should show a full house")
    check(
        report["revenue"]["total"] == MEMBER_TICKET + NON_MEMBER_TICKET * 2,
        f"ticket revenue is {report['revenue']}, expected {MEMBER_TICKET + NON_MEMBER_TICKET * 2}",
    )
    return f"VALID/ALREADY_USED/INVALID/WRONG_EVENT; sold {report['tickets_sold']}, in {report['checked_in']}, away {report['no_shows']}"


def step_five(api: Api, ctx: dict) -> str:
    """Merch, down to the last unit, then out of the door."""
    admin = api.login("admin@ssa.org")
    product = api.call(
        "POST",
        f"{API}/products",
        201,
        admin,
        json={"name": f"Smoke Hoodie {RUN}", "base_price": HOODIE_PRICE, "member_discount_pct": HOODIE_DISCOUNT_PCT},
    )
    variant = api.call(
        "POST",
        f"{API}/products/{product['id']}/variants",
        201,
        admin,
        json={"size": "M", "sku": f"SMOKE-{RUN}-M", "stock": 2},
    )
    variant_id = variant["id"]

    listed = api.call("GET", f"{API}/products/{product['id']}", 200, ctx["member"])
    check(
        listed["price_for_you"] == MEMBER_HOODIE, f"member price is {listed['price_for_you']}, expected {MEMBER_HOODIE}"
    )
    check(listed["is_member_price"] is True, "the member should be quoted the discounted price")

    order = api.call(
        "POST",
        f"{API}/orders/merch/checkout",
        201,
        ctx["member"],
        headers={"Idempotency-Key": f"smoke-merch-{RUN}-1"},
        json={"items": [{"variant_id": variant_id, "qty": 1}]},
    )
    check(order["subtotal"] == HOODIE_PRICE, f"subtotal {order['subtotal']} should be the list price")
    check(order["discount"] == HOODIE_PRICE - MEMBER_HOODIE, f"the discount should be {HOODIE_PRICE - MEMBER_HOODIE}")
    check(order["amount"] == MEMBER_HOODIE, f"the member pays {MEMBER_HOODIE}, got {order['amount']}")
    check(bool(order["expires_at"]), "an unpaid order should carry the reservation deadline")
    order_id = order["order_id"]

    too_many = api.call(
        "POST",
        f"{API}/orders/merch/checkout",
        409,
        ctx["member"],
        headers={"Idempotency-Key": f"smoke-merch-{RUN}-2"},
        json={"items": [{"variant_id": variant_id, "qty": 2}]},
    )
    check(too_many["error"]["code"] == "OUT_OF_STOCK", f"the second order should fail: {too_many['error']}")
    check(
        too_many["error"]["details"]["available"] == 1 and too_many["error"]["details"]["requested"] == 2,
        f"one unit is left, two were asked for: {too_many['error']['details']}",
    )

    paid = api.confirm(order_id, ctx["member"])
    check(paid["merch"]["fulfilment_status"] == "paid", f"a fresh order is 'paid', got {paid['merch']}")

    board = api.call("GET", f"{API}/admin/merch/orders", 200, admin)
    check(board["counts"]["paid"] >= 1, f"the packing board should show a paid order: {board['counts']}")

    skipped = api.call(
        "PATCH", f"{API}/admin/merch/orders/{order_id}", 409, admin, json={"fulfilment_status": "handed_over"}
    )
    check(skipped["error"]["code"] == "INVALID_TRANSITION", f"skipping packed should be refused: {skipped['error']}")
    check(skipped["error"]["details"]["allowed"] == "packed", f"only packed is next: {skipped['error']['details']}")

    for target in ("packed", "handed_over"):
        moved = api.call(
            "PATCH", f"{API}/admin/merch/orders/{order_id}", 200, admin, json={"fulfilment_status": target}
        )
        check(moved["fulfilment_status"] == target, f"the order should be {target}, got {moved['fulfilment_status']}")

    stock = api.call("GET", f"{API}/admin/merch/stock-summary", 200, admin)
    ours = next(row for row in stock["products"] if row["product_id"] == product["id"])
    check(ours["variants"][0]["stock"] == 1, f"one unit should be left, got {ours['variants'][0]['stock']}")
    check(ours["variants"][0]["sold_units"] == 1, f"one unit should be sold, got {ours['variants'][0]['sold_units']}")
    check(ours["variants"][0]["reserved_units"] == 0, "a paid order reserves nothing")
    return f"1 sold at {MEMBER_HOODIE // 100} (discount {HOODIE_DISCOUNT_PCT}%), paid -> packed -> handed_over, 1 left"


def step_six(api: Api, ctx: dict) -> dict:
    """A fundraiser, its board, and the cash it takes."""
    organizer = ctx["organizer"]
    volunteer_id = api.call("GET", f"{API}/auth/me", 200, api.login("volunteer@ssa.org"))["id"]

    fundraiser = api.call(
        "POST",
        f"{API}/fundraisers",
        201,
        organizer,
        json={
            "title": f"Smoke Bake Sale {RUN}",
            "description": "Cakes on the quad, for the library fund.",
            "goal_amount": FUNDRAISER_GOAL,
            "event_date": (TODAY + timedelta(days=14)).isoformat(),
        },
    )
    check(fundraiser["progress"]["raised"] == 0, f"a new fundraiser has raised nothing: {fundraiser['progress']}")
    fundraiser_id = fundraiser["id"]

    task_ids = []
    for title, category in (("Print posters", "promotion"), ("Buy flour", "supplies"), ("Man the stall", "table_duty")):
        task = api.call(
            "POST",
            f"{API}/fundraisers/{fundraiser_id}/tasks",
            201,
            organizer,
            json={
                "title": title,
                "category": category,
                "assignee_id": volunteer_id,
                "due_date": (TODAY + timedelta(days=3)).isoformat(),
            },
        )
        task_ids.append(task["id"])

    volunteer = api.login("volunteer@ssa.org")
    done = api.call("PATCH", f"{API}/tasks/{task_ids[0]}", 200, volunteer, json={"status": "done"})
    check(done["status"] == "done", f"the assignee should be able to close their own card: {done}")
    check(done["completed_at"] is not None, "closing a card should stamp completed_at")

    progress = api.call("GET", f"{API}/fundraisers/{fundraiser_id}", 200, volunteer)["progress"]
    check(progress["tasks"]["total"] == 3, f"three cards on the board: {progress['tasks']}")
    check(progress["tasks"]["done"] == 1, f"one card is done: {progress['tasks']}")
    check(progress["tasks"]["percent_done"] == 33, f"one of three is 33%: {progress['tasks']}")

    income = {"amount": FUNDRAISER_INCOME, "note": "Stall takings", "source_label": "Cash box"}
    headers = {"Idempotency-Key": f"smoke-income-{RUN}"}
    first = api.call("POST", f"{API}/fundraisers/{fundraiser_id}/income", 201, organizer, headers=headers, json=income)
    check(first["replayed"] is False, "the first call is not a replay")
    check(first["raised_total"] == FUNDRAISER_INCOME, f"raised_total is {first['raised_total']}")

    replay = api.call("POST", f"{API}/fundraisers/{fundraiser_id}/income", 201, organizer, headers=headers, json=income)
    check(replay["id"] == first["id"], "the same Idempotency-Key must return the same row")
    check(replay["replayed"] is True, "the second call with the same key is a replay")

    progress = api.call("GET", f"{API}/fundraisers/{fundraiser_id}", 200, volunteer)["progress"]
    check(progress["raised"] == FUNDRAISER_INCOME, f"the cash book should hold one entry: {progress}")
    check(progress["percent_of_goal"] == FUNDRAISER_INCOME * 100 // FUNDRAISER_GOAL, f"goal progress: {progress}")

    ctx["fundraiser_id"] = fundraiser_id
    return (
        f"3 cards, 1 done; {FUNDRAISER_INCOME // 100} INR logged twice, one row, {progress['percent_of_goal']}% of goal"
    )


def step_seven(api: Api, ctx: dict) -> dict:
    """A claim, a refusal, and a payment that moves the balance by exactly the claim."""
    treasurer = api.login("treasurer@ssa.org")
    volunteer = api.login("volunteer@ssa.org")

    own = api.call(
        "POST",
        f"{API}/expenses",
        201,
        treasurer,
        data={
            "amount": str(CLAIM_AMOUNT),
            "description": "Smoke - my own stationery run",
            "category": "supplies",
            "incurred_on": TODAY.isoformat(),
        },
        files={"receipt": ("receipt.png", png(), "image/png")},
    )
    check(own["has_receipt"] is True, "the uploaded receipt should be recorded")

    self_review = api.call("PATCH", f"{API}/expenses/{own['id']}/review", 409, treasurer, json={"decision": "approve"})
    check(
        self_review["error"]["code"] == "SELF_REVIEW",
        f"a treasurer must not approve their own claim: {self_review['error']}",
    )

    claim = api.call(
        "POST",
        f"{API}/expenses",
        201,
        volunteer,
        data={
            "amount": str(CLAIM_AMOUNT),
            "description": "Smoke - posters for the gala",
            "category": "printing",
            "incurred_on": TODAY.isoformat(),
            "event_id": ctx["event_id"],
        },
        files={"receipt": ("receipt.png", png(), "image/png")},
    )
    claim_id = claim["id"]

    signed = api.call("GET", f"{API}/expenses/{claim_id}/receipt", 200, treasurer)
    check(signed["expires_in"] == 600, f"a receipt link lives 600s, got {signed['expires_in']}")
    check(signed["url"].startswith("http"), "the receipt comes back as a URL, never a storage path")
    check(
        "receipt_path" not in api.call("GET", f"{API}/expenses/{claim_id}", 200, treasurer),
        "no storage path is returned",
    )

    before = api.call("GET", f"{API}/finance/summary", 200, treasurer)
    api.call("PATCH", f"{API}/expenses/{claim_id}/review", 200, treasurer, json={"decision": "approve"})
    paid = api.call(
        "POST",
        f"{API}/expenses/{claim_id}/reimburse",
        200,
        treasurer,
        json={"method": "upi", "reference": f"UPI/SMOKE/{RUN}"},
    )
    check(paid["status"] == "reimbursed", f"the claim should be reimbursed, got {paid['status']}")
    check(bool(paid["ledger_transaction_id"]), "reimbursing should write a ledger row")

    after = api.call("GET", f"{API}/finance/summary", 200, treasurer)
    check(
        after["total_out"] - before["total_out"] == CLAIM_AMOUNT,
        f"total_out should rise by exactly {CLAIM_AMOUNT}: {before['total_out']} -> {after['total_out']}",
    )
    check(
        before["balance"] - after["balance"] == CLAIM_AMOUNT,
        f"the balance should fall by exactly {CLAIM_AMOUNT}: {before['balance']} -> {after['balance']}",
    )

    again = api.call(
        "POST",
        f"{API}/expenses/{claim_id}/reimburse",
        200,
        treasurer,
        json={"method": "upi", "reference": f"UPI/SMOKE/{RUN}"},
    )
    check(again["ledger_transaction_id"] == paid["ledger_transaction_id"], "paying twice must not write a second row")
    settled = api.call("GET", f"{API}/finance/summary", 200, treasurer)
    check(settled["balance"] == after["balance"], "a replayed reimbursement must not move the balance")

    ctx["claim_id"] = claim_id
    ctx["balance_after"] = after["balance"]
    return f"SELF_REVIEW refused; {CLAIM_AMOUNT // 100} INR paid once, balance {before['balance'] // 100} -> {after['balance'] // 100}"


def step_eight(api: Api, ctx: dict) -> str:
    """The books, checked against the numbers this run put in them."""
    treasurer = api.login("treasurer@ssa.org")

    by_event = api.call("GET", f"{API}/finance/by-event", 200, treasurer)
    ours = next(row for row in by_event if row["id"] == ctx["event_id"])
    expected_in = MEMBER_TICKET + NON_MEMBER_TICKET * 2
    check(ours["total_in"] == expected_in, f"the event took {ours['total_in']}, expected {expected_in}")
    check(ours["total_out"] == CLAIM_AMOUNT, f"the claim was charged to the event: {ours}")
    check(ours["net"] == ours["total_in"] - ours["total_out"], "net must be in minus out")

    by_fundraiser = api.call("GET", f"{API}/finance/by-fundraiser", 200, treasurer)
    drive = next(row for row in by_fundraiser if row["id"] == ctx["fundraiser_id"])
    check(drive["total_in"] == FUNDRAISER_INCOME, f"the fundraiser raised {drive['total_in']}")
    check(drive["total_out"] == 0, f"nothing has been spent against it yet: {drive}")
    check(drive["goal_amount"] == FUNDRAISER_GOAL, f"the goal should be {FUNDRAISER_GOAL}, got {drive['goal_amount']}")

    reconciliation = api.call("GET", f"{API}/finance/reconcile", 200, treasurer)
    check(
        reconciliation["ok"] is True, f"the books do not add up: {[c for c in reconciliation['checks'] if not c['ok']]}"
    )
    check(
        all(check_row["difference"] == 0 for check_row in reconciliation["checks"]), "a check has a non-zero difference"
    )

    report = api.call(
        "GET",
        f"{API}/finance/report",
        200,
        treasurer,
        params={"from": (TODAY - timedelta(days=30)).isoformat(), "to": TODAY.isoformat()},
    )
    check(
        report["opening_balance"] + report["net_movement"] == report["closing_balance"],
        f"opening {report['opening_balance']} + movement {report['net_movement']} != closing {report['closing_balance']}",
    )
    check(report["closing_balance"] == ctx["balance_after"], "the report must agree with the dashboard balance")
    check(report["reconciliation"]["ok"] is True, "the report's own reconciliation should pass")
    return (
        f"event in {expected_in // 100} / out {CLAIM_AMOUNT // 100}; "
        f"fundraiser in {FUNDRAISER_INCOME // 100}; reconcile ok; "
        f"opening {report['opening_balance'] // 100} + {report['net_movement'] // 100} = {report['closing_balance'] // 100}"
    )


def step_nine(api: Api, ctx: dict) -> str:
    """Close a fortnight, refuse a late entry, reopen it.

    The close is tried plainly first. Whether it succeeds depends on which seeded claims fall
    inside the window: a pending one blocks a plain close (409 PENDING_CLAIMS), which is the rule
    working, not a failure. So a refusal is retried with `force`, and the step reports which path
    it took. `tests/test_e2e_semester.py` proves the unforced close on a database with nothing in
    the way; this step is here for the lock.
    """
    treasurer = api.login("treasurer@ssa.org")
    admin = api.login("admin@ssa.org")
    window = {
        "start_date": (TODAY - timedelta(days=45)).isoformat(),
        "end_date": (TODAY - timedelta(days=35)).isoformat(),
    }
    name = f"Smoke Fortnight {RUN}"

    first = api.call("POST", f"{API}/finance/periods", (201, 409), treasurer, json={"name": name, **window})
    if "error" not in first:
        period = first
        how = "closed outright"
    else:
        check(
            first["error"]["code"] in ("PENDING_CLAIMS", "RECONCILIATION_FAILED"),
            f"a plain close failed for an unexpected reason: {first['error']}",
        )
        period = api.call("POST", f"{API}/finance/periods", 201, admin, json={"name": name, "force": True, **window})
        how = f"closed with force ({first['error']['code']})"
    check(period["status"] == "closed", f"the period should be closed, got {period['status']}")

    late = api.call(
        "POST",
        f"{API}/finance/transactions",
        409,
        treasurer,
        json={
            "amount": 10_000,
            "source": "other_income",
            "note": "Late entry for a fortnight we have already signed off",
            "occurred_at": datetime.combine(TODAY - timedelta(days=40), datetime.min.time(), tzinfo=UTC).isoformat(),
        },
    )
    check(late["error"]["code"] == "PERIOD_CLOSED", f"a closed period must refuse the entry: {late['error']}")
    check(
        late["error"]["details"]["period_name"] == name,
        f"the refusal should name the period: {late['error']['details']}",
    )

    refused = api.call(
        "POST",
        f"{API}/finance/periods/{period['id']}/reopen",
        403,
        treasurer,
        json={"reason": "Reopening to check something"},
    )
    check(refused["error"]["code"] == "FORBIDDEN", f"a treasurer must not reopen the books: {refused['error']}")

    reopened = api.call(
        "POST",
        f"{API}/finance/periods/{period['id']}/reopen",
        200,
        admin,
        json={"reason": "The printer invoice for October was posted late"},
    )
    check(reopened["status"] == "reopened", f"the admin should be able to reopen: {reopened}")
    check(reopened["reopen_reason"] == "The printer invoice for October was posted late", "the reason is kept")

    balance = api.call("GET", f"{API}/finance/summary", 200, treasurer)["balance"]
    check(balance == ctx["balance_after"], "reopening a period must not move a single paisa")
    return f"{how} -> late entry 409 PERIOD_CLOSED -> treasurer 403 -> admin reopened, balance unchanged"


STEPS = (
    ("A student joins and pays dues", step_one),
    ("Organizer publishes the event and announces it", step_two),
    ("Three seats, four buyers", step_three),
    ("The door: check-in and the event report", step_four),
    ("Merch sells out and ships", step_five),
    ("A fundraiser, its board and its cash", step_six),
    ("A claim, a refusal, a payment", step_seven),
    ("The books add up", step_eight),
    ("Close the period, refuse a late entry, reopen", step_nine),
)


def main() -> int:
    api = Api(BASE_URL)
    print(f"SSA Hub - end-to-end smoke test against {BASE_URL}")
    print("-" * 96)
    print(f"  server   {BASE_URL}")
    print("  accounts admin@ / organizer@ / treasurer@ / volunteer@ssa.org (password from DEMO_PASSWORD)")
    print(f"  run id   {RUN} (every object this run creates is suffixed with it)")
    print("-" * 96)

    results: list[tuple[str, str, str]] = []
    context: dict = {}
    failed = False

    for index, (name, run_step) in enumerate(STEPS, start=1):
        label = f"{index}. {name}"
        if failed:
            results.append((label, "SKIP", "not reached: an earlier step failed"))
            continue
        started = time.perf_counter()
        try:
            detail = run_step(api, context)
            results.append((label, "PASS", f"{detail}  [{time.perf_counter() - started:.2f}s]"))
            print(f"  [{index}/9] PASS  {name}")
        except Failed as error:
            results.append((label, "FAIL", str(error)))
            print(f"  [{index}/9] FAIL  {name}")
            failed = True
        except Exception as error:  # noqa: BLE001 - a smoke test reports anything, it does not raise
            results.append((label, "FAIL", f"{type(error).__name__}: {error}"))
            print(f"  [{index}/9] FAIL  {name}")
            failed = True

    print("-" * 96)
    width = max(len(name) for name, _, _ in results)
    for name, status, detail in results:
        print(f"  {name:<{width}}  {status:<5} {detail}")
    print("-" * 96)
    passed = sum(1 for _, status, _ in results if status == "PASS")
    print(f"  {passed}/{len(results)} steps passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
