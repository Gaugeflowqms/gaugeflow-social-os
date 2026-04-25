"""Comment writer.

Generates short, helpful comments on external posts. External comments are
inherently riskier than original posts, so the safety checker bumps the score
and the orchestrator only auto-posts under FULL_AUTO with a low score.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

from connectors.ai_provider import get_provider, AIProvider
from agents.safety_checker import check_action, is_duplicate, SafetyResult

log = logging.getLogger(__name__)


@dataclass
class CommentCandidate:
    platform: str
    target_url: str
    target_name: str
    target_text: str
    text: str
    safety: SafetyResult
    is_duplicate: bool
    error: Optional[str] = None


def generate_external_comment(
    *,
    platform: str,
    target_url: str,
    target_name: str,
    target_text: str,
    recent_comments: List[str],
    provider: Optional[AIProvider] = None,
) -> CommentCandidate:
    provider = provider or get_provider()
    log.info("comment_writer: drafting comment on %s/%s", platform, target_name or target_url)

    try:
        text = provider.generate_comment(target_text, platform)
    except Exception as e:
        log.exception("AI comment generation failed: %s", e)
        return CommentCandidate(
            platform=platform,
            target_url=target_url,
            target_name=target_name,
            target_text=target_text,
            text="",
            safety=SafetyResult(100.0, "blocked", f"ai_error: {e}", []),
            is_duplicate=False,
            error=str(e),
        )

    if not text or text.strip().upper() == "SKIP":
        return CommentCandidate(
            platform=platform,
            target_url=target_url,
            target_name=target_name,
            target_text=target_text,
            text="",
            safety=SafetyResult(100.0, "blocked", "model returned SKIP/empty", []),
            is_duplicate=False,
            error="model_skipped",
        )

    safety = check_action(
        action_type="external_comment",
        text=text,
        platform=platform,
        is_owned_post=False,
        extra_context=target_text,
    )
    dup = is_duplicate(text, recent_comments)
    if dup:
        safety = SafetyResult(
            risk_score=max(safety.risk_score, 85.0),
            decision="blocked",
            reason="duplicate of a recent comment",
            matched_rules=safety.matched_rules + ["duplicate"],
        )

    return CommentCandidate(
        platform=platform,
        target_url=target_url,
        target_name=target_name,
        target_text=target_text,
        text=text.strip(),
        safety=safety,
        is_duplicate=dup,
    )
