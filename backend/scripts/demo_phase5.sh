#!/usr/bin/env bash
#
# Phase 5 demo - Fundraisers: the planning lifecycle, the task board, progress and hand-logged income.
#
#   bash scripts/demo_phase5.sh
#
# Migrates + seeds the database, starts the API on :8000 if it is not already up, then walks one
# fundraiser end to end: an organizer plans "Demo Bake Sale" (Rs 3,000 goal, six days out), picks
# assignees from the staff list, puts five cards on the board - one of them overdue, which is what
# tips the board to at_risk - a volunteer signs in, sees only their own cards, drags one from todo
# through doing to done, and is refused when they try to rename it. The organizer then logs
# Rs 1,500 of cash twice with the SAME Idempotency-Key and the ledger stays at one row, progress
# moves to 50% of goal, the card's activity trail is read back, and closing the fundraiser with a
# card still open is refused (409 OPEN_TASKS) unless forced. It ends with the ledger rows printed by
# a direct SQL read - there is no public endpoint for the raw ledger, by design - and with
# scripts/check_db.py, which fails if any public table is missing Row Level Security.
#
# Re-runnable: it clears its own "Demo Bake Sale" (and its cards, activity and income) first, then
# rebuilds it, so the numbers below read the same every run.
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
post() { curl -s -X POST "$BASE$1" -H 'Content-Type: application/json' "${@:2}"; }
patch() { curl -s -X PATCH "$BASE$1" -H 'Content-Type: application/json' "${@:2}"; }
get() { curl -s "$BASE$1" "${@:2}"; }

progress() {  # progress <fundraiser-json-on-stdin>: the numbers the dashboard reads
  "$PY" -c '
import json, sys

def rupees(paise):
    return "Rs {:,}".format(paise // 100)

data = json.load(sys.stdin)
tasks, progress = data["progress"]["tasks"], data["progress"]
print("  {:<16} {:<9} event in {:<3} days   health={}".format(
    data["title"], data["status"], progress["days_to_event"], progress["health"]))
print("  tasks: {} total | {} todo {} doing {} done | {} overdue | {} due soon | {} unassigned | {}% done".format(
    tasks["total"], tasks["todo"], tasks["doing"], tasks["done"],
    tasks["overdue"], tasks["due_soon"], tasks["unassigned"], tasks["percent_done"]))
print("  money: {} raised of {} goal ({}%){}".format(
    rupees(progress["raised"]), rupees(progress["goal"]), progress["percent_of_goal"],
    "  - completed " + data["completed_at"][:19] if data["completed_at"] else ""))
for row in progress["by_category"]:
    print("      {:<11} {} card(s), {} done".format(row["category"], row["total"], row["done"]))
for row in progress["by_assignee"]:
    print("      {:<16} {} card(s), {} done".format(row["name"] or "unassigned", row["total"], row["done"]))
'
}

columns() {  # the kanban, column by column
  "$PY" -c '
import json, sys
board = json.load(sys.stdin)
print("  counts: {}".format(board["counts"]))
for column in ("todo", "doing", "done"):
    print("  {}:".format(column.upper()))
    for card in board["columns"][column]:
        print("      [{}] {:<32} {:<11} due {:<11} {}".format(
            card["position"], card["title"], card["category"], card["due_date"] or "-",
            (card["assignee"]["full_name"] if card["assignee"] else "unassigned") + ("  OVERDUE" if card["is_overdue"] else "")))
'
}

my_cards() {
  "$PY" -c '
import json, sys
page = json.load(sys.stdin)
print("  {} card(s) assigned to me, overdue first".format(page["total"]))
for card in page["items"]:
    print("  {:<11} {:<32} {} due {}".format(
        card["status"], card["title"], "OVERDUE" if card["is_overdue"] else "      ", card["due_date"] or "-"))
'
}

trail() {
  "$PY" -c '
import json, sys
page = json.load(sys.stdin)
print("  {} row(s), newest first".format(page["total"]))
for row in page["items"]:
    print("  {:<19} {:<14} {:<24} -> {:<24} by {}".format(
        row["created_at"][:19], row["action"], row["from_value"] or "-", row["to_value"] or "-",
        row["actor"]["full_name"] if row["actor"] else "-"))
'
}

cash_book() {
  "$PY" -c '
import json, sys

def rupees(paise):
    return "Rs {:,}".format(paise // 100)

page = json.load(sys.stdin)
print("  {} entr(ies), newest first".format(page["total"]))
for row in page["items"]:
    print("  {:<19} {:>10}  {:<34} logged by {}".format(
        row["occurred_at"][:19], rupees(row["amount"]), row["note"] or "-",
        row["logged_by"]["full_name"] if row["logged_by"] else "-"))
'
}

assignable() {
  "$PY" -c '
import json, sys
rows = json.load(sys.stdin)
print("  {} assignable (active, volunteer and above):".format(len(rows)))
for row in rows:
    print("      {:<16} {:<12} {}".format(row["full_name"], row["role"], row["email"]))
'
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
ORGANIZER_TOKEN=$(post /auth/login -d "{\"email\":\"organizer@ssa.org\",\"password\":\"$PASSWORD\"}" | pick access_token)
VOLUNTEER_TOKEN=$(post /auth/login -d "{\"email\":\"volunteer@ssa.org\",\"password\":\"$PASSWORD\"}" | pick access_token)
MEMBER_TOKEN=$(post /auth/login -d "{\"email\":\"member01@ssa.org\",\"password\":\"$PASSWORD\"}" | pick access_token)
echo "signed in as organizer@ssa.org, volunteer@ssa.org (staff) and member01@ssa.org (plain member)"

hr "1. reset: clear this demo's own fundraiser so the numbers below repeat"
# Income rows are never deleted through the API - that is the point of a ledger - so a re-run
# clears last run's demo rows directly, scoped strictly to the demo title.
"$PY" -c '
from sqlalchemy import delete, select

from app.core.db import SessionLocal
from app.models import Fundraiser, Task, TaskActivity, Transaction

TITLE = "Demo Bake Sale"
db = SessionLocal()
try:
    ids = list(db.scalars(select(Fundraiser.id).where(Fundraiser.title == TITLE)))
    if ids:
        task_ids = list(db.scalars(select(Task.id).where(Task.fundraiser_id.in_(ids))))
        db.execute(delete(TaskActivity).where(TaskActivity.task_id.in_(task_ids)))
        db.execute(delete(Transaction).where(Transaction.fundraiser_id.in_(ids)))
        db.execute(delete(Task).where(Task.fundraiser_id.in_(ids)))
        db.execute(delete(Fundraiser).where(Fundraiser.id.in_(ids)))
        db.commit()
        print("  removed {} previous demo fundraiser(s) and their rows".format(len(ids)))
    else:
        print("  nothing to remove: this is the first run")
finally:
    db.close()
'

hr "2. POST /fundraisers  (organizer): \"Demo Bake Sale\", goal Rs 3,000, event in 6 days"
FUNDRAISER=$(post /fundraisers -H "Authorization: Bearer $ORGANIZER_TOKEN" -d "{
  \"title\": \"Demo Bake Sale\",
  \"description\": \"Cakes and cookies outside the library, run by the second years.\",
  \"goal_amount\": 300000,
  \"event_date\": \"$("$PY" -c 'from datetime import date, timedelta; print(date.today() + timedelta(days=6))')\"
}")
echo "$FUNDRAISER" | pretty
FUNDRAISER_ID=$(echo "$FUNDRAISER" | pick id)
echo "  status=planning and progress is all zeros - a plan is not a promise yet."

hr "3. PATCH /fundraisers/{id}  (planning -> active: the board opens for work)"
patch "/fundraisers/$FUNDRAISER_ID" -H "Authorization: Bearer $ORGANIZER_TOKEN" -d '{"status":"active"}' | progress

hr "4. GET /users/assignable  (organizer: who a card can be given to)"
get /users/assignable -H "Authorization: Bearer $ORGANIZER_TOKEN" | assignable
VOLUNTEER_ID=$(get /users/assignable -H "Authorization: Bearer $ORGANIZER_TOKEN" | pick 3 id)
ORGANIZER_ID=$(get /auth/me -H "Authorization: Bearer $ORGANIZER_TOKEN" | pick id)
echo "  VOLUNTEER_ID=$VOLUNTEER_ID  (volunteer@ssa.org)"

hr "5. POST /fundraisers/{id}/tasks  x5  (organizer): the work, one card due yesterday"
new_task() {  # new_task <title> <category> <status> <due-in-days|-> <assignee-id>
  if [ "$4" = "-" ]; then DUE=null; else DUE="\"$("$PY" -c "from datetime import date, timedelta; print(date.today() + timedelta(days=$4))")\""; fi
  post "/fundraisers/$FUNDRAISER_ID/tasks" -H "Authorization: Bearer $ORGANIZER_TOKEN" -d "{
    \"title\": \"$1\", \"category\": \"$2\", \"status\": \"$3\", \"due_date\": $DUE, \"assignee_id\": \"$5\"
  }"
}
CARD1=$(new_task "Book the quad table" promotion done -3 "$ORGANIZER_ID")
CARD2=$(new_task "Print posters and flyers" promotion done -2 "$VOLUNTEER_ID")
CARD3=$(new_task "Order flour, sugar and butter" supplies doing 2 "$VOLUNTEER_ID")
CARD4=$(new_task "Bake 200 cookies" baking doing 2 "$ORGANIZER_ID")
CARD5=$(new_task "Collect the cake tins" supplies todo -1 "$VOLUNTEER_ID")
for CARD in "$CARD1" "$CARD2" "$CARD3" "$CARD4" "$CARD5"; do
  echo "$CARD" | "$PY" -c '
import json, sys
card = json.load(sys.stdin)
print("  {:<6} pos {}  {:<32} {:<10} due {:<10} {}".format(
    card["status"], card["position"], card["title"], card["category"], card["due_date"] or "-",
    card["assignee"]["full_name"] if card["assignee"] else "unassigned"))
'
done
MINE_ID=$(echo "$CARD5" | pick id)
echo "  MINE_ID=$MINE_ID  (the overdrawn-looking todo card the volunteer moves in step 9)"
echo "  A sixth card is refused before it is written - the database CHECK is the backstop:"
post "/fundraisers/$FUNDRAISER_ID/tasks" -H "Authorization: Bearer $ORGANIZER_TOKEN" \
  -d "{\"title\":\"Due after the bake sale\",\"due_date\":\"$("$PY" -c 'from datetime import date, timedelta; print(date.today() + timedelta(days=20))')\"}" | pretty
echo "  ^ 422 DUE_AFTER_EVENT: work cannot be due after the day it is being prepared for."

hr "6. GET /fundraisers/{id}/tasks  (the board: flat items AND the columns a kanban renders)"
get "/fundraisers/$FUNDRAISER_ID/tasks" -H "Authorization: Bearer $VOLUNTEER_TOKEN" | columns

hr "7. GET /fundraisers/{id}  (progress: 2/5 done, one card overdue -> health=at_risk)"
get "/fundraisers/$FUNDRAISER_ID" -H "Authorization: Bearer $ORGANIZER_TOKEN" | progress
echo "  at_risk, not behind: one overdue card is a warning, three is a fire (DESIGN.md §4 rule 13)."

hr "8. GET /tasks/me  (volunteer: their own cards across EVERY board, overdue first)"
get /tasks/me -H "Authorization: Bearer $VOLUNTEER_TOKEN" | my_cards
echo "  The seeded boards are in here too - this is the volunteer's whole workload, not one fundraiser's."

hr "9. PATCH /tasks/{id}  (the assignee moves their OWN card: todo -> doing -> done)"
patch "/tasks/$MINE_ID" -H "Authorization: Bearer $VOLUNTEER_TOKEN" -d '{"status":"doing"}' | "$PY" -c '
import json, sys
card = json.load(sys.stdin)
print("  {} -> {}  completed_at={}".format(card["title"], card["status"], card["completed_at"]))
'
patch "/tasks/$MINE_ID" -H "Authorization: Bearer $VOLUNTEER_TOKEN" -d '{"status":"done"}' | "$PY" -c '
import json, sys
card = json.load(sys.stdin)
print("  {} -> {}  completed_at={}".format(card["title"], card["status"], card["completed_at"]))
'

hr "10. PATCH /tasks/{id}  (the same volunteer tries to RENAME it: 403 - they own the column, not the card)"
patch "/tasks/$MINE_ID" -H "Authorization: Bearer $VOLUNTEER_TOKEN" -d '{"title":"Renamed by a volunteer"}' | pretty

hr "11. GET /tasks/{id}/activity  (every change, who made it, from what to what)"
get "/tasks/$MINE_ID/activity" -H "Authorization: Bearer $VOLUNTEER_TOKEN" | trail

hr "12. GET /fundraisers/{id}  (progress after the move: 3/5 done, nothing overdue)"
get "/fundraisers/$FUNDRAISER_ID" -H "Authorization: Bearer $ORGANIZER_TOKEN" | progress

hr "13. POST /fundraisers/{id}/income  (organizer, Rs 1,500 of pre-orders, Idempotency-Key sent)"
INCOME=$(post "/fundraisers/$FUNDRAISER_ID/income" -H "Authorization: Bearer $ORGANIZER_TOKEN" \
  -H 'Idempotency-Key: demo-bake-sale-preorders' \
  -d '{"amount":150000,"note":"Pre-orders","source_label":"Cash box"}')
echo "$INCOME" | pretty

hr "14. POST ... the SAME body, the SAME key  (a double-click: replayed=true, still one ledger row)"
echo "$INCOME" | pick id
post "/fundraisers/$FUNDRAISER_ID/income" -H "Authorization: Bearer $ORGANIZER_TOKEN" \
  -H 'Idempotency-Key: demo-bake-sale-preorders' \
  -d '{"amount":150000,"note":"Pre-orders","source_label":"Cash box"}' | pretty
echo "  ^ replayed=true and the same id: raised_total is still Rs 1,500, not Rs 3,000."
echo "    There is no PATCH and no DELETE on an income row - a ledger you can rewrite is not a ledger."

hr "15. GET /fundraisers/{id}/income  (the cash book, with who logged each entry)"
get "/fundraisers/$FUNDRAISER_ID/income" -H "Authorization: Bearer $VOLUNTEER_TOKEN" | cash_book

hr "16. GET /fundraisers/{id}  (progress: raised Rs 1,500 of Rs 3,000 = 50%)"
get "/fundraisers/$FUNDRAISER_ID" -H "Authorization: Bearer $ORGANIZER_TOKEN" | progress

hr "17. PATCH /fundraisers/{id}  done with a card still open  (409 OPEN_TASKS, with the count)"
patch "/fundraisers/$FUNDRAISER_ID" -H "Authorization: Bearer $ORGANIZER_TOKEN" -d '{"status":"done"}' | pretty

hr "18. PATCH /fundraisers/{id}?force=true  (the organizer decides anyway)"
patch "/fundraisers/$FUNDRAISER_ID?force=true" -H "Authorization: Bearer $ORGANIZER_TOKEN" -d '{"status":"done"}' | progress
echo "  completed_at is stamped, and the board is now read-only:"
post "/fundraisers/$FUNDRAISER_ID/tasks" -H "Authorization: Bearer $ORGANIZER_TOKEN" -d '{"title":"One more cake"}' | pretty
echo "  ^ 409 FUNDRAISER_CLOSED. Cash counted on the day still arrives for seven days - income stays"
echo "    open until completed_at + 7 days, which is why step 14 would still be accepted today."

hr "19. the ledger rows behind it all  (direct SQL, no debug endpoint: a read a DBA would do)"
"$PY" -c '
from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.models import Fundraiser, Task, TaskActivity, Transaction, User

db = SessionLocal()
try:
    fundraiser = db.scalar(select(Fundraiser).where(Fundraiser.title == "Demo Bake Sale"))
    print("  fundraiser {}  status={}  goal=Rs {:,}  completed_at={}".format(
        fundraiser.id, fundraiser.status, fundraiser.goal_amount // 100, fundraiser.completed_at))

    print("  ledger rows for this fundraiser (source=fundraiser):")
    raised = 0
    for row in db.scalars(
        select(Transaction)
        .where(Transaction.fundraiser_id == fundraiser.id)
        .order_by(Transaction.occurred_at.desc())
    ):
        raised += row.amount if row.direction == "in" else -row.amount
        author = db.get(User, row.logged_by) if row.logged_by else None
        print("    {:<19} {:<4} Rs {:>8,}  {:<30} by {:<16} key={}".format(
            row.occurred_at.strftime("%Y-%m-%d %H:%M:%S"), row.direction, row.amount // 100,
            row.note or "-", author.full_name if author else "-", row.idempotency_key or "-"))

    # The API reports this number; this is the same number computed from the rows underneath it.
    api_total = func.sum(Transaction.amount).filter(Transaction.direction == "in")
    from_api = db.scalar(select(api_total).where(Transaction.fundraiser_id == fundraiser.id)) or 0
    print("    rows sum to Rs {:,} - the API reported raised_total=Rs {:,}".format(from_api // 100, raised // 100))

    open_cards = db.scalar(
        select(func.count()).select_from(Task).where(Task.fundraiser_id == fundraiser.id, Task.status != "done")
    )
    print("  cards: {} total, {} still open (the number OPEN_TASKS quoted in step 17)".format(
        db.scalar(select(func.count()).select_from(Task).where(Task.fundraiser_id == fundraiser.id)), open_cards))
    print("  activity rows kept for this board: {}".format(
        db.scalar(select(func.count()).select_from(TaskActivity).where(TaskActivity.task_id.in_(
            select(Task.id).where(Task.fundraiser_id == fundraiser.id))))))
finally:
    db.close()
'

hr "20. GET /fundraisers  (the list, newest first: progress is batched, not one query per row)"
get "/fundraisers?page_size=5" -H "Authorization: Bearer $VOLUNTEER_TOKEN" | "$PY" -c '
import json, sys

def rupees(paise):
    return "Rs {:,}".format(paise // 100)

page = json.load(sys.stdin)
print("  {} fundraiser(s)".format(page["total"]))
for row in page["items"]:
    progress = row["progress"]
    print("  {:<26} {:<9} {:<9} {:>3}% cards {:>4}% goal  {} / {}".format(
        row["title"], row["status"], progress["health"], progress["percent_done"],
        progress["percent_of_goal"], rupees(progress["raised"]), rupees(row["goal_amount"])))
'

hr "21. the permission wall  (guest 401, member 403, volunteer reads, organizer writes)"
echo -n "  guest GET /fundraisers          -> "; get /fundraisers -o /dev/null -w '%{http_code}\n'
echo -n "  member GET /fundraisers         -> "; get /fundraisers -H "Authorization: Bearer $MEMBER_TOKEN" -o /dev/null -w '%{http_code}\n'
echo -n "  volunteer GET /fundraisers      -> "; get /fundraisers -H "Authorization: Bearer $VOLUNTEER_TOKEN" -o /dev/null -w '%{http_code}\n'
echo -n "  member POST /fundraisers        -> "; post /fundraisers -H "Authorization: Bearer $MEMBER_TOKEN" -d '{"title":"Member idea","goal_amount":100000,"event_date":null}' -o /dev/null -w '%{http_code}\n'
echo -n "  volunteer POST /fundraisers     -> "; post /fundraisers -H "Authorization: Bearer $VOLUNTEER_TOKEN" -d '{"title":"Volunteer idea","goal_amount":100000,"event_date":null}' -o /dev/null -w '%{http_code}\n'

hr "22. script/check_db.py  (DATABASE_URL, the pooler: server, tables, RLS)"
"$PY" scripts/check_db.py

hr "23. Swagger /docs carries the three new tags"
curl -s "$ROOT/openapi.json" | "$PY" -c '
import json, sys
spec = json.load(sys.stdin)
tags = {tag["name"] for tag in spec.get("tags", [])}
paths = spec["paths"]
for wanted in ("Fundraisers", "Tasks", "Fundraiser Income"):
    print("  tag {:<18} present={}  endpoints={}".format(
        wanted, wanted in tags or any(wanted in op.get("tags", []) for path in paths.values() for op in path.values() if isinstance(op, dict)),
        sum(1 for path in paths.values() for op in path.values() if isinstance(op, dict) and wanted in op.get("tags", []))))
print("  new paths: " + ", ".join(sorted(p for p in paths if "/fundraisers" in p or "/tasks" in p or p.endswith("/users/assignable"))))
'

hr "done"
echo "One fundraiser, five cards, one volunteer moving their own card, one ledger row from two"
echo "identical requests, a full activity trail - and RLS on every public table."
echo "Swagger UI (tags: Fundraisers, Tasks, Fundraiser Income): $ROOT/docs"
