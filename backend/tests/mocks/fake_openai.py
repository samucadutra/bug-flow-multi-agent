"""Offline stand-ins for the OpenAI SDK client and the LLM probe."""

from __future__ import annotations

import httpx
import openai

from bugflow.services.health import (
    LLM_AUTH,
    LLM_CONNECTION,
    LLM_FAILED,
    LLM_TIMEOUT,
    LlmProbeError,
)

_REQUEST = httpx.Request("GET", "https://api.openai.test/v1/models/probe")


def authentication_error() -> openai.AuthenticationError:
    response = httpx.Response(401, request=_REQUEST)
    return openai.AuthenticationError("raw sdk text with sk-secret", response=response, body=None)


def connection_error() -> openai.APIConnectionError:
    return openai.APIConnectionError(message="raw connection text", request=_REQUEST)


def timeout_error() -> openai.APITimeoutError:
    return openai.APITimeoutError(request=_REQUEST)


class FakeModels:
    def __init__(self, error: Exception | None) -> None:
        self._error = error
        self.retrieved: list[str] = []

    def retrieve(self, model: str) -> object:
        self.retrieved.append(model)
        if self._error is not None:
            raise self._error
        return object()


class FakeOpenAIClient:
    """Callable like `openai.OpenAI`; records the constructor arguments it receives."""

    def __init__(self, error: Exception | None = None) -> None:
        self.models = FakeModels(error)
        self.init_kwargs: dict[str, object] = {}
        self.created = 0

    def __call__(self, **kwargs: object) -> FakeOpenAIClient:
        self.init_kwargs = kwargs
        self.created += 1
        return self


class FakeLlmProbe:
    """An `LlmProbe` that succeeds or fails with a fixed message and records its calls."""

    def __init__(self, message: str | None = None) -> None:
        self.message = message
        self.calls: list[dict[str, object]] = []

    @property
    def called(self) -> bool:
        return bool(self.calls)

    def check(self, *, api_key: str, model: str, timeout_seconds: float) -> None:
        self.calls.append({"api_key": api_key, "model": model, "timeout_seconds": timeout_seconds})
        if self.message is not None:
            raise LlmProbeError(self.message)

    @classmethod
    def succeeding(cls) -> FakeLlmProbe:
        return cls()

    @classmethod
    def authentication_failure(cls) -> FakeLlmProbe:
        return cls(LLM_AUTH)

    @classmethod
    def timeout(cls) -> FakeLlmProbe:
        return cls(LLM_TIMEOUT)

    @classmethod
    def connection_failure(cls) -> FakeLlmProbe:
        return cls(LLM_CONNECTION)

    @classmethod
    def failure(cls) -> FakeLlmProbe:
        return cls(LLM_FAILED)
