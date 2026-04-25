"""FastAPI dashboard.

Simple, server-rendered. No JS framework. Lets the human:
- see today's actions, mode, paused state, platform status
- approve / block individual actions
- change mode
- run the workflow
- pause / resume
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import CONFIG, ROOT_DIR, setup_logging
from db import session_scope, get_setting, set_setting, todays_actions
from models import (
    Action,
    PlatformStatus,
    Post,
    STATUS_DRAFT,
    STATUS_QUEUED,
    STATUS_POSTED,
    STATUS_BLOCKED,
    STATUS_FAILED,
    STATUS_HUMAN_REQUIRED,
)
from agents.platform_operator import (
    post_to_linkedin,
    post_to_facebook,
    post_to_instagram,
    reply_facebook_comment,
    reply_instagram_comment,
)
from agents.ceo_controller import run_daily_workflow, current_mode

log = logging.getLogger(__name__)
setup_logging(CONFIG)

app = FastAPI(title="GaugeFlow Social OS")

DASHBOARD_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(DASHBOARD_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(DASHBOARD_DIR / "static")), name="static")


VALID_MODES = ("DRY_RUN", "SEMI_AUTO", "FULL_AUTO")


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    with session_scope() as s:
        actions = todays_actions(s)
        platform_rows = s.query(PlatformStatus).all()
        recent_posts = (
            s.query(Post).order_by(Post.created_at.desc()).limit(10).all()
        )

        # Detach data so the template can access fields after session closes
        actions_data = [_action_dict(a) for a in actions]
        platforms_data = [
            {
                "platform": p.platform,
                "status": p.status,
                "human_required": p.human_required,
                "last_error": p.last_error or "",
                "last_checked_at": p.last_checked_at,
            }
            for p in platform_rows
        ]
        posts_data = [
            {
                "platform": p.platform,
                "topic": p.topic,
                "text": p.text,
                "posted_url": p.posted_url,
                "posted_at": p.posted_at,
            }
            for p in recent_posts
        ]

    return templates.TemplateResponse("home.html", {
        "request": request,
        "mode": current_mode(),
        "paused": get_setting("paused", "false") == "true",
        "actions": actions_data,
        "platforms": platforms_data,
        "posts": posts_data,
    })


@app.get("/actions", response_class=HTMLResponse)
def actions_list(request: Request, status: Optional[str] = None):
    with session_scope() as s:
        q = s.query(Action).order_by(Action.created_at.desc())
        if status:
            q = q.filter(Action.status == status)
        actions = [_action_dict(a) for a in q.limit(200).all()]
    return templates.TemplateResponse("actions.html", {
        "request": request,
        "actions": actions,
        "filter_status": status or "",
    })


@app.get("/actions/{action_id}", response_class=HTMLResponse)
def action_detail(request: Request, action_id: int):
    with session_scope() as s:
        a = s.query(Action).get(action_id)
        if not a:
            raise HTTPException(404)
        data = _action_dict(a)
    return templates.TemplateResponse("action_detail.html", {
        "request": request,
        "a": data,
    })


@app.post("/actions/{action_id}/approve")
def action_approve(action_id: int):
    """Approve a draft and try to actually post it."""
    with session_scope() as s:
        a = s.query(Action).get(action_id)
        if not a:
            raise HTTPException(404)
        if a.status not in (STATUS_DRAFT, STATUS_QUEUED, STATUS_FAILED):
            return RedirectResponse(f"/actions/{action_id}", status_code=303)
        platform = a.platform
        if a.action_type == "post":
            if platform == "linkedin":
                result = post_to_linkedin(a.text)
            elif platform == "facebook":
                result = post_to_facebook(a.text)
            elif platform == "instagram":
                result = post_to_instagram(a.text)
            else:
                result = {"success": False, "error": "unknown_platform"}
        elif a.action_type == "reply":
            if platform == "facebook":
                result = reply_facebook_comment(a.target_url, a.text)
            elif platform == "instagram":
                result = reply_instagram_comment(a.target_url, a.text)
            else:
                result = {"success": False, "error": "reply_unsupported"}
        else:
            result = {"success": False, "error": "approval_unsupported_for_action_type"}

        if result.get("success"):
            a.status = STATUS_POSTED
            a.result_url = result.get("result_url", "")
        else:
            a.status = STATUS_FAILED
            a.error = result.get("error", "unknown_error")
        a.screenshot_path = result.get("screenshot_path", "") or a.screenshot_path
    return RedirectResponse(f"/actions/{action_id}", status_code=303)


@app.post("/actions/{action_id}/block")
def action_block(action_id: int):
    with session_scope() as s:
        a = s.query(Action).get(action_id)
        if not a:
            raise HTTPException(404)
        a.status = STATUS_BLOCKED
        a.error = (a.error or "") + "; manually blocked"
    return RedirectResponse(f"/actions/{action_id}", status_code=303)


@app.post("/mode/{mode}")
def set_mode(mode: str):
    mode = (mode or "").upper()
    if mode not in VALID_MODES:
        raise HTTPException(400, f"invalid mode: {mode}")
    set_setting("mode_override", mode)
    return RedirectResponse("/", status_code=303)


@app.post("/run")
def run_now():
    result = run_daily_workflow()
    log.info("manual run: %s posts, %s replies, %s ext",
             len(result.get("posts", [])),
             len(result.get("replies", [])),
             len(result.get("external_comments", [])))
    return RedirectResponse("/", status_code=303)


@app.post("/pause")
def pause_now():
    set_setting("paused", "true")
    return RedirectResponse("/", status_code=303)


@app.post("/resume")
def resume_now():
    set_setting("paused", "false")
    return RedirectResponse("/", status_code=303)


@app.get("/health", response_class=PlainTextResponse)
def health():
    return "ok"


def _action_dict(a: Action) -> dict:
    return {
        "id": a.id,
        "created_at": a.created_at,
        "platform": a.platform,
        "action_type": a.action_type,
        "topic": a.topic,
        "target_name": a.target_name,
        "target_url": a.target_url,
        "text": a.text,
        "risk_score": a.risk_score,
        "safety_decision": a.safety_decision,
        "safety_reason": a.safety_reason,
        "status": a.status,
        "mode": a.mode,
        "result_url": a.result_url,
        "error": a.error or "",
        "screenshot_path": a.screenshot_path or "",
    }
