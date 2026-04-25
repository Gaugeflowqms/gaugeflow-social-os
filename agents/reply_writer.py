"""Reply writer.

Generates short replies to comments left on GaugeFlow-owned posts. Replies on
owned posts are slightly safer (we control the surrounding context), so the
safety checker gives a small discount.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

from connectors.ai_provider import get_provider, AIProvider
from agents.safety_checker import check_action, is_duplicate, SafetyResult

log = logging.getLogger(__name__)


@dataclass
class ReplyCandidate:
    platform: str
    parent_post_url: str
    parent_comment_id: str
    parent_comment_author: str
    parent_comment_text: str
    text: str
    safety: SafetyResult
    is_duplicate: bool
    error: Optional[str] = None


def generate_reply(
    *,
    platform: str,
    parent_post_url: str,
    parent_comment_id: str,
    parent_comment_author: str,
    parent_comment_text: str,
    recent_replies: List[str],
    provider: Optional[AIProvider] = None,
) -> ReplyCandidate:
    provider = provider or get_provider()
    log.info("reply_writer: drafting reply on %s for comment by %s", platform, parent_comment_author)

    try:
        text = provider.generate_reply(parent_comment_text, platform)
    except Exception as e:
        log.exception("AI reply generation failed: %s", e)
        return ReplyCandidate(
            platform=platform,
            parent_post_url=parent_post_url,
            parent_comment_id=parent_comment_id,
            parent_comment_author=parent_comment_author,
            parent_comment_text=parent_comment_text,
            text="",
            safety=SafetyResult(100.0, "blocked", f"ai_error: {e}", []),
            is_duplicate=False,
            error=str(e),
        )

    if not text or text.strip().upper() == "SKIP":
        return ReplyCandidate(
            platform=platform,
            parent_post_url=parent_post_url,
            parent_comment_id=parent_comment_id,
            parent_comment_author=parent_comment_author,
            parent_comment_text=parent_comment_text,
            text="",
            safety=SafetyResult(100.0, "blocked", "model returned SKIP/empty", []),
            is_duplicate=False,
            error="model_skipped",
        )

    safety = check_action(
        action_type="reply",
        text=text,
        platform=platform,
        is_owned_post=True,
        extra_context=parent_comment_text,
    )
    dup = is_duplicate(text, recent_replies)
    if dup:
        safety = SafetyResult(
            risk_score=max(safety.risk_score, 85.0),
            decision="blocked",
            reason="duplicate of a recent reply",
            matched_rules=safety.matched_rules + ["duplicate"],
        )

    return ReplyCandidate(
        platform=platform,
        parent_post_url=parent_post_url,
        parent_comment_id=parent_comment_id,
        parent_comment_author=parent_comment_author,
        parent_comment_text=parent_comment_text,
        text=text.strip(),
        safety=safety,
        is_duplicate=dup,
    )


def is_simple_owned_comment(text: str) -> bool:
    """Heuristic: positive/short/non-controversial comment we can auto-reply to."""
    if not text:
        return False
    t = text.strip().lower()
    if len(t) > 280:
        return False
    bad = (
        "lawsuit", "sue", "scam", "fraud", "garbage", "trash",
        "horrible", "awful", "worst", "complaint", "refund",
        "broken", "doesn't work", "doesnt work", "not working",
        "angry", "mad", "disappointed",
    )
    if any(b in t for b in bad):
        return False
    # Question marks are fine
    return True
