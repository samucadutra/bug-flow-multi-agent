"""Shared LLM client: embeddings and chat with a timeout, bounded retry and fixed error text.

The wrapper is independent of the database so every feature that calls OpenAI gets the same
retry and timeout behavior. Error messages are fixed English text; SDK text and keys are never
copied into them.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from typing import Any

import openai

from bugflow.config import Settings
from bugflow.db.models import EMBEDDING_DIMENSIONS
from bugflow.services.errors import ServiceError

KEY_MISSING = "OPENAI_API_KEY is not set"
LLM_AUTH = "OpenAI authentication failed"
LLM_RATE_LIMIT = "OpenAI rate limit exceeded"
LLM_UNAVAILABLE = "OpenAI service unavailable"
LLM_CONNECTION = "Cannot reach the OpenAI API"
LLM_TIMEOUT = "OpenAI request timed out"
LLM_FAILED = "OpenAI request failed"
LLM_EMBEDDING_SIZE = "OpenAI returned an unexpected embedding size"

MAX_CHAT_TEMPERATURE = 0.2
BACKOFF_START_SECONDS = 0.5


class LlmError(ServiceError):
    """A provider failure with a fixed, secret-free message."""


class _Retryable(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _classify(exc: Exception) -> Exception:
    """Map an SDK exception to `_Retryable` (transient) or `LlmError` (final)."""
    if isinstance(exc, openai.AuthenticationError):
        return LlmError(LLM_AUTH)
    if isinstance(exc, openai.RateLimitError):
        return _Retryable(LLM_RATE_LIMIT)
    if isinstance(exc, openai.APITimeoutError):
        return _Retryable(LLM_TIMEOUT)
    if isinstance(exc, openai.APIConnectionError):
        return _Retryable(LLM_CONNECTION)
    if isinstance(exc, openai.APIStatusError):
        if exc.status_code >= 500:
            return _Retryable(LLM_UNAVAILABLE)
        return LlmError(LLM_FAILED)
    return LlmError(LLM_FAILED)


class OpenAILlmClient:
    """Embeds texts and runs chat completions with `1 + max_retries` attempts per call."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str | None = None,
        timeout_seconds: float,
        max_retries: int,
        embedding_model: str,
        chat_model: str,
        sleep: Callable[[float], None] = time.sleep,
        client_factory: Callable[..., Any] | None = None,
    ) -> None:
        factory = client_factory or openai.OpenAI
        kwargs: dict[str, Any] = {
            "api_key": api_key,
            "timeout": timeout_seconds,
            "max_retries": 0,
        }
        if base_url is not None:
            kwargs["base_url"] = base_url
        self._client = factory(**kwargs)
        self._max_retries = max_retries
        self._sleep = sleep
        self.embedding_model = embedding_model
        self.chat_model = chat_model

    @classmethod
    def from_settings(cls, settings: Settings, **overrides: Any) -> OpenAILlmClient:
        return cls(
            settings.require_openai_key(),
            timeout_seconds=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
            embedding_model=settings.openai_embedding_model,
            chat_model=settings.openai_model,
            **overrides,
        )

    def _call(self, request: Callable[[], Any]) -> Any:
        delay = BACKOFF_START_SECONDS
        attempts = 1 + self._max_retries
        for attempt in range(1, attempts + 1):
            try:
                return request()
            except Exception as exc:
                failure = _classify(exc)
                if isinstance(failure, LlmError):
                    raise failure from None
                if attempt == attempts:
                    raise LlmError(failure.message) from None
            self._sleep(delay)
            delay *= 2
        raise LlmError(LLM_FAILED)  # pragma: no cover

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """One request for all texts; vectors come back in input order."""
        if not texts:
            return []
        response = self._call(
            lambda: self._client.embeddings.create(
                model=self.embedding_model, input=list(texts), encoding_format="float"
            )
        )
        items = sorted(response.data, key=lambda item: item.index)
        if len(items) != len(texts):
            raise LlmError(LLM_FAILED)
        vectors = [[float(value) for value in item.embedding] for item in items]
        if any(len(vector) != EMBEDDING_DIMENSIONS for vector in vectors):
            raise LlmError(LLM_EMBEDDING_SIZE)
        return vectors

    def chat(self, messages: Sequence[dict[str, str]], *, temperature: float = 0.0) -> str:
        """One chat completion; a temperature above 0.2 is refused before any request."""
        if temperature > MAX_CHAT_TEMPERATURE:
            raise ValueError(f"Temperature must not exceed {MAX_CHAT_TEMPERATURE}")
        response = self._call(
            lambda: self._client.chat.completions.create(
                model=self.chat_model, messages=list(messages), temperature=temperature
            )
        )
        try:
            content = response.choices[0].message.content
        except (AttributeError, IndexError, TypeError):
            raise LlmError(LLM_FAILED) from None
        if content is None:
            raise LlmError(LLM_FAILED)
        return str(content)
