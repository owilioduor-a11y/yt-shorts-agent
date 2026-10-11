"""Daily autonomous scheduler.

Runs the full pipeline once per day at GENERATE_TIME, then keeps the YouTube
queue fed by respecting the upload flags. Uses APScheduler (cron semantics) so
the process can run headless on any box indefinitely.

Optional: schedule a second "tops-up" job at 18:00 that only uploads the
videos built in the morning if AUTO_UPLOAD=false but publishing was requested.
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import settings
from .logging_utils import get_logger
from .orchestrator import run_pipeline

log = get_logger("scheduler")

try:
    import zoneinfo
    tz = zoneinfo.ZoneInfo(settings.timezone)
except Exception:
    tz = None


def _daily_job() -> None:
    log.info("=== daily pipeline start ===")
    try:
        videos = run_pipeline(upload=settings.auto_upload)
        log.info("=== pipeline done: %d video(s) ===", len(videos))
    except Exception as exc:  # noqa: BLE001 - keep daemon alive
        log.exception("pipeline crashed: %s", exc)


def _parse_hhmm(value: str, default: str) -> tuple[int, int]:
    try:
        hour, minute = value.split(":")
        return int(hour), int(minute)
    except (ValueError, AttributeError):
        log.warning("invalid GENERATE_TIME %r; using %s", value, default)
        hour, minute = default.split(":")
        return int(hour), int(minute)


def serve() -> None:
    scheduler = BlockingScheduler(timezone=tz)
    hour, minute = _parse_hhmm(settings.generate_time, "05:00")
    scheduler.add_job(
        _daily_job,
        CronTrigger(hour=int(hour), minute=int(minute), timezone=tz),
        id="daily-pipeline",
        misfire_grace_time=3600,
        coalesce=True,
    )
    log.info(
        "scheduler started: pipeline daily at %s (%s), auto_upload=%s",
        settings.generate_time,
        settings.timezone,
        settings.auto_upload,
    )
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("scheduler stopped")