"""OpenAI provider implementation."""
from __future__ import annotations

import logging
from typing import Optional

from config import CONFIG
from connectors.ai_provider import AIProvider

log = logging.getLogger(__name__)


class OpenAIProvider(AIProvider):
    name = "openai"

    def __init__(self) -> None:
        try:
            from openai import OpenAI  # type: ignore
        except ImportError as e:  # pragma: no cover
            raise RuntimeError(
                "openai package not installed. pip install openai"
            ) from e
        self._client = OpenAI(api_key=CONFIG.openai_api_key)
        self._model = CONFIG.openai_model or "gpt-4.1-mini"

    def complete(
        self,
        system: str,
        user: str,
        max_tokens: int = 800,
        temperature: float = 0.7,
    ) -> str:
        try:
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            choice = resp.choices[0].message.content if resp.choices else ""
            return choice or ""
        except Exception as e:
            log.error("OpenAI error: %s", e)
            raise
