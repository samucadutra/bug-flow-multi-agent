import sys

import pytest
from typer.testing import CliRunner

from bugflow.cli import app
from bugflow.cli.commands import triage as triage_module
from bugflow.cli.context import CliContext
from bugflow.enums import BugStatus, StepStatus
from bugflow.logging_config import Redactor
from bugflow.services.errors import NotFoundError, StateConflictError
from bugflow.services.triage import StepSummary, TriageOutcome

runner = CliRunner()

LABELS = [
    "AG1 Component Classifier",
    "AG2 Severity Classifier",
    "AG3 Technical Analyst",
    "AG4 Resolution Manager",
    "AG5 Bug Documenter",
]
SUMMARIES = [
    "backend",
    "major",
    "2 debugging steps, 0 similar bugs referenced",
    "backend / high / planned",
    "1 key takeaways, 1 next steps",
]


class FakeEngine:
    disposed = False

    def dispose(self):
        self.disposed = True


def steps(until=5, failed_text=None):
    result = []
    for position, (label, summary) in enumerate(zip(LABELS, SUMMARIES, strict=True), start=1):
        if position <= until:
            status, text = StepStatus.SUCCEEDED, summary
        elif position == until + 1 and failed_text:
            status, text = StepStatus.FAILED, failed_text
        else:
            status, text = StepStatus.SKIPPED, ""
        result.append(
            StepSummary(
                position=position, key=f"k{position}", label=label, status=status, summary=text
            )
        )
    return result


def outcome(bug_id, error=None):
    if error is None:
        return TriageOutcome(
            bug_id=bug_id, run_id=bug_id, status=BugStatus.PROCESSED, error=None, steps=steps()
        )
    return TriageOutcome(
        bug_id=bug_id,
        run_id=bug_id,
        status=BugStatus.FAILED,
        error=error,
        steps=steps(1, error),
    )


@pytest.fixture
def context(monkeypatch, make_settings):
    ctx = CliContext(make_settings(), FakeEngine(), Redactor())
    monkeypatch.setattr(triage_module, "bootstrap", lambda: ctx)
    return ctx


def fake_triage_bug(results):
    calls = []

    def triage_bug(engine, get_client, bug_id, redactor, on_step, **kwargs):
        calls.append((bug_id, kwargs))
        result = results[bug_id]
        for step in result.steps:
            if step.status != StepStatus.SKIPPED:
                on_step(step)
        return result

    triage_bug.calls = calls
    return triage_bug


def test_help_lists_triage(clean_env):
    out = runner.invoke(app, ["--help"]).output
    assert "triage" in out


def test_bug_prints_live_lines_then_result(monkeypatch, context):
    fake = fake_triage_bug({3: outcome(3)})
    monkeypatch.setattr(triage_module, "triage_bug", fake)
    result = runner.invoke(app, ["triage", "--bug", "3"])
    assert result.exit_code == 0
    assert result.stdout.splitlines() == [
        f"{label}: {summary}" for label, summary in zip(LABELS, SUMMARIES, strict=True)
    ] + ["Bug 3 processed"]
    assert fake.calls == [(3, {"similar_k": 5})]
    assert context.engine.disposed


def test_bug_failure_prints_error_and_exits_one(monkeypatch, context):
    error = "AG2 returned invalid severity 'high'"
    monkeypatch.setattr(triage_module, "triage_bug", fake_triage_bug({3: outcome(3, error)}))
    result = runner.invoke(app, ["triage", "--bug", "3"])
    assert result.exit_code == 1
    lines = result.stdout.splitlines()
    assert lines == [f"{LABELS[0]}: {SUMMARIES[0]}", f"Bug 3 failed: {error}"]


def test_claim_rejection_goes_to_stderr(monkeypatch, context):
    def reject(*args, **kwargs):
        raise StateConflictError("Bug 3 is already being processed")

    monkeypatch.setattr(triage_module, "triage_bug", reject)
    result = runner.invoke(app, ["triage", "--bug", "3"])
    assert result.exit_code == 1
    assert "Bug 3 is already being processed" in result.stderr and result.stdout == ""
    assert context.engine.disposed


def test_unknown_bug_message(monkeypatch, context):
    def missing(*args, **kwargs):
        raise NotFoundError("Bug 9 not found")

    monkeypatch.setattr(triage_module, "triage_bug", missing)
    result = runner.invoke(app, ["triage", "--bug", "9"])
    assert result.exit_code == 1 and "Bug 9 not found" in result.stderr


def fake_triage_all(results):
    def triage_all(engine, get_client, redactor, on_step, *, on_outcome, similar_k):
        for item in results:
            for step in item.steps:
                if step.status != StepStatus.SKIPPED:
                    on_step(step)
            on_outcome(item)
        return results

    return triage_all


def test_all_prints_lines_per_bug_and_summary(monkeypatch, context):
    monkeypatch.setattr(
        triage_module, "triage_all", fake_triage_all([outcome(1), outcome(2), outcome(3)])
    )
    result = runner.invoke(app, ["triage", "--all"])
    assert result.exit_code == 0
    lines = result.stdout.splitlines()
    assert lines[5] == "Bug 1 processed" and lines[11] == "Bug 2 processed"
    assert lines[-1] == "Triaged 3 bugs: 3 processed, 0 failed"


def test_all_with_a_failure_exits_one(monkeypatch, context):
    error = "AG2 returned invalid severity 'high'"
    monkeypatch.setattr(
        triage_module, "triage_all", fake_triage_all([outcome(1), outcome(2, error), outcome(3)])
    )
    result = runner.invoke(app, ["triage", "--all"])
    assert result.exit_code == 1
    assert f"Bug 2 failed: {error}" in result.stdout.splitlines()
    assert result.stdout.splitlines()[-1] == "Triaged 3 bugs: 2 processed, 1 failed"


def test_all_with_nothing_open(monkeypatch, context):
    monkeypatch.setattr(triage_module, "triage_all", fake_triage_all([]))
    result = runner.invoke(app, ["triage", "--all"])
    assert result.exit_code == 0 and result.stdout == "No open bugs to triage\n"


@pytest.mark.parametrize("args", [[], ["--all", "--bug", "1"]])
def test_exactly_one_option_is_required(monkeypatch, args, make_settings):
    def boom():
        raise AssertionError("bootstrap must not run on a usage error")

    monkeypatch.setattr(triage_module, "bootstrap", boom)
    result = runner.invoke(app, ["triage", *args])
    assert result.exit_code == 2
    assert "Specify exactly one of --bug or --all" in result.stderr and result.stdout == ""


def test_importing_the_command_does_not_import_openai_or_crewai():
    import subprocess

    code = (
        "import sys, bugflow.cli.commands.triage;"
        "print('crewai' in sys.modules, 'litellm' in sys.modules)"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False False"
