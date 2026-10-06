import pytest

from bugflow.db.engine import create_db_engine
from bugflow.services.health import check_health
from mocks.fake_openai import FakeLlmProbe

pytestmark = pytest.mark.integration


def test_everything_reachable(make_settings, initialized_db, canary_api_key):
    probe = FakeLlmProbe.succeeding()
    report = check_health(make_settings(OPENAI_API_KEY=canary_api_key), initialized_db, probe)
    assert report.all_ok and report.summary == "All checks passed"


def test_missing_key(make_settings, initialized_db):
    probe = FakeLlmProbe.succeeding()
    report = check_health(make_settings(), initialized_db, probe)
    assert report.database.ok and report.vector_search.ok
    assert report.llm.message == "OPENAI_API_KEY is not set" and not probe.called


def test_database_not_initialized_still_ok(make_settings, fresh_schema):
    report = check_health(make_settings(), fresh_schema)
    assert report.database.ok and report.vector_search.ok


def test_authentication_failure(make_settings, initialized_db, canary_api_key):
    settings = make_settings(OPENAI_API_KEY=canary_api_key)
    report = check_health(settings, initialized_db, FakeLlmProbe.authentication_failure())
    assert report.llm.message == "OpenAI authentication failed"
    assert report.database.ok and report.vector_search.ok
    assert canary_api_key not in repr(report) + "".join(report.lines())


def test_unreachable_database(make_settings, canary_api_key, canary_db_password):
    url = f"postgresql+psycopg://bugflow:{canary_db_password}@127.0.0.1:1/bugflow"
    engine = create_db_engine(url)
    report = check_health(
        make_settings(OPENAI_API_KEY=canary_api_key), engine, FakeLlmProbe.succeeding()
    )
    assert report.database.message == "Cannot connect to the database"
    assert report.vector_search.message == "Database unreachable; vector search not checked"
    assert report.llm.ok
    text = repr(report) + "".join(report.lines())
    assert canary_db_password not in text and "127.0.0.1" not in text


def test_plain_server_without_pgvector(make_settings, plain_engine):
    report = check_health(make_settings(), plain_engine)
    assert report.database.ok
    assert report.vector_search.message == (
        "pgvector extension is not available; use the pgvector/pgvector image"
    )
