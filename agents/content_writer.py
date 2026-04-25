"""Content writer agent.

Generates one post per platform per day. Picks a topic from the rotation,
asks the AI provider for a draft, runs it through the safety checker, and
returns a structured candidate the orchestrator can save.
"""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from config import MEMORY_DIR
from connectors.ai_provider import get_provider, AIProvider
from agents.safety_checker import check_action, is_duplicate, SafetyResult

log = logging.getLogger(__name__)


DEFAULT_TOPICS = [
    "Audit stress",
    "AS9100 readiness",
    "ISO 9001 quality records",
    "ISO 13485 traceability",
    "FAI packages",
    "AS9102 forms",
    "CMM reports tied to jobs",
    "Inspection records on the shop floor",
    "Calibration logs",
    "Cert packets",
    "Supplier quality",
    "Revision control",
    "NCRs",
    "Corrective actions",
    "Shipment delays caused by paperwork",
    "Missing material certs",
    "First article inspection",
    "Quality bottlenecks",
    "Manufacturing documentation",
    "Shop-floor reality",
    "Why spreadsheets fail quality teams",
    "How folders become a mess",
    "Practical QMS habits",
    "Digital quality records",
    "Traceability from PO to shipment",
]


@dataclass
class ContentCandidate:
    platform: str
    topic: str
    text: str
    safety: SafetyResult
    is_duplicate: bool
    error: Optional[str] = None


def load_topics() -> List[str]:
    p = MEMORY_DIR / "content_topics.md"
    if not p.exists():
        return DEFAULT_TOPICS
    raw = p.read_text(encoding="utf-8")
    found: List[str] = []
    for line in raw.splitlines():
        line = line.strip()
        # numbered list items: "1. Audit stress"
        if line and line[0].isdigit() and "." in line:
            after = line.split(".", 1)[1].strip()
            if after and len(after) < 120:
                found.append(after)
    return found or DEFAULT_TOPICS


def pick_topic(recent_topics: List[str]) -> str:
    topics = load_topics()
    fresh = [t for t in topics if t not in recent_topics[:8]]
    pool = fresh if fresh else topics
    return random.choice(pool)


def generate_for_platform(
    platform: str,
    recent_posts: List[str],
    recent_topics: List[str],
    provider: Optional[AIProvider] = None,
    forced_topic: Optional[str] = None,
) -> ContentCandidate:
    provider = provider or get_provider()
    topic = forced_topic or pick_topic(recent_topics)
    log.info("content_writer: drafting %s post on topic %r", platform, topic)

    try:
        text = provider.generate_post(platform, topic, recent_posts=recent_posts)
    except Exception as e:
        log.exception("AI generation failed for %s: %s", platform, e)
        return ContentCandidate(
            platform=platform,
            topic=topic,
            text="",
            safety=SafetyResult(100.0, "blocked", f"ai_error: {e}", []),
            is_duplicate=False,
            error=str(e),
        )

    if not text or text.strip().upper() == "SKIP":
        return ContentCandidate(
            platform=platform,
            topic=topic,
            text="",
            safety=SafetyResult(100.0, "blocked", "model returned SKIP/empty", []),
            is_duplicate=False,
            error="model_skipped",
        )

    safety = check_action(action_type="post", text=text, platform=platform)
    dup = is_duplicate(text, recent_posts)
    if dup:
        safety = SafetyResult(
            risk_score=max(safety.risk_score, 90.0),
            decision="blocked",
            reason="duplicate of a recent post",
            matched_rules=safety.matched_rules + ["duplicate"],
        )

    return ContentCandidate(
        platform=platform,
        topic=topic,
        text=text.strip(),
        safety=safety,
        is_duplicate=dup,
    )
