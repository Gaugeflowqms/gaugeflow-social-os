"""Central configuration for GaugeFlow Social OS.

Reads settings from environment (loaded via python-dotenv) and exposes them as
a single Config object that the rest of the system imports.
"""
from __future__ import annotations

import logging
import logging.handlers
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent
STORAGE_DIR = ROOT_DIR / "storage"
SCREENSHOT_DIR = STORAGE_DIR / "screenshots"
LOG_DIR = STORAGE_DIR / "logs"
EXPORT_DIR = STORAGE_DIR / "exports"
MEMORY_DIR = ROOT_DIR / "memory"
DB_PATH = STORAGE_DIR / "actions.db"

for d in (STORAGE_DIR, SCREENSHOT_DIR, LOG_DIR, EXPORT_DIR, MEMORY_DIR):
    d.mkdir(parents=True, exist_ok=True)

load_dotenv(ROOT_DIR / ".env")


def _bool(value: Optional[str], default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "y", "on")


def _int(value: Optional[str], default: int) -> int:
    try:
        return int(value) if value is not None and value != "" else default
    except ValueError:
        return default


VALID_MODES = ("DRY_RUN", "SEMI_AUTO", "FULL_AUTO")


@dataclass
class DailyLimits:
    linkedin_posts: int = 1
    linkedin_external_comments: int = 3
    linkedin_likes: int = 5
    instagram_posts: int = 1
    instagram_replies: int = 5
    instagram_likes: int = 5
    facebook_posts: int = 1
    facebook_replies: int = 10
    facebook_external_comments: int = 5


@dataclass
class Config:
    app_mode: str = "DRY_RUN"
    ai_provider: str = "openai"

    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"

    anthropic_api_key: str = ""
    claude_model: str = "claude-3-5-sonnet-latest"

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    facebook_page_id: str = ""
    facebook_page_access_token: str = ""

    instagram_business_account_id: str = ""
    instagram_access_token: str = ""

    linkedin_organization_id: str = ""
    linkedin_access_token: str = ""

    browser_enabled: bool = False
    browser_profile_path: str = ""
    headless: bool = False
    login_automation_allowed: bool = False

    daily_run_time: str = "08:30"
    timezone: str = "America/Chicago"

    dashboard_host: str = "127.0.0.1"
    dashboard_port: int = 8765

    log_level: str = "INFO"

    limits: DailyLimits = field(default_factory=DailyLimits)

    @classmethod
    def load(cls) -> "Config":
        mode = os.getenv("APP_MODE", "DRY_RUN").strip().upper()
        if mode not in VALID_MODES:
            mode = "DRY_RUN"

        cfg = cls(
            app_mode=mode,
            ai_provider=os.getenv("AI_PROVIDER", "openai").strip().lower(),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            claude_model=os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-latest"),
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
            facebook_page_id=os.getenv("FACEBOOK_PAGE_ID", ""),
            facebook_page_access_token=os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN", ""),
            instagram_business_account_id=os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID", ""),
            instagram_access_token=os.getenv("INSTAGRAM_ACCESS_TOKEN", ""),
            linkedin_organization_id=os.getenv("LINKEDIN_ORGANIZATION_ID", ""),
            linkedin_access_token=os.getenv("LINKEDIN_ACCESS_TOKEN", ""),
            browser_enabled=_bool(os.getenv("BROWSER_ENABLED"), False),
            browser_profile_path=os.getenv("BROWSER_PROFILE_PATH", ""),
            headless=_bool(os.getenv("HEADLESS"), False),
            login_automation_allowed=_bool(os.getenv("LOGIN_AUTOMATION_ALLOWED"), False),
            daily_run_time=os.getenv("DAILY_RUN_TIME", "08:30"),
            timezone=os.getenv("TIMEZONE", "America/Chicago"),
            dashboard_host=os.getenv("DASHBOARD_HOST", "127.0.0.1"),
            dashboard_port=_int(os.getenv("DASHBOARD_PORT"), 8765),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            limits=DailyLimits(
                linkedin_posts=_int(os.getenv("MAX_LINKEDIN_POSTS_PER_DAY"), 1),
                linkedin_external_comments=_int(os.getenv("MAX_LINKEDIN_EXTERNAL_COMMENTS_PER_DAY"), 3),
                linkedin_likes=_int(os.getenv("MAX_LINKEDIN_LIKES_PER_DAY"), 5),
                instagram_posts=_int(os.getenv("MAX_INSTAGRAM_POSTS_PER_DAY"), 1),
                instagram_replies=_int(os.getenv("MAX_INSTAGRAM_REPLIES_PER_DAY"), 5),
                instagram_likes=_int(os.getenv("MAX_INSTAGRAM_LIKES_PER_DAY"), 5),
                facebook_posts=_int(os.getenv("MAX_FACEBOOK_POSTS_PER_DAY"), 1),
                facebook_replies=_int(os.getenv("MAX_FACEBOOK_REPLIES_PER_DAY"), 10),
                facebook_external_comments=_int(os.getenv("MAX_FACEBOOK_EXTERNAL_COMMENTS_PER_DAY"), 5),
            ),
        )
        return cfg

    def has_facebook(self) -> bool:
        return bool(self.facebook_page_id and self.facebook_page_access_token)

    def has_instagram(self) -> bool:
        return bool(self.instagram_business_account_id and self.instagram_access_token)

    def has_linkedin_api(self) -> bool:
        return bool(self.linkedin_organization_id and self.linkedin_access_token)

    def has_telegram(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)


_logger_initialized = False


def setup_logging(cfg: Optional[Config] = None) -> None:
    """Set up rotating file + console logging. Idempotent."""
    global _logger_initialized
    if _logger_initialized:
        return

    cfg = cfg or Config.load()
    level = getattr(logging, cfg.log_level, logging.INFO)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(level)
    for h in list(root.handlers):
        root.removeHandler(h)

    file_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / "gaugeflow.log",
        maxBytes=2_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    _logger_initialized = True


CONFIG = Config.load()
