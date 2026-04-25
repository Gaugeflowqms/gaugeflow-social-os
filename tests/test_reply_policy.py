from __future__ import annotations

import importlib
import sys
from unittest.mock import Mock

import pytest

from agents.reply_writer import ReplyCandidate
from agents.safety_checker import SafetyResult


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    import config

    db_file = tmp_path / "test.db"
    monkeypatch.setattr(config, "DB_PATH", db_file, raising=False)
    if "db" in sys.modules:
        del sys.modules["db"]
    if "models" in sys.modules:
        del sys.modules["models"]
    importlib.import_module("models")
    db = importlib.import_module("db")

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    db._engine = create_engine(
        f"sqlite:///{db_file}",
        future=True,
        connect_args={"check_same_thread": False},
    )
    db.SessionLocal = sessionmaker(bind=db._engine, expire_on_commit=False, future=True)
    db.init_db()
    return db


def _reload_ceo_controller():
    import agents.ceo_controller as ceo
    return importlib.reload(ceo)


def test_duplicate_reply_prevention_same_comment_not_replied_twice(fresh_db, monkeypatch):
    ceo = _reload_ceo_controller()

    reply_result = ReplyCandidate(
        platform="facebook",
        parent_post_url="",
        parent_comment_id="c-123",
        parent_comment_author="External User",
        parent_comment_text="Great point!",
        text="Thanks for the feedback.",
        safety=SafetyResult(10.0, "auto_post", "safe", []),
        is_duplicate=False,
    )
    post_reply = Mock(return_value={"success": True, "result_url": "https://facebook.com/reply/1"})

    monkeypatch.setattr(ceo, "already_engaged_today", lambda *args, **kwargs: False)
    monkeypatch.setattr(ceo, "generate_reply", lambda **kwargs: reply_result)
    monkeypatch.setattr(ceo, "is_simple_owned_comment", lambda _: True)
    monkeypatch.setattr(ceo, "_should_auto_post", lambda *args, **kwargs: True)
    monkeypatch.setattr(ceo, "reply_facebook_comment", post_reply)

    raw_comment = {"id": "c-123", "author": "External User", "text": "Great point!"}
    with fresh_db.session_scope() as s:
        first = ceo._maybe_reply(s, "facebook", raw_comment, mode="FULL_AUTO")
        second = ceo._maybe_reply(s, "facebook", raw_comment, mode="FULL_AUTO")

    assert first is not None
    assert first["status"] == "posted"
    assert second is None
    assert post_reply.call_count == 1


def test_unsafe_owned_comment_reply_is_blocked_and_not_posted(fresh_db, monkeypatch):
    ceo = _reload_ceo_controller()

    blocked_result = ReplyCandidate(
        platform="facebook",
        parent_post_url="",
        parent_comment_id="c-unsafe-1",
        parent_comment_author="External User",
        parent_comment_text="Can you diagnose my condition?",
        text="I can diagnose your condition, DM me now.",
        safety=SafetyResult(
            100.0,
            "blocked",
            r"matches hard-block pattern: \bdiagnos\w*",
            [r"hard_block:\bdiagnos\w*"],
        ),
        is_duplicate=False,
    )
    post_reply = Mock(return_value={"success": True, "result_url": "https://facebook.com/reply/unsafe"})

    monkeypatch.setattr(ceo, "already_engaged_today", lambda *args, **kwargs: False)
    monkeypatch.setattr(ceo, "generate_reply", lambda **kwargs: blocked_result)
    monkeypatch.setattr(ceo, "reply_facebook_comment", post_reply)

    raw_comment = {"id": "c-unsafe-1", "author": "External User", "text": "Can you diagnose my condition?"}
    with fresh_db.session_scope() as s:
        outcome = ceo._maybe_reply(s, "facebook", raw_comment, mode="FULL_AUTO")

    assert outcome is not None
    assert outcome["status"] == "blocked"
    assert outcome["safety_decision"] == "blocked"
    assert post_reply.call_count == 0
