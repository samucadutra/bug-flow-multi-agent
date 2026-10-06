import pytest
from sqlalchemy.exc import OperationalError

from bugflow.services.health import CheckResult, HealthReport, check_health
from mocks.fake_openai import FakeLlmProbe


class OkEngine:
    def __init__(self, vector=True):
        self.vector = vector

    def connect(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, statement, params=None):
        class Result:
            def first(inner):
                return (1,) if self.vector else None

        return Result()


class BrokenEngine:
    def connect(self):
        raise OperationalError("SELECT 1", {}, Exception("host=127.0.0.1 password=s3cretpw"))


def test_no_key_fails_llm_without_calling_the_probe(make_settings):
    probe = FakeLlmProbe.succeeding()
    report = check_health(make_settings(), OkEngine(), probe)
    assert report.llm == CheckResult(ok=False, message="OPENAI_API_KEY is not set")
    assert not probe.called
    assert report.database.ok and report.vector_search.ok and not report.all_ok


def test_all_ok_with_a_key(make_settings, canary_api_key):
    probe = FakeLlmProbe.succeeding()
    report = check_health(make_settings(OPENAI_API_KEY=canary_api_key), OkEngine(), probe)
    assert report.all_ok and report.summary == "All checks passed"
    assert report.lines() == ["database: ok", "vector search: ok", "llm: ok"]
    assert probe.calls[0]["api_key"] == canary_api_key


def test_checks_are_independent(make_settings, canary_api_key, canary_db_password):
    report = check_health(
        make_settings(OPENAI_API_KEY=canary_api_key), BrokenEngine(), FakeLlmProbe.succeeding()
    )
    assert report.lines() == [
        "database: failed: Cannot connect to the database",
        "vector search: failed: Database unreachable; vector search not checked",
        "llm: ok",
    ]
    assert canary_db_password not in "".join(report.lines())


def test_missing_vector_extension(make_settings):
    report = check_health(make_settings(), OkEngine(vector=False))
    assert report.vector_search.message.startswith("pgvector extension is not available")


def test_llm_failure_keeps_other_results(make_settings, canary_api_key):
    probe = FakeLlmProbe.authentication_failure()
    report = check_health(make_settings(OPENAI_API_KEY=canary_api_key), OkEngine(), probe)
    assert report.llm.message == "OpenAI authentication failed"
    assert report.database.ok and not report.all_ok
    assert canary_api_key not in repr(report) + "".join(report.lines())


def test_unexpected_probe_exception_is_mapped(make_settings, canary_api_key):
    class Exploding:
        def check(self, **kwargs):
            raise RuntimeError(canary_api_key)

    report = check_health(make_settings(OPENAI_API_KEY=canary_api_key), OkEngine(), Exploding())
    assert report.llm.message == "OpenAI request failed"


@pytest.mark.parametrize(
    ("flags", "expected"), [((True, True, True), True), ((True, False, True), False)]
)
def test_all_ok_semantics(flags, expected):
    report = HealthReport(
        database=CheckResult(ok=flags[0]),
        vector_search=CheckResult(ok=flags[1]),
        llm=CheckResult(ok=flags[2]),
    )
    assert report.all_ok is expected
