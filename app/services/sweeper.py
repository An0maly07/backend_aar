"""Background thread that escalates unanswered "Medium -> Ask User" risk checks.

Good for a single-server prototype. Escalation uses an atomic status claim, so
running several workers is still safe; at scale, move this to cron or a task
queue (e.g. Celery beat) and call ``flask escalate-expired`` instead.
"""
import logging
import threading
import time

from flask import Flask

from app.extensions import db
from app.services.risk.assessment import sweep_expired_assessments

log = logging.getLogger(__name__)
_lock = threading.Lock()
_started = False


def start_sweeper(app: Flask) -> None:
    global _started
    with _lock:
        if _started:
            return
        _started = True
    thread = threading.Thread(target=_run, args=(app,), name="risk-sweeper", daemon=True)
    thread.start()
    log.info("Risk sweeper started (every %ss)", app.config["SWEEPER_INTERVAL_SECONDS"])


def _run(app: Flask) -> None:
    interval = app.config["SWEEPER_INTERVAL_SECONDS"]
    while True:
        time.sleep(interval)
        with app.app_context():
            try:
                count = sweep_expired_assessments()
                if count:
                    log.warning("Escalated %d unanswered risk check(s)", count)
            except Exception:
                log.exception("Risk sweeper iteration failed")
                db.session.rollback()
            finally:
                db.session.remove()
