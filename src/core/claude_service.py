"""Shared Claude API client with JSON parsing, retries, and usage tracking."""

import json
import logging
import time
from typing import Any, Dict, Optional

import anthropic

from src.core.config import app_config

logger = logging.getLogger(__name__)


class ClaudeService:
    """Small, reusable wrapper around the Anthropic Messages API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        client: Any = None,
    ):
        self.api_key = api_key or app_config.CLAUDE_API_KEY
        if client is None and not self.api_key:
            raise ValueError("Claude API key is required. Set CLAUDE_API_KEY in .env.")

        self.client = client or anthropic.Anthropic(api_key=self.api_key)
        self.model = model or app_config.CLAUDE_MODEL
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    def generate_json(
        self,
        *,
        system: str,
        prompt: str,
        max_tokens: int = 5000,
        attempts: int = 2,
    ) -> Dict[str, Any]:
        """Generate and parse one JSON object, retrying malformed responses."""
        last_error = None
        for attempt in range(1, attempts + 1):
            try:
                message = self.client.messages.create(
                    model=self.model,
                    max_tokens=min(max_tokens, app_config.AI_MAX_TOKENS),
                    system=system,
                    messages=[{"role": "user", "content": prompt}],
                )
                self._track_usage(message)
                text = self._extract_text(message)
                parsed = self._parse_json_object(text)
                if not isinstance(parsed, dict):
                    raise ValueError("Claude response must be a JSON object")
                return parsed
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Claude JSON request attempt %s/%s failed: %s",
                    attempt,
                    attempts,
                    exc,
                )
                if attempt < attempts:
                    time.sleep(attempt)

        raise RuntimeError(f"Claude could not return valid structured content: {last_error}")

    def _track_usage(self, message: Any) -> None:
        usage = getattr(message, "usage", None)
        self.total_input_tokens += int(getattr(usage, "input_tokens", 0) or 0)
        self.total_output_tokens += int(getattr(usage, "output_tokens", 0) or 0)

    @staticmethod
    def _extract_text(message: Any) -> str:
        content = getattr(message, "content", None)
        if not content:
            raise ValueError("Claude returned no content")

        first = content[0]
        text = getattr(first, "text", None)
        if text is None and isinstance(first, dict):
            text = first.get("text")
        if not text:
            raise ValueError("Claude returned no text content")
        return str(text).strip()

    @staticmethod
    def _parse_json_object(text: str) -> Dict[str, Any]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else ""
            if cleaned.rstrip().endswith("```"):
                cleaned = cleaned.rstrip()[:-3].rstrip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            start = cleaned.find("{")
            if start == -1:
                raise ValueError("Claude response did not contain a JSON object")
            decoder = json.JSONDecoder()
            obj, _ = decoder.raw_decode(cleaned[start:])
            return obj

    def get_usage_stats(self) -> Dict[str, Any]:
        input_cost = (
            self.total_input_tokens
            / 1_000_000
            * app_config.CLAUDE_INPUT_COST_PER_MILLION
        )
        output_cost = (
            self.total_output_tokens
            / 1_000_000
            * app_config.CLAUDE_OUTPUT_COST_PER_MILLION
        )
        return {
            "input_tokens": self.total_input_tokens,
            "output_tokens": self.total_output_tokens,
            "total_tokens": self.total_input_tokens + self.total_output_tokens,
            "estimated_cost": input_cost + output_cost,
        }
