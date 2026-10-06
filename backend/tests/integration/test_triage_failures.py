import pytest
from sqlalchemy import text

from bugflow.db.engine import session_factory
from bugflow.enums import BugStatus, RunStatus, StepStatus
from bugflow.logging_config import Redactor
from bugflow.services.llm_client import OpenAILlmClient
from bugflow.services.runs import RunRecorder
from bugflow.services.triage import triage_bug
from mocks.fake_openai_server import INVALID_KEY, default_reply
from tests_helpers import RESULT_TABLES, result_row_counts, stored_status

pytestmark = pytest.mark.integration

SEVERITY = "Severity Classifier"
COMPONENT = "Component Classifier"
PLAN = "Resolution Manager"
ANALYST = "Technical Analyst"


def script_twice(stand_in, role, **changes):
    reply = default_reply(role)
    reply.update(changes)
    stand_in.script_chat([{"role": role, "json": reply, "repeat": 2}])


def assert_failed(engine, bug_id, outcome, error):
    assert outcome.status == BugStatus.FAILED and outcome.error == error
    assert stored_status(engine, bug_id) == "failed"
    assert result_row_counts(engine, bug_id) == dict.fromkeys(RESULT_TABLES, 0)


def steps_of(engine, outcome):
    return RunRecorder(session_factory(engine)).get_steps(outcome.run_id)


def test_one_re_ask_corrects_the_answer(initialized_db, open_bug, get_client, stand_in):
    wrong = default_reply(SEVERITY)
    wrong["severity"] = "high"
    stand_in.script_chat([{"role": SEVERITY, "json": wrong}])
    outcome = triage_bug(initialized_db, get_client, open_bug)
    assert outcome.processed
    requests = stand_in.chat_requests(SEVERITY)
    assert len(requests) == 2
    second = "\n".join(m["content"] for m in requests[1]["messages"] if m["role"] == "user")
    assert "invalid severity" in second
    with initialized_db.connect() as connection:
        stored = connection.execute(text("SELECT severity FROM severity_classifications")).scalar()
    assert stored == "major"
    step = steps_of(initialized_db, outcome)[1]
    assert step.input["reask"] == {"validation_error": "AG2 returned invalid severity 'high'"}
    logs = RunRecorder(session_factory(initialized_db)).get_run_logs(outcome.run_id)
    assert any("re-ask" in log.message for log in logs)


def test_second_invalid_answer_fails_the_bug(initialized_db, open_bug, get_client, stand_in):
    script_twice(stand_in, SEVERITY, severity="high")
    outcome = triage_bug(initialized_db, get_client, open_bug)
    assert_failed(initialized_db, open_bug, outcome, "AG2 returned invalid severity 'high'")
    assert len(stand_in.chat_requests(SEVERITY)) == 2
    assert stand_in.chat_requests(ANALYST) == []
    steps = steps_of(initialized_db, outcome)
    assert [s.status for s in steps] == [
        StepStatus.SUCCEEDED,
        StepStatus.FAILED,
        StepStatus.SKIPPED,
        StepStatus.SKIPPED,
        StepStatus.SKIPPED,
    ]
    assert steps[0].input and steps[0].output
    assert steps[1].error == "AG2 returned invalid severity 'high'"
    assert steps[1].output["raw_response"].startswith("{")
    assert [s.status for s in outcome.steps] == [s.status for s in steps]
    run = RunRecorder(session_factory(initialized_db)).get_run(outcome.run_id)
    assert run.status == RunStatus.FAILED and run.error == outcome.error
    assert (run.progress_done, run.progress_total) == (1, 5)


@pytest.mark.parametrize(
    ("value", "error"),
    [
        ("Backend", "AG1 returned invalid component 'Backend'"),
        ("server-side", "AG1 returned invalid component 'server-side'"),
        ("backend ", "AG1 returned invalid component 'backend '"),
    ],
)
def test_near_misses_are_not_normalized(
    initialized_db, open_bug, get_client, stand_in, value, error
):
    script_twice(stand_in, COMPONENT, component=value)
    outcome = triage_bug(initialized_db, get_client, open_bug)
    assert_failed(initialized_db, open_bug, outcome, error)
    assert len(stand_in.chat_requests(COMPONENT)) == 2


def test_malformed_json(initialized_db, open_bug, get_client, stand_in):
    stand_in.script_chat([{"role": COMPONENT, "text": "this is not json", "repeat": 2}])
    outcome = triage_bug(initialized_db, get_client, open_bug)
    assert_failed(initialized_db, open_bug, outcome, "AG1 returned malformed JSON")
    steps = steps_of(initialized_db, outcome)
    assert steps[0].status == StepStatus.FAILED
    assert [s.status for s in steps[1:]] == [StepStatus.SKIPPED] * 4
    assert steps[0].output == {"raw_response": "this is not json"}


def test_unexpected_field_in_the_plan(initialized_db, open_bug, get_client, stand_in):
    script_twice(stand_in, PLAN, assignee_name="Alice")
    outcome = triage_bug(initialized_db, get_client, open_bug)
    assert_failed(
        initialized_db, open_bug, outcome, "AG4 returned unexpected field 'assignee_name'"
    )
    assert steps_of(initialized_db, outcome)[4].status == StepStatus.SKIPPED


@pytest.mark.parametrize("days", [0, 91])
def test_target_days_out_of_range(initialized_db, open_bug, get_client, stand_in, days):
    script_twice(stand_in, PLAN, target_days=days)
    outcome = triage_bug(initialized_db, get_client, open_bug)
    assert_failed(initialized_db, open_bug, outcome, "AG4 returned invalid target_days")


def test_unsupplied_similar_bug_id(initialized_db, open_bug, get_client, stand_in):
    script_twice(stand_in, ANALYST, referenced_similar_bug_ids=[99999])
    outcome = triage_bug(initialized_db, get_client, open_bug)
    assert_failed(
        initialized_db, open_bug, outcome, "AG3 returned invalid referenced_similar_bug_ids"
    )


def test_a_supplied_similar_bug_id_is_accepted(seed_indexed, get_client, stand_in):
    first = triage_bug(seed_indexed, get_client, 1)
    similar_id = steps_of(seed_indexed, first)[2].input["data"]["similar_bugs"][0]["id"]
    script_twice(stand_in, ANALYST, referenced_similar_bug_ids=[similar_id])
    stand_in.script_chat([])
    outcome = triage_bug(seed_indexed, get_client, 2, similar_k=19)
    assert outcome.processed
    with seed_indexed.connect() as connection:
        ids = connection.execute(
            text("SELECT referenced_similar_bug_ids FROM technical_analyses WHERE bug_id = 2")
        ).scalar_one()
    assert ids == [similar_id]


@pytest.mark.parametrize(
    ("status", "message"),
    [(429, "OpenAI rate limit exceeded"), (503, "OpenAI service unavailable")],
)
def test_transient_errors_give_exactly_three_requests(
    initialized_db, open_bug, get_client, stand_in, status, message
):
    stand_in.script_chat([{"role": COMPONENT, "status": status, "repeat": 100}])
    outcome = triage_bug(initialized_db, get_client, open_bug)
    assert_failed(initialized_db, open_bug, outcome, f"AG1 failed: {message}")
    assert len(stand_in.chat_requests()) == 3
    steps = steps_of(initialized_db, outcome)
    assert steps[0].status == StepStatus.FAILED and steps[0].output is None
    assert [s.status for s in steps[1:]] == [StepStatus.SKIPPED] * 4


def test_bad_request_is_not_retried(initialized_db, open_bug, get_client, stand_in):
    stand_in.script_chat([{"role": COMPONENT, "status": 400, "repeat": 100}])
    outcome = triage_bug(initialized_db, get_client, open_bug)
    assert_failed(initialized_db, open_bug, outcome, "AG1 failed: OpenAI request failed")
    assert len(stand_in.chat_requests()) == 1


def test_a_slow_call_times_out(initialized_db, open_bug, make_llm_client, stand_in):
    client = make_llm_client(timeout=1, retries=0)
    stand_in.script_chat([{"role": COMPONENT, "delay": 3}])
    outcome = triage_bug(initialized_db, lambda: client, open_bug)
    assert_failed(initialized_db, open_bug, outcome, "AG1 failed: OpenAI request timed out")
    assert len(stand_in.chat_requests()) == 1


def test_failure_after_a_successful_first_step_marks_the_right_step(
    initialized_db, open_bug, get_client, stand_in
):
    stand_in.script_chat([{"role": "Bug Documenter", "status": 503, "repeat": 100}])
    outcome = triage_bug(initialized_db, get_client, open_bug)
    assert_failed(initialized_db, open_bug, outcome, "AG5 failed: OpenAI service unavailable")
    steps = steps_of(initialized_db, outcome)
    assert [s.status for s in steps] == [StepStatus.SUCCEEDED] * 4 + [StepStatus.FAILED]


def test_authentication_failure_leaves_no_key_anywhere(
    initialized_db, open_bug, make_llm_client, stand_in
):
    client = make_llm_client(key=INVALID_KEY)
    outcome = triage_bug(initialized_db, lambda: client, open_bug, redactor=Redactor([INVALID_KEY]))
    assert_failed(initialized_db, open_bug, outcome, "AG1 failed: OpenAI authentication failed")
    assert len(stand_in.chat_requests()) == 1
    with initialized_db.connect() as connection:
        dump = "\n".join(
            str(row)
            for query in (
                "SELECT * FROM run_steps",
                "SELECT * FROM run_logs",
                "SELECT * FROM runs",
            )
            for row in connection.execute(text(query)).all()
        )
    assert INVALID_KEY not in dump + repr(outcome)


def test_missing_key_makes_no_chat_request(initialized_db, open_bug, make_settings, stand_in):
    settings = make_settings()
    assert not settings.has_openai_key
    outcome = triage_bug(
        initialized_db,
        lambda: OpenAILlmClient.from_settings(settings, base_url=stand_in.base_url),
        open_bug,
    )
    assert_failed(initialized_db, open_bug, outcome, "AG1 failed: OPENAI_API_KEY is not set")
    assert stand_in.chat_requests() == []
    steps = steps_of(initialized_db, outcome)
    assert steps[0].status == StepStatus.FAILED
    assert [s.status for s in steps[1:]] == [StepStatus.SKIPPED] * 4
    assert steps[0].input["prompt"]


def test_embedding_failure_fails_the_analyst_step(initialized_db, open_bug, get_client, stand_in):
    stand_in.script([{"status": 503}] * 3)
    outcome = triage_bug(initialized_db, get_client, open_bug)
    assert_failed(initialized_db, open_bug, outcome, "AG3 failed: OpenAI service unavailable")
    assert stand_in.chat_requests(ANALYST) == []
    steps = steps_of(initialized_db, outcome)
    assert [s.status for s in steps] == [
        StepStatus.SUCCEEDED,
        StepStatus.SUCCEEDED,
        StepStatus.FAILED,
        StepStatus.SKIPPED,
        StepStatus.SKIPPED,
    ]


def test_a_failed_bug_can_be_triaged_again(initialized_db, open_bug, get_client, stand_in):
    script_twice(stand_in, SEVERITY, severity="high")
    assert triage_bug(initialized_db, get_client, open_bug).status == BugStatus.FAILED
    again = triage_bug(initialized_db, get_client, open_bug)
    assert again.processed and stored_status(initialized_db, open_bug) == "processed"
    assert result_row_counts(initialized_db, open_bug) == dict.fromkeys(RESULT_TABLES, 1)


def test_unexpected_runner_error_marks_the_bug_failed_and_raises(
    initialized_db, open_bug, get_client
):
    def broken(agent, prompt, client):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        triage_bug(initialized_db, get_client, open_bug, runner=broken)
    assert stored_status(initialized_db, open_bug) == "failed"


def test_an_unexpected_agent_error_becomes_a_failed_outcome(initialized_db, open_bug, get_client):
    def broken(agent, prompt, client):
        raise RuntimeError("internal detail sk-abcdefghijklmnopqrstuvwxyz0123")

    outcome = triage_bug(initialized_db, get_client, open_bug, runner=broken)
    assert_failed(initialized_db, open_bug, outcome, "AG1 failed: unexpected agent error")
