# SSA Hub — Backend

FastAPI + SQLAlchemy 2.x + Alembic. Contract: `docs/DESIGN.md` §5. Phases 0–4 are implemented: foundation, auth & membership, events/tickets/check-in, announcements & the mailing list, and merchandise (products, stock, orders, fulfilment).

## Run it

```bash
cd backend
python -m venv .venv && . .venv/Scripts/activate   # Windows Git Bash; use .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
cp .env.example .env                                # fill in the two database URLs and JWT_SECRET

python -m alembic upgrade head                      # create the schema (Alembic is the only DDL path)
python scripts/seed.py                              # staff + plans + members + events + announcements + merch
python -m uvicorn app.main:app --reload             # http://127.0.0.1:8000
```

- Swagger UI: <http://127.0.0.1:8000/docs> — every endpoint, tagged, with example bodies.
- Health: `GET /health`.
- End-to-end demos (migrate, seed, boot the server, walk the whole flow):
  `bash scripts/demo_phase1.sh` · `bash scripts/demo_phase2.sh` · `bash scripts/demo_phase3.sh` · `bash scripts/demo_phase4.sh`

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
                   pricing, inventory (seats + stock), merch (catalogue, checkout, fulfilment)
app/jobs/          APScheduler wiring for the daily expiry scan, the ticket sweep, the
                   merchandise sweep and the announcement delivery job
alembic/           migrations (autogenerate wired to Base.metadata)
scripts/           seed.py, check_db.py, demo_phase1.sh … demo_phase4.sh
tests/             pytest (auth, membership, events/tickets/check-in, announcements, merchandise)
```

Money is **integer paise** everywhere — never a float. Errors are always
`{"error": {"code", "message", "details"}}`.

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
