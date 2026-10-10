#!/usr/bin/env bash
#
# Phase 3 demo - Announcements & the mailing list.
#
#   bash scripts/demo_phase3.sh
#
# Migrates + seeds the database, starts the API on :8000 if it is not already up, then walks the
# whole noticeboard journey: an organizer posts a members-only announcement with email on, the
# worker delivers it, a guest cannot see it and a member can, an edit leaves a revision trail, a
# member switches email off and is skipped, and the unsubscribe link from the console email turns
# the mail off for good. It ends with scripts/check_db.py, which fails if any public table in the
# database is missing Row Level Security.
#
# Depends on: curl, python.

set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PY:-python}"
PORT="${PORT:-8000}"
ROOT="http://127.0.0.1:${PORT}"
BASE="$ROOT/api/v1"
LOG="${TMPDIR:-/tmp}/ssa_uvicorn.log"
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
patch() { curl -s -X PATCH "$BASE$1" -H 'Content-Type: application/json' "${@:2}"; }

# The feed as a reader sees it: category, audience, title.
# (Single-quoted for the shell, so the Python inside uses double quotes only.)
feed() {
  "$PY" -c '
import json, sys
items = json.load(sys.stdin)["items"]
print("  {} post(s)".format(len(items)))
for item in items:
    pin = " [pinned]" if item["is_pinned"] else ""
    print("  - {:<9} {:<8} \"{}\"{}  by {}".format(
        item["category"], item["audience"], item["title"], pin, item["author_name"]))
    print("      {}...".format(item["body_preview"][:60]))
'
}

# A demo post must be findable in the feed, so the guest/member check is a real check.
visible_to() {  # visible_to <guest|member> <token-or-empty> <title>
  local body
  if [ -n "$2" ]; then body=$(curl -s "$BASE/announcements" -H "Authorization: Bearer $2"); else body=$(curl -s "$BASE/announcements"); fi
  if echo "$body" | grep -qF "$3"; then echo "  $1: SEES \"$3\""; else echo "  $1: does not see \"$3\""; fi
}

hr "0. migrate + seed  (Alembic + seed.py run on DIRECT_URL, the session pooler)"
"$PY" -m alembic upgrade head
"$PY" scripts/seed.py

if ! curl -sf "$ROOT/health" >/dev/null 2>&1; then
  hr "starting uvicorn on :$PORT  (log: $LOG)"
  "$PY" -m uvicorn app.main:app --port "$PORT" >"$LOG" 2>&1 &
  UVICORN_PID=$!
  for _ in $(seq 1 60); do
    if curl -sf "$ROOT/health" >/dev/null 2>&1; then break; fi
    sleep 0.5
  done
fi
hr "health"
curl -s "$ROOT/health" | pretty

PASSWORD="Passw0rd!"
ORG_TOKEN=$(post /auth/login -d "{\"email\":\"organizer@ssa.org\",\"password\":\"$PASSWORD\"}" | pick access_token)
ADMIN_TOKEN=$(post /auth/login -d "{\"email\":\"admin@ssa.org\",\"password\":\"$PASSWORD\"}" | pick access_token)
MEMBER_TOKEN=$(post /auth/login -d "{\"email\":\"member05@ssa.org\",\"password\":\"$PASSWORD\"}" | pick access_token)
MEMBER6_TOKEN=$(post /auth/login -d "{\"email\":\"member06@ssa.org\",\"password\":\"$PASSWORD\"}" | pick access_token)
echo "signed in as organizer@ssa.org, admin@ssa.org, member05@ssa.org and member06@ssa.org"

hr "0b. POST /users/me/email-preferences  (member06 back on, so this demo repeats cleanly)"
post /users/me/email-preferences -H "Authorization: Bearer $MEMBER6_TOKEN" -d '{"email_opt_in":true}' | pretty
echo "Every run below ends with member06 opted out, so the demo resets that first - otherwise"
echo "step 10 would show no change on a second run."

MEMBERS_TITLE="Members' AGM next Friday ($STAMP)"

hr "1. POST /announcements  (organizer+: members-only, send_email=true)"
ANNOUNCEMENT=$(post /announcements -H "Authorization: Bearer $ORG_TOKEN" -d "{
  \"title\": \"$MEMBERS_TITLE\",
  \"body\": \"The Annual General Meeting is next Friday at 4 PM in the Seminar Hall. Dues for the next year can be paid at the desk.\",
  \"category\": \"deadline\",
  \"audience\": \"members\",
  \"send_email\": true
}")
echo "$ANNOUNCEMENT" | pretty
ANNOUNCEMENT_ID=$(echo "$ANNOUNCEMENT" | pick id)
echo "delivery_summary is a QUEUE count, not a receipt - the worker has not run yet."

hr "2. wait 3s  (POST kicks the worker through BackgroundTasks; the 60s job is the safety net)"
sleep 3

hr "3. GET /announcements/$ANNOUNCEMENT_ID/deliveries  (admin): what actually went out"
curl -s "$BASE/announcements/$ANNOUNCEMENT_ID/deliveries" -H "Authorization: Bearer $ADMIN_TOKEN" | pretty
echo "Every active member has an in-app row; only the opted-in ones have an email row."

hr "4. GET /announcements  as a guest  (no token, no members-only post)"
visible_to "guest " "" "$MEMBERS_TITLE"
visible_to "member" "$MEMBER_TOKEN" "$MEMBERS_TITLE"
if curl -s "$BASE/announcements" | grep -qF "$MEMBERS_TITLE"; then
  echo "FAIL: the members-only post leaked to a guest"; exit 1
fi

hr "5. GET /announcements  as member05  (the same feed, one post longer)"
curl -s "$BASE/announcements" -H "Authorization: Bearer $MEMBER_TOKEN" | feed

hr "6. PATCH /announcements/$ANNOUNCEMENT_ID  (organizer+: body changed, revision_note required)"
patch "/announcements/$ANNOUNCEMENT_ID" -H "Authorization: Bearer $ORG_TOKEN" -d '{
  "body": "The Annual General Meeting is next Friday at 4 PM in the Seminar Hall. Dues for the next year can be paid at the desk, or online from the members page.",
  "revision_note": "Added the online payment option"
}' | pretty

hr "7. PATCH with a 2-character note  (422: the record of WHY has a floor)"
patch "/announcements/$ANNOUNCEMENT_ID" -H "Authorization: Bearer $ORG_TOKEN" -d '{"body":"nope","revision_note":"ty"}' | pretty

hr "8. GET /announcements/$ANNOUNCEMENT_ID/revisions  (organizer+: the version that was replaced)"
curl -s "$BASE/announcements/$ANNOUNCEMENT_ID/revisions" -H "Authorization: Bearer $ORG_TOKEN" | pretty

hr "9. POST /users/me/email-preferences  (member06 switches email off)"
post /users/me/email-preferences -H "Authorization: Bearer $MEMBER6_TOKEN" -d '{"email_opt_in":false}' | pretty

hr "10. POST /announcements  (organizer+ again: member06 is now skipped)"
SECOND=$(post /announcements -H "Authorization: Bearer $ORG_TOKEN" -d "{
  \"title\": \"Hoodies are in ($STAMP)\",
  \"body\": \"Pre-ordered hoodies can be collected from the club room between 11 AM and 5 PM.\",
  \"category\": \"general\",
  \"audience\": \"members\",
  \"send_email\": true
}")
echo "$SECOND" | pretty
SECOND_ID=$(echo "$SECOND" | pick id)
echo "  skipped_opted_out: $(echo "$ANNOUNCEMENT" | pick delivery_summary skipped_opted_out) for the first post, $(echo "$SECOND" | pick delivery_summary skipped_opted_out) now"
sleep 3

hr "11. GET /announcements/$SECOND_ID/deliveries  (admin: one more email skipped)"
curl -s "$BASE/announcements/$SECOND_ID/deliveries" -H "Authorization: Bearer $ADMIN_TOKEN" | pretty

hr "12. GET /unsubscribe?token=...  (the link from the console email, no session needed)"
if [ -f "$LOG" ]; then
  LINK=$(grep -o 'unsubscribe?token=[A-Za-z0-9._-]*' "$LOG" | tail -1 || true)
else
  LINK=""
fi
if [ -n "$LINK" ]; then
  echo "read from the console provider's output in $LOG:"
  echo "  ${LINK:0:60}..."
else
  echo "(no console log to read - this API was already running; minting the same link directly)"
  LINK="unsubscribe?token=$("$PY" -c '
from sqlalchemy import select
from app.core.db import SessionLocal
from app.models import User
from app.services.unsubscribe import create_unsubscribe_token

db = SessionLocal()
try:
    print(create_unsubscribe_token(db.scalar(select(User).where(User.email == "member07@ssa.org"))))
finally:
    db.close()
')"
fi
curl -s "$BASE/$LINK" | pretty

hr "13. script/check_db.py  (DATABASE_URL, the pooler: server, tables, RLS)"
"$PY" scripts/check_db.py

hr "done"
echo "One post, one audience, one queue, one revision trail, one unsubscribe - and RLS on every"
echo "public table. Swagger UI (tags: Announcements, Preferences): $ROOT/docs"
