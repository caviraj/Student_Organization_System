# SSA Hub — Demo Script

A three-minute walkthrough of the whole semester, for presenting SSA Hub to the club committee.
Every number below is what the seed produces, so the demo reads the same every time.

**Before you start (five minutes earlier, not on stage):**

```bash
cd backend
python scripts/reset_demo.py --yes        # rebuild the demo database from nothing
python -m uvicorn app.main:app            # one worker; leave it running
```

Have four browser tabs open, already logged in: `member@ssa.org`, `organizer@ssa.org`,
`volunteer@ssa.org`, `treasurer@ssa.org` (password `Passw0rd!` for all of them). Log in before the
audience arrives — the demo has no login beat, and doing it live costs forty seconds you do not
have.

If something goes wrong mid-demo: `python scripts/reset_demo.py --yes` and start the slide again.
That is what it is for.

---

## The three minutes

### 0:00 — The problem (no screen, 20 seconds)

> "Right now membership is a spreadsheet, ticket money is a cash box, and nobody can tell you what
> the club actually spent last semester. SSA Hub is one place for all of it — and every rupee that
> moves leaves a row that can't be edited, only corrected."

### 0:20 — A student joins (member tab, 25 seconds)

- **Plans** → pick Standard → **Pay** → the mock sheet → **Simulate success**.
- Point at the dashboard: the status chip flips to **Active**, and a member code appears.

> "Registration made them a guest. Paying dues is what makes them a member — and that happened in
> the same transaction as the payment, so the ledger can never disagree with the badge."

### 0:45 — The event that is nearly full (organizer tab, 40 seconds)

- **Events** → **Winter Gala**.
- Point at the seats bar: **19 of 20 VIP sold**.

> "One seat left in VIP. Watch what happens when two people want it."

- Open a second tab as `guest@ssa.org` (non-member), buy the last VIP seat → **sold**.
- Back in the first tab, buy VIP → **"Only 0 left"**.

> "That's not a check-then-write. The seat count is decremented by the same SQL statement that
> decides whether there is one, so two people clicking at the same instant produce one ticket and
> one refusal. No lock, no double-sell."

- Point at the price difference between the two tabs: the member paid less.

> "Member pricing is decided by an active membership, not by a job title. An organizer whose dues
> lapsed pays the guest price."

### 1:25 — The door (volunteer tab, 35 seconds)

- **Scanner** → pick the Gala → scan (or paste) the member's ticket code → **green, "Welcome"**.
- Scan the same code again → **amber, "Already used at 6:41 PM"**.

> "A door needs an answer, not an error page. The scanner always returns 200 and the result is in
> the body — green, amber, or red for a code that isn't a ticket at all."

- Point at the counter: **1 of 3 checked in**.

> "The volunteer sees the room fill up in real time. And it's keyed per volunteer, so the second
> door doesn't slow down the first."

### 2:00 — The money (volunteer → treasurer tab, 45 seconds)

- Volunteer: **Claim an expense** → upload a receipt photo → submit.
- Treasurer: **Review queue** → the claim is there with a thumbnail.
- Treasurer: try to approve their **own** seeded claim → **"someone else must approve this"**.

> "Approving your own claim is refused, admins included. That's a rule in the database's own
> service layer, not a UI convention."

- Treasurer: approve the volunteer's claim → **Reimburse** → the balance drops.
- Click **Reimburse** again → same row, no second payment.

> "The payment carries an idempotency key, so a double-click replays instead of paying twice."

- Open **Finance** → summary, then the ledger.

> "Every row is immutable. There's no edit button and no delete button, because a mistake in the
> books is corrected by a reversal that leaves both rows visible. The reconcile tab is the audit —
> and it currently says the books agree."

### 2:45 — The close (no screen, 15 seconds)

> "Three phases of the club's year — members, events, merch, fundraisers, expenses — on one ledger,
> with an audit trail, and every number we showed you computed from the same rows. Milestone 2 adds
> real payments and real email; the shape of the ledger doesn't change."

---

## The talking points, and where they are

If the committee asks "can it do X", these are seeded and ready:

| Point | Where to look | What to say |
|---|---|---|
| A nearly-sold-out ticket type | Winter Gala VIP, **19 of 20** | "One seat left — good for the oversell beat" |
| A sold-out merch size | Hoodie size **S** and **XXL**, stock 0 | "The shop greys it out; the API refuses it with `OUT_OF_STOCK`" |
| A low-stock size | Hoodie size **M**, stock 4 | "Enough to demo, few enough to sell out live" |
| An overdue task | Fundraiser **Bake Sale**, one card past its due date | "The board counts it; the health chip goes amber" |
| Expenses waiting for review | Treasurer's review queue: **Rs 380** (submitted with a receipt) and **Rs 2,400** (submitted, none) | "Already photographed and waiting — no live upload needed" |
| A reversal | Finance → transactions, filter `is_reversal` | "A mistake corrected the right way: two rows, nothing erased" |
| An announcement with edit history | Any seeded post → **Revisions** | "Edits keep the reason and the previous text" |
| Books that reconcile | Finance → **Reconcile** → `ok: true` | "Seven checks, all green" |
| A membership ending soon | `expiring@ssa.org` — 8 days left | "The reminder banner state" |
| A lapsed membership | `expired@ssa.org` — 30 days past | "Renew-to-get-member-pricing state" |
| A failed email delivery | Admin → any announcement → **Deliveries** | "`bouncing@fail.test` fails on purpose, so the failure state is real" |

The seed prints the exact ids for the first four when it finishes, under **KEY IDS** — those are the
ones to paste into a URL.

---

## What not to do on stage

- **Do not run `python scripts/seed.py` live.** It is idempotent, which means on an already-seeded
  database it prints "already there" and changes nothing — correct, and boring. Use
  `reset_demo.py --yes` beforehand.
- **Do not open `/docs` and start clicking.** Swagger is for the engineers; it has 90 endpoints and
  no narrative.
- **Do not demo the mock payment failure path unless you are asked.** "It handles failure" is a
  sentence; watching it fail costs thirty seconds of momentum.
- **Do not restart the server mid-demo.** The scheduler starts on boot and the rate limiter is
  in-memory, so a restart is harmless — but it is thirty seconds of dead air.

---

## If the network is down

Everything except the two storage-backed screens works against a local Postgres. `STORAGE_PROVIDER=local`
swaps the receipt bucket for a directory on disk, and the whole demo — uploads included — runs with
no network at all. Set it in `.env`, `reset_demo.py --yes`, and the receipts behave identically.

---

## After the demo

```bash
python scripts/check_db.py        # server version, which database, RLS on every table
python scripts/check_storage.py   # the private bucket, a signed URL round-trip
python scripts/smoke_e2e.py       # the same story, asserted, over HTTP — PASS/FAIL per step
```

`smoke_e2e.py` is the honest version of this script: it does everything above in one run and prints
a table saying which step failed, if one did. If a demo went well and `smoke_e2e.py` disagrees, trust
`smoke_e2e.py`.
