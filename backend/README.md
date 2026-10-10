# SSA Hub — Backend

FastAPI + SQLAlchemy 2.x + Alembic. Contract: `docs/DESIGN.md` §5. Phases 0–6 are implemented: foundation, auth & membership, events/tickets/check-in, announcements & the mailing list, merchandise (products, stock, orders, fulfilment), fundraisers (planning, the task board, progress, hand-logged income), and expenses & treasurer finance (receipt uploads, review, reimbursement, the finance dashboard, manual entries, reversals and finance periods).

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

| Role | Email |
| --- | --- |
| admin | `admin@ssa.org` |
| treasurer | `treasurer@ssa.org` |
| organizer | `organizer@ssa.org` |
| volunteer | `volunteer@ssa.org` |
| volunteer | `neha@ssa.org`, `rohit@ssa.org` (extra claimants, so one review queue has several owners) |
| member | `member01@ssa.org` … `member20@ssa.org` |

Seeding is idempotent — run it as often as you like.

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
scripts/           seed.py, check_db.py, setup_storage.py, demo_phase1.sh … demo_phase6.sh
tests/             pytest (auth, membership, events/tickets/check-in, announcements, merchandise,
                   fundraisers/tasks/income, expenses/receipts/finance)
```

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
