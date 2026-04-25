"""Database session, initialization, and helper queries."""
from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Iterator, List, Optional

from sqlalchemy import create_engine, func, and_
from sqlalchemy.orm import sessionmaker, Session

from config import DB_PATH
from models import (
    Base,
    Action,
    Post,
    Comment,
    EngagementHistory,
    PlatformStatus,
    Setting,
    STATUS_POSTED,
    STATUS_APPROVED_AUTO,
)

log = logging.getLogger(__name__)

_engine = create_engine(
    f"sqlite:///{DB_PATH}",
    echo=False,
    future=True,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, future=True)


def init_db() -> None:
    """Create all tables. Idempotent."""
    Base.metadata.create_all(_engine)
    log.info("Database initialized at %s", DB_PATH)
    # Seed default platform_status rows
    with session_scope() as s:
        for plat in ("linkedin", "facebook", "instagram"):
            existing = s.query(PlatformStatus).filter_by(platform=plat).first()
            if not existing:
                s.add(PlatformStatus(platform=plat, status="ok"))


@contextmanager
def session_scope() -> Iterator[Session]:
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


# ------------------------- Settings ------------------------- #

def get_setting(key: str, default: str = "") -> str:
    with session_scope() as s:
        row = s.query(Setting).filter_by(key=key).first()
        return row.value if row else default


def set_setting(key: str, value: str) -> None:
    with session_scope() as s:
        row = s.query(Setting).filter_by(key=key).first()
        if row:
            row.value = value
            row.updated_at = datetime.utcnow()
        else:
            s.add(Setting(key=key, value=value))


# ------------------------- Action queries ------------------------- #

def count_actions_today(
    session: Session,
    platform: str,
    action_type: str,
    posted_only: bool = True,
) -> int:
    start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    q = session.query(Action).filter(
        Action.platform == platform,
        Action.action_type == action_type,
        Action.created_at >= start,
    )
    if posted_only:
        q = q.filter(Action.status.in_((STATUS_POSTED, STATUS_APPROVED_AUTO)))
    return q.count()


def recent_post_texts(session: Session, platform: str, days: int = 14, limit: int = 30) -> List[str]:
    cutoff = datetime.utcnow() - timedelta(days=days)
    rows = (
        session.query(Action.text)
        .filter(Action.platform == platform, Action.created_at >= cutoff)
        .order_by(Action.created_at.desc())
        .limit(limit)
        .all()
    )
    return [r[0] for r in rows if r[0]]


def already_engaged_today(session: Session, platform: str, target_name: str) -> bool:
    if not target_name:
        return False
    start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    cnt = (
        session.query(func.count(EngagementHistory.id))
        .filter(
            EngagementHistory.platform == platform,
            EngagementHistory.target_name == target_name,
            EngagementHistory.created_at >= start,
        )
        .scalar()
    )
    return (cnt or 0) > 0


def todays_actions(session: Session) -> List[Action]:
    start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    return (
        session.query(Action)
        .filter(Action.created_at >= start)
        .order_by(Action.created_at.desc())
        .all()
    )


def update_platform_status(
    session: Session,
    platform: str,
    status: str,
    error: str = "",
    human_required: bool = False,
    screenshot_path: str = "",
) -> None:
    row = session.query(PlatformStatus).filter_by(platform=platform).first()
    if not row:
        row = PlatformStatus(platform=platform)
        session.add(row)
    row.status = status
    row.last_checked_at = datetime.utcnow()
    row.last_error = error or ""
    row.human_required = human_required
    if screenshot_path:
        row.screenshot_path = screenshot_path
