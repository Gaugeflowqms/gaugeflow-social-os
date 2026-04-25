"""SQLAlchemy ORM models for GaugeFlow Social OS."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    String,
    Text,
    Boolean,
    Float,
    Index,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


# Action statuses
STATUS_DRAFT = "draft"
STATUS_QUEUED = "queued"
STATUS_APPROVED_AUTO = "approved_auto"
STATUS_POSTED = "posted"
STATUS_SKIPPED = "skipped"
STATUS_BLOCKED = "blocked"
STATUS_FAILED = "failed"
STATUS_HUMAN_REQUIRED = "human_required"

ALL_STATUSES = (
    STATUS_DRAFT,
    STATUS_QUEUED,
    STATUS_APPROVED_AUTO,
    STATUS_POSTED,
    STATUS_SKIPPED,
    STATUS_BLOCKED,
    STATUS_FAILED,
    STATUS_HUMAN_REQUIRED,
)


# Action types
ACTION_POST = "post"
ACTION_REPLY = "reply"
ACTION_EXTERNAL_COMMENT = "external_comment"
ACTION_LIKE = "like"


# Safety decisions
DECISION_AUTO_POST = "auto_post"
DECISION_DRAFT_ONLY = "draft_only"
DECISION_BLOCKED = "blocked"


class Action(Base):
    __tablename__ = "actions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    platform = Column(String(50), nullable=False, index=True)
    action_type = Column(String(50), nullable=False, index=True)
    target_url = Column(String(1000), default="")
    target_name = Column(String(500), default="")
    text = Column(Text, default="")
    media_path = Column(String(1000), default="")
    risk_score = Column(Float, default=0.0)
    safety_decision = Column(String(50), default="")
    safety_reason = Column(Text, default="")
    status = Column(String(50), default=STATUS_DRAFT, index=True)
    mode = Column(String(20), default="DRY_RUN")
    result_url = Column(String(1000), default="")
    error = Column(Text, default="")
    screenshot_path = Column(String(1000), default="")
    topic = Column(String(500), default="")

    __table_args__ = (
        Index("ix_actions_platform_created", "platform", "created_at"),
    )


class Post(Base):
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    platform = Column(String(50), nullable=False, index=True)
    topic = Column(String(500), default="")
    text = Column(Text, default="")
    media_path = Column(String(1000), default="")
    posted_url = Column(String(1000), default="")
    posted_at = Column(DateTime, nullable=True)
    engagement_count = Column(Integer, default=0)


class Comment(Base):
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    platform = Column(String(50), nullable=False, index=True)
    target_url = Column(String(1000), default="")
    target_name = Column(String(500), default="")
    text = Column(Text, default="")
    posted_url = Column(String(1000), default="")
    status = Column(String(50), default=STATUS_DRAFT)
    risk_score = Column(Float, default=0.0)


class EngagementHistory(Base):
    __tablename__ = "engagement_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    platform = Column(String(50), nullable=False, index=True)
    target_name = Column(String(500), default="")
    target_url = Column(String(1000), default="")
    action_type = Column(String(50), default="")
    text = Column(Text, default="")


class PlatformStatus(Base):
    __tablename__ = "platform_status"

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(String(50), unique=True, nullable=False, index=True)
    status = Column(String(50), default="ok")
    last_checked_at = Column(DateTime, default=datetime.utcnow)
    last_error = Column(Text, default="")
    human_required = Column(Boolean, default=False)
    screenshot_path = Column(String(1000), default="")


class Setting(Base):
    __tablename__ = "settings"

    key = Column(String(100), primary_key=True)
    value = Column(Text, default="")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
