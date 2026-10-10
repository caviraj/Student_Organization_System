# Milestone 2 — Backlog

Milestone 1 shipped the club's whole semester on one ledger. Milestone 2 makes it survive contact
with reality: real money, real email, a door with bad wifi.

This is the list of what is deliberately **not** in M1, with the seam each item attaches to. It is
not a schedule — it is so that whoever picks one up starts from the right place instead of from
scratch.

`docs/TASKS.md` has the M2 phases; this has the specifics.

---

## 1. Real payments (Razorpay)

**What M1 does instead:** `POST /payments/{order_id}/mock-confirm` with `{outcome: "success" | "fail"}`.
The frontend renders the "gateway" as two buttons. There is no webhook and no real money.

**The seam.** Every payment goes through `services/payments.py::create_mock_intent` and a single
confirm handler that is already idempotent — it claims the pending payment with a conditional
`UPDATE … WHERE status = 'pending'` and the loser of a race returns the existing state. A real
provider replaces exactly two things: `create_mock_intent` becomes "create a Razorpay order and
return its id", and `mock-confirm` becomes a webhook handler. **The order, membership, ticket,
stock and ledger code behind the confirm does not change**, because none of it knows where the
confirmation came from.

**Work:**

- `RazorpayProvider` behind the existing provider interface; keep `MockProvider` for tests and for
  a deployment with no keys.
- `POST /payments/webhook` — **verify the signature before parsing anything**, then call the same
  confirm path. Reject an unsigned or mis-signed body outright; a webhook endpoint that trusts its
  input is a free-money endpoint.
- Idempotency by `provider_payment_id`, not by our order id: Razorpay retries webhooks.
- Refunds: a new ledger `direction: "out"` row with `source: "refund"`, plus a reversal-style link
  back to the original. Do not UPDATE the original row — the ledger is immutable, and a refund that
  edits history breaks the audit the club actually wants.

**Watch out:** the webhook needs a raw body to verify the signature. FastAPI's automatic JSON
parsing will have consumed it — read `await request.body()` before any model binds it.

---

## 2. Real email

**What M1 does instead:** `services/mailer.py::ConsoleProvider` prints the message. Any address at
`fail.test` raises, which is how the seeded demo gets a real `failed` delivery row.

**The seam.** `EmailProvider` is already an interface with one method, and `delivery_worker.py`
already does the hard part: it queues a row per recipient per channel inside the posting
transaction, claims work with `FOR UPDATE SKIP LOCKED`, retries three times, and records
`sent`/`failed`. Swapping the provider is a config change. What is missing is the content.

**Work:**

- A `ResendProvider` (or SMTP) behind the same interface.
- Templates: announcement, membership expiry (30/7/1 days), dues receipt, ticket confirmation,
  reimbursement paid. The reminder *scheduling* already exists (`services/reminders.py` writes the
  rows); only the rendering is missing.
- Unsubscribe links already work end to end — `create_unsubscribe_token` and
  `GET /unsubscribe?token=…`. Every bulk email must carry one.
- Bounce handling: a webhook that marks the address undeliverable, so the queue stops retrying a
  dead mailbox forever.

**Watch out:** the delivery worker runs in the API process. Sending 400 emails from inside a request
cycle is fine at this scale and will not be at the next one — a real provider moves the drain to its
own process. Do that before the list passes a few thousand.

---

## 3. Offline scanning

**What M1 does instead:** the scanner needs a live connection per scan.
`POST /checkin` requires `volunteer`+, is rate limited to 120/min per user, and always answers 200
with `result: VALID | ALREADY_USED | INVALID | WRONG_EVENT`.

**The problem.** A college auditorium has bad wifi, and a door that stops working when the wifi
blinks is worse than a paper list.

**Work:**

- `POST /checkin/bulk` — an array of `{code, scanned_at, device_id}` from a queued client, applied
  in one transaction. The existing `check_in()` service takes a code and returns a result; the bulk
  endpoint is a loop over it with `scanned_at` honoured so the attendance timeline stays true.
- Conflict rule: **first scan wins**. A replayed offline batch must not flip a `used` ticket back
  or forward; the existing conditional `UPDATE … WHERE status = 'valid'` already gives this, so the
  bulk path inherits it.
- Signed QR payloads, so a screenshot of someone else's ticket does not work. The ticket `code` is
  currently the whole secret; a signed payload with the event id and an expiry is the upgrade.
- The frontend side: a PWA with a service worker, an IndexedDB queue, and an explicit "N scans
  pending / synced" indicator. **The volunteer must be able to see whether the queue drained** —
  silent sync is how attendance data gets lost.

**Watch out:** the rate limit is per user per minute. A bulk sync of 300 scans is one request, so it
needs its own limit or none — but not the per-scan one, or the queue will never drain.

---

## 4. Analytics and exports

**What M1 does instead:** `GET /finance/report` computes a semester report, and every list endpoint
paginates. There are no charts endpoints and no file downloads.

**The seam.** `services/reports.py` already aggregates by event, fundraiser, source, category and
month — the numbers a chart needs are computed, they are just shaped for a report rather than for a
graph.

**Work:**

- Trend endpoints (membership growth by month, attendance rate by event, merch demand by size) —
  reuse the aggregation helpers rather than a second set of queries.
- CSV export for the ledger, members and attendees: streamed, not buffered, because the ledger is
  the one table that grows without bound.
- PDF for the semester report. The report is already a printable JSON shape; the PDF renderer
  consumes it rather than querying again, so the printed numbers cannot drift from the screen.

**Watch out:** exports bypass pagination. A "download everything" button on a table with a 100-row
page size is how a treasurer accidentally emails 40,000 rows. Cap it, or stream it with a row count.

---

## 5. Budgets, audit and 2FA

**What M1 does instead:** `finance_periods` closes a window of the ledger and refuses writes inside
it; `reconcile()` proves the arithmetic; the ledger is immutable and corrections are reversals.

**Work:**

- **Category budgets** with a threshold alert when a category crosses it. The aggregation already
  exists in `services/finance.py::summary` (`by_category`).
- **A general audit log.** M1 has `expense_history`, `task_activity` and `stock_movements` — a trail
  per domain, written by the service that makes the change. A general log wants the same treatment:
  a decorator or a middleware, not four more ad-hoc tables.
- **2FA** for `treasurer` and `admin` — the two roles that can move money. TOTP, with recovery
  codes, and a `require_role` variant that demands a fresh second factor rather than one from six
  days ago.

---

## 6. Smart extras

Each of these is a small feature with a disproportionate amount of product thinking behind it. They
are last on purpose.

- **Waitlist** for a sold-out event. The interesting part is not the queue, it is the release: the
  15-minute reservation sweep already knows when a seat comes back, so the offer goes out from
  there — with its own expiry, because a waitlist offer that never expires is a seat that never
  sells.
- **Promo codes** — percent or fixed, with a usage cap and a window. They interact with member
  pricing, so decide the order (member price first, then the code?) explicitly and write it down.
- **Ticket transfer** — one holder to another. It changes who is admitted, so it needs the transfer
  itself to be by a single-use token, and both sides to be notified.
- **Receipt OCR** — read the amount and date off an uploaded receipt to pre-fill the claim. The
  upload validation and the storage path already exist; this only adds a suggestion the claimant
  can correct.
- **Announcement drafting (LLM)** — a first draft from a few bullet points, which the organizer then
  edits. The revision history already records that an edit happened and why, which is exactly the
  trail an AI-assisted post needs.
- **Notification centre and dark mode** — frontend-first, and the smallest items here.

---

## 7. Operational debt

Not features, and the ones most likely to bite first.

| Item | Why it matters now | What it looks like |
|---|---|---|
| **Redis for rate limiting** | The limiter is an in-memory dict, which is why **one worker** is a deployment requirement. Two workers means two independent limits | Move `app/core/ratelimit.py` behind the same interface, backed by Redis |
| **The scheduler out of the API process** | Four jobs in the web process; a long drain delays requests | A separate worker running `app/jobs/scheduler.py`, with the web process starting none of it |
| **A real test database in CI** | The suite needs `TEST_DATABASE_URL` and takes ~9 minutes against a remote Postgres | A Postgres service container in CI, plus parallel test execution (`pytest-xdist`) once the fixtures allow it |
| **Backups and a restore drill** | Supabase's default retention is not a backup strategy; nobody has restored this database into a fresh project | A scheduled `pg_dump` to object storage, and one documented restore actually performed |
| **Observability** | Request logs go to stdout and nothing is aggregated | Structured JSON logs with the request id, shipped somewhere searchable; error-rate alerting |
| **`pytest-randomly`** | Test order is currently checked by hand (Phase 7 ran the suite in shuffled order); the suite has hidden ordering assumptions waiting to be found | Add the plugin, fix what it exposes, keep it on |
| **OpenAPI drift in CI** | `docs/openapi.json` and `docs/DESIGN.md` §5 are checked by scripts a human runs | Run `contract_check.py`, `export_openapi.py` (into a temp file, then diff) and `secret_scan.py` as a pre-commit hook and in CI |

---

## 8. What M1 got right and M2 must not break

Worth writing down, because each of these is load-bearing and easy to undo by accident:

- **Ledger rows are immutable.** No `UPDATE`, no `DELETE`, corrections are reversals. Anything that
  edits a row "just this once" ends the audit.
- **Money is integer paise.** A float in one serialiser is a rounding bug in every report after it.
- **The signed arithmetic lives in one function** (`services/ledger.py`). A second implementation
  will disagree with the first within a sprint.
- **Concurrency safety comes from conditional writes**, not locks: `UPDATE … WHERE capacity − sold >= n`.
  Replacing that with a read-then-write "because it is clearer" reintroduces the double-sell.
- **RLS is on, with no policies, on every table.** A new table without it is a public table, because
  Supabase publishes the schema.
- **The error envelope is uniform**, including the framework's own 404 and 405.
- **The storage path and the service-role key never leave the backend.** Not in a response, not in a
  log line.
- **Member pricing follows the membership, not the role.**
