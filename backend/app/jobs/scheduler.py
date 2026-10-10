"""APScheduler wiring for the daily membership expiry scan."""

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.db import SessionLocal
from app.services.reminders import run_expiry_scan

log = logging.getLogger("ssa.jobs")

SCAN_JOB_ID = "membership-expiry-scan"
scheduler = BackgroundScheduler()


def run_scan_once() -> dict | None:
    """Own session; a failing scan must never take the API down with it."""
    db = SessionLocal()
    try:
        result = run_expiry_scan(db)
        log.info("expiry scan: %s", result)
        return result
    except Exception:
        db.rollback()
        log.exception("expiry scan failed")
        return None
    finally:
        db.close()


def start_scheduler() -> None:
    if scheduler.running:
        return
    scheduler.add_job(run_scan_once, "interval", hours=24, id=SCAN_JOB_ID, replace_existing=True)
    scheduler.start()
    run_scan_once()  # also scan at startup


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
