#!/usr/bin/env bash
#
# Phase 4 demo - Merchandise: products, sizes, stock, orders and fulfilment.
#
#   bash scripts/demo_phase4.sh
#
# Migrates + seeds the database, starts the API on :8000 if it is not already up, then walks the
# whole shop journey: an admin creates a product and one size with stock 2, a guest and a member
# see different prices, a lapsed member is turned away, a member buys the last cap but one, pays,
# and watches it move from paid to packed to handed over - while a second attempt on the last
# stock is refused, an impossible transition is refused, a restock writes an audit row, and the
# stock summary and the ledger agree with the stock movements. It ends with scripts/check_db.py,
# which fails if any public table in the database is missing Row Level Security.
#
# Re-runnable: the demo reuses its own "Demo Cap" and resets that variant to stock 2 first.
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

# The shop as a shopper sees it. Single-quoted for the shell, so the Python inside uses double quotes.
shop() {  # shop <token-or-empty>
  if [ -n "$1" ]; then get /products -H "Authorization: Bearer $1"; else get /products; fi | "$PY" -c '
import json, sys

def rupees(paise):
    return "Rs {:,}".format(paise // 100)

page = json.load(sys.stdin)
print("  {} product(s), active only".format(page["total"]))
for product in page["items"]:
    yours = "price_for_you=null"
    if product["price_for_you"] is not None:
        yours = "price_for_you={} (member={})".format(rupees(product["price_for_you"]), product["is_member_price"])
    print("  - {:<22} {:<10} {}".format(product["name"], rupees(product["base_price"]), yours))
    for variant in product["variants"]:
        print("      {:<4} stock {:>2}  {:<12} sku {}".format(
            variant["size"], variant["stock"], variant["stock_status"], variant["sku"]))
'
}

movements() {  # the audit trail of one variant
  "$PY" -c '
import json, sys
page = json.load(sys.stdin)
print("  {} movement(s), newest first".format(page["total"]))
for row in page["items"]:
    print("  {:<19} {:>+4}  {:<10} by {:<14} {}".format(
        row["created_at"][:19], row["delta"], row["reason"], row["created_by_name"] or "-", row["note"] or ""))
'
}

summary() {
  "$PY" -c '
import json, sys
data = json.load(sys.stdin)
for product in data["products"]:
    print("  - {:<22} stock {:>3}  sold {:>3}  reserved {:>3}  ({} low, {} out)".format(
        product["name"], product["total_stock"], product["sold_units"], product["reserved_units"],
        product["low_stock_count"], product["out_of_stock_count"]))
    for variant in product["variants"]:
        flag = " OUT" if variant["out_of_stock"] else (" LOW" if variant["low_stock"] else "")
        print("      {:<4} stock {:>3}  sold {:>3}  reserved {:>3}{}".format(
            variant["size"], variant["stock"], variant["sold_units"], variant["reserved_units"], flag))
print("  demand by size: " + " | ".join(
    "{} sold {} pending {}".format(row["size"], row["sold_units"], row["reserved_units"])
    for row in data["demand_by_size"]))
print("  totals: stock {} sold {} reserved {}".format(
    data["totals"]["stock"], data["totals"]["sold_units"], data["totals"]["reserved_units"]))
'
}

board() {
  "$PY" -c '
import json, sys
data = json.load(sys.stdin)
print("  counts: {}".format(data["counts"]))
for row in data["items"]["items"]:
    print("  {}  {:<12} {:<11} {:<16} {:<28} Rs {:,}".format(
        row["order_id"][:8], row["buyer"]["name"], row["fulfilment_status"], row["delivery_method"],
        row["items_summary"], row["total"] // 100))
'
}

fulfilment() {
  "$PY" -c '
import json, sys
row = json.load(sys.stdin)
print("  {} -> {}".format(row["order_id"][:8], row["fulfilment_status"]))
print("  packed_at={} handed_over_at={}".format(row["packed_at"], row["handed_over_at"]))
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
ADMIN_TOKEN=$(post /auth/login -d "{\"email\":\"admin@ssa.org\",\"password\":\"$PASSWORD\"}" | pick access_token)
MEMBER_TOKEN=$(post /auth/login -d "{\"email\":\"member01@ssa.org\",\"password\":\"$PASSWORD\"}" | pick access_token)
# member15's membership ended yesterday: a member by role, a non-member at the till.
LAPSED_TOKEN=$(post /auth/login -d "{\"email\":\"member15@ssa.org\",\"password\":\"$PASSWORD\"}" | pick access_token)
echo "signed in as admin@ssa.org, member01@ssa.org (active) and member15@ssa.org (lapsed)"

hr "1. the shop before the demo product exists"
shop ""

hr "2. POST /products  (admin): \"Demo Cap\" at Rs 399, 5% member discount"
EXISTING=$(get "/products?q=Demo%20Cap&include_inactive=true" -H "Authorization: Bearer $ADMIN_TOKEN")
if [ "$(echo "$EXISTING" | pick total)" = "0" ]; then
  PRODUCT=$(post /products -H "Authorization: Bearer $ADMIN_TOKEN" -d '{
    "name": "Demo Cap",
    "description": "Six-panel cap with the club crest. One size fits most.",
    "image_url": "https://cdn.ssa.example/merch/demo-cap.png",
    "base_price": 39900,
    "member_discount_pct": 5
  }')
  echo "$PRODUCT" | pretty
  PRODUCT_ID=$(echo "$PRODUCT" | pick id)
  CAP=$(post "/products/$PRODUCT_ID/variants" -H "Authorization: Bearer $ADMIN_TOKEN" \
    -d '{"size":"M","color":"Navy","sku":"SSA-CAP-M","stock":2,"low_stock_threshold":5}')
  echo "$CAP" | pretty
  VARIANT_ID=$(echo "$CAP" | pick id)
  echo "  the opening stock of 2 is written to stock_movements as reason=initial - see step 17."
else
  PRODUCT_ID=$(echo "$EXISTING" | pick items 0 id)
  VARIANT_ID=$(echo "$EXISTING" | pick items 0 variants 0 id)
  STOCK=$(echo "$EXISTING" | pick items 0 variants 0 stock)
  echo "  Demo Cap already exists; resetting stock from $STOCK back to 2 so this demo repeats cleanly."
  post "/variants/$VARIANT_ID/stock-adjust" -H "Authorization: Bearer $ADMIN_TOKEN" \
    -d "{\"delta\":$((2 - STOCK)),\"reason\":\"adjustment\",\"note\":\"Demo reset\"}" | pretty
fi
CAP_PRICE=$(get "/products/$PRODUCT_ID" | pick base_price)
echo "  base_price = $CAP_PRICE paise (Rs $((CAP_PRICE / 100))) - integer paise everywhere, never a float"

hr "3. GET /products  as a guest  (public, and no price_for_you: there is no \"you\")"
shop ""

hr "4. GET /products  as member01  (5% off the cap, resolved from their live membership)"
shop "$MEMBER_TOKEN"

hr "5. POST /orders/merch/checkout  as member15  (lapsed: 403 MEMBERSHIP_REQUIRED)"
post /orders/merch/checkout -H "Authorization: Bearer $LAPSED_TOKEN" \
  -d "{\"items\":[{\"variant_id\":\"$VARIANT_ID\",\"qty\":1}]}" | pretty

hr "6. POST /orders/merch/checkout  as member01  (1 cap, campus delivery needs a note)"
post /orders/merch/checkout -H "Authorization: Bearer $MEMBER_TOKEN" \
  -d "{\"items\":[{\"variant_id\":\"$VARIANT_ID\",\"qty\":1}],\"delivery_method\":\"campus_delivery\"}" | pretty
echo "  ^ 422 DELIVERY_NOTE_REQUIRED - the same rule the frontend shows inline."

ORDER=$(post /orders/merch/checkout -H "Authorization: Bearer $MEMBER_TOKEN" \
  -d "{\"items\":[{\"variant_id\":\"$VARIANT_ID\",\"qty\":1}],\"delivery_method\":\"campus_delivery\",\"delivery_note\":\"Hostel B, room 214\"}")
echo "$ORDER" | pretty
ORDER_ID=$(echo "$ORDER" | pick order_id)
echo "  Stock is reserved HERE, not at payment - that is why the shelf is already down to 1."
get "/products/$PRODUCT_ID" | "$PY" -c '
import json, sys
variant = json.load(sys.stdin)["variants"][0]
print("  stock now {} ({})".format(variant["stock"], variant["stock_status"]))
'

hr "7. POST /payments/{order_id}/mock-confirm  (success)"
confirm() { post "/payments/$1/mock-confirm" -H "Authorization: Bearer $2" -d "{\"outcome\":\"${3:-success}\"}"; }
confirm "$ORDER_ID" "$MEMBER_TOKEN" | pretty
echo "  One fulfilment row (paid), one ledger row (source=merch). Stock is NOT touched again: it was"
echo "  already reserved, so paying twice can never take a second cap off the shelf."

hr "8. POST /payments/{order_id}/mock-confirm  again  (idempotent: still one cap, one ledger row)"
confirm "$ORDER_ID" "$MEMBER_TOKEN" | pretty

hr "9. GET /orders/me  as member01  (the receipt, with its fulfilment status)"
get /orders/me -H "Authorization: Bearer $MEMBER_TOKEN" | "$PY" -c '
import json, sys

def rupees(paise):
    return "Rs {:,}".format(paise // 100)

page = json.load(sys.stdin)
print("  {} order(s), newest first".format(page["total"]))
for order in page["items"][:3]:
    print("  {}  {:<10} {:<9} {:<8} {}  {}".format(
        order["id"][:8], order["kind"], order["status"], order["payment_status"] or "-",
        rupees(order["total"]), order["fulfilment_status"] or ""))
    for item in order["items"]:
        print("      {} x{} @ {}".format(item["name"], item["quantity"], rupees(item["unit_price"])))
'

hr "10. POST /orders/merch/checkout  for the last 2 caps  (409 OUT_OF_STOCK, stock is 1)"
post /orders/merch/checkout -H "Authorization: Bearer $MEMBER_TOKEN" \
  -d "{\"items\":[{\"variant_id\":\"$VARIANT_ID\",\"qty\":2}]}" | pretty

hr "11. GET /admin/merch/orders  (admin: the fulfilment board)"
get "/admin/merch/orders?product_id=$PRODUCT_ID" -H "Authorization: Bearer $ADMIN_TOKEN" | board

hr "12. PATCH /admin/merch/orders/{id}  paid -> packed"
patch "/admin/merch/orders/$ORDER_ID" -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"fulfilment_status":"packed"}' | fulfilment

hr "13. PATCH ... packed -> handed_over"
patch "/admin/merch/orders/$ORDER_ID" -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"fulfilment_status":"handed_over"}' | fulfilment

hr "14. PATCH ... handed_over -> paid  (409 INVALID_TRANSITION: one step at a time, forwards only)"
patch "/admin/merch/orders/$ORDER_ID" -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"fulfilment_status":"paid"}' | pretty

hr "15. POST /variants/{id}/stock-adjust  (admin: +5 restock)"
post "/variants/$VARIANT_ID/stock-adjust" -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"delta":5,"reason":"restock","note":"Second delivery from the supplier"}' | pretty

hr "16. POST /variants/{id}/stock-adjust  (admin: -100, refused before the CHECK constraint ever fires)"
post "/variants/$VARIANT_ID/stock-adjust" -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"delta":-100,"reason":"adjustment","note":"Stock take"}' | pretty

hr "17. GET /variants/{id}/stock-movements  (admin: initial, sale, restock - and nothing else)"
get "/variants/$VARIANT_ID/stock-movements" -H "Authorization: Bearer $ADMIN_TOKEN" | movements

hr "18. GET /admin/merch/stock-summary  (admin: what we hold, what sold, what is only reserved)"
get /admin/merch/stock-summary -H "Authorization: Bearer $ADMIN_TOKEN" | summary

hr "19. the money trail and the stock invariant  (direct SQL, no debug endpoint: this is a read a DBA would do)"
"$PY" -c '
from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.models import ProductVariant, StockMovement, Transaction

db = SessionLocal()
try:
    print("  ledger rows with source=merch, newest first:")
    for row in db.scalars(
        select(Transaction).where(Transaction.source == "merch").order_by(Transaction.occurred_at.desc()).limit(5)
    ):
        print("    {:<19} {:<4} Rs {:>9,}  {} {}  {}".format(
            row.occurred_at.strftime("%Y-%m-%d %H:%M:%S"), row.direction, row.amount // 100,
            row.ref_type, row.ref_id, row.note or ""))

    print("  stock invariant, initial + SUM(delta) == stock, for every variant:")
    moved = (
        select(StockMovement.variant_id, func.sum(StockMovement.delta).label("delta"))
        .group_by(StockMovement.variant_id)
        .subquery()
    )
    drift = db.scalar(
        select(func.count()).select_from(ProductVariant)
        .outerjoin(moved, moved.c.variant_id == ProductVariant.id)
        .where(func.coalesce(moved.c.delta, 0) != ProductVariant.stock)
    )
    total = db.scalar(select(func.count()).select_from(ProductVariant))
    print("    {}/{} variants reconcile".format(total - drift, total))
finally:
    db.close()
'

hr "20. script/check_db.py  (DATABASE_URL, the pooler: server, tables, RLS)"
"$PY" scripts/check_db.py

hr "done"
echo "One product, one size, one reservation, one payment, one fulfilment row, one audit trail - and"
echo "RLS on every public table. Swagger UI (tags: Products, Merch Orders, Merch Admin): $ROOT/docs"
