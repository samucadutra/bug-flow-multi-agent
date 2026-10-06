import pytest

from bugflow.services.health import LlmProbeError, OpenAILlmProbe
from mocks.fake_openai import (
    FakeOpenAIClient,
    authentication_error,
    connection_error,
    timeout_error,
)

KEY = "sk-test-canary-1234567890abcdef"


def run(client: FakeOpenAIClient) -> None:
    OpenAILlmProbe(client).check(api_key=KEY, model="gpt-test", timeout_seconds=7)


def test_success_looks_up_the_configured_model_once_without_retries():
    client = FakeOpenAIClient()
    run(client)
    assert client.models.retrieved == ["gpt-test"]
    assert client.init_kwargs == {"api_key": KEY, "timeout": 7, "max_retries": 0}


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (authentication_error(), "OpenAI authentication failed"),
        (connection_error(), "Cannot reach the OpenAI API"),
        (timeout_error(), "OpenAI request timed out"),
        (RuntimeError(f"boom {KEY}"), "OpenAI request failed"),
    ],
)
def test_sdk_errors_map_to_fixed_messages(error, message):
    with pytest.raises(LlmProbeError) as caught:
        run(FakeOpenAIClient(error))
    assert caught.value.message == message
    assert KEY not in str(caught.value) and "raw" not in str(caught.value)
    assert caught.value.__cause__ is None and caught.value.__suppress_context__
