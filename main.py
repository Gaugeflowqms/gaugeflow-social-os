"""CLI entry point for GaugeFlow Social OS.

Usage:
    python main.py init-db
    python main.py dry-run
    python main.py run-once
    python main.py scheduler
    python main.py dashboard
    python main.py telegram
    python main.py status
"""
from __future__ import annotations

import argparse
import json
import logging
import sys

from config import CONFIG, setup_logging
from db import init_db, set_setting

log = logging.getLogger(__name__)


def cmd_init_db(_args) -> int:
    init_db()
    print(f"Database initialized.")
    return 0


def cmd_dry_run(_args) -> int:
    """Force DRY_RUN regardless of .env, run once, print result."""
    set_setting("mode_override", "DRY_RUN")
    from agents.ceo_controller import run_daily_workflow
    from agents.report_writer import build_report_text
    from connectors import telegram_bot

    result = run_daily_workflow()
    text = build_report_text(result)
    print(text)
    telegram_bot.send_message(text)
    return 0


def cmd_run_once(_args) -> int:
    from agents.ceo_controller import run_daily_workflow
    from agents.report_writer import build_report_text
    from connectors import telegram_bot

    result = run_daily_workflow()
    text = build_report_text(result)
    print(text)
    telegram_bot.send_message(text)
    return 0


def cmd_scheduler(_args) -> int:
    from scheduler import main as sched_main
    sched_main()
    return 0


def cmd_dashboard(_args) -> int:
    import uvicorn
    uvicorn.run(
        "dashboard.app:app",
        host=CONFIG.dashboard_host,
        port=CONFIG.dashboard_port,
        reload=False,
        log_level=CONFIG.log_level.lower(),
    )
    return 0


def cmd_telegram(_args) -> int:
    from connectors.telegram_bot import run_bot
    run_bot()
    return 0


def cmd_status(_args) -> int:
    from agents.ceo_controller import get_status_text
    print(get_status_text())
    return 0


COMMANDS = {
    "init-db": cmd_init_db,
    "dry-run": cmd_dry_run,
    "run-once": cmd_run_once,
    "scheduler": cmd_scheduler,
    "dashboard": cmd_dashboard,
    "telegram": cmd_telegram,
    "status": cmd_status,
}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="gaugeflow-social-os")
    parser.add_argument("command", choices=list(COMMANDS.keys()))
    args = parser.parse_args(argv)

    setup_logging(CONFIG)
    init_db()  # always make sure tables exist
    return COMMANDS[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
