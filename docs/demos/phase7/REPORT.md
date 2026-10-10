# Phase 7 — Hardening, End-to-End Proof, Demo Data, Docs: the backend report

Phase 7 added **no product features and deployed nothing**. It made the existing seven phases
provable: audited from a clean checkout, asserted end to end twice (in-process and over HTTP),
given demo data that resets to a known state, hardened for production without a deploy, and
documented so that the frontend has one contract to build against.

Every number below was produced by running the command named next to it, on this machine, on
2026-10-10.

---

## STEP 0 — Clean-checkout audit

A fresh virtualenv with only `requirements.txt` and a `.env` built from `.env.example`, then every
gate in the definition of done.

| Check | Result |
|---|---|
| `python -m venv` + `pip install -r requirements.txt` | clean, exit 0 |
| `pip check` | `No broken requirements found.` — exit 0 (see the note below) |
| `alembic upgrade head` | applies `b7f1c9a4e2d8` on top of `ecd63b2a99ac`, exit 0 |
| `pytest -q` | green — see STEP 6 |
| `ruff check .` | `All checks passed!` |
| `black --check .` | `96 files would be left unchanged.` |
| `scripts/check_db.py` | exit 0 — RLS on all 24 public tables |
| `scripts/check_storage.py` | exit 0 — put, sign, delete, private-bucket check |
| every `scripts/demo_phaseN.sh` | all six exit 0 (see STEP 3) |

### What the audit actually found, and what was done about it

Every one of these was a real defect that the phase gates had not caught. They are listed because
the point of an audit is the list, not the green ticks.

| # | Finding | Why it was invisible | Fix |
|---|---|---|---|
| 1 | **`SupabaseStorageProvider.put()` could never work.** `_request()` passed `headers` twice (`headers=self._headers` plus the caller's `headers=`), so every receipt upload under `STORAGE_PROVIDER=supabase` raised `TypeError` → 500. | Development and the whole test suite run `STORAGE_PROVIDER=local`. The Supabase provider had **zero** tests. | `_request()` now merges the caller's headers over the auth headers. `tests/test_storage.py` added (8 tests) — the provider was the only code path holding the service-role key and the only one at 0% coverage. |
| 2 | **`demo_phase5.sh` picked the assignee by list index** (`get /users/assignable \| pick 3 id`). Phase 7's seed added eight demo accounts, the assignable list reordered, and the card was handed to `rohit@ssa.org` — so the volunteer's own `PATCH /tasks/{id}` started answering 403 and the demo died mid-run. | A positional pick depends on seed insertion order, which nothing documents and nothing tests. | Replaced with `by_email volunteer@ssa.org`. Also proves the demo is not order-dependent. |
| 3 | **`alembic/env.py` disabled every application logger.** `fileConfig()`'s default is `disable_existing_loggers=True`, which sets `.disabled = True` on `ssa.request`, `ssa.errors`, `ssa.mailer`, … the moment `app.main` has been imported. | The `alembic upgrade head` CLI never noticed, and the suite migrates **in-process** — so every Phase 7 log assertion would have passed **vacuously**, against a logger that could not emit. | `fileConfig(..., disable_existing_loggers=False)`. |
| 4 | **`RegisterIn.password` declared `min_length=8`**, so a short password answered `422 VALIDATION_ERROR` from pydantic before `check_password_policy` could answer `422 WEAK_PASSWORD`. | The frontend would have had to map two error codes onto one password field. | `min_length` removed (the length rule belongs to the policy); `max_length=72` kept because bcrypt silently ignores bytes past 72. `tests/test_auth.py` updated — it had encoded the wrong code. |
| 5 | **Four dead `# noqa: E402` directives** in new scripts (RUF100), and two unjustified broad `except` clauses (BLE001). | Untracked files, so CI had never seen them. | Directives removed; the two catches carry `# noqa: BLE001` with an inline reason. |
| 6 | **Docs used `bouncing@fail.org`; the seed uses `bouncing@fail.test`.** | A doc/seed drift nobody re-reads. | Corrected in `docs/API_HANDOFF.md`, `backend/README.md`, `docs/DEMO_SCRIPT.md`. |
| 7 | **`.test` is an RFC 2606 reserved TLD that `EmailStr` rejects.** The deliberate undeliverable sentinel is `bouncing@fail.test` (`mailer.FAILURE_DOMAIN`), seeded **directly into the database** so it never passes through `EmailStr`. | Found while chasing a seeding failure; the demo accounts are `@ssa.org` for this reason. | Documented as a rule, not just fixed. |
| 8 | **`demo_phase1.sh` wrote two live JWTs into its own artifact.** Its `pretty` helper pipes a whole response body to stdout, and steps 1–2 print `POST /auth/register` and `POST /auth/login` — so `docs/demos/phase7/demo_phase1.txt` carried a usable `access_token` for `demo.<ts>@ssa.org` and another for **`admin@ssa.org`**. | The first `secret_scan.py` run reported `OK` because it scans `git ls-files` — and the Phase 7 artifacts were still *untracked* at that point, so the very files this phase produced were the ones it could not see. It flagged them the moment they were staged. | `pretty` in `demo_phase1.sh` redacts `access_token`; the artifact was regenerated. It is the only demo that prints an auth response body — the other five assign it straight to a variable. |

No `TODO`/`FIXME`/`XXX`/`HACK`, no `breakpoint()`, no bare `print()` in `app/`, no commented-out
code, no orphan module, and no hardcoded host or port outside `app/core/config.py` — all checked by
grep, all clean.

`pip check` reported five conflicts the first time it was run. All five came from unrelated
**global** site-packages (nemoguardrails, torchvision, google-ai-generativelanguage, grpcio-status,
pdfplumber), not from `requirements.txt`. In the fresh venv — the only environment that answers the
question — it is clean. Every pin in `requirements.txt` is exact.

---

## STEP 1 — Contract truth

| Command | Result |
|---|---|
| `python scripts/contract_check.py` | `documented 90, implemented 90, matched 90`, **exit 0** |
| `python scripts/export_openapi.py` | `docs/openapi.json` regenerated — 70 paths, 344 KB, deterministic |
| `npx openapi-typescript docs/openapi.json -o docs/api-types.ts` | **succeeded** (openapi-typescript 7.13.0) — `docs/api-types.ts`, 220 KB |
| `docs/API_HANDOFF.md` | written — 19 sections (§4 is the full error-code table) |

`contract_check.py` proves the direction that matters: every route in DESIGN.md §5 exists in the
app with the documented role, and nothing is implemented that §5 does not document. Four rows have
a per-row rule (owner/assignee) that a route table cannot express, and one row is deferred to M2;
both counts are printed rather than hidden.

`docs/api-types.ts` and `docs/openapi.json` are **generated** — never hand-edited. Regenerate both
in the same commit as any contract change, or the frontend's types drift from the server silently.
The handoff doc's §19, "Changes since the original contract", is derived from
`git log -p docs/DESIGN.md` and lists the four corrections Phase 7 made to §5 (the `/health` row,
the tasks router's real role reading, the plans `POST`/`PATCH` split, and the notation changes).

---

## STEP 2 — End-to-end proof

Two independent proofs, because one proves the code and the other proves the deployment.

### In-process: `tests/test_e2e_semester.py`

Drives the whole semester story through `TestClient` against `TEST_DATABASE_URL`, creating its own
uniquely-named data so it never depends on the seed.

### Over HTTP: `scripts/smoke_e2e.py` → `smoke_e2e.txt`

Public API only, against a running server, with a PASS/FAIL table and a non-zero exit on failure.

```
  1. A student joins and pays dues                   PASS  SSA-2026-0025 on plan Basic (500 INR)
  2. Organizer publishes the event and announces it  PASS  Gala Smoke <run id> published with 3 seats
  3. Three seats, four buyers                        PASS  sold 3/3, member paid 1000, guests 1500
  4. The door: check-in and the event report         PASS  VALID/ALREADY_USED/INVALID/WRONG_EVENT
  5. Merch sells out and ships                       PASS  1 sold at 720 (discount 10%), 1 left
  6. A fundraiser, its board and its cash            PASS  3 cards, 1 done; 1000 INR twice, one row
  7. A claim, a refusal, a payment                   PASS  SELF_REVIEW refused; paid once
  8. The books add up                                PASS  reconcile ok; opening + movement = closing
  9. Close the period, refuse a late entry, reopen   PASS  409 PERIOD_CLOSED -> 403 -> admin reopened
  9/9 steps passed
```

Every step asserts real values — the seat count that comes back, the price difference between a
member and a guest, the balance before and after a reimbursement, the ledger total after a
double-submitted income. The run id is suffixed onto every object the script creates, so two runs
never collide and neither touches seeded data.

---

## STEP 3 — Demo data and reset

`scripts/reset_demo.py --yes` truncates every application table except `alembic_version`
(`RESTART IDENTITY CASCADE`), deletes the receipt objects, and runs the full seed. It prints the
database host and name, refuses to run if `APP_ENV=production`, refuses to target the test database
without `--target test`, refuses to run inside pytest, and connects on `DIRECT_URL`.

`scripts/seed.py` is complete and idempotent for all seven phases and prints a **DEMO ACCOUNTS**
table and a **KEY IDS** block. The eight demo accounts (one password: `Passw0rd!`):

| Email | Role | State |
|---|---|---|
| `member@ssa.org` | member | active, Standard, ends 2027-04-28 |
| `expiring@ssa.org` | member | active, Basic, **ends in 8 days** |
| `expired@ssa.org` | member | expired 30 days ago |
| `guest@ssa.org` | guest | never paid, no membership |
| `admin@ssa.org` / `treasurer@ssa.org` / `organizer@ssa.org` / `volunteer@ssa.org` | staff | every admin screen |

Plus `neha@ssa.org` / `rohit@ssa.org`, 20 `member01..20@ssa.org`, and `bouncing@fail.test` (the
deliberate undeliverable address, inserted directly into the database).

**All six per-phase demo scripts run green against a freshly reseeded database** — see
`demo_phase1.txt` … `demo_phase6.txt`. Phase 5 was broken by this phase's own seed change
(finding #2 above) and is fixed.

---

## STEP 4 — Security and production readiness (no deploy)

Nothing here is a new product feature; all of it is a guarantee, and every guarantee has a test in
`tests/test_hardening.py` unless noted.

| Guarantee | Where it is enforced |
|---|---|
| Startup config validation — a misconfigured dev machine warns loudly, a misconfigured **production** deployment does not start | `Settings.enforce_startup_config()` (`APP_ENV=production` ⇒ `RuntimeError`) |
| Rate limits: login 10/min/IP, register 10/min/IP, check-in 120/min/user, ticket and merch checkout 30/min/user | `app/core/ratelimit.py`, `429 TOO_MANY_REQUESTS` + `Retry-After` |
| Lockout: 5 consecutive failed logins per email locks that email for 15 minutes; a success resets it | same; the failure message never says whether the email exists |
| Password policy: 8+ characters with a letter and a number → `422 WEAK_PASSWORD` | `check_password_policy`, not a pydantic constraint |
| Generic "invalid email or password" on login | `INVALID_CREDENTIALS` |
| `X-Request-ID` echoed if supplied, minted otherwise | `app/core/middleware.py` |
| Security headers on every response, errors included: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer` | same |
| Request logging that never records `Authorization`, a password, a JWT, a signed URL, the service-role key or a token query string | the log line is built from `request.url.path`, so the query string and the headers cannot reach it |
| `404`/`405`/`422`/`500` all use the one error envelope; `422` carries `details.fields[]`; `500` carries no traceback, and the traceback plus the request id go to the log | `app/core/errors.py` |
| Route protection: every route is 401 without a token unless it is on the documented `PUBLIC_ALLOWLIST`, and a role matrix checks a member against `MEMBER_ALLOWED` | `tests/test_hardening.py` |
| No response schema exposes a secret — the openapi response schemas are walked for forbidden field names | same |
| No secret in the tree | `scripts/secret_scan.py` — 151 tracked text files, `OK: no live credentials found`, exit 0 (it found two JWTs in `demo_phase1.txt` first — finding #8) |
| `.env`, `backend/var/` (receipts) and `.venv/` are gitignored | verified with `git check-ignore` |
| Scheduler: named jobs, `max_instances=1`, `coalesce=True`, one worker | `app/jobs/scheduler.py`; the single-worker requirement is documented in `README.md` and `docs/ARCHITECTURE.md` |

### Database review

The Postgres catalog was queried for foreign keys with no supporting index and for tables with RLS
off. 47 FKs, 98 indexes, **20 FKs without a supporting index** — of which only two are actually
filtered on by the API, because the other 18 are display joins through `users`' primary key. One
migration, `b7f1c9a4e2d8`, adds exactly those two: `ix_tasks_event_id` and `ix_fundraisers_owner_id`.
Nothing else was indexed. `EXPLAIN ANALYZE` on the hot queries, against the seeded database:

| Query | Plan | Time |
|---|---|---|
| check-in by code | `Index Scan using ix_tickets_code` | 1.420 ms |
| event detail with ticket types | Seq Scan over 5 rows | 0.045 ms |
| products list | `Index Scan using ix_products_name` | 0.646 ms |
| finance summary by source | HashAggregate over 162 rows | 0.144 ms |
| ledger list | `Index Scan Backward using ix_transactions_occurred_at` + Incremental Sort | 0.658 ms |
| tasks by event | Seq Scan over 17 rows | 0.037 ms |

### Performance: `scripts/perf_check.py` → `perf_check.txt`

200 sequential `POST /checkin`, then 100 sequential reads each, against a running server and the
freshly seeded demo database:

| Endpoint | n | p50 | p95 | max | target |
|---|---|---|---|---|---|
| `POST /checkin` | 200 | 385.8 ms | **540.4 ms** | 1288.5 ms | p95 < 300 ms — **MISSED** |
| `GET /events/{id}` | 100 | 130.8 ms | 138.4 ms | 375.1 ms | — |
| `GET /finance/summary` | 100 | 325.2 ms | 373.3 ms | 1074.5 ms | — |
| `GET /products` | 100 | 164.5 ms | 190.6 ms | 406.2 ms | — |

**The target was missed, and the reason is the network, not the query.** Measured on the same
machine, in the same session:

- A bare `SELECT 1` to the Supabase pooler is **29.9 ms p50** (min 29.5) — that is the floor for
  every single round trip.
- A check-in issues **10 SQL statements** (counted with a `before_cursor_execute` listener, not
  guessed): auth, the event, the ticket by code, two `ticket_types` lookups, the conditional
  `UPDATE`, the refresh, the holder, and the two counter queries. `GET /events/{id}` is 2,
  `/finance/summary` is 8, `/products` is 3.
- 10 × 30 ms is already 300 ms before any application work, and the engine's `pool_pre_ping` adds
  one more round trip per checkout. That accounts for essentially all of the 386 ms p50.
- The server-side cost of the check-in query itself is **1.420 ms** (`EXPLAIN ANALYZE`,
  `Index Scan using ix_tickets_code`).

So the honest reading is: **the 300 ms target is a co-location target, and it cannot be measured
from a laptop 30 ms away from the database.** The application's own query time is single-digit
milliseconds; what the number above is dominated by is ten round trips to `ap-south-1`.

What this does *not* establish, and the reviewer should not read into it: **no measurement here
proves the target is met when co-located.** It proves the app's query time is 1.4 ms and the
deficit is round trips. Re-running `python scripts/perf_check.py` from the deployment region — the
Render service and the Supabase project in the same region — is the measurement that would settle
it, and it is listed as open below.

One thing was tried and **reverted**: `check_in` calls `db.get(Event, …)`, which eager-loads every
ticket type of the event (`Event.ticket_types` is `lazy="selectin"` for the events list). Replacing
it with an id-existence check did not change the statement count — 10 either way, because the
response builder's own `ticket_type` lookup triggers the same load — so the hot path was left
alone rather than churned for no measured gain.

---

## STEP 5 — Documentation

| Document | For |
|---|---|
| `backend/README.md` | how to run, change and test the backend; the scripts; the seeded accounts |
| `docs/API_HANDOFF.md` | the frontend's single contract document |
| `docs/ARCHITECTURE.md` | the layers, the two-URL database, money and the one ledger function, concurrency by conditional write, the delivery worker, storage, background jobs |
| `docs/DEMO_SCRIPT.md` | a three-minute presenter script with timings, talking points and what not to do on stage |
| `docs/M2_BACKLOG.md` | what Milestone 2 should build, and the operational debt this milestone carries |

---

## STEP 6 — Phase gate

The suite is run on `TEST_DATABASE_URL` only, three times in a row and then once in a seeded random
order, because a suite that only passes in one order is a suite that shares state between tests.
All four runs are in `pytest.txt`.

| Run | Result |
|---|---|
| 1 | `322 passed, 1 warning in 578.46s` — exit 0 |
| 2 | `322 passed, 1 warning in 588.90s` — exit 0 |
| 3 | `322 passed, 1 warning in 568.26s` — exit 0 |
| shuffled (`random.seed(7)`) | `322 passed, 1 warning in 563.73s` — exit 0 |

The single warning is third-party on every run — an `anyio.abc.BlockingPortal` deprecation raised by
the installed `starlette/testclient.py:45`. Nothing in `app/` or `tests/` raises a warning.

**The shuffled run caught a defect in the gate itself, not in the suite.** The first attempt
collected node ids with `--collect-only -q` and replayed them into a second pytest process. It
reported `EXIT=4` in 0.40 s — pytest's usage error — having executed **zero** tests:

```
ERROR: not found: ...\tests\test_hardening.py::test_framework_errors_use_the_envelope
```

`tests/test_hardening.py:66` is `FAKE_ID = str(uuid4())`, a module-level constant, and
`test_framework_errors_use_the_envelope` parametrises over it. Its node id therefore contains a uuid
that is regenerated in every process, so an id collected in one process cannot exist in the next.
pytest 9 refuses to collect anything when a single argument does not resolve. A gate that reports red
because it never ran is indistinguishable, from the exit code alone, from a genuinely failing suite.

The recorded run shuffles the item list **inside one session** instead (`-p` with a throwaway
plugin), which is what "run it shuffled" actually means. Sampled collection order confirms the
shuffle takes effect. Worth carrying forward: `--collect-only` node ids are not replayable for any
suite containing a parametrize over a per-process value. Ordinary runs are unaffected, so the test
was left alone rather than changed to suit a tool.

---

## FINISH — state at hand-off

| | |
|---|---|
| Branch | `be/phase-7-hardening-docs` — pushed, then merged into `main` with `--no-ff` |
| Merge commit | `5894f87` |
| Tag | `backend-m1-done` |
| Contract artifacts | `docs/openapi.json` (70 paths), `docs/api-types.ts` — generated, never hand-edited |
| Test console | `frontend/api-console.html` — a no-build page for driving the API by hand |

`frontend/` is otherwise empty; the React app is still the other teammate's to build from
`docs/DESIGN.md`. The console is a testing tool committed alongside it, not a start on that work.

---

## Could not be verified here, and why

- **The check-in latency target, met.** See the perf section: the app's query time is 1.4 ms and the
  deficit is round trips to a database 30 ms away. `perf_check.py` must be re-run from the
  deployment region to answer the question the target is actually asking.

- **A real Supabase Storage round trip.** `check_storage.py` passes against `STORAGE_PROVIDER=local`
  (the dev setting); the Supabase provider now has HTTP-contract tests with a stubbed transport, but
  no test on this machine downloads a receipt from a real private bucket, because the dev `.env` has
  no `SUPABASE_SERVICE_ROLE_KEY`. Set `STORAGE_PROVIDER=supabase` with real credentials and re-run
  `check_storage.py` to close this.
- **A real deployment.** Deliberately out of scope: no Dockerfile, no hosting config, no
  `APP_ENV=production` run. The production-only branch of `enforce_startup_config` is therefore
  exercised by unit test, not by an actual boot.
- **The frontend.** Built separately from `docs/DESIGN.md` against mocks. The contract published
  here is machine-checked against the running app, but no frontend request has been made against it.
- **Multiple workers.** The rate limiter is in-memory and the scheduler is in-process, so the app is
  correct only as a single worker. That is documented as a requirement rather than fixed; moving the
  limiter to Redis and the scheduler out of process is `docs/M2_BACKLOG.md` §7.
