import pytest
from sqlalchemy import text

from bugflow.db.models import BugEmbedding
from bugflow.services.errors import NotFoundError, ValidationFailedError
from bugflow.services.similarity import similar_to_bug

pytestmark = pytest.mark.integration

B_TITLE, C_TITLE = "Nightly report timeout", "Checkout page layout broken"


def test_the_bug_itself_is_excluded(session, trio_indexed, llm_client):
    items = similar_to_bug(session, lambda: llm_client, trio_indexed[0])
    assert [i.title for i in items] == [C_TITLE, B_TITLE]
    assert trio_indexed[0] not in [i.bug_id for i in items]


def test_no_other_bug_is_indexed(session, trio, llm_client):
    from bugflow.services.embeddings import ensure_embedding

    ensure_embedding(session, llm_client, trio[0])
    session.commit()
    assert similar_to_bug(session, lambda: llm_client, trio[0]) == []


def test_limit_above_the_maximum(session, trio_indexed, llm_client):
    with pytest.raises(ValidationFailedError) as caught:
        similar_to_bug(session, lambda: llm_client, trio_indexed[0], 21)
    assert [e.field for e in caught.value.field_errors] == ["limit"]


def test_limit_of_one(session, trio_indexed, llm_client):
    items = similar_to_bug(session, lambda: llm_client, trio_indexed[0], 1)
    assert [i.title for i in items] == [C_TITLE]


def test_own_stale_embedding_is_refreshed_first(session, trio_indexed, llm_client, stand_in):
    before = session.get(BugEmbedding, trio_indexed[0]).text_hash
    session.execute(
        text("UPDATE bugs SET title = 'Checkout button broken' WHERE id = :id"),
        {"id": trio_indexed[0]},
    )
    session.commit()
    items = similar_to_bug(session, lambda: llm_client, trio_indexed[0])
    assert session.get(BugEmbedding, trio_indexed[0], populate_existing=True).text_hash != before
    assert len(stand_in.embedding_requests()) == 1 and len(items) == 2


def test_unindexed_bugs_are_not_returned(session, trio, llm_client):
    from bugflow.services.embeddings import ensure_embedding

    ensure_embedding(session, llm_client, trio[0])
    ensure_embedding(session, llm_client, trio[1])
    session.commit()
    items = similar_to_bug(session, lambda: llm_client, trio[0])
    assert [i.bug_id for i in items] == [trio[1]]


def test_unknown_bug(session, initialized_db, llm_client):
    with pytest.raises(NotFoundError, match="^Bug 999999 not found$"):
        similar_to_bug(session, lambda: llm_client, 999999)
