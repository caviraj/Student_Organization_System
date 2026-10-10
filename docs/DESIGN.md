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
  *constraint:* `sold_count <= capacity`

**orders**: id, user_id, kind (`membership|ticket|merch`), status (`pending|paid|failed|cancelled|refunded`), subtotal, discount, total, currency=`INR`, meta JSONB, idempotency_key

**order_items**: id, order_id, item_type (`plan|ticket_type|variant`), item_id, quantity, unit_price, line_total

**payments**: id, order_id, provider (`mock|razorpay`), provider_ref, status (`created|succeeded|failed`), amount, raw JSONB

**tickets**: id, order_id, event_id, ticket_type_id, user_id, code (unique, short random), status (`valid|used|void`), price_paid, is_member_price, checked_in_at, checked_in_by

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
6. Membership expiry job: `active` & `end_date < today` → `expired`; `end_date <= today+30d` → reminder row.

## 5. API Contract (prefix `/api/v1`, JSON, JWT Bearer)

**Error shape (all errors):** `{ "error": { "code": "SOLD_OUT", "message": "...", "details": {} } }`
**List shape:** `{ "items": [...], "total": 0, "page": 1, "page_size": 20 }`

### Auth & Users
| Method | Path | Role | Notes |
|---|---|---|---|
| POST | /auth/register | public | returns user + token, role=`guest` until plan paid |
| POST | /auth/login | public | `{access_token, token_type, user}` |
| GET | /auth/me | any | user + membership summary |
| GET | /users | admin | search `q`, filter `role`,`status` |
| PATCH | /users/{id}/role | admin | |
| GET | /members/verify?code= or ?q= | volunteer+ | `{valid, status, name, member_code, valid_until}` |
| GET | /members/me/card | member | data for QR (member_code) |

### Memberships
| GET | /plans | public | |
| POST/PATCH | /plans, /plans/{id} | admin | |
| POST | /memberships/checkout | auth | `{plan_id}` → order+payment intent |
| GET | /memberships/me | auth | |
| GET | /memberships | admin | filter `status`, `expiring_within_days` |
| GET | /memberships/renewals-due | admin | |

### Events, Tickets, Check-in
| GET | /events | public | published only (organizer sees drafts) |
| GET | /events/{id} | public | includes ticket_types with `seats_left` |
| POST/PATCH | /events, /events/{id} | organizer+ | |
| POST | /events/{id}/ticket-types | organizer+ | |
| POST | /tickets/checkout | auth | `{ticket_type_id, quantity}` → order+payment intent; 409 `SOLD_OUT` |
| GET | /tickets/me | auth | with QR `code` |
| POST | /checkin | volunteer+ | `{event_id, code}` → `{result: VALID|ALREADY_USED|INVALID|WRONG_EVENT, ticket, checked_in_at}` |
| GET | /events/{id}/report | organizer+ | sold, seats_left, checked_in, no_shows, attendance_rate, revenue{member,non_member,total} |
| GET | /events/{id}/attendees | organizer+ | |

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
| POST | /payments/{order_id}/mock-confirm | auth | body `{outcome: "success"|"fail"}` simulates gateway |
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
Admin, treasurer, organizer, volunteer, 20 members (some expiring in 10/25 days, some expired), 3 plans, 2 events (Spring Gala: 120 seats; Workshop: 40), 3 announcements, hoodie + T-shirt with S–XXL stock, a Bake Sale fundraiser with 8 tasks, 6 expenses in different states, auto-generated ledger.
