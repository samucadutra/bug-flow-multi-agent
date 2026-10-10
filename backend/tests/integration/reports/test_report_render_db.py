"""`render_report` and `get_report` on a real database."""

from __future__ import annotations

import itertools
import re

import pytest
from sqlalchemy import text

from bugflow.enums import Component, ResolutionStatus, Severity, Team
from bugflow.services.errors import NotFoundError
from bugflow.services.reports import ReportFormat, get_report, render_report
from report_helpers import set_result_values, stored_texts, validate

pytestmark = pytest.mark.integration


def test_render_title_verbatim_text_and_stored_analysis(db_session, report_bug) -> None:
    bug_id, similar_id = report_bug
    result = render_report(db_session, bug_id)
    md = result.markdown
    assert md.split("\n")[0] == "# Checkout button does nothing on Safari 17"
    assert md.endswith("\n") and not md.endswith("\n\n")
    assert "Clicking Place order shows no response and no network call." in md
    assert "Add an item, go to checkout in Safari 17, click the button." in md
    assert "| Assignee profile | Backend engineer (Senior), skills: Python, PostgreSQL |" in md
    assert "| Priority | High |" in md
    assert "Customers cannot complete orders on Safari." in md
    assert md.index("Reproduce on Safari 17") < md.index("Inspect the server logs")
    assert f"- #{similar_id} Payment form freezes on Safari 17" in md


def test_status_label_and_no_resolved(db_session, report_bug) -> None:
    result = render_report(db_session, report_bug[0])
    assert "| Resolution status | Needs info |" in result.markdown
    assert "<td>Needs info</td>" in result.html
    assert "resolved" not in result.markdown.lower()
    assert "resolved" not in result.html.lower()


def test_deadline_for_five_days(db_session, report_bug) -> None:
    result = render_report(db_session, report_bug[0])
    assert "| Report completed | 2026-03-30 |" in result.markdown
    assert "| Deadline | 2026-04-04 |" in result.markdown
    assert str(result.completed_on) == "2026-03-30" and str(result.deadline) == "2026-04-04"


def test_deadline_crosses_month_boundaries(initialized_db, db_session, report_bug) -> None:
    set_result_values(initialized_db, report_bug[0], target_days=90)
    md = render_report(db_session, report_bug[0]).markdown
    assert "| Target | 90 days |" in md
    assert "| Deadline | 2026-06-28 |" in md


def test_stored_after_flush_and_invisible_before_commit(
    initialized_db, db_session, report_bug
) -> None:
    result = render_report(db_session, report_bug[0])
    assert stored_texts(initialized_db, report_bug[0]) == (None, None)
    db_session.commit()
    assert stored_texts(initialized_db, report_bug[0]) == (result.markdown, result.html)


def test_rendering_is_repeatable(db_session, report_bug) -> None:
    first = render_report(db_session, report_bug[0])
    second = render_report(db_session, report_bug[0])
    assert (first.markdown, first.html) == (second.markdown, second.html)


def test_html_page_and_diagram_match_the_markdown(db_session, report_bug) -> None:
    result = render_report(db_session, report_bug[0])
    assert result.html.startswith("<!DOCTYPE html>")
    assert "<title>Checkout button does nothing on Safari 17</title>" in result.html
    assert result.html.count("<script") == 1
    assert re.search(r"https://cdn\.jsdelivr\.net/npm/mermaid@\d+\.\d+\.\d+/", result.html)
    block = re.search(r"```mermaid\n(.*?)\n```", result.markdown, re.S)
    assert block
    lines = block.group(1).split("\n")
    assert lines[0] == "flowchart LR"
    assert lines[1] == (
        f'    bug["Bug {report_bug[0]}: Checkout button does nothing on Safari 17"]'
        ' --> component["Component: Backend"]'
    )
    assert lines[4] == '    team --> resolution["Resolution: Needs info"]'
    element = re.search(r'<pre class="mermaid">(.*?)</pre>', result.html, re.S)
    import html as html_lib

    assert html_lib.unescape(element.group(1)) == block.group(1)


def test_no_similar_bugs_referenced(db_session, hostile_bug) -> None:
    assert "No similar bugs referenced" in render_report(db_session, hostile_bug).markdown


def test_get_returns_the_stored_text_unchanged(initialized_db, db_session, stored_report_bug):
    md = get_report(db_session, stored_report_bug, ReportFormat.MD)
    html = get_report(db_session, stored_report_bug, ReportFormat.HTML)
    assert md.content == "# Stored report\n" and html.content == "<p>Stored report</p>\n"
    assert stored_texts(initialized_db, stored_report_bug) == (
        "# Stored report\n",
        "<p>Stored report</p>\n",
    )


def test_get_renders_a_missing_report_on_demand(initialized_db, db_session, report_bug) -> None:
    result = get_report(db_session, report_bug[0], ReportFormat.MD)
    assert result.content.startswith("# Checkout button does nothing on Safari 17")
    db_session.commit()
    markdown, html = stored_texts(initialized_db, report_bug[0])
    assert markdown and html


def test_unprocessed_and_unknown_bugs(initialized_db, db_session, unprocessed_bug) -> None:
    message = f"Bug {unprocessed_bug} has no report; triage it first"
    with pytest.raises(NotFoundError, match=f"^{message}$"):
        render_report(db_session, unprocessed_bug)
    with pytest.raises(NotFoundError, match=f"^{message}$"):
        get_report(db_session, unprocessed_bug, ReportFormat.HTML)
    with initialized_db.connect() as connection:
        count = connection.execute(
            text("SELECT count(*) FROM bug_reports WHERE bug_id = :i"), {"i": unprocessed_bug}
        ).scalar_one()
    assert count == 0
    with pytest.raises(NotFoundError, match="^Bug 999999 not found$"):
        render_report(db_session, 999999)


def test_every_enum_combination_on_stored_rows(initialized_db, db_session, report_bug) -> None:
    bug_id = report_bug[0]
    combinations = itertools.product(Component, Severity, Team, ResolutionStatus)
    for component, severity, team, status in combinations:
        set_result_values(
            initialized_db,
            bug_id,
            component=component.value,
            severity=severity.value,
            assigned_team=team.value,
            resolution_status=status.value,
        )
        db_session.expire_all()
        markdown = render_report(db_session, bug_id).markdown
        validate(re.search(r"```mermaid\n(.*?)\n```", markdown, re.S).group(1))
