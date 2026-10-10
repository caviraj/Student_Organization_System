# DESIGN — SSA Hub (Architecture, Data Model, API Contract, UI)

> This file is the **contract** between Backend (Caviraj) and Frontend (Dinesh). If an endpoint or field changes, update this file in the same PR.

---

## 1. Tech Stack
| Layer | Choice |
|---|---|
| Frontend | React 19 + TypeScript + Vite, Tailwind CSS, React Router, TanStack Query, Zod, `qrcode.react`, `html5-qrcode` (scanner), Recharts |
| Backend | Python 3.11+, FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2, PyJWT, `bcrypt` (used directly; `passlib` dropped — it is unmaintained and its bcrypt backend lags bcrypt 4.x), APScheduler (reminder job) |
| DB | PostgreSQL (Supabase-hosted; local Docker Postgres for dev). `DATABASE_URL` defaults to a local SQLite file so the API, tests and demo run with zero setup; models/migrations are portable across both |
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
│  │  │            announcements, products, orders, fundraisers, tasks,
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

**announcements**: id, title, body, category (`meeting|deadline|change|general`), audience (`all|members|event`), event_id?, is_pinned, author_id, published_at, revision_note
**announcement_deliveries**: id, announcement_id, user_id, channel (`email|inapp`), status (`queued|sent|failed`), sent_at

**products**: id, name, description, image_url, base_price, member_discount_pct, is_active
**product_variants**: id, product_id, size, color?, sku, stock, low_stock_threshold
  *constraint:* `stock >= 0`

**merch_orders** (extension of orders for fulfilment): order_id PK, fulfilment_status (`paid|packed|handed_over`), delivery_note

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
| GET | /announcements | public/member | audience filtered; paginated |
| POST | /announcements | organizer+ | creates deliveries |
| PATCH | /announcements/{id} | organizer+ | adds revision note |
| GET | /announcements/{id}/deliveries | admin | |
| POST | /users/me/email-preferences | auth | opt in/out |

### Merchandise
| GET | /products | public | with variants & `stock` |
| POST/PATCH | /products, /products/{id}, /products/{id}/variants | admin | |
| POST | /orders/merch/checkout | member | `{items:[{variant_id, qty}], delivery_note}` |
| GET | /orders/me | auth | |
| GET | /admin/merch/orders | admin | filter fulfilment_status |
| PATCH | /admin/merch/orders/{id} | admin | set fulfilment_status |
| GET | /admin/merch/stock-summary | admin | per product/size remaining + demand |

### Fundraisers & Tasks
| GET/POST | /fundraisers | organizer+ | |
| GET | /fundraisers/{id} | volunteer+ | includes progress `{tasks_total, done, overdue, raised, goal}` |
| GET/POST | /fundraisers/{id}/tasks | volunteer+ / organizer+ | |
| PATCH | /tasks/{id} | assignee or organizer+ | status, assignee |
| POST | /fundraisers/{id}/income | organizer+ | logs income → ledger |

### Payments (M1 mock)
| POST | /payments/{order_id}/mock-confirm | auth | body `{outcome: "success"\|"fail"}` simulates the gateway. Owner or admin only (403 otherwise). Returns `{order_id, payment_id, order_status, payment_status, provider_ref, membership, tickets}` — the dispatcher keys off `order.kind`, so a `membership` order fills `membership` (and leaves `tickets` empty) while a `ticket` order fills `tickets` (and leaves `membership` `null`). Safe to call twice: the second call returns the same body and changes nothing (§4 rule 3). On `fail`: payment `failed`, order `failed`, membership untouched and tickets' seats released |
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
**Public:** `/` landing (hero, next event, latest announcement, join CTA) · `/events` · `/events/:id` · `/announcements` · `/shop` · `/shop/:id` · `/join` (plans) · `/login` · `/register`
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
Admin, treasurer, organizer, volunteer, 20 members (some expiring in 10/25 days, some expired), 3 plans, 3 announcements, hoodie + T-shirt with S–XXL stock, a Bake Sale fundraiser with 8 tasks, 6 expenses in different states, auto-generated ledger.

**Events (Phase 2):** Spring Gala (published, in 14 days) with General 120 seats / VIP 20 — 85 General sold with 60 already scanned in, and VIP deliberately nearly gone at 19/20; Coding Workshop (published, free, 40 seats, 10 registered); Annual Meet (draft); Farewell 2025 (closed, in the past, with used tickets). Every seeded ticket is sold through the real checkout service, so `sold_count` and the ledger agree with the report.
