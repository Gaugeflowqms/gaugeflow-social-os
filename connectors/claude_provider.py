"""Claude (Anthropic) provider implementation."""
from __future__ import annotations

import logging

from config import CONFIG
from connectors.ai_provider import AIProvider

log = logging.getLogger(__name__)


class ClaudeProvider(AIProvider):
    name = "claude"

    def __init__(self) -> None:
        try:
            import anthropic  # type: ignore
        except ImportError as e:  # pragma: no cover
            raise RuntimeError(
                "anthropic package not installed. pip install anthropic"
            ) from e
        self._client = anthropic.Anthropic(api_key=CONFIG.anthropic_api_key)
        self._model = CONFIG.claude_model or "claude-3-5-sonnet-latest"

    def complete(
        self,
        system: str,
        user: str,
        max_tokens: int = 800,
        temperature: float = 0.7,
    ) -> str:
        try:
            msg = self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            parts = []
            for block in msg.content:
                if getattr(block, "type", "") == "text":
                    parts.append(block.text)
                elif isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
            return "\n".join(p for p in parts if p)
        except Exception as e:
            log.error("Claude error: %s", e)
            raise
