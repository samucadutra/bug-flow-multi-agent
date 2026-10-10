"""Report services without a database: the no-commit rule, hook installation, error wrapping."""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from bugflow.db.models import Bug, BugReport
from bugflow.services import reports as reports_module
from bugflow.services import triage as triage_module
from bugflow.services.errors import NotFoundError
from bugflow.services.reports import (
    ReportFormat,
    ReportRenderError,
    get_report,
    install_report_hook,
    render_report,
    report_result_hook,
)
from report_helpers import sample_report_data


class FakeSession:
    def __init__(self, bug: bool = True, report: SimpleNamespace | None = None) -> None:
        self.rows: dict[type, object] = {}
        if bug:
            self.rows[Bug] = SimpleNamespace(id=3)
        if report is not None:
            self.rows[BugReport] = report
        self.flushes = 0

    def get(self, model: type, key: int) -> object | None:
        return self.rows.get(model)

    def flush(self) -> None:
        self.flushes += 1

    def commit(self) -> None:
        raise AssertionError("services must never commit")


@pytest.fixture(autouse=True)
def _reset_installation():
    triage_module.clear_result_hooks()
    yield
    triage_module.clear_result_hooks()
    reports_module._renderer = reports_module.default_renderer


@pytest.fixture
def fake_data(monkeypatch: pytest.MonkeyPatch):
    data = sample_report_data()
    monkeypatch.setattr(reports_module, "load_report_data", lambda session, bug_id: data)
    return data


def test_the_module_never_calls_commit() -> None:
    tree = ast.parse(Path(reports_module.__file__).read_text("utf-8"))
    calls = [
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]
    assert "commit" not in calls


def test_render_report_stores_both_formats_and_flushes(fake_data) -> None:
    report = SimpleNamespace(markdown=None, html=None)
    session = FakeSession(report=report)
    result = render_report(session, 3)
    assert report.markdown == result.markdown and report.html == result.html
    assert result.markdown.startswith("# Checkout button")
    assert (result.completed_on, result.deadline) == (fake_data.completed_on, fake_data.deadline)
    assert session.flushes == 1


def test_install_twice_leaves_one_hook_and_keeps_other_order() -> None:
    def other(session, bug_id, results) -> None:
        return None

    triage_module.register_result_hook(other)
    install_report_hook()
    install_report_hook()
    assert triage_module._RESULT_HOOKS == [other, report_result_hook]


def test_replacement_renderer_error_is_wrapped(fake_data) -> None:
    def failing(data):
        raise RuntimeError("forced render failure\nsecond line")

    install_report_hook(render=failing)
    session = FakeSession(report=SimpleNamespace(markdown=None, html=None))
    with pytest.raises(ReportRenderError) as caught:
        report_result_hook(session, 3, None)
    assert str(caught.value) == "Report rendering failed: forced render failure"


def test_install_without_renderer_restores_the_default(fake_data) -> None:
    install_report_hook(render=lambda data: ("a", "b"))
    install_report_hook()
    session = FakeSession(report=SimpleNamespace(markdown=None, html=None))
    report_result_hook(session, 3, None)
    assert session.rows[BugReport].markdown.startswith("# ")


def test_get_report_returns_the_stored_text_without_rendering(monkeypatch) -> None:
    def boom(*args):
        raise AssertionError("must not render")

    monkeypatch.setattr(reports_module, "render_report", boom)
    session = FakeSession(report=SimpleNamespace(markdown="# Stored\n", html="<p>x</p>\n"))
    md = get_report(session, 3, ReportFormat.MD)
    html = get_report(session, 3, ReportFormat.HTML)
    assert (md.content, md.rendered) == ("# Stored\n", False)
    assert html.content == "<p>x</p>\n"


def test_get_report_renders_when_the_requested_text_is_null(fake_data) -> None:
    session = FakeSession(report=SimpleNamespace(markdown="# Stored\n", html=None))
    result = get_report(session, 3, ReportFormat.HTML)
    assert result.rendered and result.content.startswith("<!DOCTYPE html>")
    assert session.rows[BugReport].markdown.startswith("# Checkout")


def test_not_found_messages() -> None:
    with pytest.raises(NotFoundError, match=r"^Bug 3 not found$"):
        get_report(FakeSession(bug=False), 3, ReportFormat.MD)
    with pytest.raises(NotFoundError, match=r"^Bug 3 has no report; triage it first$"):
        get_report(FakeSession(), 3, ReportFormat.MD)
