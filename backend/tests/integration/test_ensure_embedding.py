import pytest
from sqlalchemy import select, text

from bugflow.db.models import BugEmbedding
from bugflow.services.embeddings import ensure_embedding
from bugflow.services.errors import NotFoundError
from bugflow.services.llm_client import LlmError
from mocks.fake_openai_server import INVALID_KEY

pytestmark = pytest.mark.integration


def stored(session, bug_id):
    return session.execute(
        select(BugEmbedding.text_hash, BugEmbedding.embedded_at).where(
            BugEmbedding.bug_id == bug_id
        )
    ).one_or_none()


def update_bug(session, bug_id, **values):
    assignments = ", ".join(f"{name} = :{name}" for name in values)
    session.execute(text(f"UPDATE bugs SET {assignments} WHERE id = :id"), {**values, "id": bug_id})  # noqa: S608
    session.commit()


def test_missing_embedding_is_created(session, trio, llm_client, stand_in):
    assert ensure_embedding(session, llm_client, trio[0]) is True
    session.commit()
    row = session.get(BugEmbedding, trio[0])
    assert len(row.embedding) == 1536 and len(row.text_hash) == 64
    int(row.text_hash, 16)
    (request,) = stand_in.embedding_requests()
    assert request["inputs"] == 1


def test_unchanged_bug_is_left_untouched(session, trio_indexed, llm_client, stand_in):
    before = stored(session, trio_indexed[0])
    assert ensure_embedding(session, llm_client, trio_indexed[0]) is False
    assert stand_in.embedding_requests() == []
    assert stored(session, trio_indexed[0]) == before


def test_changed_title_is_re_embedded(session, trio_indexed, llm_client, stand_in):
    before = stored(session, trio_indexed[0])
    update_bug(session, trio_indexed[0], title="Checkout button broken")
    assert ensure_embedding(session, llm_client, trio_indexed[0]) is True
    after = stored(session, trio_indexed[0])
    assert after.text_hash != before.text_hash and after.embedded_at > before.embedded_at
    assert len(stand_in.embedding_requests()) == 1


def test_changed_environment_is_re_embedded(session, trio_indexed, llm_client):
    before = stored(session, trio_indexed[0])
    update_bug(session, trio_indexed[0], environment="staging")
    assert ensure_embedding(session, llm_client, trio_indexed[0]) is True
    assert stored(session, trio_indexed[0]).text_hash != before.text_hash


def test_non_text_changes_do_not_re_embed(session, trio_indexed, llm_client, stand_in):
    before = stored(session, trio_indexed[0])
    update_bug(session, trio_indexed[0], reporting_team="qa", status="processed")
    assert ensure_embedding(session, llm_client, trio_indexed[0]) is False
    assert stand_in.embedding_requests() == []
    assert stored(session, trio_indexed[0]).text_hash == before.text_hash


def test_unknown_bug(session, llm_client, stand_in):
    with pytest.raises(NotFoundError, match="^Bug 999999 not found$"):
        ensure_embedding(session, llm_client, 999999)
    assert stand_in.embedding_requests() == []


def test_provider_failure_leaves_nothing_behind(session, trio, make_llm_client):
    with pytest.raises(LlmError, match="^OpenAI authentication failed$"):
        ensure_embedding(session, make_llm_client(key=INVALID_KEY), trio[0])
    session.commit()
    assert stored(session, trio[0]) is None
