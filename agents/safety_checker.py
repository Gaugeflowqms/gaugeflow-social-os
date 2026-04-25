"""Safety checker.

Every outbound action passes through here before posting. The checker returns
a structured result with a risk_score (0-100), a decision (auto_post,
draft_only, blocked), and a reason. The rules are deliberately conservative.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, asdict
from typing import Dict, Iterable, List, Optional, Tuple

log = logging.getLogger(__name__)


# --- Hard-block phrases (any match -> blocked) ---
HARD_BLOCK_PATTERNS: Tuple[str, ...] = (
    # Politics & religion
    r"\b(democrat|republican|gop|liberal|conservative|maga|biden|trump|obama)\b",
    r"\b(abortion|pro[- ]?life|pro[- ]?choice|gun control|second amendment)\b",
    r"\b(jesus|christ|allah|muhammad|bible|quran|torah|atheist|believer)\b",
    # Medical / legal / financial advice  (stem-style: leave trailing chars open)
    r"\bdiagnos\w*",
    r"\bprescrib\w*",
    r"\btreat your\b",
    r"\bmedical advice\b",
    r"\b(legal advice|sue them|file a lawsuit|attorney recommend)\b",
    r"\b(guaranteed return|guaranteed profit|risk[- ]free investment)\b",
    # Aggressive sales / spam
    r"\b(dm me now|click the link|don't miss out|limited time|act now)\b",
    r"\b(book a demo today|book your demo|call me now)\b",
    r"\b(buy now|order today|exclusive offer)\b",
    # Tragedy / sensitive
    r"\b(layoff|fired|deceased|passed away|funeral|tragedy|disaster)\b",
    r"\b(suicide|self[- ]?harm|overdose)\b",
    # Bypass / abuse
    r"\b(bypass|circumvent).{0,20}(captcha|2fa|security|login)\b",
    r"\b(scrape|harvest).{0,20}(private|personal)\b",
    # Buzzwords flagged as not-our-voice
    r"\b(game[- ]?changer|revolutionary|seamless|10x|world[- ]?class|cutting[- ]?edge|supercharge|unlock|leverage)\b",
    r"\btransform your business\b",
)

# --- Soft penalty patterns (each adds risk) ---
SOFT_PENALTY_PATTERNS: Tuple[Tuple[str, int], ...] = (
    (r"\bbest[- ]?in[- ]?class\b", 15),
    (r"\bsynergy\b", 15),
    (r"\bdisrupt\b", 12),
    (r"\bnext[- ]?gen\b", 10),
    (r"\bplatform of the future\b", 12),
    (r"\b!!+", 8),  # multiple exclamation marks
    (r"\bASAP\b", 6),
    (r"\bvisit (our|my) (website|site)\b", 18),
    (r"\bdm (me|us)\b", 18),
    (r"\bcontact (me|us) (today|now)\b", 14),
    (r"https?://", 8),  # any link adds risk
    (r"#\w+.*#\w+.*#\w+.*#\w+.*#\w+.*#\w+", 12),  # > 5 hashtags
    (r"\b(amazing|incredible|insane|mind[- ]?blowing)\b", 8),
)

# --- Manufacturing / quality vocabulary that lowers risk ---
DOMAIN_TERMS = (
    "as9100", "as9102", "iso 9001", "iso 13485", "fai", "first article",
    "cmm", "inspection", "calibration", "traceability", "qms",
    "quality", "audit", "ncrs", "ncr", "corrective action", "supplier",
    "machinist", "shop floor", "cnc", "aerospace", "medical device",
    "cert packet", "material cert", "revision", "rev control",
    "pcr", "ppap", "control plan", "fmea", "gauge",
)

# --- Action types that are auto-blocked ---
BLOCKED_ACTION_TYPES = (
    "mass_like",
    "mass_follow",
    "mass_connection_request",
    "cold_dm",
    "scrape_private_profile",
    "bypass_captcha",
    "bypass_2fa",
    "ignore_platform_warning",
)

# --- Browser stop conditions / security challenge keywords ---
SECURITY_CHALLENGE_KEYWORDS = (
    "captcha",
    "security check",
    "verify it's you",
    "verify it is you",
    "unusual activity",
    "we noticed unusual",
    "two-factor",
    "2fa",
    "enter the code",
    "account restricted",
    "action blocked",
    "try again later",
    "suspicious login",
    "confirm your identity",
)


@dataclass
class SafetyResult:
    risk_score: float
    decision: str  # auto_post | draft_only | blocked
    reason: str
    matched_rules: List[str]

    def to_dict(self) -> Dict:
        return asdict(self)


def _has_security_challenge(text: str) -> Optional[str]:
    low = text.lower()
    for kw in SECURITY_CHALLENGE_KEYWORDS:
        if kw in low:
            return kw
    return None


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).lower()


def check_action(
    *,
    action_type: str,
    text: str,
    platform: str,
    is_owned_post: bool = False,
    extra_context: Optional[str] = None,
) -> SafetyResult:
    """Score and decide on a single action.

    Args:
        action_type: 'post', 'reply', 'external_comment', 'like', etc.
        text: outbound text (post body, comment, reply).
        platform: 'linkedin', 'facebook', 'instagram'.
        is_owned_post: True if replying to a comment on a GaugeFlow-owned post.
        extra_context: optional additional text (target post body, page snippet)
            that gets scanned for security challenges and sensitive content.
    """
    matched: List[str] = []
    score = 0.0

    # --- Action-type level blocks ---
    if action_type in BLOCKED_ACTION_TYPES:
        return SafetyResult(
            risk_score=100.0,
            decision="blocked",
            reason=f"action_type {action_type!r} is hard-blocked",
            matched_rules=[f"action_type:{action_type}"],
        )

    body = _normalize(text)
    ctx = _normalize(extra_context or "")

    # --- Security challenges anywhere -> block ---
    sec_kw = _has_security_challenge(text or "") or _has_security_challenge(extra_context or "")
    if sec_kw:
        return SafetyResult(
            risk_score=100.0,
            decision="blocked",
            reason=f"security challenge detected: {sec_kw}",
            matched_rules=[f"security_challenge:{sec_kw}"],
        )

    if not body:
        return SafetyResult(
            risk_score=100.0,
            decision="blocked",
            reason="empty content",
            matched_rules=["empty"],
        )

    # --- Hard-block patterns ---
    for pat in HARD_BLOCK_PATTERNS:
        if re.search(pat, body, flags=re.IGNORECASE):
            matched.append(f"hard_block:{pat}")
            return SafetyResult(
                risk_score=100.0,
                decision="blocked",
                reason=f"matches hard-block pattern: {pat}",
                matched_rules=matched,
            )

    # Sensitive context (target post body) hard-blocks too
    for pat in HARD_BLOCK_PATTERNS:
        if ctx and re.search(pat, ctx, flags=re.IGNORECASE):
            matched.append(f"context_hard_block:{pat}")
            return SafetyResult(
                risk_score=100.0,
                decision="blocked",
                reason=f"target context matches sensitive pattern: {pat}",
                matched_rules=matched,
            )

    # --- Soft penalties ---
    for pat, weight in SOFT_PENALTY_PATTERNS:
        if re.search(pat, body, flags=re.IGNORECASE):
            score += weight
            matched.append(f"soft:{pat}:+{weight}")

    # Length penalties
    if len(body) > 2200:
        score += 12
        matched.append("length:too_long:+12")
    elif len(body) < 30 and action_type == "post":
        score += 20
        matched.append("length:too_short_for_post:+20")

    # ALL CAPS detection
    letters = [c for c in (text or "") if c.isalpha()]
    if letters:
        upper_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
        if upper_ratio > 0.4 and len(letters) > 30:
            score += 15
            matched.append(f"caps_ratio:{upper_ratio:.2f}:+15")

    # Reward domain relevance
    domain_hits = sum(1 for term in DOMAIN_TERMS if term in body)
    if domain_hits >= 1:
        score -= min(15, 5 * domain_hits)
        matched.append(f"domain_terms:{domain_hits}:-{min(15, 5*domain_hits)}")

    # External comments are inherently riskier
    if action_type == "external_comment":
        score += 10
        matched.append("external_comment_baseline:+10")

    # Replies on owned posts are slightly safer
    if action_type == "reply" and is_owned_post:
        score -= 5
        matched.append("owned_reply:-5")

    # Posts have a small floor so we still review them
    if action_type == "post":
        score += 2

    score = max(0.0, min(100.0, score))

    # --- Decision bands ---
    if score >= 81:
        decision = "blocked"
        reason = f"risk score {score:.0f} in blocked band (>=81)"
    elif score >= 51:
        decision = "draft_only"
        reason = f"risk score {score:.0f} in medium band (51-80) -> draft only"
    elif score >= 21:
        decision = "auto_post"
        reason = f"risk score {score:.0f} in low band (21-50) -> auto-post for posts and owned replies"
    else:
        decision = "auto_post"
        reason = f"risk score {score:.0f} in safe band (0-20) -> auto-post"

    return SafetyResult(
        risk_score=score,
        decision=decision,
        reason=reason,
        matched_rules=matched,
    )


def is_duplicate(new_text: str, existing_texts: Iterable[str], threshold: float = 0.85) -> bool:
    """Cheap shingle-based similarity. No external deps."""
    n = _normalize(new_text)
    if not n:
        return False
    n_tokens = set(_shingles(n))
    if not n_tokens:
        return False
    for prev in existing_texts:
        p = _normalize(prev)
        if not p:
            continue
        if p == n:
            return True
        p_tokens = set(_shingles(p))
        if not p_tokens:
            continue
        inter = len(n_tokens & p_tokens)
        union = len(n_tokens | p_tokens)
        if union == 0:
            continue
        sim = inter / union
        if sim >= threshold:
            return True
    return False


def _shingles(text: str, k: int = 5) -> List[str]:
    tokens = text.split()
    if len(tokens) < k:
        return [" ".join(tokens)] if tokens else []
    return [" ".join(tokens[i : i + k]) for i in range(len(tokens) - k + 1)]


def scan_browser_page(visible_text: str) -> Optional[str]:
    """Return the matched security keyword if a page shows a stop condition."""
    return _has_security_challenge(visible_text or "")
