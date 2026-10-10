# DESIGN — SSA Hub (Architecture, Data Model, API Contract, UI)

> This file is the **contract** between Backend (Caviraj) and Frontend (Dinesh). If an endpoint or field changes, update this file in the same PR.

---

## 1. Tech Stack
| Layer | Choice |
|---|---|
| Frontend | React 19 + TypeScript + Vite, Tailwind CSS, React Router, TanStack Query, Zod, `qrcode.react`, `html5-qrcode` (scanner), Recharts |
| Backend | Python 3.11+, FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2, PyJWT, `bcrypt` (used directly; `passlib` dropped — it is unmaintained and its bcrypt backend lags bcrypt 4.x), APScheduler (reminder job) |
| DB | PostgreSQL (Supabase-hosted). **Two URLs, and they are not interchangeable:** `DATABASE_URL` points at the **transaction pooler** (port 6543) and is what the running API uses — prepared statements disabled, `sslmode=require`, small pool; `DIRECT_URL` points at the **session pooler / direct connection** (port 5432) and is used by Alembic and `scripts/seed.py` only. Tests use `TEST_DATABASE_URL`, a different database. Postgres-only: UUID, JSONB, TIMESTAMPTZ — no SQLite anywhere in app code |
| DB safety | Every table in `public` has **RLS enabled with no policies** (migration `275474077f1c…`): Supabase publishes `public` over its own REST API, and RLS-on-with-no-policies is what keeps that door shut. The backend is the table owner, so it is unaffected; `FORCE ROW LEVEL SECURITY` is never used. No advisory locks or session-level state anywhere (the transaction pooler may hand each statement to a different backend); `SELECT … FOR UPDATE SKIP LOCKED` inside one transaction is the concurrency tool. `scripts/check_db.py` exits non-zero if any table has RLS off |
| Storage | Supabase Storage (receipts, banners, product images) |
| Payments | `PaymentProvider` interface → `MockProvider` (M1), `RazorpayProvider` (M2) |
| Hosting (demo) | Frontend: Vercel · Backend: Render/Railway · DB: Supabase |
| Tests | pytest + httpx (backend), Vitest + Testing Library (frontend) |

## 2. Repository Layout (monorepo)
```
ssa-hub/
├─ docs/            PRD.md DESIGN.md TASKS.md
├─ AGENTS.md        (copy to backend/CLAUDE.md for Claude Code)
├─ backend/
│  ├─ app/
│  │  ├─ main.py  core/(config,security,db,deps)  models/  schemas/
│  │  ├─ routers/ (auth, users, plans, memberships, events, tickets, checkin,
│  │  │            announcements, products, orders, merch_admin, fundraisers, tasks,
│  │  │            expenses, finance, payments)
│  │  ├─ services/ (pricing, inventory, payments, ledger, reminders)
│  │  └─ jobs/
│  ├─ alembic/  tests/  scripts/(seed.py, demo_phaseN.sh)
│  └─ requirements.txt  .env.example
└─ frontend/
   ├─ src/ (app, api, components, features/*, pages, hooks, lib, mocks)
   └─ .env.example
```

## 3. Architecture
```
React SPA ──HTTPS/JSON──> FastAPI ──SQLAlchemy──> Postgres
                              ├── services/payments  (Mock → Razorpay)
                              ├── services/ledger    (auto income entries)
                              ├── jobs/reminders     (daily expiry scan)
                              └── Supabase Storage   (uploads)
```
**Core idea:** everything that costs money is an **Order** → has a **Payment** → on success creates **Fulfilment** (membership / tickets / merch reservation) **and** a **Ledger transaction**. Expenses are the only outflow. Therefore the treasurer's numbers always reconcile.

## 4. Data Model (PostgreSQL)
All money = `INTEGER` paise. All PKs = UUID. All tables: `created_at`, `updated_at`.

**users**: id, email (unique), password_hash, full_name, phone, department, year, role (`admin|treasurer|organizer|volunteer|member|guest`), member_code (unique, e.g. `SSA-2026-0042`), email_opt_in, is_active

**membership_plans**: id, name, price, duration_months, ticket_discount_pct, merch_discount_pct, description, is_active

**memberships**: id, user_id→users, plan_id→plans, status (`pending|active|expired|cancelled`), start_date, end_date, order_id→orders, renewal_reminded_at
  *constraint:* `unique(user_id)` — one membership row per member; renewals extend it (past orders keep the purchase trail). The member's QR card is therefore always a single, current code.

**events**: id, title, description, venue, starts_at, ends_at, banner_url, status (`draft|published|closed`), created_by

**ticket_types**: id, event_id, name, member_price, non_member_price, capacity, sold_count, sale_starts_at, sale_ends_at
  *constraint:* `sold_count <= capacity`, plus `capacity > 0`, `sold_count >= 0` and both prices `>= 0` — the database refuses an oversell even if a future caller forgets rule 2.

**orders**: id, user_id, kind (`membership|ticket|merch`), status (`pending|paid|failed|cancelled|refunded`), subtotal, discount, total, currency=`INR`, meta JSONB, idempotency_key

**order_items**: id, order_id, item_type (`plan|ticket_type|variant`), item_id, quantity, unit_price, line_total

**payments**: id, order_id, provider (`mock|razorpay`), provider_ref, status (`created|succeeded|failed`), amount, raw JSONB

**tickets**: id, order_id, event_id, ticket_type_id, user_id, code (unique, short random), status (`valid|used|void`), price_paid, is_member_price, checked_in_at, checked_in_by
  *constraint:* `code` unique+indexed, and an index on `(event_id, status)` so the door counters and the report stay cheap. `price_paid`/`is_member_price` are **frozen at purchase time**, so a later price change or lapsed membership never rewrites history.

**announcements**: id, title, body, category (`meeting|deadline|change|general`), audience (`all|members|event`), event_id?, is_pinned (default false), author_id, published_at, revision_note, edited_at?
  *constraint:* `event_id` is required when `audience='event'` and refused otherwise; at most **3** rows may have `is_pinned` at once. There is **no DELETE** — the record of what was said, and when, is permanent.

**announcement_revisions** (immutable history): id, announcement_id→announcements, title, body, category, audience, edited_by→users, edited_at, note
  *meaning:* a row stores the **previous** version each time an announcement is edited — so `announcements` is always current and the revisions read as the trail behind it. Rows are never updated or deleted.

**announcement_deliveries**: id, announcement_id, user_id, channel (`email|inapp`), status (`queued|sent|failed`), attempts (default 0, max 3), error?, sent_at
  *constraint:* `unique(announcement_id, user_id, channel)` — one delivery per person per channel, which is what makes the worker safe to run twice. Indexed on `(status, channel)` (the worker's claim) and `(announcement_id)` (the admin view). An `inapp` row is delivered by being in the feed: the worker marks it `sent` without calling a provider, so in-app delivery cannot fail.

**products**: id, name, description, image_url, base_price, member_discount_pct, is_active
  *meaning:* `base_price` is what a non-member pays; `member_discount_pct` is the product's own member discount (0–100). A member pays the **better** of this and their plan's `merch_discount_pct` (§4 rule 12).

**product_variants**: id, product_id→products, size, color?, sku, stock, low_stock_threshold
  *constraint:* `stock >= 0`, `low_stock_threshold >= 0`, and `unique(product_id, size, color)` — one row per size/colour on a product (colour is `NULL` for a one-colour product, so the constraint uses `NULLS NOT DISTINCT` to stop a second colourless row of the same size). `sku` is unique and the **stock is only ever changed by a stock movement** (§4 rule 12): checkout, release, restock and manual adjustment all write one `stock_movements` row in the same transaction, so the shelf and the audit trail can never disagree.

**stock_movements** (immutable audit trail): id, variant_id→product_variants, delta (signed), reason (`initial|sale|release|restock|adjustment`), order_id→orders?, created_by→users?, note?
  *meaning:* append-only — rows are never updated or deleted, and there is no endpoint that writes one directly. `initial` is written with the variant (the opening stock), `sale` at checkout, `release` when a dead order gives stock back, `restock`/`adjustment` for an admin's manual change. **Invariant, asserted by the tests and by `scripts/seed.py`: `SUM(stock_movements.delta) == product_variants.stock`** for every variant. Visible via `GET /variants/{id}/stock-movements`.

**merch_orders** (extension of orders for fulfilment): order_id PK→orders, fulfilment_status (`paid|packed|handed_over`), delivery_method (`pickup|campus_delivery`), delivery_note?, packed_at?, handed_over_at?, handled_by→users?
  *meaning:* a row exists **only once a merch order is paid**, and is created inside the payment transaction starting at `paid`. The buyer's choice of `delivery_method` and `delivery_note` is captured in `orders.meta` at checkout and copied here on success, so the fulfilment board never depends on parsing `meta`. Delivery info is a merch concern, which is why it lives here and not on `orders`.

**fundraisers**: id, title, description, goal_amount, event_date, status (`planning|active|done`), owner_id
**tasks**: id, fundraiser_id?, event_id?, title, description, category, assignee_id, due_date, status (`todo|doing|done`)

**expenses**: id, claimant_id, amount, description, category, event_id?, fundraiser_id?, receipt_url, status (`submitted|approved|rejected|reimbursed`), reviewed_by, review_note, reimbursed_at
**transactions** (ledger): id, direction (`in|out`), amount, source (`dues|tickets|merch|fundraiser|other_income|expense_reimbursement`), ref_type, ref_id, event_id?, fundraiser_id?, occurred_at, note

**reminders**: id, membership_id, kind (`expiry_30|expiry_7|expired`), created_at, delivered (bool)
  *constraint:* `unique(membership_id, kind)` — the idempotency guard that makes "at most one reminder per kind per membership" (rule 6) structural rather than a hope. A renewal deletes the membership's reminders, opening a fresh cycle for the new term.

### Key rules (enforce in services, covered by tests)
1. **Price rule:** member price iff user has `active` membership at purchase time; discounts from the plan perks apply to merch.
2. **No oversell:** `UPDATE ticket_types SET sold_count = sold_count + :q WHERE id=:id AND sold_count + :q <= capacity` (0 rows → 409 `SOLD_OUT`). Same pattern for `product_variants.stock`.
3. **Payment success handler is idempotent** and, in ONE DB transaction: marks order paid → creates fulfilment → writes ledger `in` row. The `M2` Razorpay handler keys off `provider_ref`; the `M1` mock handler has no gateway callback to dedupe on, so it claims the order first — `UPDATE orders SET status='paid' WHERE id=:id AND status='pending'` — and a 0-row result means "already settled", so the caller replays the stored result instead of repeating the work. Both are the same idea: the conditional UPDATE is the lock.
4. **Check-in:** `UPDATE tickets SET status='used', checked_in_at=now() WHERE code=:c AND status='valid' AND event_id=:e` — row count decides valid vs already-used.
5. **Expense** can be `approved` only if `receipt_url` present; `reimbursed` creates ledger `out` row.
6. Membership expiry job (daily; `services.reminders.run_expiry_scan()` so tests can drive it directly): `active` & `end_date < today` → `expired` **and** an `expired` reminder; otherwise `active` & `end_date <= today+30d` → `expiry_30` reminder, plus `expiry_7` once it is within 7 days. At most one reminder per kind per membership, enforced by the unique constraint — so a scan that runs twice in a day is a no-op. Returns `{scanned, expired, reminders_created}`.
   **Academic year:** `end_date = start_date + plan.duration_months` only. The "cap to the academic year end" from the PRD is deliberately not applied — a one-year plan bought in month 3 would otherwise silently grant only 9 months. Revisit if the club decides dues are per-academic-year rather than rolling.
7. **Activation (part of the rule-3 transaction):** on a successful membership payment the member's `memberships` row goes `active`, `renewal_reminded_at` resets, its old reminders are cleared, a `member_code` is minted if the user has none (`SSA-<year>-NNNN`, sequential within the year), and the role is promoted `guest → member` **only** — paying dues can never demote a volunteer, organizer, treasurer or admin whose role was set deliberately.
8. **Ticket fulfilment (part of the rule-3 transaction):** a successful ticket payment marks the order `paid`, issues exactly `quantity` tickets with unique 10-character codes, and writes one ledger `in` row (`source=tickets`, `ref_type=order`, `event_id` from the order's meta). Idempotent twice over: the pending→paid claim guards a replayed callback, and the ticket issuer returns the existing tickets rather than minting more. Codes use an unambiguous alphabet (`ABCDEFGHJKMNPQRSTUVWXYZ23456789` — no `0/O/1/I/L`) because volunteers read them aloud at the door. Rule 1 applies at checkout, not at payment: the price is resolved and frozen when the order is created.
9. **Seats are reserved at checkout, not at payment** (so two shoppers cannot both be told there is one seat left), and released when the order dies: `mock-confirm {outcome:"fail"}` marks it `failed`, and a sweep every 5 minutes cancels ticket orders still `pending` after 15 minutes (`services.tickets.release_expired_pending_orders()`, called by the scheduler and directly by tests). Release never pushes `sold_count` below 0. A **free** ticket type skips payment entirely — seats reserved, tickets issued, no payment row and **no ledger row**, because nothing was earned.
10. **Announcement visibility is one filter, applied everywhere** (`services.announcements.visibility_clause`): guest → `audience='all'`; active member → `all` + `members`; anyone signed in who holds a `valid` **or** `used` ticket for the event → that event's `audience='event'` posts; organizer and above → everything. A post the caller may not see answers **404, never 403** — the existence of a members-only post is itself members-only news. Posting resolves the audience to recipients and writes all delivery rows in the **same transaction** as the post; a change to `title`/`body`/`category` requires `revision_note` (3+ chars) and copies the replaced version into `announcement_revisions` first, while `audience`/`event_id` are frozen after posting (422 `AUDIENCE_LOCKED`). Pin toggles need no note but still obey the limit of 3 (409 `PIN_LIMIT_REACHED`).
11. **Delivery worker** (`services.delivery_worker.process_queued_deliveries`): claims up to 100 `queued` rows with `SELECT … FOR UPDATE SKIP LOCKED` in one transaction (so two workers never send the same mail), sends `inapp` by marking it `sent`, and calls the email provider for the rest. Success → `sent` + `sent_at`; failure → `attempts += 1` + `error`, still `queued` until `attempts` reaches 3, then `failed` for good. A recipient who opted out after their mail was queued is marked `failed` with the reason rather than mailed. Idempotent: a second pass over the same rows sends nothing. Run by a 60-second APScheduler job **and** once immediately after a post via `BackgroundTasks`. Email is console-only in M1 (`EMAIL_PROVIDER=console`; any address at `fail.test` raises), behind the `EmailProvider` interface, so M2 swaps in a real sender without touching the worker.
12. **Merchandise** (`services/pricing.resolve_merch_unit_price`, `services.inventory`, `services/merch`):
    - **Member price** = `base_price` less the **larger** of `product.member_discount_pct` and the caller's **active** plan's `merch_discount_pct` (source `product` or `plan`), rounded half-up in integer paise: `unit_price = (base_price * (100 - pct) + 50) // 100`. No floats anywhere in the path. A guest, or a member whose membership has expired, pays `base_price`. The price is resolved and frozen on the `order_items` row at checkout, exactly like tickets — a later price change or lapse never rewrites an order. `MERCH_MEMBERS_ONLY=true` (default) requires an **active** membership to check out at all: 403 `MEMBERSHIP_REQUIRED`, which is the club's "merch is a member perk" rule and is one setting away from being switched off.
    - **Stock is reserved at checkout, not at payment** (the same reason as rule 9): `UPDATE product_variants SET stock = stock - :q WHERE id = :id AND stock >= :q AND is_active` — 0 rows → 409 `OUT_OF_STOCK` with `details {variant_id, product_name, size, available, requested}`. Lines are sorted by variant id so two overlapping checkouts always take row locks in the same order (no deadlock 500s), and the whole multi-line cart lives in the **one** order transaction: if line 3 is short, lines 1 and 2 are rolled back with it — never a half-reserved cart. Each line writes a `sale` movement. Limits: at most 5 lines and 1–5 per line (422 above that) — a cap on how much one person can take off a shelf that is only ever a few dozen units.
    - **Release** gives a dead order's stock back with a `release` movement, idempotent by marker: the order row is locked `FOR UPDATE`, then `orders.meta.stock_released` is checked, so a payment failure and the sweep racing over the same order cannot both credit the stock back. It happens when `mock-confirm {outcome:"fail"}` marks the order `failed`, and when the every-5-minute sweep (`services.merch.release_expired_pending_merch_orders`, same 15-minute TTL, `SKIP LOCKED`) cancels merch orders still `pending`. Confirming an order the sweep already cancelled → 409 `ORDER_NOT_PAYABLE`, so a late tap on the gateway cannot resurrect an order whose stock is gone; an already-*failed* order that is replayed (either outcome) changes nothing and releases nothing further.
    - **Fulfilment** (`merch_orders`) is created by the payment success handler inside rule 3's single transaction, at `paid`, with the ledger row (`source=merch`, `ref_type=order`, note `Merch sale - <items>`). It is idempotent twice over: the pending→paid claim stops a replayed confirmation, and `fulfil_merch_order` returns the existing row rather than creating a second one. So paying twice reserves once, credits the ledger once, and never takes a second item off the shelf. Fulfilment moves **forwards, one step at a time** — `paid → packed → handed_over`, 409 `INVALID_TRANSITION` with `details {from, to, allowed}` for anything else (including re-setting the current status) — and `packed_at`/`handed_over_at` record when it happened.
    - **Manual stock changes** (`adjust_stock`) are a conditional UPDATE too — `WHERE stock + delta >= 0` — so a write-off below zero is 409 `NEGATIVE_STOCK`, not a CHECK-constraint 500. `restock` and `adjustment` are the admin's only ways to move stock by hand; `PATCH /variants/{id}` deliberately cannot set `stock`.
    - **Stock status** is derived, never stored: `out_of_stock` at 0, `low` at 0 < stock ≤ `low_stock_threshold`, else `in_stock`. `GET /admin/merch/stock-summary` reports per product and per size what is on the shelf, what **sold** (units on `paid` orders) and what is merely **reserved** (units on `pending` orders, i.e. in someone's cart), plus demand by size — which is what tells you which size to reorder.

## 5. API Contract (prefix `/api/v1`, JSON, JWT Bearer)

**Error shape (all errors):** `{ "error": { "code": "SOLD_OUT", "message": "...", "details": {} } }`
**List shape:** `{ "items": [...], "total": 0, "page": 1, "page_size": 20 }`

### Auth & Users
| Method | Path | Role | Notes |
|---|---|---|---|
| POST | /auth/register | public | 201; body `{email, password, full_name, phone?, department?, year?}` → `{access_token, token_type, user}`, role=`guest` until plan paid |
| POST | /auth/login | public | `{access_token, token_type, user}` |
| GET | /auth/me | any | flat user fields (`id, email, full_name, phone, department, year, role, member_code, email_opt_in, is_active, created_at`) + nested `membership` = `{status, plan_name, end_date, days_left}`; `status` is `none` before the first membership |
| GET | /users | admin | search `q`, filter `role`,`status`, `page`, `page_size` |
| PATCH | /users/{id}/role | admin | 404 `USER_NOT_FOUND` |
| GET | /members/verify?code= or ?q= | volunteer+ | `{valid, status, name, member_code, valid_until, reason}` — `reason` explains a `false` (`Membership expired on …`, `Not a member`, …) and is `null` when valid. Also: a non-existent code answers **200** with `valid:false, reason:"No member found"` — scanning an unknown card is a normal door event, not a server error. 400 `MISSING_QUERY` when neither param is sent; 409 `AMBIGUOUS_QUERY` (with `details.member_codes`) when `q` matches several members, so staff retype the code instead of the API guessing |
| GET | /members/me/card | member | data for QR: `{member_code, full_name, status, valid_until}` |

### Memberships
| GET | /plans | public | active plans only, cheapest first |
| POST/PATCH | /plans, /plans/{id} | admin | 201; 409 `PLAN_NAME_TAKEN` on duplicate name |
| POST | /memberships/checkout | auth | 201; body `{plan_id}` → `{order_id, payment_id, amount, provider, status}`. Creates order(`membership`, `pending`) + order_item + `mock` payment intent. If the member is still active, the new period starts when the current one ends (see §4 rule 1); 404 `PLAN_NOT_FOUND` for a missing/inactive plan |
| GET | /memberships/me | auth | 404 `MEMBERSHIP_NOT_FOUND` before the first purchase |
| GET | /memberships | admin | filter `status`, `expiring_within_days`, `page`, `page_size` |
| GET | /memberships/renewals-due | admin | `active` memberships ending within 30 days, each with `days_left` |

### Events, Tickets, Check-in
| GET | /events | public | published only, soonest first. Items are a summary: `{id, title, venue, starts_at, ends_at, banner_url, status, min_price, seats_left}` — `min_price` is the cheapest price **for the caller** (member price with a token, else non-member) and `seats_left` sums every ticket type. Filters `upcoming=true`, `q` (title or venue), `page`, `page_size`. `include_drafts=true` also returns drafts: **401** anonymous, **403** below organizer |
| GET | /events/{id} | public | 404 for a non-`published` event unless the caller is organizer+. `ticket_types[]` = `{id, event_id, name, member_price, non_member_price, capacity, sold_count, seats_left, is_on_sale, price_for_you, sale_starts_at, sale_ends_at}`; `price_for_you` is **null for an anonymous caller** (there is no "you"), else the price that caller would pay — both list prices are always present |
| POST | /events | organizer+ | 201; new events always start as `draft`. 422 `VALIDATION_ERROR` when `ends_at <= starts_at` |
| PATCH | /events/{id} | organizer+ | `draft → published → closed` only; 409 `INVALID_STATUS_TRANSITION` with `details {from, to}` for anything else (an event never un-publishes) |
| POST | /events/{id}/ticket-types | organizer+ | 201 → the ticket type, with `seats_left` and `is_on_sale` |
| PATCH | /ticket-types/{id} | organizer+ | 404 `TICKET_TYPE_NOT_FOUND`; 409 `CAPACITY_BELOW_SOLD` with `details {sold_count, capacity}` when the new capacity would strand sold seats |
| POST | /tickets/checkout | auth | `{ticket_type_id, quantity}` (quantity **1..10**, else 422) → 201 `{order_id, payment_id, amount, unit_price, is_member_price, quantity, provider, status, tickets}`. Honours an `Idempotency-Key` header: the same key replays the same order instead of reserving seats twice. 409 `SOLD_OUT` with `details {seats_left, requested}`, 409 `EVENT_NOT_ON_SALE` (draft/closed), 409 `NOT_IN_SALE_WINDOW` (outside `sale_starts_at`/`sale_ends_at`). A **free** ticket type returns `status:"paid"`, `payment_id:null` and the tickets already filled — nothing to pay, so nothing to confirm |
| GET | /tickets/me | auth | paginated tickets, **upcoming first** (soonest at the top, then past events most-recent-first), each with event title/date/venue and the QR `code` |
| GET | /tickets/{id} | auth | owner or organizer+ (403 otherwise), 404 `TICKET_NOT_FOUND` |
| POST | /checkin | volunteer+ | `{event_id, code}`. **Always 200** for the four door outcomes: `{result: VALID\|ALREADY_USED\|INVALID\|WRONG_EVENT, ticket, holder_name, ticket_type, checked_in_at, message, checked_in, sold}` — `ticket` is null when nothing matched, `message` is human-readable for the scanner, and `checked_in`/`sold` drive its live counter. The code is normalised (spaces stripped, upper-cased) so a scanner's noise is harmless. A voided ticket is `INVALID`; a ticket for another event is `WRONG_EVENT` and names that event |
| GET | /events/{id}/report | organizer+ | `{event_id, title, status, tickets_sold, seats_total, seats_left, checked_in, no_shows, attendance_rate, revenue{member, non_member, total}, by_ticket_type[]}`. `tickets_sold` counts `valid`+`used`; `seats_left` is live availability (`seats_total - sum(sold_count)`) so it agrees with `GET /events/{id}`; `attendance_rate` is a percentage (0 when nothing sold); revenue is integer paise summed from `tickets.price_paid`. Per type: `{ticket_type_id, name, capacity, sold, seats_left, checked_in, revenue}` |
| GET | /events/{id}/attendees | organizer+ | paginated `{ticket_id, code, status, holder_name, holder_email, ticket_type, price_paid, is_member_price, checked_in_at}`; filter `status=valid\|used\|void`, search `q` over name, email or code |

### Announcements
| Method | Path | Role | Notes |
|---|---|---|---|
| GET | /announcements | public (optional Bearer) | **pinned first, then `published_at` desc.** Filters `category`, `q` (title or body), `pinned` (`true` = pinned only, `false` = unpinned only), `page`, `page_size`. Items: `{id, title, category, audience, event_id, is_pinned, author_name, published_at, edited_at, body_preview}` — `body_preview` is the first 200 characters and `edited_at` is `null` until the post is edited. What comes back depends on the caller (§4 rule 10) |
| GET | /announcements/{id} | public/member | the detail: the same fields plus the full `body` and `revision_note`. **404, never 403**, for a post outside your audience — hidden and nonexistent are deliberately indistinguishable, so an unknown id and a members-only one answer identically |
| POST | /announcements | organizer+ | 201 → the announcement plus `delivery_summary: {inapp_queued, email_queued, skipped_opted_out}`. `{title 3–120, body 1–5000, category, audience (default "all"), event_id?, is_pinned (false), send_email (false)}`. 422 `EVENT_REQUIRED` (audience=event with no event_id) / `EVENT_NOT_ALLOWED` (event_id with another audience), 404 `EVENT_NOT_FOUND`, 409 `PIN_LIMIT_REACHED` on a 4th pinned post. The summary counts what was **queued** in the same transaction, not what was sent — the worker runs right after the response, so `GET …/deliveries` is the receipt |
| PATCH | /announcements/{id} | organizer+ | `{title?, body?, category?, is_pinned?, revision_note?}`. A real change to title/body/category without a `revision_note` of 3+ characters → 422 `REVISION_NOTE_REQUIRED`; the replaced version is copied into `announcement_revisions` before the change lands. `audience` and `event_id` are frozen after posting → 422 `AUDIENCE_LOCKED` (they are accepted in the body only so that attempt is a clear error, not a silent no-op). `is_pinned` needs no note but still counts against the limit. Re-sending the current value is a no-op, not a change |
| GET | /announcements/{id}/revisions | organizer+ | paginated edit history **newest first**; each row `{id, title, body, category, audience, edited_by, edited_by_name, edited_at, note}` is the version that was *replaced*, so the oldest row holds the original text. 404 for an unknown id |
| GET | /announcements/{id}/deliveries | admin | `{announcement_id, summary: {email: {queued, sent, failed}, inapp: {...}, total_recipients}, items: {items, total, page, page_size}}`; filters `channel=email\|inapp`, `status=queued\|sent\|failed`, `page`, `page_size`. `summary` always counts the whole announcement even when `items` is filtered. Each item: `{id, user_id, user_name, user_email, channel, status, attempts, error, sent_at}` |
| GET / POST | /users/me/email-preferences | auth | `{email, email_opt_in}` — the switch for announcement **email** only; in-app notices arrive either way |
| GET | /unsubscribe?token=… | public | the link at the foot of every announcement email (signed JWT, purpose `unsubscribe`, long expiry; no session needed) → `{unsubscribed: true, email: "m*****@ssa.org"}`, masked so the page can confirm which inbox changed without disclosing it. Sets `email_opt_in=false`; safe to click twice. 400 `INVALID_TOKEN` for expired, tampered, foreign-signed or wrong-purpose tokens; 422 when `token` is missing |

**No DELETE for an announcement** — PRD FR-3.2: the record of what was said, and when, is permanent. Corrections are edits with a revision note, and the trail stays readable.

### Merchandise
| Method | Path | Role | Notes |
|---|---|---|---|
| GET | /products | public | the shelf, **active products only, A–Z by name**. Filters `q` (name or description), `page`, `page_size`. `include_inactive=true` also returns retired products: **403** for anyone below admin (anonymous included) |
| GET | /products/{id} | public | one product, same shape. A retired product answers **404** for everyone below admin |
| POST | /products | admin | 201; `{name 2–80, description?, image_url?, base_price > 0, member_discount_pct 0–100 (default 0), is_active (true)}`. Starts with no variants, so `total_stock` is 0 until one is added |
| PATCH | /products/{id} | admin | any subset of the create fields; 404 `PRODUCT_NOT_FOUND` |
| POST | /products/{id}/variants | admin | 201 → the variant. `{size 1–20, color?, sku 1–40, stock (0), low_stock_threshold (5), is_active (true)}`. The opening `stock` is written to the audit trail as an `initial` movement, so `SUM(delta)` rebuilds the shelf from zero. 404 `PRODUCT_NOT_FOUND`, 409 `SKU_TAKEN` on a duplicate sku, 409 `VARIANT_TAKEN` on a duplicate size/colour for the product |
| PATCH | /variants/{id} | admin | `{size?, color?, sku?, low_stock_threshold?, is_active?}` — **stock is deliberately not settable here**; it moves through stock-adjust so every change leaves an audit row. 404 `VARIANT_NOT_FOUND`, 409 `SKU_TAKEN` / `VARIANT_TAKEN` |
| POST | /variants/{id}/stock-adjust | admin | `{delta (signed), reason: "restock"\|"adjustment", note?}` → the updated variant. 404 `VARIANT_NOT_FOUND`, 409 `NEGATIVE_STOCK` with `details {variant_id, stock, delta}` when the change would go below zero. Reaching 0 only changes how the size is *labelled* (`out_of_stock`); the variant stays active, because the size still exists — set `is_active=false` to retire it |
| GET | /variants/{id}/stock-movements | admin | paginated audit trail, **newest first**: `{id, variant_id, delta, reason, order_id, created_by, created_by_name, note, created_at}` |
| POST | /orders/merch/checkout | auth (member, see below) | 201 → `{order_id, payment_id, amount, subtotal, discount, items[{variant_id, product_name, size, color, qty, unit_price, line_total}], delivery_method, provider, status, expires_at}`. Body `{items: [{variant_id, qty 1–5}] (1–5 lines), delivery_method: "pickup"\|"campus_delivery" (pickup), delivery_note?}`. **Stock is reserved here, not at payment.** Honours `Idempotency-Key`. 403 `MEMBERSHIP_REQUIRED` when `MERCH_MEMBERS_ONLY` and the caller has no active membership; 409 `OUT_OF_STOCK` with `details {variant_id, product_name, size, available, requested}`; 409 `PRODUCT_UNAVAILABLE` for a variant the club has retired or deactivated; 422 `DELIVERY_NOTE_REQUIRED` for a campus delivery with no note (5+ characters), `DUPLICATE_VARIANT` when the same variant is sent twice, `VALIDATION_ERROR` for more than 5 lines or a qty outside 1–5. `items` is the frozen receipt line — the price is resolved once, here |
| GET | /orders/me | auth | paginated own orders, **newest first**, every kind. Filter `kind=membership\|ticket\|merch`. Each item: `{id, kind, status, subtotal, discount, total, currency, created_at, items[{item_type, name, quantity, unit_price, line_total}], payment_status, fulfilment_status, delivery_method, delivery_note, packed_at, handed_over_at}` — the last five are `null` for anything that is not merch. `name` is the human label (plan, ticket type or `SSA Hoodie (M)`) |
| GET | /orders/{id} | auth | the same shape for one order. Owner or admin; **404** for anyone else (not 403 — someone else's order is none of your business, and its existence is not either) |
| GET | /admin/merch/orders | admin | the fulfilment board: `{counts: {paid, packed, handed_over}, items: Page}` where `counts` always counts the **whole** board and `items` is filtered. Filters `fulfilment_status`, `product_id`, `size`, `q` (buyer name/email/member code), `page`, `page_size`. Each row: `{order_id, buyer{name, email, member_code, phone}, items_summary, items[], total, delivery_method, delivery_note, fulfilment_status, created_at, packed_at, handed_over_at}` |
| PATCH | /admin/merch/orders/{id} | admin | `{fulfilment_status}` — `paid → packed → handed_over`, **one step at a time and forwards only**. 409 `INVALID_TRANSITION` with `details {from, to, allowed}` for anything else, including re-sending the status it already has. Stamps `packed_at`/`handed_over_at` and records `handled_by`. 404 `MERCH_ORDER_NOT_FOUND` for a non-merch or unknown order |
| GET | /admin/merch/stock-summary | admin | `{products[{product_id, name, is_active, total_stock, sold_units, reserved_units, low_stock_count, out_of_stock_count, variants[{variant_id, size, color, sku, stock, sold_units, reserved_units, low_stock_threshold, low_stock, out_of_stock}]}], demand_by_size[{size, stock, sold_units, reserved_units}], totals{stock, sold_units, reserved_units}}`. `sold_units` counts **paid** orders, `reserved_units` counts orders still awaiting payment — so "we sold 12 mediums" is never confused with "12 mediums are sitting in someone's cart" |

**Product shape** (every endpoint above): `{id, name, description, image_url, base_price, member_discount_pct, is_active, price_range{min, max}, total_stock, variants[{id, size, color, sku, stock, stock_status, is_active}], price_for_you, is_member_price}`. `price_range` is the price **this caller** would pay at both ends (one price level per product today, so `min == max`; the shop grid renders "from ₹X" and stays correct if per-size pricing ever arrives). `price_for_you` and `is_member_price` are **null for an anonymous caller** — there is no "you" to price for. `stock_status` is `in_stock` / `low` / `out_of_stock` (§4 rule 12).

**What is NOT here, on purpose:** there is no DELETE for a product or variant (retire it with `is_active=false` — past orders must keep resolving their lines), no cart, no shipping fee, no payment gateway for merch beyond the mock, and no public ledger endpoint (§6's finance routes stay treasurer-only).

### Fundraisers & Tasks
| GET/POST | /fundraisers | organizer+ | |
| GET | /fundraisers/{id} | volunteer+ | includes progress `{tasks_total, done, overdue, raised, goal}` |
| GET/POST | /fundraisers/{id}/tasks | volunteer+ / organizer+ | |
| PATCH | /tasks/{id} | assignee or organizer+ | status, assignee |
| POST | /fundraisers/{id}/income | organizer+ | logs income → ledger |

### Payments (M1 mock)
| POST | /payments/{order_id}/mock-confirm | auth | body `{outcome: "success"\|"fail"}` simulates the gateway. Owner or admin only (403 otherwise). Returns `{order_id, payment_id, order_status, payment_status, provider_ref, membership, tickets, merch}` — the dispatcher keys off `order.kind`, so a `membership` order fills `membership` (and leaves `tickets`/`merch` `null`), a `ticket` order fills `tickets`, and a `merch` order fills `merch` = `{order_id, fulfilment_status, delivery_method, delivery_note, packed_at, handed_over_at}` (the others stay `null`). Safe to call twice: the second call returns the same body and changes nothing (§4 rule 3). On `fail`: payment `failed`, order `failed`, membership untouched, tickets' seats released and merch stock released once (§4 rule 12). Cancelling an order the sweep already expired → 409 `ORDER_NOT_PAYABLE` whichever outcome is sent, because its stock is already back on the shelf. An order that already **failed** is not an error: a repeat `fail` releases nothing further (one `release` movement, never two) and a `success` aimed at it cannot revive it — the claim finds no `pending` row and the stored failure is replayed. No path pays for stock that has gone back |
| POST | /payments/webhook | provider | M2 Razorpay |

### Expenses & Finance
| POST | /expenses | volunteer+ | multipart w/ receipt |
| GET | /expenses/me | volunteer+ | |
| GET | /expenses | treasurer | filter status |
| PATCH | /expenses/{id}/review | treasurer | `{decision: approve|reject, note}` |
| POST | /expenses/{id}/reimburse | treasurer | writes ledger out |
| GET | /finance/summary | treasurer/admin | `{total_in,total_out,balance,by_source,by_category,pending_reimbursements}` |
| GET | /finance/transactions | treasurer/admin | filters: date, source, event |
| GET | /finance/by-event, /finance/by-fundraiser | treasurer/admin | |
| POST | /finance/transactions | treasurer | manual income/expense |

## 6. Frontend Design

### Design language
Clean, modern campus-club feel. Primary: deep indigo `#4338CA`; accent: amber `#F59E0B`; success green, danger red; neutral slate. Font: Inter. Rounded-xl cards, soft shadows, generous spacing. Mobile-first, dark mode optional (M2). Skeleton loaders, toasts, empty states with illustrations, form validation messages inline.

### Route map
**Public:** `/` landing (hero, next event, latest announcement, join CTA) · `/events` · `/events/:id` · `/announcements` · `/announcements/:id` · `/unsubscribe` (target of the email footer link, reads `?token=`) · `/shop` · `/shop/:id` · `/join` (plans) · `/login` · `/register`
**Member:** `/me` dashboard (membership status/renew banner, QR member card, upcoming tickets) · `/me/tickets` · `/me/orders` · `/checkout/:orderId`
**Staff:** `/staff/scan` (door scanner, big green/red result, event picker) · `/staff/verify-member`
**Organizer:** `/manage/events` (+ create/edit, ticket types, report) · `/manage/announcements` · `/manage/fundraisers` (+ `/:id` kanban board) 
**Admin:** `/admin/members` · `/admin/plans` · `/admin/renewals` · `/admin/products` · `/admin/merch-orders` · `/admin/users`
**Treasurer:** `/finance` dashboard (cards + charts + tables) · `/finance/expenses` review queue · `/finance/ledger` · `/finance/report` (printable)
**Volunteer:** `/tasks` (my tasks) · `/expenses/new`

### Key screen specs
- **Event page:** banner, date/venue, ticket type cards showing member vs non-member price (highlight the one that applies to the viewer), "seats left" progress bar, sold-out state.
- **Door scanner:** camera scan + manual code field; full-screen result colour (green VALID / amber ALREADY USED w/ time / red INVALID); live counter "checked in 87 / 120".
- **Member card:** QR + name + status chip (Active until DD MMM YYYY).
- **Kanban:** 3 columns, drag between columns, assignee avatars, due-date chips (red if overdue), progress ring on top + raised-vs-goal bar.
- **Treasurer dashboard:** 4 KPI cards (In, Out, Balance, Pending reimbursements), donut by source, bar by category, recent transactions, per-event profit table.
- **Shop:** product grid, size selector with per-size stock ("Only 3 left"), cart drawer, mobile-friendly checkout.

### Frontend rules
- API client in `src/api/` generated from types matching this contract; all money displayed via `formatINR(paise)`.
- Use TanStack Query; auth token in memory + refresh via `localStorage` (M1 acceptable).
- Until backend phase endpoints land, use **mock handlers (MSW)** matching this contract; switch with `VITE_USE_MOCKS=false`.

## 7. Seed Data (for demos)
Admin, treasurer, organizer, volunteer, 20 members (some expiring in 10/25 days, some expired), 3 plans, 6 announcements, hoodie + T-shirt with S–XXL stock, a Bake Sale fundraiser with 8 tasks, 6 expenses in different states, auto-generated ledger.

**Events (Phase 2):** Spring Gala (published, in 14 days) with General 120 seats / VIP 20 — 85 General sold with 60 already scanned in, and VIP deliberately nearly gone at 19/20; Coding Workshop (published, free, 40 seats, 10 registered); Annual Meet (draft); Farewell 2025 (closed, in the past, with used tickets). Every seeded ticket is sold through the real checkout service, so `sold_count` and the ledger agree with the report.

**Announcements (Phase 3):** 6 posts across all four categories — one pinned "Welcome to Spring Semester" (`all`), a members-only AGM (`deadline`), an event post for Spring Gala ("Doors open 6 PM, bring your QR ticket", `audience=event`), a general one, and one edited twice so `announcement_revisions` has two rows and the post shows an `edited_at`. Deliveries are written by the real service and drained by the real worker, so the admin view shows all three states: 3 members have `email_opt_in=false` (in-app only) and `bouncing@fail.test` always fails, giving one visible `failed` row with its error after 3 attempts.

**Merchandise (Phase 4):** SSA Hoodie (₹999, 10% member discount, opening stock S 0 / M 8 / L 10 / XL 6 / XXL 1) and SSA T-Shirt (₹499, 15%, 10/15/15/10/5), plus a retired "Old Mug" (₹299) that only an admin can see — the empty Hoodie S/XXL are deliberate, so the shop shows a sold-out size and a "1 left" size without staging anything. 12 orders are bought through the **real** checkout and payment services (6 left `paid`, 4 walked to `packed`, 2 to `handed_over`) with a mix of pickup and campus delivery, so `merch_orders`, the ledger's `source=merch` rows and `stock_movements` all agree. The seed finishes by asserting `SUM(stock_movements.delta) == product_variants.stock` for every variant and prints the count, which is the same invariant the tests check.
