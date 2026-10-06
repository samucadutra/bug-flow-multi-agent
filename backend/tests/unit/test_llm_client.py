import httpx2 as httpx
import openai
import pytest

from bugflow.config import ConfigError
from bugflow.services.errors import ServiceError
from bugflow.services.llm_client import LlmError, OpenAILlmClient

KEY = "sk-test-canary-1234567890abcdef"
RAW = "raw sdk text"
_REQUEST = httpx.Request("POST", "https://api.openai.test/v1/embeddings")


def status_error(cls, status):
    return cls(f"{RAW} {KEY}", response=httpx.Response(status, request=_REQUEST), body=None)


def rate_limit():
    return status_error(openai.RateLimitError, 429)


def server_error():
    return status_error(openai.InternalServerError, 503)


def bad_request():
    return status_error(openai.BadRequestError, 400)


def auth_error():
    return status_error(openai.AuthenticationError, 401)


def connection_error():
    return openai.APIConnectionError(message=RAW, request=_REQUEST)


def timeout_error():
    return openai.APITimeoutError(request=_REQUEST)


class Item:
    def __init__(self, index, embedding):
        self.index = index
        self.embedding = embedding


class Embeddings:
    def __init__(self, outcomes, size=1536):
        self.outcomes = list(outcomes)
        self.calls = []
        self.size = size

    def create(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0) if self.outcomes else None
        if isinstance(outcome, Exception):
            raise outcome
        data = [Item(i, [0.1] * self.size) for i in range(len(kwargs["input"]))]
        data.reverse()
        return type("R", (), {"data": data})()


class Completions:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        message = type("M", (), {"content": "reply"})()
        return type("R", (), {"choices": [type("C", (), {"message": message})()]})()


class FakeSdk:
    def __init__(self, outcomes=(), size=1536):
        self.embeddings = Embeddings(outcomes, size)
        self.chat = type("Chat", (), {"completions": Completions()})()
        self.init_kwargs = None

    def factory(self, **kwargs):
        self.init_kwargs = kwargs
        return self


def build(sdk, retries=2, sleeps=None):
    sleeps = sleeps if sleeps is not None else []
    return OpenAILlmClient(
        KEY,
        timeout_seconds=7,
        max_retries=retries,
        embedding_model="embed-model",
        chat_model="chat-model",
        sleep=sleeps.append,
        client_factory=sdk.factory,
    )


def test_embed_returns_vectors_in_order():
    sdk = FakeSdk()
    vectors = build(sdk).embed(["a", "b", "c"])
    assert len(vectors) == 3 and all(len(v) == 1536 for v in vectors)
    assert len(sdk.embeddings.calls) == 1
    assert sdk.embeddings.calls[0]["model"] == "embed-model"
    assert sdk.embeddings.calls[0]["input"] == ["a", "b", "c"]


def test_embed_of_nothing_makes_no_request():
    sdk = FakeSdk()
    assert build(sdk).embed([]) == []
    assert sdk.embeddings.calls == []


def test_sdk_retries_disabled_and_timeout_passed():
    sdk = FakeSdk()
    build(sdk)
    assert sdk.init_kwargs["max_retries"] == 0 and sdk.init_kwargs["timeout"] == 7
    assert "base_url" not in sdk.init_kwargs


def test_explicit_base_url_is_passed():
    sdk = FakeSdk()
    OpenAILlmClient(
        KEY,
        base_url="http://127.0.0.1:1/v1",
        timeout_seconds=1,
        max_retries=0,
        embedding_model="e",
        chat_model="c",
        client_factory=sdk.factory,
    )
    assert sdk.init_kwargs["base_url"] == "http://127.0.0.1:1/v1"


@pytest.mark.parametrize(
    ("make", "message"),
    [
        (rate_limit, "OpenAI rate limit exceeded"),
        (server_error, "OpenAI service unavailable"),
        (connection_error, "Cannot reach the OpenAI API"),
        (timeout_error, "OpenAI request timed out"),
    ],
)
def test_transient_errors_are_retried_up_to_the_limit(make, message):
    sdk = FakeSdk([make(), make(), make(), make()])
    with pytest.raises(LlmError) as caught:
        build(sdk, retries=2).embed(["a"])
    assert str(caught.value) == message and isinstance(caught.value, ServiceError)
    assert len(sdk.embeddings.calls) == 3


def test_backoff_delays():
    sleeps = []
    sdk = FakeSdk([rate_limit(), rate_limit(), rate_limit()])
    with pytest.raises(LlmError):
        build(sdk, retries=2, sleeps=sleeps).embed(["a"])
    assert sleeps == [0.5, 1.0]


def test_success_after_a_retry():
    sdk = FakeSdk([rate_limit()])
    assert len(build(sdk).embed(["a"])) == 1
    assert len(sdk.embeddings.calls) == 2


def test_authentication_error_not_retried():
    sdk = FakeSdk([auth_error()])
    with pytest.raises(LlmError) as caught:
        build(sdk).embed(["a"])
    assert str(caught.value) == "OpenAI authentication failed" and KEY not in str(caught.value)
    assert len(sdk.embeddings.calls) == 1


def test_other_client_errors_not_retried():
    sdk = FakeSdk([bad_request()])
    with pytest.raises(LlmError, match="^OpenAI request failed$"):
        build(sdk).embed(["a"])
    assert len(sdk.embeddings.calls) == 1


def test_unknown_exception_is_a_generic_failure():
    sdk = FakeSdk([RuntimeError(KEY)])
    with pytest.raises(LlmError, match="^OpenAI request failed$"):
        build(sdk).embed(["a"])


def test_wrong_vector_size_rejected():
    sdk = FakeSdk(size=3)
    with pytest.raises(LlmError, match="^OpenAI returned an unexpected embedding size$"):
        build(sdk).embed(["a"])
    assert len(sdk.embeddings.calls) == 1


def test_chat_temperature_guard():
    sdk = FakeSdk()
    with pytest.raises(ValueError):
        build(sdk).chat([{"role": "user", "content": "hi"}], temperature=0.3)
    assert sdk.chat.completions.calls == []


def test_chat_returns_text_with_default_temperature():
    sdk = FakeSdk()
    assert build(sdk).chat([{"role": "user", "content": "hi"}]) == "reply"
    call = sdk.chat.completions.calls[0]
    assert call["temperature"] == 0.0 and call["model"] == "chat-model"


def test_from_settings_requires_key(make_settings):
    with pytest.raises(ConfigError) as caught:
        OpenAILlmClient.from_settings(make_settings())
    assert str(caught.value) == "OPENAI_API_KEY is not set"


def test_from_settings_uses_settings_values(make_settings):
    sdk = FakeSdk()
    settings = make_settings(
        OPENAI_API_KEY=KEY,
        LLM_TIMEOUT_SECONDS="9",
        LLM_MAX_RETRIES="1",
        OPENAI_EMBEDDING_MODEL="emb",
        OPENAI_MODEL="chat",
    )
    client = OpenAILlmClient.from_settings(settings, client_factory=sdk.factory)
    assert sdk.init_kwargs["timeout"] == 9 and sdk.init_kwargs["api_key"] == KEY
    assert (client.embedding_model, client.chat_model) == ("emb", "chat")


@pytest.mark.parametrize("make", [rate_limit, server_error, connection_error, auth_error])
def test_error_messages_never_contain_key_or_sdk_text(make):
    sdk = FakeSdk([make()] * 5)
    with pytest.raises(LlmError) as caught:
        build(sdk).embed(["a"])
    assert KEY not in str(caught.value) and RAW not in str(caught.value)
    assert caught.value.__cause__ is None
