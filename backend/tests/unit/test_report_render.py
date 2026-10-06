"""Rendering of a plain `ReportData` without a database."""

from __future__ import annotations

from html.parser import HTMLParser

import pytest

from bugflow.enums import ResolutionStatus, label_of
from bugflow.reports.render import render_html, render_markdown
from report_helpers import HOSTILE_OVERRIDES, sample_report_data


class Collector(HTMLParser):
    VOID = {"meta", "br", "hr", "img", "input", "link"}

    def __init__(self) -> None:
        super().__init__()
        self.stack: list[str] = []
        self.scripts = 0
        self.unbalanced = False
        self.elements: list[str] = []
        self.texts: dict[str, str] = {}
        self._capture: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.elements.append(tag)
        if tag == "script":
            self.scripts += 1
        if tag in self.VOID:
            return
        self.stack.append(tag)
        classes = dict(attrs).get("class")
        if tag == "title":
            self._capture = "title"
        elif tag == "pre" and classes:
            self._capture = classes

    def handle_endtag(self, tag: str) -> None:
        if tag in self.VOID:
            return
        if not self.stack or self.stack.pop() != tag:
            self.unbalanced = True
        self._capture = None

    def handle_data(self, data: str) -> None:
        if self._capture:
            self.texts[self._capture] = self.texts.get(self._capture, "") + data


def parse(html: str) -> Collector:
    collector = Collector()
    collector.feed(html)
    collector.close()
    return collector


def test_markdown_first_line_and_layout() -> None:
    text = render_markdown(sample_report_data())
    assert text.startswith("# Checkout button does nothing on Safari 17\n")
    assert text.endswith("\n") and not text.endswith("\n\n")
    headings = [line for line in text.split("\n") if line.startswith("## ")]
    assert headings == [
        "## Bug details",
        "## Description",
        "## Reproduction steps",
        "## Classification",
        "## Technical analysis",
        "## Resolution plan",
        "## Flow diagram",
        "## Summary",
    ]


def test_description_and_steps_verbatim_inside_fences() -> None:
    data = sample_report_data()
    text = render_markdown(data)
    assert f"```text\n{data.description}\n```" in text
    assert f"```text\n{data.reproduction_steps}\n```" in text


def test_table_rows_are_exact() -> None:
    text = render_markdown(sample_report_data())
    for row in (
        "| Bug ID | 3 |",
        "| Opened | 2026-03-01 10:00 UTC |",
        "| Report completed | 2026-03-30 |",
        "| Resolution status | Needs info |",
        "| Assignee profile | Backend engineer (Senior), skills: Python, PostgreSQL |",
        "| Priority | High |",
        "| Target | 5 days |",
        "| Deadline | 2026-04-04 |",
        "| Notes | Waiting for browser logs. |",
    ):
        assert row in text.split("\n")


@pytest.mark.parametrize("status", list(ResolutionStatus))
def test_status_label_for_each_resolution_status(status: ResolutionStatus) -> None:
    data = sample_report_data(resolution_status=status)
    assert f"| Resolution status | {label_of(status)} |" in (render_markdown(data))
    assert "resolved" not in render_markdown(data).lower()
    assert "resolved" not in render_html(data).lower()


def test_empty_lists_and_notes_use_fixed_text() -> None:
    data = sample_report_data(side_effects=(), similar_bugs=(), notes="")
    text = render_markdown(data)
    assert "None identified" in text
    assert "No similar bugs referenced" in text
    assert "| Notes | None |" in text


def test_similar_bug_listing_and_missing_title() -> None:
    text = render_markdown(sample_report_data())
    assert "- #2 Payment form freezes on Safari 17" in text
    from bugflow.reports.data import SimilarBug

    gone = render_markdown(sample_report_data(similar_bugs=(SimilarBug(id=9, title=None),)))
    assert "- #9\n" in gone


def test_singular_day() -> None:
    assert "| Target | 1 day |" in render_markdown(sample_report_data(target_days=1))
    assert "<td>1 day</td>" in render_html(sample_report_data(target_days=1))


def test_html_structure() -> None:
    data = sample_report_data()
    html = render_html(data)
    assert html.startswith("<!DOCTYPE html>")
    parsed = parse(html)
    assert parsed.scripts == 1
    assert not parsed.unbalanced and not parsed.stack
    assert parsed.texts["description"] == data.description
    assert parsed.texts["title"] == data.title
    assert '<pre class="mermaid">' in html


def test_hostile_text_is_escaped() -> None:
    data = sample_report_data(**HOSTILE_OVERRIDES)
    html = render_html(data)
    parsed = parse(html)
    assert parsed.scripts == 1
    assert "b" not in parsed.elements and "img" not in parsed.elements
    assert parsed.texts["description"] == data.description
    assert parsed.texts["title"] == data.title
    assert not parsed.unbalanced
    markdown = render_markdown(data)
    assert markdown.split("\n")[0] == '# Crash on \\`save\\` \\| \\<b\\>bold\\</b\\> says "no"'
    assert "````text\n" in markdown


def test_output_is_deterministic() -> None:
    data = sample_report_data()
    assert render_markdown(data) == render_markdown(data)
    assert render_html(data) == render_html(data)
