# SSA Hub — Backend

FastAPI + SQLAlchemy 2.x + Alembic. Contract: `docs/DESIGN.md` §5. Phases 0–7 are implemented: foundation, auth & membership, events/tickets/check-in, announcements & the mailing list, merchandise (products, stock, orders, fulfilment), fundraisers (planning, the task board, progress, hand-logged income), expenses & treasurer finance (receipt uploads, review, reimbursement, the finance dashboard, manual entries, reversals and finance periods), and the Phase 7 hardening pass (rate limits, request ids and request logging that cannot leak a secret, uniform errors, an end-to-end proof over HTTP, one-command demo reset, and the frontend handoff pack).

**Starting here?** Read [`docs/API_HANDOFF.md`](../docs/API_HANDOFF.md) if you are connecting a
client, [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md) if you are changing the backend, and
[`docs/DEMO_SCRIPT.md`](../docs/DEMO_SCRIPT.md) if you are about to present it.

## Run it

```bash
cd backend
python -m venv .venv && . .venv/Scripts/activate   # Windows Git Bash; use .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
cp .env.example .env                                # fill in the two database URLs and JWT_SECRET

python -m alembic upgrade head                      # create the schema (Alembic is the only DDL path)
python scripts/setup_storage.py                     # creates the private receipts bucket (Supabase only; no-op for local)
python scripts/seed.py                              # staff + plans + members + events + announcements + merch + fundraisers + expenses
python -m uvicorn app.main:app --reload             # http://127.0.0.1:8000
```

- Swagger UI: <http://127.0.0.1:8000/docs> — every endpoint, tagged, with example bodies.
- Health: `GET /health`.
- End-to-end demos (migrate, seed, boot the server, walk the whole flow):
  `bash scripts/demo_phase1.sh` · `bash scripts/demo_phase2.sh` · `bash scripts/demo_phase3.sh` · `bash scripts/demo_phase4.sh` · `bash scripts/demo_phase5.sh` · `bash scripts/demo_phase6.sh`

**Run one worker.** The background jobs live in the API process, and the Phase 7 rate limiter is an
in-memory dict — both assume a single process. `uvicorn app.main:app` with no `--workers` is the
supported deployment; more than one worker means N schedulers and N independent rate-limit counters.
(M2 replaces the limiter with Redis and the schedulers with a separate process.)

## Database (Supabase Postgres — two URLs, not interchangeable)

| Variable | Points at | Used by |
| --- | --- | --- |
| `DATABASE_URL` | the **transaction pooler**, port **6543** | the running API |
| `DIRECT_URL` | the **session pooler** (or a direct connection), port **5432** | Alembic and `scripts/seed.py` only |
| `TEST_DATABASE_URL` | a **different database** on the same server | `pytest` only |

The transaction pooler hands each statement to a possibly different backend, so the app connects
with prepared statements disabled (`prepare_threshold=None` for psycopg 3), `sslmode=require`,
`pool_pre_ping=True` and a small pool (5 + 5 overflow). For the same reason **no advisory locks or
session-level state anywhere** — row locking inside one transaction (`SELECT … FOR UPDATE SKIP
LOCKED`, which the delivery worker uses) is fine. Migrations and the seed run on `DIRECT_URL`
because Alembic's DDL wants one session.

There is no SQLite path: models and migrations use native `UUID`, `JSONB` and `TIMESTAMPTZ`.

```bash
python scripts/check_db.py     # server version, which database, pooler or not, and RLS per table
```

`check_db.py` exits non-zero if any table in `public` has Row Level Security disabled. Every table
ships with **RLS on and no policies**: Supabase publishes `public` over its own REST API, and that
combination is what keeps it closed while the backend (the table owner) is unaffected.

## Receipt storage (Phase 6)

Receipts never touch the database: `expenses` stores a path, a mime type and a size, and the bytes
live in a **private** bucket that only the backend can reach with `SUPABASE_SERVICE_ROLE_KEY`. That
key bypasses RLS, so it is never logged, never returned and never committed — every response that
needs a file hands out a **signed URL that expires in 10 minutes** instead, and the storage path
itself is never returned to a client.

| Variable | Meaning |
| --- | --- |
| `STORAGE_PROVIDER` | `supabase` (real) or `local` (dev and tests — a fake rooted at `LOCAL_STORAGE_DIR`) |
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | required when `STORAGE_PROVIDER=supabase` |
| `RECEIPTS_BUCKET` | bucket name, default `receipts`; `scripts/setup_storage.py` creates it idempotently |

Uploads are validated **before** they are stored: jpeg/png/webp/pdf only (checked by magic bytes,
not by the client's `Content-Type`), 5 MB maximum, and the object key is
`receipts/{claimant_id}/{expense_id}/{uuid4}.{ext}` — the client's filename is never used, so a
path-traversal or collision trick has nothing to grab. The suite runs on the `local` provider, so no
test needs network access or a real bucket.

## Tests

```bash
python -m pytest -q
```

The suite runs against Postgres at `TEST_DATABASE_URL` — the real database engine, because the
pooler, JSONB, the enum CHECK constraints and the row locks behave differently anywhere else. It
builds its schema by running the **actual migrations** (never `create_all`), truncates every table
between tests, and refuses to start if `TEST_DATABASE_URL` is missing or resolves to the same
host+database as `DATABASE_URL`: truncating between tests is a fixture, but against the real
database it would be data loss. Background work is pointed at the test session, so the scheduler is
never started and no test opens a second connection to your application database.

## Seeded accounts

Password for all of them: `Passw0rd!`

| Role | Email | What it is for |
| --- | --- | --- |
| admin | `admin@ssa.org` | every admin screen; products, stock, roles, period reopen |
| treasurer | `treasurer@ssa.org` | the finance dashboard, the claim queue, ledger and reports |
| organizer | `organizer@ssa.org` | creating events, tickets, announcements, fundraisers |
| volunteer | `volunteer@ssa.org` | the scanner, the task board, submitting a claim |
| member | `member@ssa.org` | the default happy path: active dues, member pricing, a member code |
| member | `expiring@ssa.org` | dues end in 8 days — the renewal-reminder state |
| member | `expired@ssa.org` | dues lapsed 30 days ago — the "renew for member pricing" state |
| guest | `guest@ssa.org` | signed in, never paid: public announcements only, non-member prices |
| volunteer | `neha@ssa.org`, `rohit@ssa.org` | extra claimants, so the review queue has several owners |
| member | `member01@ssa.org` … `member20@ssa.org` | fills the events, orders and merch demo data |

There is also `bouncing@fail.test`, a deliberately undeliverable address, so the admin deliveries
screen has a `failed` row to show.

Seeding is idempotent — run it as often as you like. To throw the demo away and rebuild it from
nothing (the state a rehearsal needs):

```bash
python scripts/reset_demo.py --yes    # TRUNCATEs every table and reseeds; refuses in production
```

`scripts/seed.py` prints a **DEMO ACCOUNTS** and a **KEY IDS** table when it finishes — the ids to
paste into a URL for the nearly-sold-out ticket type, the sold-out hoodie size, the overdue task and
the pending claim.

## Layout

```
app/main.py        app factory, lifespan (scheduler), CORS, error handlers
app/core/          config, db session, security (bcrypt + JWT), deps (auth + role guards), errors
app/models/        SQLAlchemy models — one file (DESIGN.md §4)
app/schemas/       Pydantic v2 request/response models, kept separate from ORM models
app/routers/       HTTP only: parse, call a service, shape the response
app/services/      business rules — memberships, payments, ledger, reminders, accounts,
                   check-in, reports, announcements, mailer, delivery_worker, unsubscribe,
                   pricing, inventory (seats + stock), merch (catalogue, checkout, fulfilment),
                   fundraisers (lifecycle + progress + health), tasks (board, positions, activity),
                   income (hand-logged ledger rows), storage (private receipts), expenses (claims,
                   review, reimbursement), finance (summary, transactions, reports, periods)
app/jobs/          APScheduler wiring for the daily expiry scan, the ticket sweep, the
                   merchandise sweep and the announcement delivery job
alembic/           migrations (autogenerate wired to Base.metadata)
scripts/           the operator's toolbox, below
tests/             pytest (auth, membership, events/tickets/check-in, announcements, merchandise,
                   fundraisers/tasks/income, expenses/receipts/finance, the semester end-to-end
                   story, and the Phase 7 hardening guarantees)
```

### `scripts/`

| Script | What it is for |
| --- | --- |
| `seed.py` | idempotent demo data for every phase; prints the accounts and key ids |
| `reset_demo.py` | **destructive**: TRUNCATE every table, clear the receipt objects, reseed. Needs `--yes` |
| `check_db.py` | server version, which database, pooler or not, RLS per table. Non-zero exit if RLS is off anywhere |
| `check_storage.py` | proves the private bucket is reachable, writable, and that a signed URL round-trips |
| `contract_check.py` | compares `docs/DESIGN.md` §5 against the app's real routes, methods and roles |
| `export_openapi.py` | regenerates `docs/openapi.json` deterministically |
| `smoke_e2e.py` | drives the whole semester story **over HTTP** against a running server; PASS/FAIL table, non-zero exit on failure |
| `perf_check.py` | times 200 check-ins, 100 event reads and 100 finance summaries; prints p50/p95/max. Non-zero exit if check-in p95 ≥ 300 ms |
| `secret_scan.py` | greps the tree for keys, tokens and credentials that should not be committed |
| `setup_storage.py` | creates the private receipts bucket (Supabase only; no-op for local) |
| `demo_phase1.sh` … `demo_phase6.sh` | per-phase end-to-end walkthroughs against a running server |

Money is **integer paise** everywhere — never a float. Errors are always
`{"error": {"code", "message", "details"}}`.

**Fundraisers** (Phase 5): a fundraiser runs `planning → active → done` and never backwards; a `done`
board is read-only, but income stays open for 7 days after `completed_at`. Every card change goes
through `services/tasks.update_task`/`move_task`, which is why the `task_activity` trail can never be
forgotten. `progress.health` (`on_track`/`at_risk`/`behind`/`completed`) is computed from named
constants in the service, so the frontend's colours have one source of truth. Income is the one
ledger entry a human types, so it is the one that can be typed twice: an `Idempotency-Key` plus
`unique(fundraiser_id, idempotency_key)` turns a double-click into a replay, and there is no PATCH or
DELETE for an income row.

**Expenses & finance** (Phase 6): every ledger row — ticket, merch, dues, fundraiser income, claim
reimbursement, manual entry — is written by the one function in `services/ledger.py`, so there is
exactly one place where the signed arithmetic lives (`balance = total_in − total_out`, with
reversals cancelling the side they mirror). A claim moves `submitted → approved|rejected`, then
`approved → reimbursed`; approving needs a receipt, the reviewer can never be the claimant
(`SELF_REVIEW`, `409`, admins included), and the review decision takes a `SELECT … FOR UPDATE` so
two treasurers racing on the same claim leave one winner and one `INVALID_STATE`. Reimbursement is
one transaction that re-checks the balance (`INSUFFICIENT_FUNDS`), and exactly one ledger row per
claim — a second call replays instead of paying twice. Ledger rows are **immutable**: a mistake is
corrected by `POST /finance/transactions/{id}/reverse`, which writes a mirror row, never by an
UPDATE. `reconcile()` is the audit: it asserts balance is not negative, that every reimbursed claim
has exactly one matching ledger row, and that opening + net == closing; `scripts/seed.py` and the
tests both fail loudly if it ever disagrees.

**Merchandise** (Phase 4): stock lives on `product_variants` and every change to it writes a
`stock_movements` row in the same transaction, so `SUM(delta) == stock` holds for every variant —
`scripts/seed.py` prints that count and `tests/test_merch.py` asserts it. Stock is reserved at
checkout with a conditional `UPDATE … WHERE stock >= qty` (never read-then-write), released once
per order via a marker under `SELECT … FOR UPDATE`, and a `merch_orders` row exists only after
payment succeeds. Prices are resolved once, at checkout, in integer paise.

## Hardening (Phase 7)

No new product features — the phase that makes the existing ones survivable in a room full of
students. What it added, and where it is proved:

| Thing | Behaviour | Proof |
| --- | --- | --- |
| Startup config validation | `Settings.problems()` refuses to boot on a `*` CORS origin, a short `JWT_SECRET`, or a production `APP_ENV` with `STORAGE_PROVIDER=local` | `app/core/config.py` |
| Rate limiting | login/register 10/min per IP, check-in 120/min per user, ticket and merch checkout 30/min per user; `429` with `Retry-After` | `tests/test_hardening.py` |
| Login lockout | 5 consecutive failures lock that **email** for 15 minutes, answered even for the right password; a success clears the count | `tests/test_hardening.py` |
| Password policy | 8+ characters with a letter and a digit, as `422 WEAK_PASSWORD` | `tests/test_hardening.py` |
| Errors | every status from every route is `{"error": {code, message, details}}` — including the framework's own 404 and 405; 422 lists `details.fields`; 500 says nothing and logs everything with the request id | `tests/test_hardening.py` |
| Request identity | `X-Request-ID` echoed or minted, on `request.state`, in every log line | `tests/test_hardening.py` |
| Request logging | method, path, status, duration, request id — **no** query string, **no** headers | `tests/test_hardening.py` proves a password and an unsubscribe token never reach the log |
| Route audit | every route outside a documented `PUBLIC_ALLOWLIST` answers `401` with no token; a role matrix asserts what a plain member may reach | `tests/test_hardening.py` |
| Response schemas | no response model exposes `password_hash`, a storage path or the service-role key | `tests/test_hardening.py` |
| Secret scanning | `scripts/secret_scan.py` over the tree, with a self-test that its own rules fire | `scripts/secret_scan.py` |

**Query review.** The Postgres catalog was queried for foreign keys without a supporting index: 20
of 47 lack one, and 18 of those are display-only joins through `users`' primary key, which needs no
index and would only cost write amplification. The two the API actually filters on —
`tasks.event_id` and `fundraisers.owner_id` — got an index in
`alembic/versions/b7f1c9a4e2d8`. `EXPLAIN ANALYZE` on the five hot queries (check-in by code, an
event's ticket types, the product list, the finance summary, the ledger page) shows an index scan or
a plan over a table small enough that it makes no difference; the numbers are in the Phase 7 report.

## Roles

`admin > treasurer > organizer > volunteer > member > guest`. `require_role("volunteer")` admits
volunteer and everyone above it. Role is read from the database on every request, so a promotion
applies immediately. Registering creates a `guest`; paying dues promotes `guest → member` and never
demotes anyone.

## Background jobs

APScheduler runs four jobs, each also callable directly so tests can drive it:

- `services.reminders.run_expiry_scan()` — startup and every 24h: expires memberships whose
  `end_date` has passed and raises `expiry_30` / `expiry_7` / `expired` reminders, at most once per
  membership per kind.
- `services.tickets.release_expired_pending_orders()` — every 5 minutes: cancels ticket orders still
  `pending` after 15 minutes and returns their seats.
- `services.merch.release_expired_pending_merch_orders()` — every 5 minutes: the same 15-minute
  sweep for merch, cancelling unpaid orders and putting their stock back (one `release` movement
  each). A late `mock-confirm` on a swept order answers 409 `ORDER_NOT_PAYABLE`.
- `services.delivery_worker.process_queued_deliveries()` — every 60 seconds, **and once immediately
  after a post** via `BackgroundTasks`: claims queued announcement deliveries with `SELECT … FOR
  UPDATE SKIP LOCKED`, sends the email ones through the `EmailProvider` (console in M1; any address
  at `fail.test` fails), and retries a failure up to 3 times before marking it `failed`. Safe to run
  twice and safe to run concurrently: the unique `(announcement_id, user_id, channel)` constraint
  and the row lock are the whole guarantee.
