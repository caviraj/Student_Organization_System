"""APScheduler wiring: the daily membership expiry scan, the stale-checkout sweeps, and the
announcement delivery worker.

| Job id                  | Interval | Purpose                                                            |
|-------------------------|----------|--------------------------------------------------------------------|
| membership-expiry-scan  | 24h      | Expire lapsed memberships; raise 30-day / 7-day / expired reminders |
| ticket-order-sweep      | 5 min    | Cancel ticket orders `pending` for over 15 minutes, return the seats |
| merch-order-sweep       | 5 min    | The same sweep for merch orders, putting the stock back             |
| announcement-deliveries | 60 s     | Claim queued announcement deliveries and send them                  |

All four also run once at startup, which is what makes a restart safe: anything queued while the
process was down goes out immediately rather than at the top of the next interval.

**The app must run as a single worker.** These jobs and the rate limiter in `core/ratelimit.py`
both keep their state in the process, so a second worker would mean two schedulers sending the
same announcement and two counters that each allow the full limit. Milestone 2 moves both to a
shared store before the worker count goes up.

`max_instances=1` and `coalesce=True` on every job: a job that outruns its interval must not
overlap itself, and a job that was missed while the process was paused must run once, not once per
missed interval. Each job opens its own session and swallows its own failures - a job that raises
must never take the API down with it. `tests/test_hardening.py` covers the job table.
"""

import logging
import time

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.db import SessionLocal
from app.services.delivery_worker import process_queued_deliveries
from app.services.merch import release_expired_pending_merch_orders
from app.services.reminders import run_expiry_scan
from app.services.tickets import release_expired_pending_orders

log = logging.getLogger("ssa.jobs")

SCAN_JOB_ID = "membership-expiry-scan"
SWEEP_JOB_ID = "ticket-order-sweep"
MERCH_SWEEP_JOB_ID = "merch-order-sweep"
DELIVERY_JOB_ID = "announcement-deliveries"

# id -> (interval in seconds, what it does). One place to read the schedule off, and the source
# `start_scheduler` adds jobs from, so the table above cannot drift from the code.
JOBS: dict[str, tuple[int, str]] = {
    SCAN_JOB_ID: (24 * 60 * 60, "expire lapsed memberships and raise reminders"),
    SWEEP_JOB_ID: (5 * 60, "cancel stale ticket orders and return their seats"),
    MERCH_SWEEP_JOB_ID: (5 * 60, "cancel stale merch orders and return their stock"),
    DELIVERY_JOB_ID: (60, "send queued announcement deliveries"),
}

scheduler = BackgroundScheduler()


def _counts(result) -> str:
    """Whatever the service returned, as something a log line can carry."""
    if result is None:
        return "no result"
    if isinstance(result, dict):
        return " ".join(f"{key}={value}" for key, value in result.items())
    return str(result)


def _run(job_id: str, work) -> dict | None:
    """Own session; a failing job must never take the API down with it."""
    db = SessionLocal()
    started = time.perf_counter()
    log.info("job %s: start", job_id)
    try:
        result = work(db)
        log.info("job %s: done in %.0fms (%s)", job_id, (time.perf_counter() - started) * 1000, _counts(result))
        return result
    except Exception:
        db.rollback()
        log.exception("job %s: failed after %.0fms", job_id, (time.perf_counter() - started) * 1000)
        return None
    finally:
        db.close()


def run_scan_once() -> dict | None:
    return _run(SCAN_JOB_ID, run_expiry_scan)


def run_sweep_once() -> dict | None:
    return _run(SWEEP_JOB_ID, release_expired_pending_orders)


def run_merch_sweep_once() -> dict | None:
    return _run(MERCH_SWEEP_JOB_ID, release_expired_pending_merch_orders)


def run_deliveries_once() -> dict | None:
    """Also called straight after an announcement is posted, so mail goes out at once rather than
    at the top of the next minute."""
    return _run(DELIVERY_JOB_ID, process_queued_deliveries)


RUNNERS = {
    SCAN_JOB_ID: run_scan_once,
    SWEEP_JOB_ID: run_sweep_once,
    MERCH_SWEEP_JOB_ID: run_merch_sweep_once,
    DELIVERY_JOB_ID: run_deliveries_once,
}


def start_scheduler() -> None:
    if scheduler.running:
        return
    for job_id, (seconds, _) in JOBS.items():
        scheduler.add_job(
            RUNNERS[job_id],
            "interval",
            seconds=seconds,
            id=job_id,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
    scheduler.start()
    for job_id in JOBS:  # a restart must not wait for the first interval
        RUNNERS[job_id]()


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
