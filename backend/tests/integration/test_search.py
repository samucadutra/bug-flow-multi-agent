import pytest

from bugflow.services.errors import EmptySearchTextError, ValidationFailedError
from bugflow.services.llm_client import LlmError
from bugflow.services.similarity import search_similar
from mocks.fake_openai_server import INVALID_KEY

pytestmark = pytest.mark.integration


def descending(items):
    scores = [item.score for item in items]
    return all(a >= b for a, b in zip(scores, scores[1:], strict=False))


def test_default_limit(session, seed_indexed, llm_client):
    result = search_similar(session, lambda: llm_client, "button does nothing")
    assert len(result.items) == 5 and result.hint == ""
    assert all(i.bug_id and i.title and i.status for i in result.items)
    assert descending(result.items)
    assert all(-1 <= i.score <= 1 for i in result.items)


def test_maximum_limit(session, seed_indexed, llm_client):
    result = search_similar(session, lambda: llm_client, "button does nothing", 20)
    assert len(result.items) == 20 and descending(result.items)


@pytest.mark.parametrize("limit", [21, 0])
def test_limit_out_of_range_rejected_without_request(
    session, seed_indexed, llm_client, stand_in, limit
):
    with pytest.raises(ValidationFailedError) as caught:
        search_similar(session, lambda: llm_client, "button does nothing", limit)
    assert [(e.field, e.message) for e in caught.value.field_errors] == [
        ("limit", "must be between 1 and 20")
    ]
    assert stand_in.embedding_requests() == []


def test_most_similar_first(session, trio_indexed, llm_client):
    result = search_similar(session, lambda: llm_client, "checkout button")
    assert [i.title for i in result.items] == [
        "Checkout button unresponsive",
        "Checkout page layout broken",
        "Nightly report timeout",
    ]


def test_empty_text_refused(session, initialized_db, llm_client, stand_in):
    with pytest.raises(EmptySearchTextError, match="^Search text must not be empty$"):
        search_similar(session, lambda: llm_client, "   ")
    assert stand_in.embedding_requests() == []


def test_nothing_indexed(session, seeded_db, llm_client, stand_in):
    result = search_similar(session, lambda: llm_client, "anything")
    assert result.items == [] and result.hint == "No bugs are indexed; run index"
    assert stand_in.embedding_requests() == []


def test_over_long_text_refused(session, seed_indexed, llm_client, stand_in):
    with pytest.raises(ValidationFailedError) as caught:
        search_similar(session, lambda: llm_client, "a" * 501)
    assert [e.field for e in caught.value.field_errors] == ["text"]
    assert stand_in.embedding_requests() == []


def test_invalid_key(session, seed_indexed, make_llm_client):
    client = make_llm_client(key=INVALID_KEY)
    with pytest.raises(LlmError) as caught:
        search_similar(session, lambda: client, "button does nothing")
    assert str(caught.value) == "OpenAI authentication failed"
    assert INVALID_KEY not in str(caught.value)
