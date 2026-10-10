# AGENTS.md — Rules for AI Coding Agents (Claude Code / DeepSeek / Antigravity / Gemini)

> Copy this file to `backend/CLAUDE.md` for Claude Code. Antigravity reads `AGENTS.md` at repo root.
> **Always read first:** `docs/PRD.md`, `docs/DESIGN.md`, `docs/TASKS.md`. Work ONLY on the current phase given in the prompt.

## Project
SSA Hub — one platform for a student club: members, events/tickets, announcements, merch, fundraiser tasks, finance. Monorepo: `backend/` (FastAPI) and `frontend/` (React+TS).

## Golden Rules (all agents)
1. **DESIGN.md §5 is the API contract.** Never rename/remove fields or endpoints silently. If a change is needed, update DESIGN.md in the same change and say so.
2. **Stay in the current phase.** No features from later phases. No refactoring unrelated code.
3. **Money = integer paise.** Never floats. Display via `formatINR`.
4. **Never commit secrets.** Use `.env` (gitignored) + `.env.example`.
5. **Finish with visibility:** run tests/build, produce the demo artifact for the phase, then print the exact git commands to push (do not force-push; never push to `main` directly).
6. Small, reviewable commits using Conventional Commits.
7. If something is ambiguous, pick the simplest option consistent with the PRD, note the assumption in the PR description, and continue.
8. Don't leave TODO stubs that break the demo; either implement or hide behind a feature flag.

## Backend rules (Claude Code + DeepSeek)
- Python 3.11, FastAPI, SQLAlchemy 2.x (typed `Mapped[]`), Alembic migrations for every schema change (no manual DDL), Pydantic v2 schemas separate from ORM models.
- Layering: `routers` (HTTP only) → `services` (business rules, transactions) → `models`. No business logic in routers.
- Auth: JWT (HS256) + bcrypt; dependencies `require_role(...)`. Every non-public route must be protected.
- **Concurrency-safe writes:** capacity/stock via conditional `UPDATE ... WHERE ...` inside a transaction; payment success handler idempotent.
- Consistent error shape `{error:{code,message,details}}`; use HTTP 409 for conflicts (SOLD_OUT, ALREADY_USED).
- Every phase must add: pytest tests for the business rules, `scripts/demo_phaseN.sh`, and seed data additions in `scripts/seed.py`.
- Type hints everywhere; `ruff` + `black` clean.
- Commands: `uvicorn app.main:app --reload` · `alembic upgrade head` · `pytest -q` · `python scripts/seed.py`.

## Frontend rules (Antigravity + Gemini)
- React 19 + TypeScript (strict), Vite, Tailwind, React Router, TanStack Query, Zod for forms.
- Feature-folder structure `src/features/<domain>`; shared UI in `src/components/ui`.
- Build against the contract; use MSW mocks until backend is ready (`VITE_USE_MOCKS`).
- Mobile-first; every page needs loading skeleton, empty state, and error state.
- Accessible: labels, focus states, colour contrast; scanner result must be readable at arm's length (big colour + text).
- No hardcoded API URLs — use `VITE_API_URL`.
- Commands: `npm run dev` · `npm run build` · `npm run lint` · `npm test`.

## Definition of Done per phase
Tests/build pass · demo artifacts saved in `docs/demos/phaseN/` · Phase Log updated · branch pushed + PR + tag (commands printed for the human to run).

## Git Conventions
Branches: `be/phase-N-topic`, `fe/phase-N-topic`. Tags: `phase-N-done`, `v1.0-m1`.
