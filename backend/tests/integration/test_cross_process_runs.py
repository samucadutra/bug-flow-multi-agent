"""CLI-started runs streamed from another process, and a killed child recovered."""

import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest

from bugflow.services.recovery import recover_interrupted_runs
from bugflow.services.run_events import iter_run_events, read_run_events
from mocks.fake_openai_server import VALID_KEY, default_reply
from tests_helpers import result_row_counts, run_rows, step_rows, stored_status, wait_until

pytestmark = pytest.mark.integration

BACKEND = Path(__file__).resolve().parents[2]
BINARY = Path(sys.executable).parent / "bugflow"
ROOT_ENV_FILE = BACKEND.parent / ".env"


@pytest.fixture
def spawn(test_engine, stand_in):
    url = test_engine.url.render_as_string(hide_password=False)
    assert not ROOT_ENV_FILE.exists(), "the contracts require that no root .env file exists"
    children: list[subprocess.Popen] = []

    def start(*args):
        env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith(("DATABASE_", "TEST_DATABASE_", "OPENAI_", "LOG_LEVEL", "SIMILAR"))
        }
        env.update(
            DATABASE_URL=url,
            OPENAI_BASE_URL=stand_in.base_url,
            OPENAI_API_KEY=VALID_KEY,
            TZ="UTC",
        )
        child = subprocess.Popen(
            [str(BINARY), *args],
            cwd=BACKEND,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        children.append(child)
        return child

    yield start
    for child in children:
        if child.poll() is None:
            child.kill()
        child.communicate()


def delay_severity(stand_in, seconds):
    stand_in.script_chat(
        [
            {
                "role": "Severity Classifier",
                "json": default_reply("Severity Classifier"),
                "delay": seconds,
            }
        ]
    )


def test_a_cli_run_is_streamed_from_another_process(spawn, initialized_db, open_bug, stand_in):
    delay_severity(stand_in, 3)
    child = spawn("triage", "--bug", str(open_bug))
    (run,) = wait_until(lambda: run_rows(initialized_db, f"bug_id = {open_bug}"), 120)
    events = []
    running_seen_before_exit = False
    for event in iter_run_events(initialized_db, run.id):
        events.append(event)
        if event.type == "step" and event.step.position == 2 and event.step.status == "running":
            running_seen_before_exit = child.poll() is None
    assert child.wait(timeout=120) == 0
    assert events[-1].type == "run" and events[-1].run.status.value == "succeeded"
    last = {}
    for event in events:
        if event.type == "step":
            last[event.step.position] = event.step.status.value
    assert last == {position: "succeeded" for position in range(1, 6)}
    assert running_seen_before_exit
    log_ids = [e.log.id for e in events if e.type == "log"]
    assert log_ids == sorted(log_ids)
    assert "AG1 Component Classifier started" in [e.log.message for e in events if e.type == "log"]


def test_resuming_after_a_cursor_on_a_cli_run(spawn, initialized_db, open_bug):
    assert spawn("triage", "--bug", str(open_bug)).wait(timeout=120) == 0
    (run,) = run_rows(initialized_db)
    full = read_run_events(initialized_db, run.id)
    third = full.events[2]
    page = read_run_events(initialized_db, run.id, third.cursor)
    assert page.events == full.events[3:]
    assert page.finished is True


def test_a_killed_triage_is_recovered(spawn, initialized_db, open_bug, stand_in):
    delay_severity(stand_in, 10)
    child = spawn("triage", "--bug", str(open_bug))

    def step_two_running():
        runs = run_rows(initialized_db, f"bug_id = {open_bug}")
        if not runs:
            return False
        steps = step_rows(initialized_db, runs[0].id)
        return len(steps) >= 2 and steps[1].status == "running"

    wait_until(step_two_running, 120)
    child.send_signal(signal.SIGKILL)
    child.wait(timeout=30)
    (run,) = run_rows(initialized_db)
    assert run.status == "running" and stored_status(initialized_db, open_bug) == "processing"
    recover_interrupted_runs(initialized_db)
    run = run_rows(initialized_db)[0]
    assert (run.status, run.error) == ("failed", "interrupted")
    assert stored_status(initialized_db, open_bug) == "failed"
    steps = step_rows(initialized_db, run.id)
    assert [s.status for s in steps] == ["succeeded", "failed", "skipped", "skipped", "skipped"]
    assert steps[1].error == "interrupted"
    assert set(result_row_counts(initialized_db, open_bug).values()) == {0}
    page = read_run_events(initialized_db, run.id)
    assert page.events[-1].type == "run" and page.events[-1].run.status.value == "failed"
