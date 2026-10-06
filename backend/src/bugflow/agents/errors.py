"""Agent errors that do not depend on CrewAI, so services can import them cheaply."""

from __future__ import annotations


class AgentCallError(Exception):
    """A failed agent call with a neutral message and the original fixed text.

    The message is `LLM call failed (<reason>)` and never contains the wording CrewAI treats as a
    rate limit; the error has no `code` or `status_code` attribute. The original fixed provider
    message is kept in `.llm_message`.
    """

    def __init__(self, reason: str, llm_message: str) -> None:
        super().__init__(f"LLM call failed ({reason})")
        self.reason = reason
        self.llm_message = llm_message
