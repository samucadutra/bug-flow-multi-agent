import pytest

from bugflow.services.background import RunKind, RunRequest, StartResult, parse_request
from bugflow.services.errors import ValidationFailedError


def errors_of(kind, params):
    with pytest.raises(ValidationFailedError) as caught:
        parse_request(kind, params)
    return [(e.field, e.message) for e in caught.value.field_errors]


@pytest.mark.parametrize("params", [{}, None, {"bug_id": 1, "all": True}, {"all": False}])
def test_triage_requires_exactly_one_target(params):
    assert errors_of("triage", params) == [("params", "Specify exactly one of bug_id or all")]


@pytest.mark.parametrize("value", ["3", 3.5, None, True])
def test_bug_id_must_be_integer(value):
    errors = errors_of("triage", {"bug_id": value})
    assert errors == [("bug_id", "must be an integer")]
    assert str(value) not in errors[0][1]


def test_all_must_be_boolean():
    assert errors_of("triage", {"all": "yes"}) == [("all", "must be a boolean")]


def test_unknown_param_key_is_rejected():
    assert errors_of("triage", {"bug_id": 1, "x": 1}) == [("x", "is not allowed")]


@pytest.mark.parametrize("kind", ["index", "seed"])
def test_index_and_seed_take_no_params(kind):
    assert errors_of(kind, {"bug_id": 1}) == [("params", "must be empty")]


@pytest.mark.parametrize("kind", ["reset", "init", ""])
def test_unknown_kind(kind):
    assert errors_of(kind, {}) == [("kind", "must be one of triage, index, seed")]


def test_valid_requests_parse():
    assert parse_request("triage", {"bug_id": 3}) == RunRequest(RunKind.TRIAGE, bug_id=3)
    assert parse_request(RunKind.TRIAGE, {"all": True}) == RunRequest(RunKind.TRIAGE, all_open=True)
    assert parse_request("index", {}) == RunRequest(RunKind.INDEX)
    assert parse_request("seed", None) == RunRequest(RunKind.SEED)


def test_start_result_run_id():
    assert StartResult(run_ids=[4]).run_id == 4
    for ids in ([], [1, 2]):
        with pytest.raises(ValueError):
            _ = StartResult(run_ids=ids).run_id
