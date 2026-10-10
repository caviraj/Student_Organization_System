# SSA Hub — Backend

FastAPI + SQLAlchemy 2.x + Alembic. Contract: `docs/DESIGN.md` §5. This README covers **Phase 1 (Auth & Membership)** only.

## Run it

```bash
cd backend
python -m venv .venv && . .venv/Scripts/activate   # Windows Git Bash; use .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
cp .env.example .env                                # edit JWT_SECRET before deploying

python -m alembic upgrade head                      # create the schema (Alembic is the only DDL path)
python scripts/seed.py                              # staff + 3 plans + 20 members in varied states
python -m uvicorn app.main:app --reload             # http://127.0.0.1:8000
```

- Swagger UI: <http://127.0.0.1:8000/docs> — every endpoint, tagged, with example bodies.
- Health: `GET /health`.
- End-to-end demo (migrate, seed, boot the server, walk the whole membership flow):
  `bash scripts/demo_phase1.sh`

`DATABASE_URL` defaults to a local SQLite file so nothing needs to be installed to run the demo.
Set it to `postgresql+psycopg://…` (see `.env.example`) to use Postgres; no model or migration changes are needed for either.

## Tests

```bash
python -m pytest -q
```

In-memory SQLite, one session per test, bcrypt rounds lowered via `BCRYPT_ROUNDS=4`. The suite never
starts the scheduler (the app is used without `TestClient`'s context manager), so it stays fast.

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
app/models/        SQLAlchemy models — one file, 8 tables (DESIGN.md §4)
app/schemas/       Pydantic v2 request/response models, kept separate from ORM models
app/routers/       HTTP only: parse, call a service, shape the response
app/services/      business rules — memberships, payments, ledger, reminders, accounts
app/jobs/          APScheduler wiring for the daily expiry scan
alembic/           migrations (autogenerate wired to Base.metadata)
scripts/           seed.py, demo_phase1.sh
tests/             pytest (auth, membership flow, reminders)
```

Money is **integer paise** everywhere — never a float. Errors are always
`{"error": {"code", "message", "details"}}`.

## Roles

`admin > treasurer > organizer > volunteer > member > guest`. `require_role("volunteer")` admits
volunteer and everyone above it. Role is read from the database on every request, so a promotion
applies immediately. Registering creates a `guest`; paying dues promotes `guest → member` and never
demotes anyone.

## Background job

APScheduler runs `services.reminders.run_expiry_scan()` at startup and every 24h: it expires
memberships whose `end_date` has passed and raises `expiry_30` / `expiry_7` / `expired` reminders,
at most once per membership per kind.
