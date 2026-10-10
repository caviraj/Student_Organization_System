# SSA Hub — Architecture

How the backend is put together and **why**, for whoever changes it next. For what the API does,
read `docs/API_HANDOFF.md`; for the route list, `docs/DESIGN.md` §5. This file is about the shapes
that are not obvious from either.

---

## 1. The stack and the layers

FastAPI 0.138, SQLAlchemy 2.x with typed `Mapped[]`, Pydantic v2, Alembic, Postgres (Supabase),
APScheduler. Python 3.11.

```
app/routers/   HTTP only: parse the request, call one service function, shape the response.
               No business rule, no query that is not "load this one row to check ownership".
app/services/  Business rules and transactions. One module per domain. The only place that
               decides anything.
app/models/    SQLAlchemy models. One module (DESIGN.md §4 is the schema of record).
app/schemas/   Pydantic request/response models, deliberately separate from the ORM models.
app/core/      Settings, sessions, security, deps, errors, middleware, rate limiting.
app/jobs/      The APScheduler wiring. Each job is a thin call into a service function.
```

The rule that keeps this honest: **a router may not import a model to query it.** If a router
needs a rule, the rule goes in the service. The handful of exceptions (a router loading a row to
check `owner_id`) are visible on inspection and are all in the same shape.

Schemas are separate from models on purpose. `User.password_hash` and `Expense.storage_path` exist
on the model and must never be on the wire; a shared model would make that a per-field decision
made at the serializer instead of a property of the response schema. `UserOut` simply has no such
field, and `tests/test_hardening.py` walks every response schema in the OpenAPI document to assert
none of them grows one.

---

## 2. The database

Supabase Postgres, reached through **two different URLs** for two different jobs:

| Variable | Port | Who | Why |
|---|---|---|---|
| `DATABASE_URL` | **6543**, transaction pooler | the running API | serverless-friendly connection pooling |
| `DIRECT_URL` | 5432, session/direct | Alembic and `scripts/*` | one session for DDL and bulk writes |
| `TEST_DATABASE_URL` | 5432 | pytest only | a different database; the suite truncates it |

The transaction pooler may hand each statement to a different backend, which rules out anything
that lives on a connection:

- **No advisory locks.** Never written, anywhere.
- **No session-level state** — no `SET`, no temp tables, no prepared statements (`prepare_threshold=None`
  for psycopg 3), `sslmode=require`, `pool_pre_ping=True`, a small pool.
- Row locking *inside one transaction* is fine and is used: `SELECT … FOR UPDATE` for the review
  decision and the stock release, `FOR UPDATE SKIP LOCKED` for the delivery worker.

**UUID primary keys**, **`JSONB`** for the ledger/report detail blobs, **`TIMESTAMPTZ`** everywhere
a timestamp is stored, **`NUMERIC`-free**: money is `INTEGER` paise. There is no SQLite path — the
tests run against the real engine because the pooler, the CHECK constraints and the row locks all
behave differently anywhere else.

### Row Level Security

Every table in `public` is created with **RLS enabled and no policies**. Supabase publishes the
`public` schema over its own REST API; the anonymous and authenticated roles it hands out can read
nothing when RLS is on and no policy grants anything, while the FastAPI backend — connecting as the
table owner — is unaffected. `FORCE ROW LEVEL SECURITY` is deliberately **not** used: it would apply
to the owner too and lock the backend out of its own tables. `scripts/check_db.py` exits non-zero if
any public table has RLS off.

### Migrations

Alembic is the only DDL path — no `create_all` outside tests' `_migrate()` (which runs the real
migrations). Every migration that creates a table also enables RLS on it. The index review in Phase
7 is `alembic/versions/b7f1c9a4e2d8`.

---

## 3. Money: one function, integer paise

Every amount in the system is an integer number of paise. There is no float in any model, schema or
service. The signed arithmetic lives in **one** place, `services/ledger.py`:

```
total_in  = SUM(amount WHERE direction='in'  AND NOT is_reversal)
          − SUM(amount WHERE direction='out' AND     is_reversal)
total_out = SUM(amount WHERE direction='out' AND NOT is_reversal)
          − SUM(amount WHERE direction='in'  AND     is_reversal)
balance   = total_in − total_out
```

A reversal is a **new mirror row**, never an UPDATE or DELETE. Ledger rows are immutable in the
code as well as in the contract: no service writes an UPDATE against `transactions`, and there is no
`PATCH`/`DELETE` route for one. `reconcile()` is the audit that proves the arithmetic held — it
checks that every reimbursed claim has exactly one matching ledger row, that the balance is not
negative, and that opening + net movement == closing.

Percentages round **half up**, once, in `services/pricing.py`:

```python
discounted(base, pct) = (base * (100 - pct) + 50) // 100
```

The frontend must render the server's numbers rather than recompute them; a client that rounds
differently is off by a paisa and nobody can explain why.

---

## 4. Concurrency without locks

Two things in this system can be sold twice if written naively: event seats and merchandise stock.
Neither is protected by a lock. Both are protected by making the write itself conditional:

```sql
UPDATE ticket_types
   SET sold_count = sold_count + :n
 WHERE id = :id AND capacity - sold_count >= :n
```

Zero rows affected means sold out, and the API raises `409 SOLD_OUT`. There is no read-then-write
window because there is no read. The `UPDATE` is atomic on its own, so an arbitrary number of
concurrent checkouts produce exactly `capacity` successes and no more, without a lock, without a
transaction isolation level anyone has to reason about, and without session state the pooler would
break. Merchandise uses the identical shape on `product_variants.stock`.

Reservations have a deadline. An unpaid order holds its seats or stock for **15 minutes**
(`PENDING_ORDER_TTL_MINUTES`), and a sweep every 5 minutes cancels the stragglers and returns what
they held. The sweep is idempotent and safe to run twice: the release is guarded by a marker column
under `SELECT … FOR UPDATE`, so a double release is impossible.

Payment success is idempotent by construction. `mock_confirm` claims the pending payment with a
conditional `UPDATE … WHERE status = 'pending'`; the loser of a race sees zero rows and returns the
existing state rather than charging again. That is what makes a double-tap on "Simulate success"
harmless.

---

## 5. The delivery worker

Announcements queue one `announcement_deliveries` row per recipient per channel inside the posting
transaction — so the queue is a table, not a process, and a crash loses nothing. The worker drains
it every 60 seconds (and once immediately after a post, via `BackgroundTasks`):

- Claims work with `SELECT … FOR UPDATE SKIP LOCKED`, so two workers never take the same row and a
  long send does not block the others.
- A unique `(announcement_id, user_id, channel)` constraint makes a double-queue a no-op.
- A failure retries up to 3 times, then goes `failed` — and stays visible on the admin deliveries
  screen. The console email provider fails any address at `fail.test`, which is how the seeded demo
  gets a `failed` row without breaking a real address.

The consequence worth knowing: `email_queued > 0` straight after a post is normal, and a queued
delivery is not a lost one.

---

## 6. Pricing and who counts as a member

**Member pricing is decided by an active membership row, not by the role string.** A user is a
member for pricing purposes when they have a membership whose `status` is active and whose
`end_date` has not passed (`services/pricing.py::is_active_member`). An `organizer` whose dues
lapsed pays the non-member price.

This is deliberate. A role is a permission; a membership is a paid status, and they change for
different reasons and at different times. Tying the discount to the role would mean either granting
member pricing to every staff member forever, or demoting an organizer the moment their dues lapsed.

Related: **registration creates a `guest`**, and paying dues promotes to `member` in the same
transaction as the ledger row. The promotion only ever goes up, so a renewal never demotes an
admin. `ROLE_RANK` lives in `app/core/deps.py` and `require_role("volunteer")` means volunteer *and
above* — the minimum rank of the roles listed, not the exact set.

---

## 7. Errors and the request lifecycle

One exception type, `AppError`, carrying `(status, code, message, details)`. Handlers registered for
`AppError`, **Starlette's** `HTTPException` (not FastAPI's — the framework raises the Starlette one
for a 404 and a 405, and both are the errors a client hits by accident), `RequestValidationError`,
and bare `Exception`. Every one of them produces `{"error": {code, message, details}}`.

The 500 handler logs the traceback with the request id and returns a body that says nothing about
it. That asymmetry is the point: the operator needs the traceback, the client must not have it.

`RequestContextMiddleware` wraps everything, mints or echoes `X-Request-ID`, puts it on
`request.state`, adds the three security headers, and writes one log line per request — method,
path, status, duration, request id, and **nothing else**. The query string is dropped and headers
are never touched, because this API carries an `Authorization` header, an unsubscribe token in a
query string and a signed receipt URL. `tests/test_hardening.py` proves a password and an
unsubscribe token never reach a log record.

Middleware order matters and is commented in `app/main.py`: `RequestContextMiddleware` is added
last so it wraps CORS, which means the request id and security headers are present even on a
response CORS rejects — the case someone is most likely to be debugging.

---

## 8. Storage

Receipts live in a **private** Supabase Storage bucket. The backend holds the service-role key,
which bypasses RLS, so:

- The key never reaches a response, a log line or the repository (`scripts/secret_scan.py` checks
  the last one; `tests/test_hardening.py` checks the first two).
- The storage path is never returned. `ExpenseOut` carries `has_receipt`, `receipt_mime` and
  `receipt_size`; the path is not a field.
- A client that needs the bytes gets `GET /expenses/{id}/receipt`, which mints a **signed URL valid
  for 10 minutes**. Short enough that a leaked URL is not a leak, long enough to open a PDF.
- The object key is `receipts/{claimant_id}/{expense_id}/{uuid4}.{ext}`. The client's filename is
  never used, so a traversal or collision trick has nothing to grab.
- Uploads are validated by **magic bytes**, not the client's `Content-Type`, before anything is
  stored.

`STORAGE_PROVIDER=local` swaps in a filesystem-backed provider rooted at `LOCAL_STORAGE_DIR`, which
is what the test suite uses — so no test needs network access or a real bucket.

---

## 9. Background jobs

`app/jobs/scheduler.py` registers four jobs on an `AsyncIOScheduler` started in the app's lifespan:
the daily membership expiry scan, the 5-minute ticket sweep, the 5-minute merch sweep, and the
60-second delivery drain. Each is a thin call into a service function, so every job is also
callable directly and the tests drive them without a scheduler.

Every job is registered with `max_instances=1` and `coalesce=True`: a job that overruns its interval
does not stack up behind itself, and a machine that was asleep for an hour does not run sixty
catch-ups. Jobs run in the API process, which is why **one worker is a deployment requirement** —
the Phase 7 rate limiter is an in-memory dict for the same reason. Both are M2 work (Redis, and a
separate scheduler process).

---

## 10. What is deliberately not here

Recorded so the next reader does not go looking:

- **No real payments.** `mock-confirm` is the whole gateway. M2 replaces it with Razorpay and a
  webhook; the request/response shapes on either side do not change.
- **No email delivery.** `EmailProvider` prints to the console in M1.
- **No refresh tokens.** A 7-day JWT, then log in again.
- **No background workers outside the API process.** See §9.
- **No caching layer.** Every read hits Postgres.
- **No soft deletes** on ledger rows; corrections are reversals.
- **No multi-tenancy.** One club, one database.

`docs/M2_BACKLOG.md` lists what Milestone 2 picks up, with the specific seam each item attaches to.
