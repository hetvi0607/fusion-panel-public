"""Unified LLM client supporting Anthropic native and OpenAI-compatible APIs.

The wrapper exposes the same ``client.messages.create(...)`` surface used by
existing callers, normalising responses so downstream code can keep reading
``response.content[0].text`` and ``response.usage.input_tokens`` /
``response.usage.output_tokens`` regardless of provider.
"""
import logging
from typing import Any, Dict, List, Optional

from src.core.config import app_config

logger = logging.getLogger(__name__)


class _LLMResponseUsage:
    def __init__(self, input_tokens: int, output_tokens: int):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class _LLMResponseContent:
    def __init__(self, text: str):
        self.text = text


class _LLMResponse:
    def __init__(self, text: str, input_tokens: int, output_tokens: int):
        self.content = [_LLMResponseContent(text)]
        self.usage = _LLMResponseUsage(input_tokens, output_tokens)


class _MessagesProxy:
    """Provider-agnostic stand-in for Anthropic's ``messages`` namespace."""

    def __init__(self, client: "LLMClient"):
        self._client = client

    def create(
        self,
        *,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        system: Optional[str] = None,
        messages: Optional[List[Dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> _LLMResponse:
        """Call the configured provider and return a normalised response."""
        model = model or self._client.model
        messages = messages or []

        if self._client.provider == "anthropic":
            return self._create_anthropic(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
                **kwargs,
            )
        if self._client.provider == "openai":
            return self._create_openai(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
                **kwargs,
            )
        raise ValueError(f"Unsupported LLM provider: {self._client.provider}")

    def _create_anthropic(
        self,
        *,
        model: str,
        max_tokens: Optional[int],
        system: Optional[str],
        messages: List[Dict[str, Any]],
        **kwargs: Any,
    ) -> _LLMResponse:
        import anthropic

        call_kwargs: Dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            call_kwargs["system"] = system
        if kwargs:
            call_kwargs.update(kwargs)

        response = self._client._native_client.messages.create(**call_kwargs)

        text = response.content[0].text
        input_tokens = getattr(response.usage, "input_tokens", 0)
        output_tokens = getattr(response.usage, "output_tokens", 0)
        return _LLMResponse(text, input_tokens, output_tokens)

    def _create_openai(
        self,
        *,
        model: str,
        max_tokens: Optional[int],
        system: Optional[str],
        messages: List[Dict[str, Any]],
        **kwargs: Any,
    ) -> _LLMResponse:
        openai_messages: List[Dict[str, str]] = []
        if system:
            openai_messages.append({"role": "system", "content": system})
        openai_messages.extend(messages)

        call_kwargs: Dict[str, Any] = {
            "model": model,
            "messages": openai_messages,
        }
        if max_tokens is not None:
            call_kwargs["max_tokens"] = max_tokens
        if kwargs:
            call_kwargs.update(kwargs)

        response = self._client._native_client.chat.completions.create(**call_kwargs)

        text = ""
        choice = response.choices[0]
        message = getattr(choice, "message", None)
        if message is not None:
            text = getattr(message, "content", "") or ""
        else:
            text = getattr(choice, "text", "") or ""

        usage = getattr(response, "usage", None)
        if usage is not None:
            input_tokens = getattr(usage, "prompt_tokens", 0) or 0
            output_tokens = getattr(usage, "completion_tokens", 0) or 0
        else:
            # Some OpenAI-compatible proxies omit usage; estimate from length.
            input_tokens = sum(len(m.get("content", "")) for m in openai_messages) // 4
            output_tokens = len(text) // 4

        return _LLMResponse(text, int(input_tokens), int(output_tokens))


class LLMClient:
    """Provider-agnostic LLM client.

    Supports:
      - ``anthropic``  : native Anthropic Messages API (default).
      - ``openai``     : any OpenAI-compatible endpoint (Groq, Cerebras,
                         OpenRouter, local vLLM, etc.). Set ``LLM_BASE_URL``
                         to point at the provider's base URL.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self.provider = (provider or app_config.LLM_PROVIDER or "anthropic").lower()
        self.api_key = api_key or app_config.LLM_API_KEY or app_config.CLAUDE_API_KEY or ""
        self.model = model or app_config.LLM_MODEL or app_config.CLAUDE_MODEL or ""
        self.base_url = base_url or app_config.LLM_BASE_URL or ""

        if not self.api_key:
            raise ValueError(
                "LLM API key is required. Configure it in Settings or set "
                "LLM_API_KEY / CLAUDE_API_KEY in the environment."
            )
        if not self.model:
            raise ValueError(
                "LLM model is required. Configure it in Settings or set "
                "LLM_MODEL / CLAUDE_MODEL in the environment."
            )

        if self.provider == "anthropic":
            import anthropic

            self._native_client = anthropic.Anthropic(api_key=self.api_key)
        elif self.provider == "openai":
            import openai

            client_kwargs: Dict[str, Any] = {"api_key": self.api_key}
            if self.base_url:
                client_kwargs["base_url"] = self.base_url
            self._native_client = openai.OpenAI(**client_kwargs)
        else:
            raise ValueError(
                f"Unsupported LLM provider '{self.provider}'. "
                "Use 'anthropic' or 'openai'."
            )

        logger.info(f"LLMClient initialised ({self.provider}, model={self.model})")

    @property
    def messages(self) -> _MessagesProxy:
        return _MessagesProxy(self)
