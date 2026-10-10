"""Measure the four endpoints a full house hits hardest, against a running server.

    python -m uvicorn app.main:app        # in another shell, against the seeded demo database
    python scripts/perf_check.py

`tests/` proves the API is *correct*; this proves it is fast enough to stand at a door with a queue
in front of it. It talks to a live server over HTTP and nothing else - the same public surface the
frontend uses - so what it measures is what a phone in an auditorium experiences, including the
network round trip and the auth dependency on every request.

What it drives:

  * **200 sequential `POST /checkin`** - the door, the one endpoint with a person waiting on it.
    Target: **p95 < 300 ms**.
  * **100 `GET /events/{id}`** - the event page, the most-visited read.
  * **100 `GET /finance/summary`** - the treasurer's dashboard, the heaviest query in the API.
  * **100 `GET /products`** - the shop grid, which joins variants for stock.

Two things this has to get right or the numbers mean nothing:

* **Real ticket codes.** Checking in a code that does not exist skips the `UPDATE` that marks the
  ticket used, i.e. it measures the easy half of the endpoint. The codes are read from the event's
  attendee list (organizer+) and cycled, so every request is a real lookup and the first pass
  through each one is a real write.
* **The rate limiter is on.** Check-in is 120/min per user, so 200 scans as one volunteer would
  spend most of the run collecting `429`s and reporting a beautiful p95. The scans are spread
  across the three seeded volunteer accounts instead, which is also how a real door with three
  phones behaves. If you see a `429` the script says so and exits non-zero rather than quietly
  measuring the limiter.

`python scripts/reset_demo.py --yes` first, so the event it picks has tickets and the ledger has
rows - an empty database makes every number here meaningless.
"""

import os
import statistics
import sys
import time

import httpx

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000").rstrip("/")
PASSWORD = os.environ.get("DEMO_PASSWORD", "Passw0rd!")
API = "/api/v1"

# Spread the scans, don't spend one volunteer's whole budget (see the module docstring).
SCANNERS = ["volunteer@ssa.org", "neha@ssa.org", "rohit@ssa.org"]
TREASURER = "treasurer@ssa.org"
ADMIN = "admin@ssa.org"

CHECKIN_SAMPLES = 200
EVENT_SAMPLES = 100
SUMMARY_SAMPLES = 100
PRODUCT_SAMPLES = 100
CHECKIN_P95_TARGET_MS = 300.0


class Failed(Exception):
    """A run that cannot produce a meaningful number, as opposed to a slow one."""


class Api:
    def __init__(self) -> None:
        self.client = httpx.Client(base_url=BASE_URL, timeout=30.0)

    def call(self, method: str, path: str, token: str | None = None, expect=(200,), **kw):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        response = self.client.request(method, path, headers=headers, **kw)
        if response.status_code not in expect:
            raise Failed(f"{method} {path} -> {response.status_code} {response.text[:300]}")
        return response.json()

    def login(self, email: str) -> str:
        return self.call("POST", f"{API}/auth/login", json={"email": email, "password": PASSWORD})["access_token"]

    def timed(self, method: str, path: str, token: str | None = None, expect=(200,), **kw) -> float:
        """One request, in milliseconds."""
        started = time.perf_counter()
        self.call(method, path, token, expect, **kw)
        return (time.perf_counter() - started) * 1000


def percentile(samples: list[float], pct: float) -> float:
    """Nearest-rank. On 200 samples p95 is the 190th slowest value - the number a person feels,
    not an interpolation between two of them."""
    ordered = sorted(samples)
    index = min(len(ordered) - 1, max(0, round(pct / 100 * len(ordered)) - 1))
    return ordered[index]


def pick_event(api: Api, token: str) -> tuple[str, list[str]]:
    """The first event that has tickets, and the codes of up to a page of its holders."""
    events = api.call("GET", f"{API}/events", token, params={"page_size": 100})["items"]
    if not events:
        raise Failed("no events in the database - run `python scripts/reset_demo.py --yes` first")

    for event in events:
        attendees = api.call("GET", f"{API}/events/{event['id']}/attendees", token, params={"page_size": 100})
        codes = [row["code"] for row in attendees["items"]]
        if codes:
            return event["id"], codes
    raise Failed("no event has any tickets - run `python scripts/reset_demo.py --yes` first")


def report(label: str, samples: list[float], target_ms: float | None = None) -> bool:
    p50, p95, worst = percentile(samples, 50), percentile(samples, 95), max(samples)
    ok = target_ms is None or p95 < target_ms
    target = f"  target p95 < {target_ms:.0f} ms  {'OK' if ok else 'MISSED'}" if target_ms else ""
    print(f"  {label:<26} n={len(samples):<4} p50 {p50:6.1f}  p95 {p95:6.1f}  max {worst:6.1f} ms{target}")
    return ok


def main() -> int:
    print("SSA Hub - performance check")
    print("-" * 72)
    print(f"  target   {BASE_URL}")
    print("  note     the server must be running and the database seeded")
    print("-" * 72)

    api = Api()
    try:
        started = time.perf_counter()
        api.call("GET", "/health")
        print(f"  connected in {(time.perf_counter() - started) * 1000:.0f} ms")
    except (httpx.HTTPError, Failed) as exc:
        print(f"  FAIL: cannot reach {BASE_URL} ({exc}). Start the server first.")
        return 1

    try:
        admin = api.login(ADMIN)
        treasurer = api.login(TREASURER)
        scanners = [api.login(email) for email in SCANNERS]
        event_id, codes = pick_event(api, admin)
    except Failed as exc:
        print(f"  FAIL: {exc}")
        return 1

    print(f"  event    {event_id} with {len(codes)} tickets")
    print(f"  scanners {len(scanners)} volunteers, spreading the 120/min/user limit")
    print("-" * 72)

    everything_ok = True

    # --- the door ------------------------------------------------------------------
    print("  POST /checkin  (200 sequential, real ticket codes)")
    checkin: list[float] = []
    for index in range(CHECKIN_SAMPLES):
        token = scanners[index % len(scanners)]
        code = codes[index % len(codes)]
        elapsed = api.timed(
            "POST",
            f"{API}/checkin",
            token,
            json={"event_id": event_id, "code": code},
        )
        checkin.append(elapsed)
    everything_ok &= report("check-in", checkin, CHECKIN_P95_TARGET_MS)

    # --- the reads -----------------------------------------------------------------
    print("\n  Reads  (100 sequential each)")
    event_reads = [api.timed("GET", f"{API}/events/{event_id}") for _ in range(EVENT_SAMPLES)]
    everything_ok &= report("event detail", event_reads)

    summary_reads = [api.timed("GET", f"{API}/finance/summary", treasurer) for _ in range(SUMMARY_SAMPLES)]
    everything_ok &= report("finance summary", summary_reads)

    product_reads = [api.timed("GET", f"{API}/products", params={"page_size": 100}) for _ in range(PRODUCT_SAMPLES)]
    everything_ok &= report("product list", product_reads)

    print("-" * 72)
    mean = statistics.fmean(checkin)
    print(f"  mean check-in {mean:.1f} ms  ({CHECKIN_SAMPLES} scans)")
    print(f"  RESULT: {'PASS' if everything_ok else 'FAIL'}")
    return 0 if everything_ok else 1


if __name__ == "__main__":
    sys.exit(main())
