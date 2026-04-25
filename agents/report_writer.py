"""Daily report writer.

Reads today's actions from the database and produces a Telegram-friendly
summary. Optionally asks the AI provider to compress it into a short brief.
"""
from __future__ import annotations

import logging
from typing import Dict, List

from db import session_scope, todays_actions
from models import (
    STATUS_POSTED,
    STATUS_BLOCKED,
    STATUS_FAILED,
    STATUS_DRAFT,
    STATUS_HUMAN_REQUIRED,
)

log = logging.getLogger(__name__)


def build_report_text(workflow_result: Dict) -> str:
    """Build a human-readable report from the dict returned by the controller."""
    lines: List[str] = []
    mode = workflow_result.get("mode", "DRY_RUN")
    paused = workflow_result.get("paused", False)
    lines.append(f"*GaugeFlow Social OS — daily report*")
    lines.append(f"mode: `{mode}`{'  (paused)' if paused else ''}")

    posts = workflow_result.get("posts", [])
    if posts:
        lines.append("")
        lines.append("*Posts*")
        for p in posts:
            mark = _mark(p.get("status"))
            lines.append(
                f"{mark} {p.get('platform')} — {p.get('topic','')} "
                f"(risk {p.get('risk_score', 0):.0f})"
            )
            if p.get("result_url"):
                lines.append(f"   {p['result_url']}")

    replies = workflow_result.get("replies", [])
    if replies:
        lines.append("")
        lines.append("*Replies*")
        for r in replies[:10]:
            mark = _mark(r.get("status"))
            lines.append(
                f"{mark} {r.get('platform')} — to {r.get('target_name','?')[:30]} "
                f"(risk {r.get('risk_score', 0):.0f})"
            )

    ext = workflow_result.get("external_comments", [])
    if ext:
        lines.append("")
        lines.append("*External comments*")
        for c in ext[:10]:
            mark = _mark(c.get("status"))
            lines.append(
                f"{mark} {c.get('platform')} — {c.get('target_name','?')[:40]} "
                f"(risk {c.get('risk_score', 0):.0f})"
            )

    issues = workflow_result.get("issues", [])
    if issues:
        lines.append("")
        lines.append("*Issues*")
        for i in issues[:10]:
            lines.append(f"⚠ {i}")

    if not (posts or replies or ext or issues):
        lines.append("\nNothing to report.")

    return "\n".join(lines)[:3900]


def _mark(status: str) -> str:
    if status == STATUS_POSTED:
        return "✅"
    if status == STATUS_BLOCKED:
        return "⛔"
    if status == STATUS_FAILED:
        return "❌"
    if status == STATUS_HUMAN_REQUIRED:
        return "🛑"
    if status == STATUS_DRAFT:
        return "📝"
    return "•"


def build_report_for_today() -> str:
    """Read database for today's actions and assemble a report."""
    lines = ["*GaugeFlow Social OS — today*"]
    with session_scope() as s:
        actions = todays_actions(s)
    if not actions:
        return "*GaugeFlow Social OS*\nNo actions today."

    for a in actions:
        mark = _mark(a.status)
        lines.append(
            f"{mark} {a.platform}/{a.action_type} — risk {a.risk_score:.0f} — {a.status}"
        )
        if a.target_name:
            lines.append(f"   target: {a.target_name[:60]}")
        if a.result_url:
            lines.append(f"   {a.result_url}")
    return "\n".join(lines)[:3900]
