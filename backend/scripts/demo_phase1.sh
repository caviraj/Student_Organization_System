#!/usr/bin/env bash
#
# Phase 1 demo - Auth & Membership.
#
#   bash scripts/demo_phase1.sh
#
# Migrates + seeds the database, starts the API on :8000 if it is not already up,
# then walks the whole membership journey (register -> pay dues -> active member ->
# QR card -> staff verification -> renewals due) and pretty-prints every response.
#
# Depends on: curl, python.

set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PY:-python}"
PORT="${PORT:-8000}"
ROOT="http://127.0.0.1:${PORT}"
BASE="$ROOT/api/v1"
UVICORN_PID=""

cleanup() {
  if [ -n "$UVICORN_PID" ]; then kill "$UVICORN_PID" 2>/dev/null || true; fi
}
trap cleanup EXIT

pick() {  # pick <key|index>... : read JSON on stdin, walk that path, print the value
  "$PY" -c '
import json, sys
data = json.load(sys.stdin)
for key in sys.argv[1:]:
    data = data[int(key)] if key.lstrip("-").isdigit() else data[key]
print(data)
' "$@"
}

pretty() { "$PY" -m json.tool; }
hr() { printf "\n\033[1m%s\033[0m\n" "$1"; }
post() { curl -s -X POST "$BASE$1" -H 'Content-Type: application/json' "${@:2}"; }

EMAIL="demo.$(date +%s)@ssa.org"
PASSWORD="Passw0rd!"

hr "0. migrate + seed"
"$PY" -m alembic upgrade head
"$PY" scripts/seed.py

if ! curl -sf "$ROOT/health" >/dev/null 2>&1; then
  hr "starting uvicorn on :$PORT"
  "$PY" -m uvicorn app.main:app --port "$PORT" >"${TMPDIR:-/tmp}/ssa_uvicorn.log" 2>&1 &
  UVICORN_PID=$!
  for _ in $(seq 1 60); do
    if curl -sf "$ROOT/health" >/dev/null 2>&1; then break; fi
    sleep 0.5
  done
fi
hr "health"
curl -s "$ROOT/health" | pretty

hr "1. POST /auth/register  ($EMAIL)"
REGISTER=$(post /auth/register -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\",\"full_name\":\"Demo Student\",\"phone\":\"9876500000\",\"department\":\"CSE\",\"year\":2}")
echo "$REGISTER" | pretty
TOKEN=$(echo "$REGISTER" | pick access_token)

hr "2. POST /auth/login"
LOGIN=$(post /auth/login -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}")
echo "$LOGIN" | pretty
TOKEN=$(echo "$LOGIN" | pick access_token)

hr "3. GET /plans  (public, active only)"
PLANS=$(curl -s "$BASE/plans")
echo "$PLANS" | pretty
PLAN_ID=$(echo "$PLANS" | pick items 1 id)

hr "4. POST /memberships/checkout  (Standard plan)"
CHECKOUT=$(post /memberships/checkout -H "Authorization: Bearer $TOKEN" -d "{\"plan_id\":\"$PLAN_ID\"}")
echo "$CHECKOUT" | pretty
ORDER_ID=$(echo "$CHECKOUT" | pick order_id)

hr "5. POST /payments/$ORDER_ID/mock-confirm  {outcome: success}"
CONFIRM=$(post "/payments/$ORDER_ID/mock-confirm" -H "Authorization: Bearer $TOKEN" -d '{"outcome":"success"}')
echo "$CONFIRM" | pretty

hr "6. same call again -> idempotent, nothing duplicated"
post "/payments/$ORDER_ID/mock-confirm" -H "Authorization: Bearer $TOKEN" -d '{"outcome":"success"}' | pretty

hr "7. GET /auth/me  (role promoted guest -> member, membership active)"
ME=$(curl -s "$BASE/auth/me" -H "Authorization: Bearer $TOKEN")
echo "$ME" | pretty
MEMBER_CODE=$(echo "$ME" | pick member_code)

hr "8. GET /members/me/card  (QR payload)"
curl -s "$BASE/members/me/card" -H "Authorization: Bearer $TOKEN" | pretty

hr "9. POST /auth/login  (admin@ssa.org - seeded)"
ADMIN_TOKEN=$(post /auth/login -d '{"email":"admin@ssa.org","password":"Passw0rd!"}' | pick access_token)
echo "admin token issued"

hr "10. GET /members/verify?code=$MEMBER_CODE  (volunteer+; admin here)"
curl -s "$BASE/members/verify?code=$MEMBER_CODE" -H "Authorization: Bearer $ADMIN_TOKEN" | pretty

hr "10b. GET /members/verify?code=SSA-2026-9999  (not a member)"
curl -s "$BASE/members/verify?code=SSA-2026-9999" -H "Authorization: Bearer $ADMIN_TOKEN" | pretty

hr "11. GET /memberships/renewals-due  (active memberships ending within 30 days)"
curl -s "$BASE/memberships/renewals-due?page_size=5" -H "Authorization: Bearer $ADMIN_TOKEN" | pretty

hr "12. ledger row for this order  (money is traceable, DESIGN.md 4.3)"
ORDER_ID="$ORDER_ID" "$PY" -c '
import json, os
from uuid import UUID

from app.core.db import SessionLocal
from app.models import Transaction

db = SessionLocal()
try:
    rows = db.query(Transaction).filter(Transaction.ref_id == UUID(os.environ["ORDER_ID"])).all()
    print(json.dumps(
        [{"direction": t.direction, "source": t.source, "amount": t.amount, "ref_type": t.ref_type, "note": t.note} for t in rows],
        indent=2,
    ))
finally:
    db.close()
'

hr "done"
echo "The new member is active, has a member code, shows in the admin renewals list,"
echo "and their dues are on the ledger. Swagger UI: $ROOT/docs"
