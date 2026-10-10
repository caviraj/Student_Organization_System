#!/usr/bin/env bash
#
# Phase 2 demo - Events, Tickets & Check-in.
#
#   bash scripts/demo_phase2.sh
#
# Migrates + seeds the database, starts the API on :8000 if it is not already up, then walks
# the whole ticketing journey: organizer creates and publishes an event, a non-member and an
# active member each buy a ticket at their own price, a volunteer scans them in at the door,
# the last seat is defended against an oversell, and the organizer reads the report.
#
# Depends on: curl, python.

set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PY:-python}"
PORT="${PORT:-8000}"
ROOT="http://127.0.0.1:${PORT}"
BASE="$ROOT/api/v1"
UVICORN_PID=""
STAMP="$(date +%s)"

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
hr() { if [ -t 1 ]; then printf "\n\033[1m%s\033[0m\n" "$1"; else printf "\n== %s\n" "$1"; fi; }
post() { curl -s -X POST "$BASE$1" -H 'Content-Type: application/json' "${@:2}"; }
# Same request, but with the HTTP status appended - so a 409/403 is visible, not just its body.
post_status() { curl -s -X POST "$BASE$1" -w '\nHTTP %{http_code}\n' -H 'Content-Type: application/json' "${@:2}"; }
patch() { curl -s -X PATCH "$BASE$1" -H 'Content-Type: application/json' "${@:2}"; }
in_days() { "$PY" -c "from datetime import UTC, datetime, timedelta; print((datetime.now(UTC)+timedelta(days=$1, hours=$2)).isoformat().replace('+00:00','Z'))"; }

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

hr "1. POST /auth/login  (organizer@ssa.org)"
ORG_TOKEN=$(post /auth/login -d "{\"email\":\"organizer@ssa.org\",\"password\":\"$PASSWORD\"}" | pick access_token)
echo "organizer token issued"

hr "2. POST /events  (organizer+; new events start as a draft)"
EVENT=$(post /events -H "Authorization: Bearer $ORG_TOKEN" -d "{
  \"title\": \"Demo Night $STAMP\",
  \"description\": \"One-night showcase for the Phase 2 demo.\",
  \"venue\": \"Main Auditorium\",
  \"starts_at\": \"$(in_days 7 0)\",
  \"ends_at\": \"$(in_days 7 3)\"
}")
echo "$EVENT" | pretty
EVENT_ID=$(echo "$EVENT" | pick id)

hr "3. POST /events/$EVENT_ID/ticket-types  (capacity 3, so the last seat is scarce)"
TICKET_TYPE=$(post "/events/$EVENT_ID/ticket-types" -H "Authorization: Bearer $ORG_TOKEN" -d '{
  "name": "General",
  "member_price": 30000,
  "non_member_price": 50000,
  "capacity": 3
}')
echo "$TICKET_TYPE" | pretty
TICKET_TYPE_ID=$(echo "$TICKET_TYPE" | pick id)

hr "4. PATCH /events/$EVENT_ID {status: published}  (draft -> published)"
patch "/events/$EVENT_ID" -H "Authorization: Bearer $ORG_TOKEN" -d '{"status":"published"}' | pretty

hr "5. GET /events/$EVENT_ID  (as a guest: both prices, price_for_you null, 3 seats left)"
curl -s "$BASE/events/$EVENT_ID" | pretty

hr "6. POST /tickets/checkout  (a NON-member: pays 50000 paise)"
GUEST_EMAIL="demo.guest.$STAMP@ssa.org"
GUEST_TOKEN=$(post /auth/register -d "{
  \"email\": \"$GUEST_EMAIL\",
  \"password\": \"$PASSWORD\",
  \"full_name\": \"Demo Guest\",
  \"department\": \"CSE\",
  \"year\": 2
}" | pick access_token)
GUEST_CHECKOUT=$(post /tickets/checkout -H "Authorization: Bearer $GUEST_TOKEN" -d "{\"ticket_type_id\":\"$TICKET_TYPE_ID\",\"quantity\":1}")
echo "$GUEST_CHECKOUT" | pretty
GUEST_ORDER_ID=$(echo "$GUEST_CHECKOUT" | pick order_id)

hr "7. POST /tickets/checkout  (an ACTIVE member, member01@ssa.org: pays 30000 paise)"
MEMBER_TOKEN=$(post /auth/login -d "{\"email\":\"member01@ssa.org\",\"password\":\"$PASSWORD\"}" | pick access_token)
MEMBER_CHECKOUT=$(post /tickets/checkout -H "Authorization: Bearer $MEMBER_TOKEN" -d "{\"ticket_type_id\":\"$TICKET_TYPE_ID\",\"quantity\":1}")
echo "$MEMBER_CHECKOUT" | pretty
MEMBER_ORDER_ID=$(echo "$MEMBER_CHECKOUT" | pick order_id)

hr "8. POST /payments/{order}/mock-confirm  x2  (each order mints its own ticket)"
GUEST_CONFIRM=$(post "/payments/$GUEST_ORDER_ID/mock-confirm" -H "Authorization: Bearer $GUEST_TOKEN" -d '{"outcome":"success"}')
echo "$GUEST_CONFIRM" | pretty
GUEST_CODE=$(echo "$GUEST_CONFIRM" | pick tickets 0 code)
MEMBER_CONFIRM=$(post "/payments/$MEMBER_ORDER_ID/mock-confirm" -H "Authorization: Bearer $MEMBER_TOKEN" -d '{"outcome":"success"}')
echo "$MEMBER_CONFIRM" | pretty
MEMBER_CODE=$(echo "$MEMBER_CONFIRM" | pick tickets 0 code)
echo "non-member code $GUEST_CODE (paid 50000) | member code $MEMBER_CODE (paid 30000)"

hr "9. GET /tickets/me  (upcoming first, with event title, venue and code)"
curl -s "$BASE/tickets/me" -H "Authorization: Bearer $MEMBER_TOKEN" | pretty

hr "10. POST /checkin  (volunteer@ssa.org scans the member's code -> VALID)"
VOL_TOKEN=$(post /auth/login -d "{\"email\":\"volunteer@ssa.org\",\"password\":\"$PASSWORD\"}" | pick access_token)
post /checkin -H "Authorization: Bearer $VOL_TOKEN" -d "{\"event_id\":\"$EVENT_ID\",\"code\":\"$MEMBER_CODE\"}" | pretty

hr "11. POST /checkin  (same code again -> ALREADY_USED, with the first scan's timestamp)"
post /checkin -H "Authorization: Bearer $VOL_TOKEN" -d "{\"event_id\":\"$EVENT_ID\",\"code\":\"$MEMBER_CODE\"}" | pretty

hr "12. POST /checkin  (junk code -> INVALID; still HTTP 200, the door needs an answer)"
post /checkin -H "Authorization: Bearer $VOL_TOKEN" -d "{\"event_id\":\"$EVENT_ID\",\"code\":\"NOT-A-TICKET\"}" | pretty

hr "13. POST /tickets/checkout x5  (only 1 seat left -> 409 SOLD_OUT with seats_left)"
post_status /tickets/checkout -H "Authorization: Bearer $GUEST_TOKEN" -d "{\"ticket_type_id\":\"$TICKET_TYPE_ID\",\"quantity\":5}"

hr "14. GET /events/$EVENT_ID/report  (organizer+: sales, attendance, revenue)"
curl -s "$BASE/events/$EVENT_ID/report" -H "Authorization: Bearer $ORG_TOKEN" | pretty

hr "15. GET /events/$EVENT_ID/attendees  (organizer+; filter by status)"
curl -s "$BASE/events/$EVENT_ID/attendees?status=used" -H "Authorization: Bearer $ORG_TOKEN" | pretty

hr "16. ledger rows for this event  (ticket income lands on the ledger, DESIGN.md 4.3)"
EVENT_ID="$EVENT_ID" "$PY" -c '
import json, os
from uuid import UUID

from app.core.db import SessionLocal
from app.models import Transaction

db = SessionLocal()
try:
    rows = db.query(Transaction).filter(Transaction.event_id == UUID(os.environ["EVENT_ID"])).all()
    print(json.dumps(
        [{"direction": t.direction, "source": t.source, "amount": t.amount, "ref_type": t.ref_type, "note": t.note} for t in rows],
        indent=2,
    ))
finally:
    db.close()
'

hr "done"
echo "One event, two prices, one seat defended, two scans, one report - and every rupee on the"
echo "ledger. Swagger UI (tags: events, tickets, check-in): $ROOT/docs"
