"""Telegram bot connector.

Two roles:
1. send_message / send_photo  -> reports and alerts (synchronous, simple).
2. run_bot()                  -> long-running command listener (async).

The send_* helpers use the Telegram Bot HTTP API directly so they work even
without python-telegram-bot installed. The interactive bot uses
python-telegram-bot.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

import httpx

from config import CONFIG

log = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org"


def is_configured() -> bool:
    return CONFIG.has_telegram()


def send_message(text: str, parse_mode: str = "Markdown") -> bool:
    if not is_configured():
        log.info("Telegram not configured; would have sent: %s", text[:80])
        return False
    url = f"{API_BASE}/bot{CONFIG.telegram_bot_token}/sendMessage"
    try:
        r = httpx.post(
            url,
            data={
                "chat_id": CONFIG.telegram_chat_id,
                "text": text[:4000],
                "parse_mode": parse_mode,
                "disable_web_page_preview": "true",
            },
            timeout=15,
        )
        r.raise_for_status()
        return True
    except Exception as e:
        log.warning("Telegram send_message error: %s", e)
        return False


def send_photo(path: str, caption: str = "") -> bool:
    if not is_configured():
        return False
    if not Path(path).exists():
        log.warning("Telegram send_photo: file missing %s", path)
        return False
    url = f"{API_BASE}/bot{CONFIG.telegram_bot_token}/sendPhoto"
    try:
        with open(path, "rb") as f:
            files = {"photo": f}
            r = httpx.post(
                url,
                data={"chat_id": CONFIG.telegram_chat_id, "caption": caption[:1000]},
                files=files,
                timeout=30,
            )
            r.raise_for_status()
            return True
    except Exception as e:
        log.warning("Telegram send_photo error: %s", e)
        return False


def alert(title: str, body: str) -> None:
    """Send a clearly-formatted alert."""
    msg = f"*{title}*\n{body}"
    send_message(msg)


# --------------------- Interactive bot --------------------- #

HELP_TEXT = (
    "*GaugeFlow Social OS*\n"
    "/start_day — run today's workflow now\n"
    "/status — show system status\n"
    "/mode — show current mode\n"
    "/dry_run — switch to DRY_RUN\n"
    "/semi_auto — switch to SEMI_AUTO\n"
    "/full_auto — switch to FULL_AUTO\n"
    "/pause — pause posting\n"
    "/resume — resume\n"
    "/post_now — generate and post one safe post\n"
    "/draft_comments — draft external comments only\n"
    "/report — send today's report\n"
    "/limits — show daily limits\n"
    "/help — show this list"
)


def run_bot() -> None:
    """Start a long-running command-handler bot."""
    if not is_configured():
        log.warning("Telegram bot not configured (missing token/chat_id). Exiting.")
        return

    try:
        from telegram import Update  # type: ignore
        from telegram.ext import (  # type: ignore
            Application,
            CommandHandler,
            ContextTypes,
        )
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("python-telegram-bot not installed.") from e

    # Imports kept local so the rest of the system can run without these.
    from db import get_setting, set_setting
    from agents.ceo_controller import (
        run_daily_workflow,
        run_post_now,
        run_draft_comments_only,
        get_status_text,
    )
    from agents.report_writer import build_report_text

    AUTH_CHAT = str(CONFIG.telegram_chat_id)

    def _authorized(update: "Update") -> bool:
        return str(update.effective_chat.id) == AUTH_CHAT

    async def _send(update, text):
        await update.message.reply_text(text, parse_mode="Markdown", disable_web_page_preview=True)

    async def cmd_help(update, ctx):
        if not _authorized(update):
            return
        await _send(update, HELP_TEXT)

    async def cmd_status(update, ctx):
        if not _authorized(update):
            return
        await _send(update, get_status_text())

    async def cmd_mode(update, ctx):
        if not _authorized(update):
            return
        mode = get_setting("mode_override", CONFIG.app_mode)
        paused = get_setting("paused", "false")
        await _send(update, f"mode: *{mode}*\npaused: *{paused}*")

    def _set_mode(name: str):
        async def _h(update, ctx):
            if not _authorized(update):
                return
            set_setting("mode_override", name)
            await _send(update, f"Mode set to *{name}*.")
        return _h

    async def cmd_pause(update, ctx):
        if not _authorized(update):
            return
        set_setting("paused", "true")
        await _send(update, "Paused. No further automated posts until /resume.")

    async def cmd_resume(update, ctx):
        if not _authorized(update):
            return
        set_setting("paused", "false")
        await _send(update, "Resumed.")

    async def cmd_start_day(update, ctx):
        if not _authorized(update):
            return
        await _send(update, "Running daily workflow...")
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, run_daily_workflow)
        await _send(update, build_report_text(result))

    async def cmd_post_now(update, ctx):
        if not _authorized(update):
            return
        await _send(update, "Generating one safe post...")
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, run_post_now)
        await _send(update, build_report_text(result))

    async def cmd_draft_comments(update, ctx):
        if not _authorized(update):
            return
        await _send(update, "Drafting external comments...")
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, run_draft_comments_only)
        await _send(update, build_report_text(result))

    async def cmd_report(update, ctx):
        if not _authorized(update):
            return
        from agents.report_writer import build_report_for_today
        await _send(update, build_report_for_today())

    async def cmd_limits(update, ctx):
        if not _authorized(update):
            return
        l = CONFIG.limits
        text = (
            "*Daily limits*\n"
            f"LinkedIn — posts: {l.linkedin_posts}, ext comments: {l.linkedin_external_comments}, likes: {l.linkedin_likes}\n"
            f"Instagram — posts: {l.instagram_posts}, replies: {l.instagram_replies}, likes: {l.instagram_likes}\n"
            f"Facebook — posts: {l.facebook_posts}, replies: {l.facebook_replies}, ext comments: {l.facebook_external_comments}"
        )
        await _send(update, text)

    app = Application.builder().token(CONFIG.telegram_bot_token).build()
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("start", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("mode", cmd_mode))
    app.add_handler(CommandHandler("dry_run", _set_mode("DRY_RUN")))
    app.add_handler(CommandHandler("semi_auto", _set_mode("SEMI_AUTO")))
    app.add_handler(CommandHandler("full_auto", _set_mode("FULL_AUTO")))
    app.add_handler(CommandHandler("pause", cmd_pause))
    app.add_handler(CommandHandler("resume", cmd_resume))
    app.add_handler(CommandHandler("start_day", cmd_start_day))
    app.add_handler(CommandHandler("post_now", cmd_post_now))
    app.add_handler(CommandHandler("draft_comments", cmd_draft_comments))
    app.add_handler(CommandHandler("report", cmd_report))
    app.add_handler(CommandHandler("limits", cmd_limits))

    log.info("Telegram bot starting...")
    app.run_polling(close_loop=False)
