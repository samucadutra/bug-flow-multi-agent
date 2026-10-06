import pytest
from sqlalchemy import select

from bugflow.db.engine import session_factory
from bugflow.db.models import BugEmbedding
from bugflow.services.embeddings import index_all_bugs
from bugflow.services.llm_client import LlmError
from tests_helpers import add_numbered

pytestmark = pytest.mark.integration


def rows(engine):
    with session_factory(engine)() as db_session:
        return {
            r.bug_id: r
            for r in db_session.execute(
                select(BugEmbedding.bug_id, BugEmbedding.text_hash, BugEmbedding.embedded_at)
            )
        }


def test_every_bug_is_embedded_whatever_its_status(seeded_db, llm_client, stand_in):
    with seeded_db.begin() as connection:
        connection.exec_driver_sql(
            "UPDATE bugs SET status = CASE id WHEN 1 THEN 'processing' WHEN 2 THEN 'processed' "
            "WHEN 3 THEN 'processed' WHEN 4 THEN 'failed' ELSE status END"
        )
    result = index_all_bugs(session_factory(seeded_db), llm_client)
    assert (result.indexed, result.total) == (20, 20)
    assert len(rows(seeded_db)) == 20
    requests = stand_in.embedding_requests()
    assert [r["inputs"] for r in requests] == [20]
    assert {r["model"] for r in requests} == {"text-embedding-3-small"}


def test_batches_of_at_most_20_and_progress_callback(initialized_db, llm_client, stand_in):
    add_numbered(initialized_db, 45)
    calls = []
    result = index_all_bugs(
        session_factory(initialized_db), llm_client, on_batch=lambda *args: calls.append(args)
    )
    assert [r["inputs"] for r in stand_in.embedding_requests()] == [20, 20, 5]
    assert (result.indexed, result.total) == (45, 45)
    assert calls == [(20, 45, 1, 3, 20), (40, 45, 2, 3, 20), (45, 45, 3, 3, 5)]


def test_rebuild_replaces_vectors_without_duplicates(seeded_db, llm_client, stand_in):
    factory = session_factory(seeded_db)
    index_all_bugs(factory, llm_client)
    before = rows(seeded_db)
    stand_in.reset()
    index_all_bugs(factory, llm_client)
    after = rows(seeded_db)
    assert len(after) == 20
    assert all(after[i].embedded_at > before[i].embedded_at for i in after)
    assert [r["inputs"] for r in stand_in.embedding_requests()] == [20]


def test_failing_batch_stores_nothing(initialized_db, llm_client, stand_in):
    add_numbered(initialized_db, 45)
    stand_in.script([{"status": 200}, {"status": 401}])
    with pytest.raises(LlmError, match="^OpenAI authentication failed$"):
        index_all_bugs(session_factory(initialized_db), llm_client)
    assert len(rows(initialized_db)) == 20


def test_zero_bugs_makes_no_request(initialized_db, llm_client, stand_in):
    result = index_all_bugs(session_factory(initialized_db), llm_client)
    assert (result.indexed, result.total) == (0, 0)
    assert stand_in.embedding_requests() == []
