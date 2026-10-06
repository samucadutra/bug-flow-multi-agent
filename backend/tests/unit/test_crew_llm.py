import logging

import pytest

from bugflow.agents.crew_llm import (
    AGENT_TEMPERATURE,
    AgentCallError,
    BugflowCrewLlm,
    to_chat_messages,
)
from bugflow.agents.outputs import AGENTS
from bugflow.agents.runtime import run_agent
from bugflow.config import THIRD_PARTY_RUNTIME_FLAGS
from bugflow.services import llm_client
from bugflow.services.llm_client import LlmError

MARKERS = ("rate limit", "rate-limit", "too many requests", "throttled", "resource exhausted")
REPLY = '{"component": "backend", "justification": "j"}'


class FakeClient:
    chat_model = "gpt-4o-mini"

    def __init__(self, reply=REPLY, error=None):
        self.reply = reply
        self.error = error
        self.calls = []

    def chat(self, messages, *, temperature=0.0, json_mode=False):
        self.calls.append({"messages": messages, "temperature": temperature, "json": json_mode})
        if self.error is not None:
            raise LlmError(self.error)
        return self.reply


def test_string_and_list_messages_convert():
    assert to_chat_messages("hello") == [{"role": "user", "content": "hello"}]
    messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "u", "x": 1}]
    assert to_chat_messages(messages) == [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "u"},
    ]
    with pytest.raises(ValueError):
        to_chat_messages([{"role": "user", "content": [{"type": "image"}]}])


def test_call_uses_json_mode_and_temperature_zero():
    client = FakeClient()
    llm = BugflowCrewLlm(model="gpt-4o-mini", client=client)
    assert llm.call("hi") == REPLY
    assert client.calls == [
        {
            "messages": [{"role": "user", "content": "hi"}],
            "temperature": AGENT_TEMPERATURE,
            "json": True,
        }
    ]
    assert AGENT_TEMPERATURE == 0.0
    assert llm.supports_function_calling() is False and llm.supports_stop_words() is False


@pytest.mark.parametrize(
    ("message", "reason"),
    [
        (llm_client.LLM_AUTH, "auth"),
        (llm_client.LLM_RATE_LIMIT, "rate_limited"),
        (llm_client.LLM_UNAVAILABLE, "unavailable"),
        (llm_client.LLM_CONNECTION, "connection"),
        (llm_client.LLM_TIMEOUT, "timeout"),
        (llm_client.LLM_FAILED, "failed"),
        ("anything else", "failed"),
    ],
)
def test_llm_errors_map_to_neutral_agent_errors(message, reason):
    llm = BugflowCrewLlm(model="m", client=FakeClient(error=message))
    with pytest.raises(AgentCallError) as caught:
        llm.call("hi")
    error = caught.value
    assert str(error) == f"LLM call failed ({reason})" and error.reason == reason
    assert error.llm_message == message
    assert not any(marker in str(error).lower() for marker in MARKERS)
    assert not hasattr(error, "code") and not hasattr(error, "status_code")
    assert error.__cause__ is None and error.__context__ is None


def test_one_agent_crew_makes_exactly_one_call_and_returns_raw_text():
    client = FakeClient()
    assert run_agent(AGENTS[0], "PROMPT BODY", client) == REPLY
    assert len(client.calls) == 1
    system, user = client.calls[0]["messages"]
    assert system["role"] == "system" and system["content"].startswith(
        "You are Component Classifier."
    )
    assert "PROMPT BODY" in user["content"]
    assert client.calls[0]["json"] is True and client.calls[0]["temperature"] == 0.0


@pytest.mark.parametrize("message", [llm_client.LLM_RATE_LIMIT, llm_client.LLM_UNAVAILABLE])
def test_failing_client_raises_once_without_crewai_retry(message):
    client = FakeClient(error=message)
    with pytest.raises(AgentCallError) as caught:
        run_agent(AGENTS[0], "P", client)
    assert caught.value.llm_message == message
    assert len(client.calls) == 1


def test_crewai_logging_stays_quiet(capsys):
    client = FakeClient(error=llm_client.LLM_RATE_LIMIT)
    with pytest.raises(AgentCallError):
        run_agent(AGENTS[0], "P", client)
    captured = capsys.readouterr()
    assert "Error executing listener" not in captured.err + captured.out
    assert logging.getLogger("crewai").propagate is False


def test_runtime_flags_are_set_without_overriding(monkeypatch):
    from bugflow.config import configure_third_party_runtime

    for name in THIRD_PARTY_RUNTIME_FLAGS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("CREWAI_TRACING_ENABLED", "true")
    configure_third_party_runtime()
    import os

    assert os.environ["OTEL_SDK_DISABLED"] == "true"
    assert os.environ["CREWAI_DISABLE_VERSION_CHECK"] == "true"
    assert os.environ["CREWAI_TRACING_ENABLED"] == "true"
