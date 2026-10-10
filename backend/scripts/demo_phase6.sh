#!/usr/bin/env bash
#
# Phase 6 demo - expense claims, receipts, reimbursements and the treasurer's books.
#
#   bash scripts/demo_phase6.sh
#
# Migrates + seeds the database, starts the API on :8000 if it is not already up, then walks one
# claim from a volunteer's phone to the ledger: neha@ssa.org submits Rs 450 of printing with NO
# receipt, the treasurer approves it and is refused (409 RECEIPT_REQUIRED - a photo is what makes a
# claim auditable), the receipt goes up as a real PNG, approval lands, the owner is locked out of
# their own claim, and the treasurer pays it by UPI. Paying it again with the same body returns the
# same ledger row instead of paying twice. Then a rejection and a resubmission, a treasurer trying to
# approve their own claim (409 SELF_REVIEW), the upload wall (422 INVALID_FILE_TYPE, 413
# FILE_TOO_LARGE), the queue totals, the dashboard summary, the ledger table with a running balance,
# a hand-logged entry replayed by Idempotency-Key, a reversal, the funds check (409
# INSUFFICIENT_FUNDS, then an admin override), the semester report, closing a period and being
# refused a write inside it (409 PERIOD_CLOSED), and reopening it as an admin - never as a treasurer.
# It ends with the ledger rows printed by a direct SQL read (there is no public endpoint for the raw
# ledger, by design) and with scripts/check_db.py.
#
# Re-runnable: it clears its own demo rows first - claims whose description starts with "DEMO", the
# ledger rows that paid them, its manual entries and its period - then rebuilds them, so the numbers
# below read the same every run.
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
rupees() { "$PY" -c 'import sys; print("Rs {:,}".format(int(sys.argv[1]) // 100))' "$1"; }
post() { curl -s -X POST "$BASE$1" -H 'Content-Type: application/json' "${@:2}"; }
patch() { curl -s -X PATCH "$BASE$1" -H 'Content-Type: application/json' "${@:2}"; }
put() { curl -s -X PUT "$BASE$1" "${@:2}"; }
del() { curl -s -X DELETE "$BASE$1" -H 'Content-Type: application/json' "${@:2}"; }
get() { curl -s "$BASE$1" "${@:2}"; }
code() { curl -s -o /dev/null -w '%{http_code}' "$@"; }

claim() {  # claim <amount-paise> <description> <category> [extra curl args...]
  curl -s -X POST "$BASE/expenses" -F "amount=$1" -F "description=$2" -F "category=$3" \
    -F "incurred_on=$TODAY" "${@:4}"
}

claim_line() {  # one claim, the fields a claimant and a treasurer both look at
  "$PY" -c '
import json, sys

def rupees(paise):
    return "Rs {:,}".format(paise // 100)

c = json.load(sys.stdin)
print("  {:<9} {:>10}  {:<9} {:<38} receipt={} {:<11} {}".format(
    c["status"], rupees(c["amount"]), c["category"], c["description"][:38], c["has_receipt"],
    ("by " + c["reviewed_by"]["full_name"]) if c["reviewed_by"] else "",
    ("paid via " + c["reimbursement_method"]) if c["reimbursement_method"] else ""))
'
}

history() {
  "$PY" -c '
import json, sys

c = json.load(sys.stdin)
print("  {}  status={}  history:".format(c["description"], c["status"]))
for row in c["history"]:
    print("      {:<19} {:<11} {:<28} {}{}".format(
        row["created_at"][:19], row["action"], (row["actor"]["full_name"] if row["actor"] else "-"),
        row["note"] or "", "  note=" + row["note"] if row["action"] == "rejected" and row["note"] else ""))
'
}

ledger() {
  "$PY" -c '
import json, sys

def rupees(paise):
    return "Rs {:,}".format(paise // 100)

page = json.load(sys.stdin)
print("  {} entr(ies)".format(page["total"]))
for row in page["items"]:
    print("  {:<19} {:<4} {:>10}  {:<30} {:<22} {}".format(
        row["occurred_at"][:19], row["direction"], rupees(row["amount"]), row["label"][:30],
        row["source"], "REVERSAL of " + str(row["reverses_id"])[:8] if row["is_reversal"] else ""))
'
}

summary() {
  "$PY" -c '
import json, sys

def rupees(paise):
    return "Rs {:,}".format(paise // 100)

s = json.load(sys.stdin)
print("  in {}  out {}  balance {}".format(rupees(s["total_in"]), rupees(s["total_out"]), rupees(s["balance"])))
for row in s["by_source"]:
    print("      {:<22} in {:>10}  out {:>10}  net {:>10}".format(
        row["source"], rupees(row["in"]), rupees(row["out"]), rupees(row["net"])))
pending = s["pending_reimbursements"]
print("  waiting: {} submitted ({}) | {} approved unpaid ({})".format(
    pending["submitted_count"], rupees(pending["submitted_amount"]),
    pending["approved_unpaid_count"], rupees(pending["approved_unpaid_amount"])))
print("  counts: {}".format(s["counts"]))
'
}

# Both of these read an error body and neither may crash the script: a body that is not JSON at
# all (a 500 from a proxy, an empty reply) is exactly the thing the demo should show rather than hide.
err_body() {  # err_body <code|full>: print the code, or the whole error, from a body that may not be JSON
  "$PY" -c '
import json, sys

want = sys.argv[1]
raw = sys.stdin.read().strip()
try:
    error = json.loads(raw)["error"]
except Exception:
    print("  " + (raw[:200] or "(empty response body)"))
else:
    if want == "code":
        print("  " + error["code"])
    else:
        print("  ^ {} {} {}".format(error["code"], error["message"], json.dumps(error["details"])))
' "$1"
}
err_code() { err_body code; }
reason() { err_body full; }

# ---------------------------------------------------------------------------------------------
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
TODAY=$("$PY" -c 'from datetime import date; print(date.today())')
TREASURER_TOKEN=$(post /auth/login -d "{\"email\":\"treasurer@ssa.org\",\"password\":\"$PASSWORD\"}" | pick access_token)
ADMIN_TOKEN=$(post /auth/login -d "{\"email\":\"admin@ssa.org\",\"password\":\"$PASSWORD\"}" | pick access_token)
VOLUNTEER_TOKEN=$(post /auth/login -d "{\"email\":\"neha@ssa.org\",\"password\":\"$PASSWORD\"}" | pick access_token)
ORGANIZER_TOKEN=$(post /auth/login -d "{\"email\":\"organizer@ssa.org\",\"password\":\"$PASSWORD\"}" | pick access_token)
MEMBER_TOKEN=$(post /auth/login -d "{\"email\":\"member01@ssa.org\",\"password\":\"$PASSWORD\"}" | pick access_token)
TREASURER_ID=$(get /auth/me -H "Authorization: Bearer $TREASURER_TOKEN" | pick id)
echo "signed in as treasurer@ssa.org, admin@ssa.org, organizer@ssa.org, neha@ssa.org (volunteer) and member01@ssa.org"

hr "1. reset: clear this demo's own claims, their ledger rows, its manual entries and its period"
# Ledger rows are immutable through the API - that is the point of a ledger - so a re-run clears
# last run's demo rows directly, scoped strictly to rows this script created.
"$PY" -c '
from sqlalchemy import delete, or_, select

from app.core.db import SessionLocal
from app.models import Expense, ExpenseHistory, FinancePeriod, Transaction

MARK = "DEMO %"
db = SessionLocal()
try:
    claims = list(db.scalars(select(Expense).where(Expense.description.like(MARK))))
    paid = [c.ledger_transaction_id for c in claims if c.ledger_transaction_id]
    # Claims first, then the rows that paid them: `expenses.ledger_transaction_id` points at the
    # ledger row, so the reference has to go before its target can.
    if claims:
        db.execute(delete(ExpenseHistory).where(ExpenseHistory.expense_id.in_([c.id for c in claims])))
        db.execute(delete(Expense).where(Expense.id.in_([c.id for c in claims])))
    if paid:
        db.execute(delete(Transaction).where(Transaction.id.in_(paid)))
    manual = list(db.scalars(select(Transaction).where(Transaction.note.like(MARK))))
    keys = [row.id for row in manual]
    if keys:
        # A reversal mirror references its original, so both go together.
        db.execute(delete(Transaction).where(or_(Transaction.id.in_(keys), Transaction.reverses_id.in_(keys))))
    periods = list(db.scalars(select(FinancePeriod).where(FinancePeriod.name.like(MARK))))
    for period in periods:
        db.delete(period)
    db.commit()
    print("  removed {} claim(s), {} manual ledger row(s), {} period(s)".format(
        len(claims), len(manual), len(periods)))
finally:
    db.close()
'

# A real PNG and a real PDF, so storage's magic-byte check sees what it says it sees.
TMP="${TMPDIR:-/tmp}"
"$PY" -c '
import struct, zlib, sys

width, height = 48, 24
rows = b"".join(b"\x00" + bytes((x * 5 + y * 3) % 256 for x in range(width)) for y in range(height))


def chunk(kind, body):
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))


png = (
    b"\x89PNG\r\n\x1a\n"
    + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
    + chunk(b"IDAT", zlib.compress(rows))
    + chunk(b"IEND", b"")
)
open(sys.argv[1], "wb").write(png)
' "$TMP/ssa_demo_receipt.png"
printf 'not really a receipt, and not a picture either\n' >"$TMP/ssa_demo_decoy.png"
"$PY" -c 'import sys; open(sys.argv[1], "wb").write(b"\x89PNG\r\n\x1a\n" + b"\x00" * (6 * 1024 * 1024))' "$TMP/ssa_demo_big.png"
echo "made a 48x24 PNG, a text file with a .png name, and a 6 MB PNG in $TMP"

hr "2. POST /expenses  (neha, multipart, NO receipt: a claim does not need one to be submitted)"
CLAIM1=$(claim 45000 "DEMO Auto fare to the printer" printing -H "Authorization: Bearer $VOLUNTEER_TOKEN")
echo "$CLAIM1" | claim_line
CLAIM1_ID=$(echo "$CLAIM1" | pick id)
echo "  status=submitted, has_receipt=false. Submitting is not the same as being paid."

hr "3. PATCH /expenses/{id}/review  (treasurer approves with no receipt attached)"
patch "/expenses/$CLAIM1_ID/review" -H "Authorization: Bearer $TREASURER_TOKEN" -d '{"decision":"approve"}' | reason
echo "    ^ 409 RECEIPT_REQUIRED. Approval is the signature on a document, and there is no document."

hr "4. PUT /expenses/{id}/receipt  (neha attaches a real PNG; the OLD object is deleted server-side)"
put "/expenses/$CLAIM1_ID/receipt" -H "Authorization: Bearer $VOLUNTEER_TOKEN" -F "receipt=@$TMP/ssa_demo_receipt.png" | claim_line
echo "  the stored path is receipts/{claimant_id}/{expense_id}/{uuid4}.png - never the filename curl sent."

hr "5. GET /expenses/{id}/receipt  (a signed URL that expires; the path is never returned)"
get "/expenses/$CLAIM1_ID/receipt" -H "Authorization: Bearer $VOLUNTEER_TOKEN" | pretty
RECEIPT_URL=$(get "/expenses/$CLAIM1_ID/receipt" -H "Authorization: Bearer $TREASURER_TOKEN" | pick url)
echo "  expires_in=600, and the URL carries no storage path: $RECEIPT_URL"
echo "  no 'receipt_path' field appears anywhere in the body - that is the rule, not an omission."
echo "  the bytes are in the private bucket on disk (STORAGE_PROVIDER=local in dev):"
"$PY" -c '
from pathlib import Path

from app.core.config import settings

bucket = Path(settings.LOCAL_STORAGE_DIR) / settings.RECEIPTS_BUCKET
files = sorted(bucket.rglob("*")) if bucket.exists() else []
files = [path for path in files if path.is_file()]
print("    {} object(s) under {}, each named by uuid, never by the name curl sent: {}".format(
    len(files), bucket, ", ".join(path.name for path in files[:3])))
'
echo "  another volunteer cannot read this receipt at all:"
OTHER_TOKEN=$(post /auth/login -d "{\"email\":\"rohit@ssa.org\",\"password\":\"$PASSWORD\"}" | pick access_token)
echo -n "    rohit GET /expenses/$CLAIM1_ID/receipt -> "
code "$BASE/expenses/$CLAIM1_ID/receipt" -H "Authorization: Bearer $OTHER_TOKEN"; echo " (403 - the claimant sees their own, nobody else's)"

hr "6. PATCH /expenses/{id}/review  (now it goes through)"
patch "/expenses/$CLAIM1_ID/review" -H "Authorization: Bearer $TREASURER_TOKEN" -d '{"decision":"approve"}' | claim_line

hr "7. PATCH /expenses/{id}  (the owner tries to edit an APPROVED claim: 409 INVALID_STATE)"
patch "/expenses/$CLAIM1_ID" -H "Authorization: Bearer $VOLUNTEER_TOKEN" -d '{"amount":99900}' | reason
echo "    ^ once a treasurer has decided, the claim is theirs to pay and nobody else's to touch."

hr "8. POST /expenses/{id}/reimburse  (treasurer pays Rs 450 by UPI: exactly one ledger row)"
BEFORE=$(get /finance/summary -H "Authorization: Bearer $TREASURER_TOKEN" | pick balance)
PAID=$(post "/expenses/$CLAIM1_ID/reimburse" -H "Authorization: Bearer $TREASURER_TOKEN" \
  -d '{"method":"upi","reference":"UPI/2026/8891"}')
echo "$PAID" | claim_line
echo "  ledger_transaction_id=$(echo "$PAID" | pick ledger_transaction_id)"
echo "  balance before $(rupees "$BEFORE") -> after $(rupees "$(get /finance/summary -H "Authorization: Bearer $TREASURER_TOKEN" | pick balance)")"

hr "9. POST .../reimburse  again, the SAME body  (a double-click, not a double payment)"
REPLAY=$(post "/expenses/$CLAIM1_ID/reimburse" -H "Authorization: Bearer $TREASURER_TOKEN" \
  -d '{"method":"upi","reference":"UPI/2026/8891"}')
echo "  same ledger_transaction_id: $([ "$(echo "$REPLAY" | pick ledger_transaction_id)" = "$(echo "$PAID" | pick ledger_transaction_id)" ] && echo yes || echo NO)"
# Filtered by source AND by this claim's own description: the seed already has a travel claim with
# the same wording, so a bare search would count both.
echo "  ledger rows paying this claim now: $(get "/finance/transactions?source=expense_reimbursement&q=DEMO%20Auto%20fare" -H "Authorization: Bearer $TREASURER_TOKEN" | pick total) (it stays 1)"

hr "10. a rejection, the resubmission, and the trail both leave behind"
CLAIM2=$(claim 22000 "DEMO Photocopies for the notice board" printing -H "Authorization: Bearer $VOLUNTEER_TOKEN")
CLAIM2_ID=$(echo "$CLAIM2" | pick id)
echo -n "  reject with no note     -> "; patch "/expenses/$CLAIM2_ID/review" -H "Authorization: Bearer $TREASURER_TOKEN" -d '{"decision":"reject"}' | err_code
patch "/expenses/$CLAIM2_ID/review" -H "Authorization: Bearer $TREASURER_TOKEN" \
  -d '{"decision":"reject","note":"The shop gave a GST bill - please attach that one."}' | claim_line
put "/expenses/$CLAIM2_ID/receipt" -H "Authorization: Bearer $VOLUNTEER_TOKEN" -F "receipt=@$TMP/ssa_demo_receipt.png" >/dev/null
put "/expenses/$CLAIM2_ID/receipt" -H "Authorization: Bearer $VOLUNTEER_TOKEN" -F "receipt=@$TMP/ssa_demo_receipt.png" >/dev/null
patch "/expenses/$CLAIM2_ID" -H "Authorization: Bearer $VOLUNTEER_TOKEN" -d '{"description":"DEMO Photocopies for the notice board (GST bill attached)"}' >/dev/null
echo "  neha edits the rejected claim - editing is what reopens it:"
get "/expenses/$CLAIM2_ID" -H "Authorization: Bearer $VOLUNTEER_TOKEN" | history
echo "    ^ a rejected claim is not dead, it is handed back. Note the review fields are cleared."

hr "11. PATCH /expenses/{id}/review  (the treasurer claims Rs 300 themselves, then approves it)"
CLAIM3=$(claim 30000 "DEMO Treasurer's own auto fare" travel -H "Authorization: Bearer $TREASURER_TOKEN")
CLAIM3_ID=$(echo "$CLAIM3" | pick id)
patch "/expenses/$CLAIM3_ID/review" -H "Authorization: Bearer $TREASURER_TOKEN" -d '{"decision":"approve"}' | reason
echo "    ^ 409 SELF_REVIEW, and it is the same for an admin: the money rule does not care about rank."

hr "12. the upload wall  (these are refused before any row is written)"
echo -n "  text bytes with a .png name -> "
curl -s -X POST "$BASE/expenses" -F "amount=10000" -F "description=DEMO Wrong type" -F "category=other" \
  -F "incurred_on=$TODAY" -F "receipt=@$TMP/ssa_demo_decoy.png" \
  -H "Authorization: Bearer $VOLUNTEER_TOKEN" | err_code
echo -n "  6 MB png                    -> "
curl -s -X POST "$BASE/expenses" -F "amount=10000" -F "description=DEMO Too big" -F "category=other" \
  -F "incurred_on=$TODAY" -F "receipt=@$TMP/ssa_demo_big.png" \
  -H "Authorization: Bearer $VOLUNTEER_TOKEN" -o /dev/null -w '%{http_code}\n'
echo -n "  amount above the cap        -> "
claim 5000001 "DEMO Way too much" other -H "Authorization: Bearer $VOLUNTEER_TOKEN" | err_code
echo -n "  incurred 91 days ago        -> "
curl -s -X POST "$BASE/expenses" -F "amount=10000" -F "description=DEMO Stale receipt" -F "category=other" \
  -F "incurred_on=$("$PY" -c 'from datetime import date, timedelta; print(date.today() - timedelta(days=91))')" \
  -H "Authorization: Bearer $VOLUNTEER_TOKEN" | err_code

hr "13. GET /expenses  (the treasurer's queue: tabs, and the two totals that matter)"
get "/expenses?page_size=8" -H "Authorization: Bearer $TREASURER_TOKEN" | "$PY" -c '
import json, sys

def rupees(paise):
    return "Rs {:,}".format(paise // 100)

page = json.load(sys.stdin)
print("  {} claim(s) | counts={} | submitted {} | approved unpaid {}".format(
    page["total"], page["counts"], rupees(page["submitted_amount"]), rupees(page["approved_unpaid_amount"])))
for row in page["items"]:
    print("  {:<10} {:>10}  {:<9} {:<40} receipt={}".format(
        row["status"], rupees(row["amount"]), row["category"], row["description"][:40], row["has_receipt"]))
print("  /expenses/me is the same list filtered to one claimant - a volunteer cannot read anothers.")
'

hr "14. GET /finance/summary  (the dashboard KPIs, every number an integer of paise)"
get /finance/summary -H "Authorization: Bearer $TREASURER_TOKEN" | summary

hr "15. GET /finance/transactions?sort=asc  (the ledger table, with a running balance)"
get "/finance/transactions?sort=asc&page_size=6" -H "Authorization: Bearer $TREASURER_TOKEN" | "$PY" -c '
import json, sys

def rupees(paise):
    return "Rs {:,}".format(paise // 100)

page = json.load(sys.stdin)
print("  {} row(s), oldest first - running_balance is only filled for sort=asc".format(page["total"]))
for row in page["items"][-6:]:
    print("  {:<19} {:>10}  {:>10}  {:<28} {}".format(
        row["occurred_at"][:19], rupees(row["signed_amount"]), rupees(row["running_balance"] or 0),
        row["label"][:28], row["source"]))
'
get "/finance/transactions?source=expense_reimbursement" -H "Authorization: Bearer $TREASURER_TOKEN" | ledger

hr "16. GET /finance/by-event and /by-fundraiser  (grouped totals, no query per row)"
for DIM in by-event by-fundraiser; do
  echo "  $DIM:"
  get "/finance/$DIM" -H "Authorization: Bearer $TREASURER_TOKEN" | "$PY" -c '
import json, sys

def rupees(paise):
    return "Rs {:,}".format(paise // 100)

rows = json.load(sys.stdin)
for row in rows:
    goal = "  goal " + rupees(row["goal_amount"]) if row["goal_amount"] else ""
    print("      {:<34} in {:>10}  out {:>10}  net {:>10}{}".format(
        row["title"][:34], rupees(row["total_in"]), rupees(row["total_out"]), rupees(row["net"]), goal))
'
done

hr "17. GET /finance/outstanding-reimbursements  (who is waiting, and for how long)"
get /finance/outstanding-reimbursements -H "Authorization: Bearer $TREASURER_TOKEN" | "$PY" -c '
import json, sys

def rupees(paise):
    return "Rs {:,}".format(paise // 100)

rows = json.load(sys.stdin)
if not rows:
    print("  nobody is waiting")
for row in rows:
    print("  {:<18} submitted {:>10}  approved unpaid {:>10}  oldest {}".format(
        row["user"]["full_name"], rupees(row["submitted_amount"]),
        rupees(row["approved_unpaid_amount"]), row["oldest_pending_date"]))
'

hr "18. POST /finance/transactions  x2 with the SAME Idempotency-Key  (one row, not two)"
ENTRY=$(post /finance/transactions -H "Authorization: Bearer $TREASURER_TOKEN" \
  -H 'Idempotency-Key: demo-6-sponsor' \
  -d '{"amount":500000,"source":"other_income","note":"DEMO Sponsor - campus bookstore"}')
echo "$ENTRY" | "$PY" -c '
import json, sys

def rupees(paise):
    return "Rs {:,}".format(paise // 100)

row = json.load(sys.stdin)
print("  {:<19} {:<4} {:>10}  {:<34} logged by {}".format(
    row["occurred_at"][:19], row["direction"], rupees(row["amount"]), row["label"][:34],
    row["actor"]["full_name"] if row["actor"] else "-"))
'
echo -n "  the same key again -> same id: "
[ "$(post /finance/transactions -H "Authorization: Bearer $TREASURER_TOKEN" -H 'Idempotency-Key: demo-6-sponsor' -d '{"amount":500000,"source":"other_income","note":"DEMO Sponsor - campus bookstore"}' | pick id)" = "$(echo "$ENTRY" | pick id)" ] && echo yes || echo NO
echo "  A manual entry carries a direction from its source: other_income is in, other_expense is out."
echo -n "  asking for the wrong direction -> "
post /finance/transactions -H "Authorization: Bearer $TREASURER_TOKEN" \
  -d '{"amount":1000,"source":"other_income","direction":"out","note":"DEMO Contradiction"}' | err_code

hr "19. POST /finance/transactions  (Rs 5,000 of banner printing, then a row bigger than the balance)"
BANNER=$(post /finance/transactions -H "Authorization: Bearer $TREASURER_TOKEN" \
  -d '{"amount":80000,"source":"other_expense","note":"DEMO Banner printing"}')
echo "  logged a banner bill: $(echo "$BANNER" | pick label)"
BANNER_ID=$(echo "$BANNER" | pick id)
BALANCE=$(get /finance/summary -H "Authorization: Bearer $TREASURER_TOKEN" | pick balance)
BIG=$(("$BALANCE" + 100000))
echo "  balance is $(rupees "$BALANCE"); trying to write an expense of $(rupees "$BIG") as the treasurer:"
post /finance/transactions -H "Authorization: Bearer $TREASURER_TOKEN" \
  -d "{\"amount\":$BIG,\"source\":\"other_expense\",\"note\":\"DEMO Cheque for the venue\"}" | reason
echo "    ^ 409 INSUFFICIENT_FUNDS with both numbers, so the UI can say how short it is."
echo "  the same write as an ADMIN with allow_negative:"
OVERRIDE=$(post /finance/transactions -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d "{\"amount\":$BIG,\"source\":\"other_expense\",\"note\":\"DEMO Cheque for the venue\",\"allow_negative\":true}")
echo "  balance now $(rupees "$(get /finance/summary -H "Authorization: Bearer $ADMIN_TOKEN" | pick balance)") - negative, and the API said so."
echo "  a treasurer may not reach for that flag:"
post /finance/transactions -H "Authorization: Bearer $TREASURER_TOKEN" \
  -d "{\"amount\":$BIG,\"source\":\"other_expense\",\"note\":\"DEMO Treasurer override\",\"allow_negative\":true}" | err_code

hr "20. POST /finance/transactions/{id}/reverse  (a refund lands: the row is mirrored, not edited)"
MIRROR=$(post "/finance/transactions/$(echo "$OVERRIDE" | pick id)/reverse" -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"reason":"The venue refunded the cheque, so the row is undone by a mirror."}')
echo "$MIRROR" | "$PY" -c '
import json, sys

def rupees(paise):
    return "Rs {:,}".format(paise // 100)

row = json.load(sys.stdin)
print("  direction={}  amount={}  is_reversal={}  reverses_id={}".format(
    row["direction"], rupees(row["amount"]), row["is_reversal"], row["reverses_id"]))
'
echo "  balance is back to $(rupees "$(get /finance/summary -H "Authorization: Bearer $ADMIN_TOKEN" | pick balance)")"
echo -n "  reversing the mirror -> "
post "/finance/transactions/$(echo "$MIRROR" | pick id)/reverse" -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"reason":"Trying to reverse a reversal"}' | err_code
echo -n "  reversing the same row twice -> "
post "/finance/transactions/$(echo "$OVERRIDE" | pick id)/reverse" -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"reason":"Reversing it a second time"}' | err_code
echo "    ^ NOT_REVERSIBLE (a mirror is not an original) and ALREADY_REVERSED (the id is UNIQUE)."
echo -n "  reversing a ticket sale -> "
SEEDED=$(get "/finance/transactions?source=tickets&page_size=1" -H "Authorization: Bearer $TREASURER_TOKEN" | pick items 0 id)
post "/finance/transactions/$SEEDED/reverse" -H "Authorization: Bearer $TREASURER_TOKEN" \
  -d '{"reason":"Trying to erase a real sale"}' | err_code
echo "    ^ the books of record are not editable by hand; only other_income/other_expense reverse."

hr "21. GET /finance/reconcile  (the invariant: balance = SUM(in) - SUM(out), checked seven ways)"
get /finance/reconcile -H "Authorization: Bearer $TREASURER_TOKEN" | "$PY" -c '
import json, sys
report = json.load(sys.stdin)
print("  ok={}".format(report["ok"]))
for check in report["checks"]:
    print("  {:<28} ledger={:>10} source={:>10} difference={:>6}  {}".format(
        check["name"], check["ledger_total"], check["source_total"], check["difference"],
        "OK" if check["ok"] else "MISMATCH"))
'

hr "22. GET /finance/report  (the semester report: opening + net == closing, asserted server-side)"
FROM=$("$PY" -c 'from datetime import date, timedelta; print(date.today() - timedelta(days=120))')
get "/finance/report?from=$FROM&to=$TODAY" -H "Authorization: Bearer $TREASURER_TOKEN" | "$PY" -c '
import json, sys

def rupees(paise):
    return "Rs {:,}".format(paise // 100)

r = json.load(sys.stdin)
print("  period {} .. {}".format(r["period"]["from"], r["period"]["to"]))
print("  opening {}  +  net {}  =  closing {}".format(
    rupees(r["opening_balance"]), rupees(r["net_movement"]), rupees(r["closing_balance"])))
print("  income   total {}  by_source={}".format(
    rupees(r["income"]["total"]),
    ", ".join("{} {}".format(row["source"], rupees(row["in"])) for row in r["income"]["by_source"])))
print("  expenses total {}  by_category={}".format(
    rupees(r["expenses"]["total"]),
    ", ".join("{} {}".format(row["category"], rupees(row["amount"])) for row in r["expenses"]["by_category"])))
print("  by_event={} by_fundraiser={} top_expenses={} outstanding={} reconciliation_ok={}".format(
    len(r["by_event"]), len(r["by_fundraiser"]), len(r["top_expenses"]),
    len(r["outstanding_reimbursements"]), r["reconciliation"]["ok"]))
'

hr "23. POST /finance/periods  (freeze the books, then try to write inside the frozen window)"
START=$("$PY" -c 'from datetime import date, timedelta; print(date.today() - timedelta(days=20))')
END=$("$PY" -c 'from datetime import date, timedelta; print(date.today() - timedelta(days=10))')
echo -n "  treasurer FORCING it closed -> "
post /finance/periods -H "Authorization: Bearer $TREASURER_TOKEN" \
  -d "{\"name\":\"DEMO Frozen window\",\"start_date\":\"$START\",\"end_date\":\"$END\",\"force\":true}" | err_code
echo "    ^ 403: forcing a signed-off number closed is an admin's call, not a treasurer's."
echo "  without force this is also refused while claims dated inside it are unsettled (409 PENDING_CLAIMS)"
echo "  or the books do not reconcile (409 RECONCILIATION_FAILED) - both are the feature working."
PERIOD=$(post /finance/periods -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d "{\"name\":\"DEMO Frozen window\",\"start_date\":\"$START\",\"end_date\":\"$END\",\"force\":true}")
echo "$PERIOD" | "$PY" -c '
import json, sys

def rupees(paise):
    return "Rs {:,}".format(paise // 100)

p = json.load(sys.stdin)
print("  closed {} {} .. {}  status={}  closing_balance={}  by {}".format(
    p["name"], p["start_date"], p["end_date"], p["status"], rupees(p["closing_balance"]),
    p["closed_by"]["full_name"] if p["closed_by"] else "-"))
'
PERIOD_ID=$(echo "$PERIOD" | pick id)
BACKDATE=$("$PY" -c 'from datetime import date, timedelta; print(date.today() - timedelta(days=15))')
echo -n "  a manual entry dated INSIDE the closed window -> "
post /finance/transactions -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d "{\"amount\":5000,\"source\":\"other_income\",\"note\":\"DEMO Backdated into a closed period\",\"occurred_at\":\"${BACKDATE}T00:00:00Z\"}" | reason
echo "    ^ 409 PERIOD_CLOSED naming the period. The past is closed; the present is still writable."
echo -n "  a write dated today still works -> "
post /finance/transactions -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"amount":5000,"source":"other_income","note":"DEMO Chai money, today"}' -o /dev/null -w '%{http_code}\n'
echo -n "  treasurer reopening it -> "
post "/finance/periods/$PERIOD_ID/reopen" -H "Authorization: Bearer $TREASURER_TOKEN" \
  -d '{"reason":"I closed it by mistake and would like it back"}' | err_code
echo "    ^ 403: the person who froze the books cannot quietly unfreeze them."
post "/finance/periods/$PERIOD_ID/reopen" -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"reason":"Closed by mistake; the cheque for the venue had not been entered yet."}' | "$PY" -c '
import json, sys
p = json.load(sys.stdin)
print("  reopened {}  status={}  by admin  reason={}".format(p["name"], p["status"], p["reopen_reason"]))
'
get /finance/periods -H "Authorization: Bearer $TREASURER_TOKEN" | "$PY" -c '
import json, sys
rows = json.load(sys.stdin)
print("  {} period(s) on record - reopened ones are kept, not deleted: {}".format(
    len(rows), ", ".join("{}={}".format(r["name"], r["status"]) for r in rows)))
'

hr "24. GET /fundraisers  (Phase 5 progress, now with what the board SPENT)"
FUNDRAISER=$(get "/fundraisers?page_size=1" -H "Authorization: Bearer $ORGANIZER_TOKEN" | pick items 0 id)
FUNDRAISER_TITLE=$(get "/fundraisers?page_size=1" -H "Authorization: Bearer $ORGANIZER_TOKEN" | pick items 0 title)
echo "  charging a claim to '$FUNDRAISER_TITLE':"
BOOTH=$(claim 60000 "DEMO Stall hire at the bake sale" venue -H "Authorization: Bearer $VOLUNTEER_TOKEN" \
  -F "fundraiser_id=$FUNDRAISER")
BOOTH_ID=$(echo "$BOOTH" | pick id)
put "/expenses/$BOOTH_ID/receipt" -H "Authorization: Bearer $VOLUNTEER_TOKEN" -F "receipt=@$TMP/ssa_demo_receipt.png" >/dev/null
patch "/expenses/$BOOTH_ID/review" -H "Authorization: Bearer $TREASURER_TOKEN" -d '{"decision":"approve"}' >/dev/null
post "/expenses/$BOOTH_ID/reimburse" -H "Authorization: Bearer $TREASURER_TOKEN" -d '{"method":"cash"}' >/dev/null
echo "  submitted, receipted, approved and paid - so it is now spend against that fundraiser:"
get "/fundraisers?page_size=5" -H "Authorization: Bearer $ORGANIZER_TOKEN" | "$PY" -c '
import json, sys

def rupees(paise):
    return "Rs {:,}".format(paise // 100)

page = json.load(sys.stdin)
print("  spent and net_raised are the Phase 6 additions. `raised` stays GROSS, so the frontend mock")
print("  that divides raised by goal keeps its meaning; net_raised is the honest number.")
for row in page["items"]:
    p = row["progress"]
    print("  {:<26} raised {:>9}  spent {:>9}  net {:>9}  of goal {:>9}  ({}%)".format(
        row["title"][:26], rupees(p["raised"]), rupees(p["spent"]), rupees(p["net_raised"]),
        rupees(row["goal_amount"]), p["percent_of_goal"]))
'

hr "25. the ledger rows behind it all  (direct SQL, no debug endpoint: a read a DBA would do)"
"$PY" -c '
from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.models import Expense, Transaction, User
from app.services import ledger

def rupees(paise):
    return "Rs {:,}".format(paise // 100)

db = SessionLocal()
try:
    print("  every reimbursed claim and the ONE out row that paid it:")
    for expense in db.scalars(select(Expense).where(Expense.status == "reimbursed").order_by(Expense.incurred_on)):
        paid = db.get(Transaction, expense.ledger_transaction_id) if expense.ledger_transaction_id else None
        payer = db.get(User, expense.reimbursed_by) if expense.reimbursed_by else None
        print("    {:<44} {}  <- ledger {:<4} {}  {}  by {}".format(
            expense.description[:44], rupees(expense.amount),
            paid.direction if paid else "MISSING", rupees(paid.amount) if paid else "-",
            expense.reimbursement_method or "-", payer.full_name if payer else "-"))

    rows = db.scalar(select(func.count()).select_from(Transaction))
    # The four disjoint buckets the signed arithmetic is built from, counted straight off the rows.
    def total(direction, reversal):
        return db.scalar(
            select(func.sum(Transaction.amount)).where(
                Transaction.direction == direction, Transaction.is_reversal.is_(reversal)
            )
        ) or 0

    plain_in, plain_out = total("in", False), total("out", False)
    # A reversal row points the OTHER way from its original: an `in` reversal cancels an `out` row.
    rev_of_out, rev_of_in = total("in", True), total("out", True)
    rev = db.scalar(select(func.count()).select_from(Transaction).where(Transaction.is_reversal))
    print("  ledger rows: {}  ({} of them reversals, each linked by reverses_id)".format(rows, rev))
    print("    in,  not a reversal    {:>12}".format(rupees(plain_in)))
    print("    out, not a reversal    {:>12}".format(rupees(plain_out)))
    print("    in  reversing an out   {:>12}  (a refund of an earlier payment)".format(rupees(rev_of_out)))
    print("    out reversing an in    {:>12}  (a cancellation of recorded income)".format(rupees(rev_of_in)))
    print("    total_in  = (in  - not reversal) - (out reversing an in)  = {}".format(
        rupees(plain_in - rev_of_in)))
    print("    total_out = (out - not reversal) - (in  reversing an out) = {}".format(
        rupees(plain_out - rev_of_out)))
    print("    balance   = total_in - total_out                          = {}".format(
        rupees(plain_in - rev_of_in - plain_out + rev_of_out)))
    # The same three numbers, from the expressions the API itself adds up with.
    print("  recomputed with services/ledger.py: total_in {}  total_out {}  balance {}".format(
        rupees(db.scalar(select(ledger.total_in_expr()))),
        rupees(db.scalar(select(ledger.total_out_expr()))),
        rupees(db.scalar(select(ledger.balance_expr())))))
finally:
    db.close()
'

hr "26. the permission wall  (guest 401, member 403, volunteer claims, treasurer decides)"
echo -n "  guest POST /expenses            -> "; code -X POST "$BASE/expenses" -F "amount=100" -F "description=guest" -F "category=other" -F "incurred_on=$TODAY"; echo
echo -n "  guest GET /finance/summary      -> "; code "$BASE/finance/summary"; echo
echo -n "  member POST /expenses           -> "; code -X POST "$BASE/expenses" -F "amount=100" -F "description=member cannot claim" -F "category=other" -F "incurred_on=$TODAY" -H "Authorization: Bearer $MEMBER_TOKEN"; echo
echo -n "  volunteer GET /finance/summary  -> "; code "$BASE/finance/summary" -H "Authorization: Bearer $VOLUNTEER_TOKEN"; echo
echo -n "  organizer GET /expenses         -> "; code "$BASE/expenses" -H "Authorization: Bearer $ORGANIZER_TOKEN"; echo
echo -n "  volunteer GET /expenses         -> "; code "$BASE/expenses" -H "Authorization: Bearer $VOLUNTEER_TOKEN"; echo
echo -n "  volunteer PATCH review          -> "; code -X PATCH "$BASE/expenses/$CLAIM3_ID/review" -H 'Content-Type: application/json' -H "Authorization: Bearer $VOLUNTEER_TOKEN" -d '{"decision":"approve"}'; echo
echo -n "  organizer POST /finance/transactions -> "; code -X POST "$BASE/finance/transactions" -H 'Content-Type: application/json' -H "Authorization: Bearer $ORGANIZER_TOKEN" -d '{"amount":1000,"source":"other_income","note":"organizer try"}'; echo
echo -n "  treasurer reopen a period       -> "; code -X POST "$BASE/finance/periods/$PERIOD_ID/reopen" -H 'Content-Type: application/json' -H "Authorization: Bearer $TREASURER_TOKEN" -d '{"reason":"not allowed at this rank"}'; echo

hr "27. script/check_db.py  (DATABASE_URL, the pooler: server, tables, RLS)"
"$PY" scripts/check_db.py

hr "28. Swagger /docs carries the three new tags"
curl -s "$ROOT/openapi.json" | "$PY" -c '
import json, sys
spec = json.load(sys.stdin)
paths = spec["paths"]
for wanted in ("Expenses", "Finance", "Finance Periods"):
    count = sum(1 for path in paths.values() for op in path.values() if isinstance(op, dict) and wanted in op.get("tags", []))
    print("  tag {:<18} endpoints={}".format(wanted, count))
print("  new paths: " + ", ".join(sorted(p for p in paths if "/expenses" in p or "/finance" in p)))
'

hr "done"
echo "One claim from a phone to the ledger: refused without a receipt, approved, paid by UPI exactly"
echo "once, a rejection handed back and resubmitted, a self-approval blocked, the funds check, a"
echo "reversal instead of an edit, a closed period that refuses backdated writes and that only an"
echo "admin can reopen - and receipts in a private bucket behind expiring signed URLs."
echo "Swagger UI (tags: Expenses, Finance, Finance Periods): $ROOT/docs"
