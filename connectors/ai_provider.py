"""AI provider abstraction.

The rest of the system calls into a single AIProvider interface. The actual
implementation (OpenAI or Claude) is selected from config.AI_PROVIDER.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterable, List, Optional

from config import CONFIG, MEMORY_DIR

log = logging.getLogger(__name__)


def _read_memory(name: str) -> str:
    p = MEMORY_DIR / name
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8")


def load_brand_memory() -> str:
    """Concatenate the standing brand context the AI should always have."""
    parts = [
        _read_memory("company_context.md"),
        _read_memory("brand_voice.md"),
        _read_memory("sam_callahan_voice.md"),
        _read_memory("banned_topics.md"),
    ]
    return "\n\n".join(p for p in parts if p)


def system_prompt(extra: str = "") -> str:
    base = (
        "You write social content for GaugeFlow QMS in the voice of Sam Callahan, "
        "a senior solutions advisor with a manufacturing/quality background. "
        "Plain English. Short sentences. No hype, no buzzwords, no fake urgency, "
        "no aggressive sales language, no 'book a demo' or 'visit our website' "
        "unless the human approves it manually. Helpful before selling. "
        "Sound like a real shop-floor quality person.\n"
        "If you cannot produce safe content for the request, return the single "
        "word: SKIP."
    )
    mem = load_brand_memory()
    if mem:
        base += "\n\n=== BRAND MEMORY ===\n" + mem
    if extra:
        base += "\n\n" + extra
    return base


class AIProvider(ABC):
    name: str = "base"

    @abstractmethod
    def complete(self, system: str, user: str, max_tokens: int = 800, temperature: float = 0.7) -> str:
        ...

    # ---- High-level generators ---- #

    def generate_post(
        self,
        platform: str,
        topic: str,
        recent_posts: Optional[List[str]] = None,
    ) -> str:
        recent_block = ""
        if recent_posts:
            joined = "\n---\n".join(p[:600] for p in recent_posts[:8])
            recent_block = (
                "\n\nRecent posts (do NOT repeat phrasing or angles):\n" + joined
            )
        platform_rules = _platform_rules(platform)
        user = (
            f"Write one {platform} post for GaugeFlow QMS.\n"
            f"Topic: {topic}\n"
            f"{platform_rules}\n"
            "Return only the post text. No preamble, no quotes around it."
            f"{recent_block}"
        )
        out = self.complete(system_prompt(), user, max_tokens=900, temperature=0.7)
        return _clean(out)

    def generate_comment(self, target_post: str, platform: str) -> str:
        user = (
            f"You are reading this {platform} post:\n---\n{target_post[:1500]}\n---\n"
            "Write one short, helpful comment (1-3 sentences) from Sam Callahan. "
            "Add value from a manufacturing/quality perspective. "
            "Do not pitch GaugeFlow. Do not include links. Do not use hashtags. "
            "If the post is political, religious, sensitive, or off-topic, return SKIP."
        )
        out = self.complete(system_prompt(), user, max_tokens=300, temperature=0.6)
        return _clean(out)

    def generate_reply(self, original_comment: str, platform: str) -> str:
        user = (
            f"Someone left this comment on a GaugeFlow {platform} post:\n---\n"
            f"{original_comment[:1200]}\n---\n"
            "Write a short, helpful reply (1-2 sentences) from Sam Callahan. "
            "Acknowledge the point if reasonable, add one practical observation. "
            "No sales pitch. No links. If the comment is hostile, off-topic, "
            "political, or sensitive, return SKIP."
        )
        out = self.complete(system_prompt(), user, max_tokens=250, temperature=0.5)
        return _clean(out)

    def summarize_report(self, summary_lines: Iterable[str]) -> str:
        body = "\n".join(summary_lines)
        user = (
            "Summarize today's GaugeFlow Social OS activity in plain language, "
            "no more than 6 short bullet lines. No hype.\n\n"
            f"Raw events:\n{body}"
        )
        try:
            out = self.complete(system_prompt(), user, max_tokens=400, temperature=0.3)
            return _clean(out)
        except Exception as e:
            log.warning("AI summary failed, falling back to raw lines: %s", e)
            return body

    def safety_reasoning(self, text: str) -> str:
        user = (
            "Briefly evaluate whether this content is safe to post for a "
            "manufacturing-quality SaaS brand. One sentence.\n\n"
            f"Content:\n{text[:1500]}"
        )
        try:
            return _clean(self.complete(system_prompt(), user, max_tokens=120, temperature=0.2))
        except Exception:
            return ""


def _clean(text: str) -> str:
    if not text:
        return ""
    t = text.strip()
    # Strip surrounding quotes if model wrapped output
    if (t.startswith('"') and t.endswith('"')) or (t.startswith("'") and t.endswith("'")):
        t = t[1:-1].strip()
    return t


def _platform_rules(platform: str) -> str:
    p = (platform or "").lower()
    if p == "linkedin":
        return (
            "Rules: 500-1200 characters. Short paragraphs. At most 3 hashtags. "
            "No hard CTA. No link unless I approved one."
        )
    if p == "facebook":
        return (
            "Rules: 200-700 characters. Practical tip. Plain language. "
            "Slightly more direct is fine."
        )
    if p == "instagram":
        return (
            "Rules: 100-500 characters. Short hook. Simple caption. "
            "Up to 5 hashtags."
        )
    return "Rules: short and practical."


def get_provider() -> AIProvider:
    """Return the configured provider, with safe fallbacks."""
    from connectors.openai_provider import OpenAIProvider
    from connectors.claude_provider import ClaudeProvider

    name = (CONFIG.ai_provider or "openai").lower()

    if name == "claude":
        if CONFIG.anthropic_api_key:
            return ClaudeProvider()
        log.warning("Claude selected but ANTHROPIC_API_KEY missing; falling back to OpenAI")
        if CONFIG.openai_api_key:
            return OpenAIProvider()
        return NullProvider()

    if name == "openai":
        if CONFIG.openai_api_key:
            return OpenAIProvider()
        log.warning("OpenAI selected but OPENAI_API_KEY missing; falling back to Claude")
        if CONFIG.anthropic_api_key:
            return ClaudeProvider()
        return NullProvider()

    log.warning("Unknown AI_PROVIDER %r; using NullProvider", name)
    return NullProvider()


class NullProvider(AIProvider):
    """Used when no API key is configured. Returns a clearly-marked stub
    so dry-runs and tests still produce something visible without crashing."""

    name = "null"

    def complete(self, system: str, user: str, max_tokens: int = 800, temperature: float = 0.7) -> str:
        # Surface the request topic if present
        return (
            "[STUB CONTENT - no AI provider configured]\n"
            "Quality records are part of the product. "
            "If a cert packet is a scavenger hunt the day shipping needs it, "
            "the system has already failed. GaugeFlow QMS keeps inspections, "
            "FAI, calibration, and traceability tied to the job."
        )
