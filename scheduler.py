"""APScheduler entry point.

Runs the daily workflow at DAILY_RUN_TIME in the configured timezone.
"""
from __future__ import annotations

import logging
import time

import pytz
from apscheduler.schedulers.blocking import BlockingScheduler

from config import CONFIG, setup_logging
from agents.ceo_controller import run_daily_workflow
from agents.report_writer import build_report_text
from connectors import telegram_bot

log = logging.getLogger(__name__)


def _job() -> None:
    log.info("Scheduled daily workflow firing")
    try:
        result = run_daily_workflow()
        text = build_report_text(result)
        telegram_bot.send_message(text)
    except Exception as e:
        log.exception("scheduled workflow failed: %s", e)
        telegram_bot.alert("scheduler error", str(e))


def main() -> None:
    setup_logging(CONFIG)

    try:
        tz = pytz.timezone(CONFIG.timezone)
    except Exception:
        tz = pytz.UTC
        log.warning("invalid timezone %r; using UTC", CONFIG.timezone)

    sched = BlockingScheduler(timezone=tz)
    hh, mm = (CONFIG.daily_run_time or "08:30").split(":")
    sched.add_job(_job, "cron", hour=int(hh), minute=int(mm), id="daily_workflow")
    log.info(
        "Scheduler started. Daily workflow at %s %s.",
        CONFIG.daily_run_time, CONFIG.timezone,
    )
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("scheduler stopping")


if __name__ == "__main__":
    main()
