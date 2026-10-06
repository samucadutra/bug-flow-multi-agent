"""CrewAI adapter over the shared LLM client.

CrewAI wraps every `BaseLLM.call` with its own retry (up to three attempts) when an error, or
any error in its cause or context chain, looks like a rate limit: an error text with markers
such as "rate limit", a `code` or `status_code` attribute, or a rate-limit class name. The
shared client already retries, so the adapter raises a neutral `AgentCallError` outside of any
`except` block (so it has no `__context__`), whose text and attributes carry none of those
markers. The original fixed message stays in `.llm_message`.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

from crewai import Crew
from crewai.llms.base_llm import BaseLLM
from pydantic import PrivateAttr

from bugflow.agents.errors import AgentCallError
from bugflow.services import llm_client
from bugflow.services.llm_client import LlmError

AGENT_TEMPERATURE = 0.0

_REASONS = {
    llm_client.LLM_AUTH: "auth",
    llm_client.LLM_RATE_LIMIT: "rate_limited",
    llm_client.LLM_UNAVAILABLE: "unavailable",
    llm_client.LLM_CONNECTION: "connection",
    llm_client.LLM_TIMEOUT: "timeout",
    llm_client.LLM_FAILED: "failed",
}


class ChatClient(Protocol):
    def chat(
        self, messages: Sequence[dict[str, str]], *, temperature: float = ..., json_mode: bool = ...
    ) -> str: ...


def to_chat_messages(messages: str | Sequence[Any]) -> list[dict[str, str]]:
    """Convert CrewAI messages (a string or role/content dictionaries) to chat messages."""
    if isinstance(messages, str):
        return [{"role": "user", "content": messages}]
    converted: list[dict[str, str]] = []
    for message in messages:
        content = message["content"]
        if not isinstance(content, str):
            raise ValueError("Only text messages are supported")
        converted.append({"role": str(message["role"]), "content": content})
    return converted


class BugflowCrewLlm(BaseLLM):
    """A `BaseLLM` that delegates to the shared client in JSON mode at temperature 0.0."""

    llm_type: str = "bugflow"
    client: Any = None

    def call(  # type: ignore[override]
        self,
        messages: str | list[Any],
        tools: list[Any] | None = None,
        callbacks: list[Any] | None = None,
        available_functions: dict[str, Any] | None = None,
        from_task: Any = None,
        from_agent: Any = None,
        response_model: Any = None,
    ) -> str:
        failure: LlmError | None = None
        try:
            return self.client.chat(
                to_chat_messages(messages), temperature=AGENT_TEMPERATURE, json_mode=True
            )
        except LlmError as exc:
            failure = exc
        # Raised outside the `except` block on purpose: no `__context__` may expose the cause.
        reason = _REASONS.get(failure.message, "failed")
        raise AgentCallError(reason, failure.message)

    def supports_function_calling(self) -> bool:
        return False

    def supports_stop_words(self) -> bool:
        return False

    def get_context_window_size(self) -> int:
        return 128_000


class NullTaskOutputStorage:
    """Replaces CrewAI's task-output storage so nothing is written to the user's data directory."""

    def update(self, task_index: int, log: dict[str, Any]) -> None:
        return None

    def add(self, *args: Any, **kwargs: Any) -> None:
        return None

    def reset(self) -> None:
        return None

    def load(self) -> list[dict[str, Any]]:
        return []


class OneShotCrew(Crew):
    """A crew that keeps no kickoff history on disk."""

    _task_output_handler: Any = PrivateAttr(default_factory=NullTaskOutputStorage)
