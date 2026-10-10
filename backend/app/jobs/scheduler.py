"""APScheduler wiring: the daily membership expiry scan, the stale-checkout sweeps, and the
announcement delivery worker."""

import logging

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


def run_merch_sweep_once() -> dict | None:
    return _run("merch order sweep", release_expired_pending_merch_orders)


def run_deliveries_once() -> dict | None:
    """Also called straight after an announcement is posted, so mail goes out at once rather than
    at the top of the next minute."""
    return _run("announcement deliveries", process_queued_deliveries)


def start_scheduler() -> None:
    if scheduler.running:
        return
    scheduler.add_job(run_scan_once, "interval", hours=24, id=SCAN_JOB_ID, replace_existing=True)
    scheduler.add_job(run_sweep_once, "interval", minutes=5, id=SWEEP_JOB_ID, replace_existing=True)
    scheduler.add_job(
        run_merch_sweep_once, "interval", minutes=5, id=MERCH_SWEEP_JOB_ID, replace_existing=True
    )
    scheduler.add_job(
        run_deliveries_once, "interval", seconds=60, id=DELIVERY_JOB_ID, replace_existing=True
    )
    scheduler.start()
    run_scan_once()  # also scan at startup
    run_sweep_once()
    run_merch_sweep_once()
    run_deliveries_once()  # anything still queued from before a restart


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
