# PRD — Skyline Student Association Platform (SSA Hub)

**Version:** 1.0 | **Team:** Dinesh Kumar (Frontend), Caviraj (Backend) | **Status:** Approved for build

---

## 1. Problem
Skyline Student Association (SSA) runs on a spreadsheet (members), cash at the door (tickets), a notebook (budget), WhatsApp (announcements) and paper receipts (reimbursements). Result: members lose track of events, money goes missing, nobody knows who owes what.

## 2. Product Vision
**One platform** for the club's three pillars: **Events, Members, Money**. Every rupee that enters or leaves must be traceable to a member, an event, an order or an expense.

## 3. Users & Roles
| Role | Who | Can do |
|---|---|---|
| **Guest** | Public visitor | See public events, announcements, shop, sign up |
| **Member** | Paid-up student | Buy tickets/merch at member price, see own tickets/orders/membership, renew |
| **Volunteer** | Member helping with an event/fundraiser | See and update assigned tasks, submit expense claims, scan tickets at door (if granted) |
| **Organizer** | Event/fundraiser lead | Create events, ticket types, fundraisers, tasks, announcements |
| **Treasurer** | Finance owner | Approve/reject expenses, see full ledger, reports, close the semester |
| **Admin (President)** | Leadership | Everything + manage roles, plans, members |

Roles are additive via a `role` field on user (single primary role in M1 is fine; hierarchy: admin > treasurer > organizer > volunteer > member > guest).

## 4. Milestone Strategy
- **Milestone 1 (Core):** every scene in the problem statement works end-to-end with a **simulated payment provider**. Demoable, clean, deployable.
- **Milestone 2 (Advanced):** real payments, email/WhatsApp delivery, offline scanner, analytics, exports, audit, polish.

Each milestone is split into **phases**; every phase ends with a **visible demo + GitHub push** (see TASKS.md).

## 5. Milestone 1 — Functional Requirements

### FR-1 Membership
- FR-1.1 Public sign-up form: name, email, password, phone, department, year.
- FR-1.2 Admin defines **membership plans** (name, price, duration, perks: ticket discount %, merch discount %).
- FR-1.3 Member buys/pays a plan → membership `active` with `start_date`, `end_date` (default: academic year end).
- FR-1.4 System shows per member: status (`pending / active / expired`), dues paid, perks.
- FR-1.5 **Renewal reminders:** a daily job flags memberships expiring in ≤30 days; a "Renewals due" list for admin and a banner for the member. (Actual email sending = M2; M1 stores a `reminder` record + in-app banner.)
- FR-1.6 **Member verification:** search by name/email/member-ID and a QR "member card" that returns *valid / expired / not a member* instantly.
- FR-1.7 Admin member directory: search, filter by status, export-ready table.

### FR-2 Events & Tickets
- FR-2.1 Organizer creates event: title, description, venue, start/end, banner, status (`draft / published / closed`).
- FR-2.2 Ticket types per event: name, **member price**, **non-member price**, capacity (seats), sale window.
- FR-2.3 Public event page shows live "seats left"; sold-out blocks purchase; **no overselling** (atomic capacity check).
- FR-2.4 Checkout: price chosen automatically by membership status → order → (simulated) payment → ticket(s) with unique code + QR.
- FR-2.5 "My Tickets" page with QR for each ticket.
- FR-2.6 **Door check-in:** staff opens scanner page, scans QR / types code → result in <1s: `VALID (checked in) / ALREADY USED (time) / INVALID / WRONG EVENT`. No printed list.
- FR-2.7 **Event report:** tickets sold, seats left, checked-in count, attendance rate (no-shows), revenue (member vs non-member split).

### FR-3 Announcements
- FR-3.1 Organizer/Admin posts one announcement: title, body, category (`meeting / deadline / change / general`), audience (`all / members only / event attendees`), pinned flag.
- FR-3.2 Public/member **announcement feed** website page (newest first, pinned on top), permanent history with author + timestamp (immutable log; edits create a revision note).
- FR-3.3 **Mailing list:** posting triggers a "delivery" record per recipient (M1: stored as `queued/sent(simulated)`; M2: real email). Members can unsubscribe from emails.

### FR-4 Merchandise
- FR-4.1 Admin creates products (hoodie, T-shirt) with images, base price, member discount.
- FR-4.2 Variants by **size** (S–XXL) and optionally colour, each with **stock count**.
- FR-4.3 Member orders from phone: pick variant+qty, address/pickup choice, pay → order `paid`. Stock decremented atomically; out-of-stock disabled.
- FR-4.4 Admin order board: `paid → packed → handed over`; low-stock indicators; "how many of each size are left" view; size demand summary for bulk ordering.

### FR-5 Fundraiser & Tasks
- FR-5.1 Organizer creates a fundraiser (e.g., Bake Sale): goal amount, date, description.
- FR-5.2 Tasks inside it: title, owner, due date, status (`todo / doing / done`), category (baking / supplies / table duty).
- FR-5.3 Kanban board + "at a glance" progress: % tasks done, overdue count, who is doing what, amount raised vs goal.
- FR-5.4 Money raised is logged as an income transaction linked to the fundraiser.

### FR-6 Finance (Treasurer)
- FR-6.1 **Ledger:** every successful payment (dues, tickets, merch) auto-creates an **income** transaction; fundraiser income and other manual income can be added.
- FR-6.2 **Expense claims:** volunteer submits amount, description, category, event/fundraiser link, **receipt upload**.
- FR-6.3 Treasurer reviews: `submitted → approved/rejected → reimbursed` with a note. No receipt → cannot be approved.
- FR-6.4 **Dashboard:** total in, total out, balance; breakdown by source (dues / tickets / merch / fundraisers) and by category; per-event and per-fundraiser profit; outstanding reimbursements.
- FR-6.5 Semester report view (printable) — "where did the money go" on one page.

## 6. Non-Functional Requirements
- **Usable on phones** (members shop/buy tickets on mobile); door scanner works on a phone browser.
- **Data integrity:** money in integer paise (no floats); atomic capacity/stock; idempotent payment callbacks.
- **Security:** JWT auth, bcrypt, role-based access, input validation, CORS restricted, no secrets in repo.
- **Speed:** check-in API p95 < 300 ms; list pages paginated.
- **Observability:** every API returns consistent error shape; request logs.
- **Quality:** pytest for money/stock/check-in logic; seed data for demos.

## 7. Milestone 2 — Advanced (after M1 is shipped)
1. Real payments (Razorpay test→live), webhooks, refunds.
2. Real email (Resend/SMTP) + templated renewal reminders (auto at 30/7/1 days) + WhatsApp share/broadcast link.
3. Installable PWA door scanner with **offline check-in + sync**.
4. Analytics: attendance trends, member growth/churn, merch demand forecast, cohort retention.
5. Exports: CSV/PDF for ledger, members, event reports; budgets with category limits and alerts.
6. Waitlists, promo codes, group tickets, ticket transfer, refunds.
7. Audit log, 2FA for treasurer/admin, rate limiting.
8. AI assist (Gemini/DeepSeek): announcement drafting, expense receipt OCR/auto-fill, budget summary narrative.
9. Notifications center, calendar (.ics) export, multi-club tenancy (optional).

## 8. Success Metrics (demo-able)
- A new student signs up → pays dues → buys gala ticket at member price → QR checked at door → appears in event report → shows in treasurer ledger. **Entire flow < 3 minutes, zero paper.**
- Treasurer answers "dues / tickets / merch / reimbursements / balance" from one screen.

## 9. Out of Scope (M1)
Real money movement, native mobile apps, multi-club, complex accounting (double-entry), WhatsApp API integration.

## 10. Risks
| Risk | Mitigation |
|---|---|
| Overselling tickets/stock | DB transaction + row lock / conditional update |
| Frontend blocked by backend | Contract-first API in DESIGN.md + mock data/MSW on frontend |
| Scope creep | M1 frozen to the scenes above; extras go to M2 list |
| Payment provider delays | `PaymentProvider` interface; `mock` impl in M1, `razorpay` in M2 |
