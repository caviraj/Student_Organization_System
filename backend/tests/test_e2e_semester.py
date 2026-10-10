"""One semester, start to finish, over the real HTTP API on a real Postgres database.

Every other test file proves one rule. This one proves the rules *compose*: a student registers and
pays dues, an organizer runs an event that sells out, the door scans tickets, merch sells down to
its last unit and ships, a fundraiser collects and spends money, the treasurer pays a claim, and
the books close - all through `TestClient`, with nothing written straight to a table.

Three habits make it worth more than the sum of its parts:

* **It computes its own expected numbers.** The finance figures at the end are summed in the test
  from the amounts it used earlier, and compared against what the API reports. Reading a number
  back out of the API and asserting it equals itself would pass for any bug that is consistent with
  itself; this catches the one that is not.
* **It asserts values, not statuses.** "201" is not a fact about the system. "three tickets exist,
  the third cost the member price, and the fourth buyer got seats_left: 0" is.
* **It builds everything it uses.** No seeded row is read, so this passes on a database that has
  never run `seed.py` - and fails on its own terms rather than on the seed's.

Kept as one function on purpose. The suite truncates every table between tests (conftest `_clean`),
so a story split across functions would be nine unrelated tests sharing a name.
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from app.models import Expense, Transaction

PASSWORD = "Passw0rd!"
TODAY = date.today()

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


def _png() -> bytes:
    """A 1x1 PNG. The receipt check reads the magic bytes, so this is a valid receipt."""
    return bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000a49444154789c6300010000050001a5f645400000000049454e44ae426082"
    )


def _register(client, email: str, full_name: str) -> str:
    """Register a student over the API. Returns their token; their role is `guest` until they pay."""
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": PASSWORD,
            "full_name": full_name,
            "phone": "9876500000",
            "department": "CSE",
            "year": 2,
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["user"]["role"] == "guest"
    return response.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _confirm(client, order_id, token: str, outcome: str = "success") -> dict:
    response = client.post(f"/api/v1/payments/{order_id}/mock-confirm", json={"outcome": outcome}, headers=_auth(token))
    assert response.status_code == 200, response.text
    return response.json()


def _summary(client, token: str, **params) -> dict:
    response = client.get("/api/v1/finance/summary", headers=_auth(token), params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_a_semester_end_to_end(client, db, make_plan, make_user, make_event):
    admin = make_user("e2e.admin@ssa.org", role="admin")
    organizer = make_user("e2e.organizer@ssa.org", role="organizer")
    treasurer = make_user("e2e.treasurer@ssa.org", role="treasurer")
    volunteer = make_user("e2e.volunteer@ssa.org", role="volunteer")
    logins = {}
    for user in (admin, organizer, treasurer, volunteer):
        response = client.post("/api/v1/auth/login", json={"email": user.email, "password": PASSWORD})
        assert response.status_code == 200, response.text
        logins[user.role] = response.json()["access_token"]
    admin_headers = _auth(logins["admin"])
    organizer_headers = _auth(logins["organizer"])
    treasurer_headers = _auth(logins["treasurer"])
    volunteer_headers = _auth(logins["volunteer"])

    # --- STEP 1: a student joins and pays their dues -------------------------------------------
    member_token = _register(client, "e2e.member@ssa.org", "Meera E2E")
    me = client.get("/api/v1/auth/me", headers=_auth(member_token)).json()
    assert me["member_code"] is None, "a guest has no member code yet"
    assert me["membership"]["status"] == "none"

    plan = make_plan(name="E2E Standard", price=PLAN_PRICE)
    checkout = client.post("/api/v1/memberships/checkout", json={"plan_id": str(plan.id)}, headers=_auth(member_token))
    assert checkout.status_code == 201, checkout.text
    assert checkout.json()["amount"] == PLAN_PRICE

    confirmed = _confirm(client, checkout.json()["order_id"], member_token)
    assert confirmed["order_status"] == "paid"
    assert confirmed["membership"]["status"] == "active"
    assert confirmed["membership"]["plan_name"] == "E2E Standard"

    me = client.get("/api/v1/auth/me", headers=_auth(member_token)).json()
    assert me["role"] == "member", "paying dues is what promotes a guest"
    assert me["member_code"], "the member code is issued when the membership activates"

    dues = db.scalars(select(Transaction).where(Transaction.source == "dues")).all()
    assert len(dues) == 1, "one membership, one dues row - a replayed confirm must not write a second"
    assert (dues[0].direction, dues[0].amount) == ("in", PLAN_PRICE)

    # --- STEP 2: the organizer posts the event and tells the members ----------------------------
    gala = client.post(
        "/api/v1/events",
        json={
            "title": "Gala E2E",
            "venue": "Main Auditorium",
            "starts_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
            "ends_at": (datetime.now(UTC) + timedelta(hours=4)).replace(microsecond=0).isoformat(),
        },
        headers=organizer_headers,
    )
    assert gala.status_code == 201, gala.text
    assert gala.json()["status"] == "draft"
    gala_id = gala.json()["id"]

    published = client.patch(f"/api/v1/events/{gala_id}", json={"status": "published"}, headers=organizer_headers)
    assert published.status_code == 200 and published.json()["status"] == "published"

    ticket_type = client.post(
        f"/api/v1/events/{gala_id}/ticket-types",
        json={
            "name": "Balcony",
            "member_price": MEMBER_TICKET,
            "non_member_price": NON_MEMBER_TICKET,
            "capacity": GALA_CAPACITY,
        },
        headers=organizer_headers,
    )
    assert ticket_type.status_code == 201, ticket_type.text
    assert ticket_type.json()["seats_left"] == GALA_CAPACITY
    ticket_type_id = ticket_type.json()["id"]

    announcement = client.post(
        "/api/v1/announcements",
        json={
            "title": "Gala tickets are live",
            "body": "Three seats. Member price first, then it is everyone for themselves.",
            "category": "general",
            "audience": "members",
            "send_email": True,
        },
        headers=organizer_headers,
    )
    assert announcement.status_code == 201, announcement.text
    announcement_id = announcement.json()["id"]
    summary = announcement.json()["delivery_summary"]
    assert summary["inapp_queued"] >= 1, "the one member we created should be queued"
    assert summary["email_queued"] >= 1, "send_email=True and this member has not opted out"

    inbox = client.get(f"/api/v1/announcements/{announcement_id}/deliveries", headers=admin_headers)
    assert inbox.status_code == 200, inbox.text
    assert inbox.json()["summary"]["inapp"]["sent"] >= 1
    assert inbox.json()["summary"]["email"]["sent"] >= 1, "the client fixture drains the queue"
    assert inbox.json()["summary"]["email"]["failed"] == 0
    member_rows = [row for row in inbox.json()["items"]["items"] if row["user_email"] == "e2e.member@ssa.org"]
    assert {row["channel"] for row in member_rows} == {"inapp", "email"}, "one row per channel per recipient"
    assert all(row["status"] == "sent" and row["sent_at"] for row in member_rows)

    # --- STEP 3: three seats, four buyers --------------------------------------------------------
    def buy(token: str, quantity: int = 1):
        body = client.post(
            "/api/v1/tickets/checkout",
            json={"ticket_type_id": ticket_type_id, "quantity": quantity},
            headers=_auth(token),
        )
        if body.status_code != 201:
            return body
        assert body.json()["status"] == "pending", "a paid ticket type is never free"
        return _confirm(client, body.json()["order_id"], token)

    member_sale = buy(member_token)
    assert member_sale["order_status"] == "paid"
    (member_ticket,) = member_sale["tickets"]
    assert member_ticket["price_paid"] == MEMBER_TICKET, "an active member pays the member price"

    guest_a_token = _register(client, "e2e.guest.a@ssa.org", "Guest A")
    guest_a_sale = buy(guest_a_token)
    assert guest_a_sale["tickets"][0]["price_paid"] == NON_MEMBER_TICKET, "no membership, no discount"

    guest_b_token = _register(client, "e2e.guest.b@ssa.org", "Guest B")
    guest_b_sale = buy(guest_b_token)
    assert guest_b_sale["tickets"][0]["price_paid"] == NON_MEMBER_TICKET

    guest_c_token = _register(client, "e2e.guest.c@ssa.org", "Guest C")
    too_late = client.post(
        "/api/v1/tickets/checkout",
        json={"ticket_type_id": ticket_type_id, "quantity": 1},
        headers=_auth(guest_c_token),
    )
    assert too_late.status_code == 409, too_late.text
    assert too_late.json()["error"]["code"] == "SOLD_OUT"
    assert too_late.json()["error"]["details"] == {"seats_left": 0, "requested": 1}

    sold_out = client.get(f"/api/v1/events/{gala_id}").json()
    (only_type,) = sold_out["ticket_types"]
    assert only_type["sold_count"] == GALA_CAPACITY
    assert only_type["seats_left"] == 0

    # --- STEP 4: the door ------------------------------------------------------------------------
    def scan(code: str, headers=volunteer_headers, event_id=gala_id):
        response = client.post("/api/v1/checkin", json={"event_id": event_id, "code": code}, headers=headers)
        assert response.status_code == 200, response.text
        return response.json()

    first = scan(member_ticket["code"])
    assert first["result"] == "VALID"
    assert first["holder_name"] == "Meera E2E"
    assert (first["checked_in"], first["sold"]) == (1, GALA_CAPACITY)

    assert scan(member_ticket["code"])["result"] == "ALREADY_USED"
    assert scan("NOT-A-REAL-CODE")["result"] == "INVALID"

    # A ticket for a different event: the scanner must say so, not turn the holder away silently.
    other = make_event(title="Freshers Mixer E2E", status="published", starts_in_days=20)
    wrong = client.post(
        "/api/v1/checkin",
        json={"event_id": str(other.id), "code": member_ticket["code"]},
        headers=volunteer_headers,
    )
    assert wrong.status_code == 200
    assert wrong.json()["result"] == "WRONG_EVENT"
    assert "Gala E2E" in wrong.json()["message"], "it names the event the ticket is really for"

    report = client.get(f"/api/v1/events/{gala_id}/report", headers=organizer_headers)
    assert report.status_code == 200, report.text
    report = report.json()
    assert report["tickets_sold"] == GALA_CAPACITY
    assert report["checked_in"] == 1
    assert report["no_shows"] == GALA_CAPACITY - 1
    assert report["seats_left"] == 0
    assert report["revenue"] == {
        "member": MEMBER_TICKET,
        "non_member": NON_MEMBER_TICKET * 2,
        "total": MEMBER_TICKET + NON_MEMBER_TICKET * 2,
    }

    # --- STEP 5: merch, down to the last unit ----------------------------------------------------
    product = client.post(
        "/api/v1/products",
        json={"name": "E2E Hoodie", "base_price": HOODIE_PRICE, "member_discount_pct": HOODIE_DISCOUNT_PCT},
        headers=admin_headers,
    )
    assert product.status_code == 201, product.text
    product_id = product.json()["id"]

    variant = client.post(
        f"/api/v1/products/{product_id}/variants",
        json={"size": "M", "sku": "E2E-HOODIE-M", "stock": 2},
        headers=admin_headers,
    )
    assert variant.status_code == 201, variant.text
    variant_id = variant.json()["id"]

    def order_merch(quantity: int, token: str, key: str):
        body = client.post(
            "/api/v1/orders/merch/checkout",
            json={"items": [{"variant_id": variant_id, "qty": quantity}]},
            headers={**_auth(token), "Idempotency-Key": key},
        )
        if body.status_code != 201:
            return body
        return _confirm(client, body.json()["order_id"], token)

    listed = client.get(f"/api/v1/products/{product_id}", headers=_auth(member_token)).json()
    assert listed["price_for_you"] == MEMBER_HOODIE
    assert listed["is_member_price"] is True

    first_order = client.post(
        "/api/v1/orders/merch/checkout",
        json={"items": [{"variant_id": variant_id, "qty": 1}]},
        headers={**_auth(member_token), "Idempotency-Key": "e2e-merch-1"},
    )
    assert first_order.status_code == 201, first_order.text
    priced = first_order.json()
    assert priced["subtotal"] == HOODIE_PRICE
    assert priced["discount"] == HOODIE_PRICE - MEMBER_HOODIE, "the member discount is a real number, not a flag"
    assert priced["amount"] == MEMBER_HOODIE
    assert priced["items"][0]["unit_price"] == MEMBER_HOODIE
    assert priced["status"] == "pending" and priced["expires_at"]
    first_order_id = priced["order_id"]

    two_too_many = client.post(
        "/api/v1/orders/merch/checkout",
        json={"items": [{"variant_id": variant_id, "qty": 2}]},
        headers={**_auth(member_token), "Idempotency-Key": "e2e-merch-2"},
    )
    assert two_too_many.status_code == 409, two_too_many.text
    assert two_too_many.json()["error"]["code"] == "OUT_OF_STOCK"
    assert two_too_many.json()["error"]["details"] == {
        "variant_id": variant_id,
        "product_name": "E2E Hoodie",
        "size": "M",
        "available": 1,
        "requested": 2,
    }, "stock is reserved at checkout, so the second order sees one unit left"

    paid_order = _confirm(client, first_order_id, member_token)
    assert paid_order["merch"]["fulfilment_status"] == "paid"
    assert paid_order["merch"]["delivery_method"] == "pickup"

    board = client.get("/api/v1/admin/merch/orders", headers=admin_headers).json()
    assert board["counts"]["paid"] == 1

    skipped = client.patch(
        f"/api/v1/admin/merch/orders/{first_order_id}", json={"fulfilment_status": "handed_over"}, headers=admin_headers
    )
    assert skipped.status_code == 409, "paid -> handed_over skips packed"
    assert skipped.json()["error"]["code"] == "INVALID_TRANSITION"
    assert skipped.json()["error"]["details"] == {"from": "paid", "to": "handed_over", "allowed": "packed"}

    for step in ("packed", "handed_over"):
        moved = client.patch(
            f"/api/v1/admin/merch/orders/{first_order_id}", json={"fulfilment_status": step}, headers=admin_headers
        )
        assert moved.status_code == 200, moved.text
        assert moved.json()["fulfilment_status"] == step
    assert moved.json()["packed_at"] and moved.json()["handed_over_at"]

    last_one = order_merch(1, member_token, "e2e-merch-3")
    assert last_one["merch"]["fulfilment_status"] == "paid", "the last hoodie sells"
    stock = client.get("/api/v1/admin/merch/stock-summary", headers=admin_headers).json()
    (only_product,) = [row for row in stock["products"] if row["product_id"] == product_id]
    assert only_product["variants"][0]["stock"] == 0
    assert only_product["variants"][0]["out_of_stock"] is True
    assert only_product["sold_units"] == 2 and only_product["reserved_units"] == 0

    # --- STEP 6: a fundraiser, and the money it raises -------------------------------------------
    fundraiser = client.post(
        "/api/v1/fundraisers",
        json={
            "title": "E2E Bake Sale",
            "description": "Cakes on the quad, for the library fund.",
            "goal_amount": FUNDRAISER_GOAL,
            "event_date": (TODAY + timedelta(days=14)).isoformat(),
            "owner_id": str(organizer.id),
        },
        headers=organizer_headers,
    )
    assert fundraiser.status_code == 201, fundraiser.text
    fundraiser_id = fundraiser.json()["id"]
    assert fundraiser.json()["status"] == "planning"
    assert fundraiser.json()["progress"]["raised"] == 0

    task_ids = []
    for title, category in (("Print posters", "promotion"), ("Buy flour", "supplies"), ("Man the stall", "table_duty")):
        created = client.post(
            f"/api/v1/fundraisers/{fundraiser_id}/tasks",
            json={
                "title": title,
                "category": category,
                "assignee_id": str(volunteer.id),
                "due_date": (TODAY + timedelta(days=3)).isoformat(),
            },
            headers=organizer_headers,
        )
        assert created.status_code == 201, created.text
        task_ids.append(created.json()["id"])

    moved = client.patch(f"/api/v1/tasks/{task_ids[0]}", json={"status": "done"}, headers=volunteer_headers)
    assert moved.status_code == 200, moved.text
    assert moved.json()["status"] == "done"
    assert moved.json()["completed_at"] is not None

    progress = client.get(f"/api/v1/fundraisers/{fundraiser_id}", headers=volunteer_headers).json()["progress"]
    assert progress["tasks"]["total"] == 3
    assert progress["tasks"]["done"] == 1
    assert progress["tasks"]["todo"] == 2
    assert progress["tasks"]["percent_done"] == 33
    assert progress["raised"] == 0
    assert progress["health"] in ("on_track", "at_risk", "behind")

    income_headers = {**organizer_headers, "Idempotency-Key": "e2e-fundraiser-income"}
    first_income = client.post(
        f"/api/v1/fundraisers/{fundraiser_id}/income",
        json={"amount": FUNDRAISER_INCOME, "note": "Stall takings", "source_label": "Cash box"},
        headers=income_headers,
    )
    assert first_income.status_code == 201, first_income.text
    assert first_income.json()["replayed"] is False
    assert first_income.json()["raised_total"] == FUNDRAISER_INCOME

    replay = client.post(
        f"/api/v1/fundraisers/{fundraiser_id}/income",
        json={"amount": FUNDRAISER_INCOME, "note": "Stall takings", "source_label": "Cash box"},
        headers=income_headers,
    )
    assert replay.status_code == 201
    assert replay.json()["id"] == first_income.json()["id"], "same key, same row"
    assert replay.json()["replayed"] is True

    fundraiser_rows = db.scalars(select(Transaction).where(Transaction.source == "fundraiser")).all()
    assert len(fundraiser_rows) == 1, "the replayed request must not write a second ledger row"
    assert (fundraiser_rows[0].direction, fundraiser_rows[0].amount) == ("in", FUNDRAISER_INCOME)

    progress = client.get(f"/api/v1/fundraisers/{fundraiser_id}", headers=volunteer_headers).json()["progress"]
    assert progress["raised"] == FUNDRAISER_INCOME
    assert progress["percent_of_goal"] == FUNDRAISER_INCOME * 100 // FUNDRAISER_GOAL
    assert progress["net_raised"] == FUNDRAISER_INCOME, "nothing has been spent against it yet"

    # --- STEP 7: a claim, a refusal, and a payment ------------------------------------------------
    own_claim = client.post(
        "/api/v1/expenses",
        data={
            "amount": str(CLAIM_AMOUNT),
            "description": "Trevor's own stationery run",
            "category": "supplies",
            "incurred_on": TODAY.isoformat(),
        },
        files={"receipt": ("receipt.png", _png(), "image/png")},
        headers=treasurer_headers,
    )
    assert own_claim.status_code == 201, own_claim.text
    assert own_claim.json()["has_receipt"] is True

    self_review = client.patch(
        f"/api/v1/expenses/{own_claim.json()['id']}/review", json={"decision": "approve"}, headers=treasurer_headers
    )
    assert self_review.status_code == 409, "nobody approves their own claim, treasurer included"
    assert self_review.json()["error"]["code"] == "SELF_REVIEW"

    claim = client.post(
        "/api/v1/expenses",
        data={
            "amount": str(CLAIM_AMOUNT),
            "description": "Posters for the gala",
            "category": "printing",
            "incurred_on": TODAY.isoformat(),
            "event_id": gala_id,
        },
        files={"receipt": ("receipt.png", _png(), "image/png")},
        headers=volunteer_headers,
    )
    assert claim.status_code == 201, claim.text
    claim_id = claim.json()["id"]

    signed = client.get(f"/api/v1/expenses/{claim_id}/receipt", headers=treasurer_headers)
    assert signed.status_code == 200, signed.text
    assert signed.json()["expires_in"] == 600, "ten minutes, then the link is dead"
    assert signed.json()["url"].startswith("http") and "?" in signed.json()["url"], "a signed URL, not a path"
    detail = client.get(f"/api/v1/expenses/{claim_id}", headers=treasurer_headers).json()
    assert "receipt_path" not in detail, "the storage path is never returned"

    balance_before = _summary(client, logins["treasurer"])["balance"]
    approved = client.patch(
        f"/api/v1/expenses/{claim_id}/review",
        json={"decision": "approve", "note": "Receipt is fine"},
        headers=treasurer_headers,
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"

    paid = client.post(
        f"/api/v1/expenses/{claim_id}/reimburse",
        json={"method": "upi", "reference": "UPI/E2E/1"},
        headers=treasurer_headers,
    )
    assert paid.status_code == 200, paid.text
    assert paid.json()["status"] == "reimbursed"
    assert paid.json()["ledger_transaction_id"]

    balance_after = _summary(client, logins["treasurer"])["balance"]
    assert balance_after == balance_before - CLAIM_AMOUNT, "the balance moves by exactly the claim"

    out_rows = db.scalars(select(Transaction).where(Transaction.source == "expense_reimbursement")).all()
    assert len(out_rows) == 1
    assert (out_rows[0].direction, out_rows[0].amount) == ("out", CLAIM_AMOUNT)

    repaid = client.post(
        f"/api/v1/expenses/{claim_id}/reimburse",
        json={"method": "upi", "reference": "UPI/E2E/1"},
        headers=treasurer_headers,
    )
    assert repaid.status_code == 200
    assert repaid.json()["ledger_transaction_id"] == paid.json()["ledger_transaction_id"]
    assert (
        len(db.scalars(select(Transaction).where(Transaction.source == "expense_reimbursement")).all()) == 1
    ), "paying twice writes nothing the second time"
    assert _summary(client, logins["treasurer"])["balance"] == balance_after

    still_open = db.scalar(select(Expense).where(Expense.id == own_claim.json()["id"]))
    assert still_open.status == "submitted", "the refused claim is untouched - a rejection is not a silent delete"

    # --- STEP 8: the books, checked against arithmetic done here ----------------------------------
    expected_in = PLAN_PRICE + (MEMBER_TICKET + NON_MEMBER_TICKET * 2) + (MEMBER_HOODIE * 2) + FUNDRAISER_INCOME
    expected_out = CLAIM_AMOUNT
    expected_balance = expected_in - expected_out

    summary = _summary(client, logins["treasurer"])
    assert summary["total_in"] == expected_in, "summed here from the prices used above, not read back"
    assert summary["total_out"] == expected_out
    assert summary["balance"] == expected_balance

    by_source = {row["source"]: row for row in summary["by_source"]}
    assert by_source["dues"]["in"] == PLAN_PRICE
    assert by_source["tickets"]["in"] == MEMBER_TICKET + NON_MEMBER_TICKET * 2
    assert by_source["merch"]["in"] == MEMBER_HOODIE * 2
    assert by_source["fundraiser"]["in"] == FUNDRAISER_INCOME
    assert by_source["expense_reimbursement"]["out"] == CLAIM_AMOUNT

    by_event = client.get("/api/v1/finance/by-event", headers=treasurer_headers).json()
    gala_row = next(row for row in by_event if row["id"] == gala_id)
    assert gala_row["total_in"] == MEMBER_TICKET + NON_MEMBER_TICKET * 2
    assert gala_row["total_out"] == CLAIM_AMOUNT, "the claim was charged to the event"
    assert gala_row["net"] == gala_row["total_in"] - gala_row["total_out"]

    by_fundraiser = client.get("/api/v1/finance/by-fundraiser", headers=treasurer_headers).json()
    fundraiser_row = next(row for row in by_fundraiser if row["id"] == fundraiser_id)
    assert fundraiser_row["total_in"] == FUNDRAISER_INCOME
    assert fundraiser_row["total_out"] == 0
    assert fundraiser_row["net"] == FUNDRAISER_INCOME

    reconciliation = client.get("/api/v1/finance/reconcile", headers=treasurer_headers)
    assert reconciliation.status_code == 200, reconciliation.text
    assert reconciliation.json()["ok"] is True, reconciliation.json()["checks"]
    assert all(check["ok"] for check in reconciliation.json()["checks"])
    assert all(check["difference"] == 0 for check in reconciliation.json()["checks"] if "difference" in check)

    window = {"from": (TODAY - timedelta(days=30)).isoformat(), "to": TODAY.isoformat()}
    report = client.get("/api/v1/finance/report", headers=treasurer_headers, params=window)
    assert report.status_code == 200, report.text
    report = report.json()
    assert report["opening_balance"] + report["net_movement"] == report["closing_balance"]
    assert report["closing_balance"] == expected_balance
    assert report["net_movement"] == expected_in - expected_out
    assert report["income"]["total"] == expected_in
    assert report["expenses"]["total"] == expected_out
    assert report["reconciliation"]["ok"] is True

    # --- STEP 9: close the period, then reopen it --------------------------------------------------
    closed = client.post(
        "/api/v1/finance/periods",
        json={
            "name": "E2E Quiet Fortnight",
            "start_date": (TODAY - timedelta(days=20)).isoformat(),
            "end_date": (TODAY - timedelta(days=10)).isoformat(),
        },
        headers=treasurer_headers,
    )
    assert closed.status_code == 201, closed.text
    assert closed.json()["status"] == "closed"
    period_id = closed.json()["id"]

    late = client.post(
        "/api/v1/finance/transactions",
        json={
            "amount": 10_000,
            "source": "other_income",
            "note": "Late entry for a fortnight we have already signed off",
            "occurred_at": datetime.combine(TODAY - timedelta(days=15), datetime.min.time(), tzinfo=UTC).isoformat(),
        },
        headers=treasurer_headers,
    )
    assert late.status_code == 409, late.text
    assert late.json()["error"]["code"] == "PERIOD_CLOSED"
    assert late.json()["error"]["details"]["period_name"] == "E2E Quiet Fortnight"

    refused = client.post(
        f"/api/v1/finance/periods/{period_id}/reopen",
        json={"reason": "Reopening to check something"},
        headers=treasurer_headers,
    )
    assert refused.status_code == 403, "reopening the books is an admin decision"

    reopened = client.post(
        f"/api/v1/finance/periods/{period_id}/reopen",
        json={"reason": "The printer invoice for October was posted late"},
        headers=admin_headers,
    )
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["status"] == "reopened"
    assert reopened.json()["reopen_reason"] == "The printer invoice for October was posted late"

    # The books still add up after a full semester, and the balance never moved by accident.
    assert _summary(client, logins["treasurer"])["balance"] == expected_balance
    assert client.get("/api/v1/finance/reconcile", headers=treasurer_headers).json()["ok"] is True
