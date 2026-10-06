"""The wrapper against the local OpenAI stand-in."""

from __future__ import annotations

import socket
import time

import pytest

from bugflow.services.llm_client import LlmError, OpenAILlmClient
from mocks.fake_openai_server import CHAT_REPLY, INVALID_KEY, VALID_KEY

pytestmark = pytest.mark.integration


def make_client(stand_in, *, key=VALID_KEY, timeout=60, retries=2, base_url=None, sleep=None):
    kwargs = {"sleep": sleep} if sleep else {}
    return OpenAILlmClient(
        key,
        base_url=base_url or stand_in.base_url,
        timeout_seconds=timeout,
        max_retries=retries,
        embedding_model="text-embedding-3-small",
        chat_model="gpt-4o-mini",
        **kwargs,
    )


def test_embed_request_and_vectors(stand_in):
    vectors = make_client(stand_in).embed(["alpha", "beta", "gamma"])
    assert len(vectors) == 3 and all(len(v) == 1536 for v in vectors)
    (request,) = stand_in.embedding_requests()
    assert request["model"] == "text-embedding-3-small" and request["inputs"] == 3
    assert request["key_accepted"] is True


def test_rate_limit_is_retried(stand_in):
    stand_in.script([{"status": 429}])
    assert len(make_client(stand_in, sleep=lambda _: None).embed(["alpha"])) == 1
    assert len(stand_in.embedding_requests()) == 2


def test_rate_limit_retries_are_bounded_and_back_off(stand_in):
    stand_in.script([{"status": 429}] * 3)
    started = time.monotonic()
    with pytest.raises(LlmError, match="^OpenAI rate limit exceeded$"):
        make_client(stand_in).embed(["alpha"])
    assert time.monotonic() - started >= 1.5
    assert len(stand_in.embedding_requests()) == 3


def test_server_errors_are_retried_then_reported(stand_in):
    stand_in.script([{"status": 503}] * 3)
    with pytest.raises(LlmError, match="^OpenAI service unavailable$"):
        make_client(stand_in, sleep=lambda _: None).embed(["alpha"])
    assert len(stand_in.embedding_requests()) == 3


def test_invalid_key_is_not_retried(stand_in):
    with pytest.raises(LlmError) as caught:
        make_client(stand_in, key=INVALID_KEY).embed(["alpha"])
    assert str(caught.value) == "OpenAI authentication failed"
    assert INVALID_KEY not in str(caught.value)
    assert len(stand_in.embedding_requests()) == 1


def test_rejected_request_is_not_retried(stand_in):
    stand_in.script([{"status": 400}])
    with pytest.raises(LlmError, match="^OpenAI request failed$"):
        make_client(stand_in).embed(["alpha"])
    assert len(stand_in.embedding_requests()) == 1


def test_timeout(stand_in):
    stand_in.script([{"delay": 3}])
    with pytest.raises(LlmError, match="^OpenAI request timed out$"):
        make_client(stand_in, timeout=1, retries=0).embed(["alpha"])
    assert len(stand_in.embedding_requests()) == 1


def test_unreachable_service(stand_in):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    client = make_client(stand_in, retries=0, base_url=f"http://127.0.0.1:{port}/v1")
    with pytest.raises(LlmError, match="^Cannot reach the OpenAI API$"):
        client.embed(["alpha"])


def test_unexpected_vector_size(stand_in):
    stand_in.script([{"wrong_size": True}])
    with pytest.raises(LlmError, match="^OpenAI returned an unexpected embedding size$"):
        make_client(stand_in).embed(["alpha"])
    assert len(stand_in.embedding_requests()) == 1


def test_chat_reply_model_and_temperature(stand_in):
    assert make_client(stand_in).chat([{"role": "user", "content": "hello"}]) == CHAT_REPLY
    (request,) = stand_in.chat_requests()
    assert request["model"] == "gpt-4o-mini" and request["temperature"] <= 0.2


def test_high_temperature_refused_without_request(stand_in):
    with pytest.raises(ValueError):
        make_client(stand_in).chat([{"role": "user", "content": "hello"}], temperature=0.5)
    assert stand_in.chat_requests() == []
