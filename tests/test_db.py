"""DB tests. Use a temporary on-disk SQLite by monkeypatching the module
engine before importing dependent modules."""
import importlib
import os
import sys
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    # Force config to use a tmp DB path
    db_file = tmp_path / "test.db"
    # Re-import config and db with patched DB_PATH
    import config
    monkeypatch.setattr(config, "DB_PATH", db_file, raising=False)
    if "db" in sys.modules:
        del sys.modules["db"]
    if "models" in sys.modules:
        del sys.modules["models"]
    import models  # noqa: F401
    db = importlib.import_module("db")
    # rebuild engine to point at tmp db
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    db._engine = create_engine(f"sqlite:///{db_file}", future=True,
                               connect_args={"check_same_thread": False})
    db.SessionLocal = sessionmaker(bind=db._engine, expire_on_commit=False, future=True)
    db.init_db()
    return db


def test_init_db_creates_tables(fresh_db):
    from sqlalchemy import inspect
    insp = inspect(fresh_db._engine)
    names = set(insp.get_table_names())
    assert {"actions", "posts", "comments", "engagement_history",
            "platform_status", "settings"}.issubset(names)


def test_action_insert_and_status_change(fresh_db):
    from models import Action, STATUS_DRAFT, STATUS_POSTED
    with fresh_db.session_scope() as s:
        a = Action(
            platform="linkedin", action_type="post",
            text="Quality records are part of the product.",
            risk_score=12.0, safety_decision="auto_post",
            safety_reason="ok", status=STATUS_DRAFT, mode="DRY_RUN",
        )
        s.add(a)
        s.flush()
        action_id = a.id
    with fresh_db.session_scope() as s:
        a = s.query(Action).get(action_id)
        a.status = STATUS_POSTED
    with fresh_db.session_scope() as s:
        a = s.query(Action).get(action_id)
        assert a.status == STATUS_POSTED


def test_count_actions_today_and_limit(fresh_db):
    from models import Action, STATUS_POSTED
    with fresh_db.session_scope() as s:
        for _ in range(3):
            s.add(Action(
                platform="linkedin", action_type="external_comment",
                text="x", risk_score=10.0, safety_decision="auto_post",
                safety_reason="", status=STATUS_POSTED, mode="FULL_AUTO",
            ))
    with fresh_db.session_scope() as s:
        n = fresh_db.count_actions_today(s, "linkedin", "external_comment")
        assert n == 3


def test_engagement_dedup(fresh_db):
    from models import EngagementHistory
    with fresh_db.session_scope() as s:
        s.add(EngagementHistory(
            platform="linkedin", target_name="Acme Quality",
            target_url="https://linkedin.com/in/acme",
            action_type="external_comment", text="hi",
        ))
    with fresh_db.session_scope() as s:
        assert fresh_db.already_engaged_today(s, "linkedin", "Acme Quality") is True
        assert fresh_db.already_engaged_today(s, "linkedin", "Other Person") is False


def test_settings_get_set(fresh_db):
    fresh_db.set_setting("mode_override", "FULL_AUTO")
    assert fresh_db.get_setting("mode_override", "DRY_RUN") == "FULL_AUTO"
    fresh_db.set_setting("mode_override", "DRY_RUN")
    assert fresh_db.get_setting("mode_override", "") == "DRY_RUN"


def test_daily_limit_enforcement(fresh_db, monkeypatch):
    """The controller's _under_limit should refuse a new action once today's
    posted count for that (platform, action_type) reaches the cap."""
    from models import Action, STATUS_POSTED
    # Patch CONFIG.limits so we don't depend on .env state in the test
    import config
    monkeypatch.setattr(config.CONFIG.limits, "linkedin_external_comments", 2, raising=False)

    # Re-import the controller so it sees the patched limits when computing _limit_for
    import importlib
    import agents.ceo_controller as ceo
    ceo = importlib.reload(ceo)

    # Replace the controller's count_actions_today with our fresh_db one
    monkeypatch.setattr(ceo, "count_actions_today", fresh_db.count_actions_today)

    with fresh_db.session_scope() as s:
        # Zero so far -> under limit
        assert ceo._under_limit(s, "linkedin", "external_comment") is True
        s.add(Action(
            platform="linkedin", action_type="external_comment",
            text="x", risk_score=10.0, safety_decision="auto_post",
            safety_reason="", status=STATUS_POSTED, mode="FULL_AUTO",
        ))
    with fresh_db.session_scope() as s:
        # 1 posted -> still under (cap is 2)
        assert ceo._under_limit(s, "linkedin", "external_comment") is True
        s.add(Action(
            platform="linkedin", action_type="external_comment",
            text="y", risk_score=10.0, safety_decision="auto_post",
            safety_reason="", status=STATUS_POSTED, mode="FULL_AUTO",
        ))
    with fresh_db.session_scope() as s:
        # 2 posted -> at cap, no longer under
        assert ceo._under_limit(s, "linkedin", "external_comment") is False
