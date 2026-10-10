"""Hostile text end to end."""

from __future__ import annotations

import re

import pytest

from bugflow.services.reports import render_report
from report_helpers import HOSTILE_OVERRIDES, parse, validate

pytestmark = pytest.mark.integration


def test_html_stays_intact(db_session, hostile_bug) -> None:
    result = render_report(db_session, hostile_bug)
    parsed = parse(result.html)
    assert parsed.scripts == 1
    assert "b" not in parsed.elements and "img" not in parsed.elements
    assert parsed.texts["description"] == HOSTILE_OVERRIDES["description"]
    assert parsed.texts["title"] == HOSTILE_OVERRIDES["title"]
    assert not parsed.unbalanced


def test_markdown_text_is_verbatim_inside_fences(db_session, hostile_bug) -> None:
    markdown = render_report(db_session, hostile_bug).markdown
    assert HOSTILE_OVERRIDES["description"] in markdown
    assert HOSTILE_OVERRIDES["reproduction_steps"] in markdown
    assert re.search(r"^````+text$", markdown, re.M)


def test_table_cells_and_heading(db_session, hostile_bug) -> None:
    markdown = render_report(db_session, hostile_bug).markdown
    lines = markdown.split("\n")
    assert lines[0] == '# Crash on \\`save\\` \\| \\<b\\>bold\\</b\\> says "no"'
    profile = "Backend \\| Platform engineer (Senior), skills: Python, SQL \\| NoSQL"
    assert f"| Assignee profile | {profile} |" in lines
    assert "| Notes | Check \\`retry\\|backoff\\` and \\<config\\>. |" in lines


def test_diagram_is_valid_with_the_encoded_title(db_session, hostile_bug) -> None:
    markdown = render_report(db_session, hostile_bug).markdown
    diagram = re.search(r"```mermaid\n(.*?)\n```", markdown, re.S).group(1)
    validate(diagram)
    assert (
        f'bug["Bug {hostile_bug}: Crash on #96;save#96; #124; #60;b#62;bold#60;/b#62;'
        ' says #34;no#34;"]' in diagram
    )
