"""APScheduler wiring: the daily membership expiry scan and the stale-checkout sweep."""

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.db import SessionLocal
from app.services.reminders import run_expiry_scan
from app.services.tickets import release_expired_pending_orders

log = logging.getLogger("ssa.jobs")

SCAN_JOB_ID = "membership-expiry-scan"
SWEEP_JOB_ID = "ticket-order-sweep"
scheduler = BackgroundScheduler()


def _run(label: str, work) -> dict | None:
    """Own session; a failing job must never take the API down with it."""
    db = SessionLocal()
    try:
        result = work(db)
        log.info("%s: %s", label, result)
        return result
    except Exception:
        db.rollback()
        log.exception("%s failed", label)
        return None
    finally:
        db.close()


def run_scan_once() -> dict | None:
    return _run("expiry scan", run_expiry_scan)


def run_sweep_once() -> dict | None:
    return _run("ticket order sweep", release_expired_pending_orders)


def start_scheduler() -> None:
    if scheduler.running:
        return
    scheduler.add_job(run_scan_once, "interval", hours=24, id=SCAN_JOB_ID, replace_existing=True)
    scheduler.add_job(run_sweep_once, "interval", minutes=5, id=SWEEP_JOB_ID, replace_existing=True)
    scheduler.start()
    run_scan_once()  # also scan at startup
    run_sweep_once()


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
