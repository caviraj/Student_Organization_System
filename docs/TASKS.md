# TASKS — Phase Plan, Ownership & Demo/Push Gates

Team: **Backend = Caviraj** (Claude Code + DeepSeek) · **Frontend = Dinesh Kumar** (Antigravity + Gemini)
Rule: **a phase is DONE only when its Demo Gate passes and code is pushed + tagged.**

---

## Working Agreement
1. **Contract first:** DESIGN.md §5 is law. Frontend builds against MSW mocks, then flips to real backend.
2. **Branches:** `main` (always demo-able) ← PRs from `be/phase-N-<topic>` and `fe/phase-N-<topic>`. Squash merge.
3. **Commits:** Conventional Commits (`feat(events): ...`, `fix(checkin): ...`).
4. **Push gate (every phase):**
   ```
   git add -A && git commit -m "feat(phase-N): <summary>"
   git push -u origin <branch>      # open PR → merge to main
   git tag phase-N-done && git push --tags
   ```
5. **Visibility per phase (mandatory):**
   - **Backend:** (a) Swagger `/docs` shows all new endpoints, (b) `backend/scripts/demo_phaseN.sh` runs a real flow with curl and prints results, (c) `pytest` green, (d) 3–5 screenshots/GIF saved in `docs/demos/phaseN/`.
   - **Frontend:** (a) `npm run dev` pages working, (b) screenshots/GIF in `docs/demos/phaseN/`, (c) `npm run build` passes.
   - Both update the **Phase Log** at bottom of this file.
6. **Sync points:** at phase start (confirm contract) and phase end (integration test together).

---

# MILESTONE 1 — CORE

## Phase 0 — Foundation (Day 1)
| Backend (Cavi) | Frontend (Dinesh) |
|---|---|
| Repo scaffold, FastAPI app, config, DB connection, Alembic init, health endpoint, error handler, CORS, `.env.example`, CI (pytest) | Vite+React+TS+Tailwind scaffold, router, layout shell (navbar, sidebar by role), design tokens, API client, MSW mocks, auth context skeleton |
**Demo Gate:** `/health` + `/docs` live; frontend shell renders role-based menu. **Push & tag `phase-0-done`.**

## Phase 1 — Auth & Membership
| Backend | Frontend |
|---|---|
| Models: users, plans, memberships, orders, payments, transactions. Register/login/me, RBAC deps, plans CRUD, membership checkout with Mock payment, auto member_code, ledger entry on dues, verify endpoint, expiry job + reminders, renewals-due | Landing, Register/Login, Join (plans) + mock checkout, Member dashboard (status chip, QR card, renew banner), Admin members table, plans admin, renewals list, verify-member page |
**Demo Gate:** sign up → pay dues → become Active → QR card → admin verifies → shows in ledger. 

## Phase 2 — Events, Tickets, Check-in
| Backend | Frontend |
|---|---|
| events, ticket_types, tickets; pricing service (member/non-member); atomic capacity; ticket checkout; check-in endpoint; event report/attendees; tests for oversell & double check-in | Events list/detail with seats-left bar, ticket checkout, My Tickets with QR, organizer event create/edit + ticket types, **door scanner page**, event report page |
**Demo Gate:** buy ticket as member vs non-member (different price) → scan → second scan says ALREADY USED → report shows attendance & revenue; last seat can't be oversold.

## Phase 3 — Announcements
| Backend | Frontend |
|---|---|
| announcements + deliveries, audience filtering, pinned, revisions, email opt-in, simulated delivery worker | Public feed, organizer composer, history view with delivery counts, member email preference toggle |
**Demo Gate:** one post → visible in feed + N delivery records; history preserved.

## Phase 4 — Merchandise
| Backend | Frontend |
|---|---|
| products, variants (stock), merch checkout with atomic decrement, member discount, merch_orders fulfilment, stock summary | Shop grid, product detail with size/stock, cart + checkout, My Orders, admin products/stock editor, order board, stock summary |
**Demo Gate:** order hoodie size M until stock hits 0 → blocked; order board moves paid→packed→handed over; ledger shows merch income.

## Phase 5 — Fundraiser & Tasks
| Backend | Frontend |
|---|---|
| fundraisers, tasks, progress calc, income logging → ledger | Fundraiser list, detail with Kanban (drag/drop), progress ring, raised vs goal, my tasks page |
**Demo Gate:** bake sale with 8 tasks; move cards; progress updates; log ₹ raised.

## Phase 6 — Expenses & Treasurer Finance
| Backend | Frontend |
|---|---|
| expenses w/ receipt upload (Supabase Storage), review/approve/reject/reimburse, finance summary/by-event/by-fundraiser/transactions, manual entries | Expense claim form, my claims, treasurer review queue, finance dashboard (KPIs + charts), ledger table with filters, printable semester report |
**Demo Gate:** volunteer claims → treasurer approves → reimburses → balance drops; dashboard totals reconcile with ledger.

## Phase 7 — Integration, Seed, Polish, Deploy
| Both |
|---|
| Seed script, end-to-end happy-path run, bug bash, mobile responsiveness pass, empty/loading/error states, README with screenshots, deploy (Vercel + Render + Supabase), 3-min demo script |
**Demo Gate (Milestone 1 sign-off):** full semester story from PRD §8 works on deployed URL. **Tag `v1.0-m1`.**

---

# MILESTONE 2 — ADVANCED (starts after `v1.0-m1`)
| Phase | Backend | Frontend |
|---|---|---|
| M2-P1 Real payments | Razorpay provider, webhook signature verify, refunds | Razorpay checkout widget, refund UI |
| M2-P2 Messaging | Email via Resend/SMTP, templates, auto reminders 30/7/1 days, unsubscribe links, WhatsApp share links | Templates preview, delivery status UI |
| M2-P3 Offline scanner | Bulk ticket-sync endpoint, signed ticket QR payloads | PWA + service worker, offline queue + sync |
| M2-P4 Analytics & exports | Aggregation endpoints, CSV/PDF exports | Charts (growth, attendance, demand), export buttons |
| M2-P5 Budgets & audit | Category budgets/alerts, audit log, 2FA, rate limit | Budget bars, audit viewer, 2FA screens |
| M2-P6 Smart extras | Waitlist, promo codes, ticket transfer, receipt OCR + announcement drafting (LLM) | Matching UIs, dark mode, notification center, .ics export |

---

## Definition of Done (every phase)
- [ ] Contract matches DESIGN.md (or DESIGN.md updated)
- [ ] Tests pass (`pytest`, `npm run build`)
- [ ] Demo artifacts in `docs/demos/phaseN/`
- [ ] Pushed, PR merged, tag created
- [ ] Phase Log updated

## Phase Log
| Phase | Backend done | Frontend done | Demo link/screens | Tag |
|---|---|---|---|---|
| 0 | ☐ | ☐ | | |
| 1 | ☐ | ☐ | | |
| 2 | ☐ | ☐ | | |
| 3 | ☐ | ☐ | | |
| 4 | ☐ | ☐ | | |
| 5 | ☐ | ☐ | | |
| 6 | ☐ | ☐ | | |
| 7 | ☐ | ☐ | | |
