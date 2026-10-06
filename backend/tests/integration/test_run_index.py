import pytest
from sqlalchemy import text

from bugflow.config import ConfigError
from bugflow.db.engine import session_factory
from bugflow.logging_config import Redactor
from bugflow.services.errors import SchemaNotInitializedError
from bugflow.services.llm_client import LlmError, OpenAILlmClient
from bugflow.services.operations import run_index
from bugflow.services.runs import RunRecorder
from tests_helpers import add_numbered

pytestmark = pytest.mark.integration


def index_runs(engine):
    with engine.connect() as connection:
        ids = [row.id for row in connection.execute(text("SELECT id FROM runs WHERE type='index'"))]
    return RunRecorder(session_factory(engine)), ids


def embedding_count(engine):
    with engine.connect() as connection:
        return connection.execute(text("SELECT count(*) FROM bug_embeddings")).scalar()


def test_success_records_progress_and_a_log_line_per_batch(initialized_db, llm_client):
    add_numbered(initialized_db, 45)
    result = run_index(initialized_db, lambda: llm_client)
    assert (result.indexed, result.total) == (45, 45)
    recorder, (run_id,) = index_runs(initialized_db)
    run = recorder.get_run(run_id)
    assert (run.status, run.progress_done, run.progress_total) == ("succeeded", 45, 45)
    assert run.started_at is not None and run.finished_at is not None
    assert len(recorder.get_run_logs(run_id)) >= 3


def test_failing_batch_records_a_redacted_error(initialized_db, make_llm_client, stand_in):
    add_numbered(initialized_db, 45)
    stand_in.script([{"status": 200}, {"status": 401}])
    key = "sk-test-valid"
    with pytest.raises(LlmError, match="^OpenAI authentication failed$"):
        run_index(initialized_db, lambda: make_llm_client(), Redactor([key]))
    recorder, (run_id,) = index_runs(initialized_db)
    run = recorder.get_run(run_id)
    assert run.status == "failed" and run.error == "OpenAI authentication failed"
    assert embedding_count(initialized_db) == 20


def test_missing_key_records_the_failure_and_makes_no_request(seeded_db, make_settings, stand_in):
    settings = make_settings()
    with pytest.raises(ConfigError, match="^OPENAI_API_KEY is not set$"):
        run_index(seeded_db, lambda: OpenAILlmClient.from_settings(settings))
    recorder, (run_id,) = index_runs(seeded_db)
    run = recorder.get_run(run_id)
    assert run.status == "failed" and run.error == "OPENAI_API_KEY is not set"
    assert stand_in.embedding_requests() == []


def test_uninitialized_schema(fresh_schema, llm_client):
    with pytest.raises(SchemaNotInitializedError):
        run_index(fresh_schema, lambda: llm_client)


def test_empty_table_indexes_zero(initialized_db, llm_client, stand_in):
    result = run_index(initialized_db, lambda: llm_client)
    assert (result.indexed, result.total) == (0, 0)
    recorder, (run_id,) = index_runs(initialized_db)
    assert recorder.get_run(run_id).status == "succeeded"
    assert stand_in.embedding_requests() == []
