"""Flow diagram shape and the validator over the full enum cross product."""

from __future__ import annotations

import itertools
import re

import pytest

from bugflow.enums import Component, ResolutionStatus, Severity, Team, label_of
from bugflow.reports.diagram import build_flow_diagram
from bugflow.reports.escape import decode_mermaid_label
from report_helpers import sample_report_data

RAW_FORBIDDEN = set('"<>|()[]{}%;`')
RESERVED = {"end", "graph", "subgraph", "flowchart", "click", "style", "class", "default"}
LINE_PATTERNS = [
    re.compile(r'^    (bug)\["([^"]*)"\] --> (component)\["([^"]*)"\]$'),
    re.compile(r'^    (component) --> (severity)\["([^"]*)"\]$'),
    re.compile(r'^    (severity) --> (team)\["([^"]*)"\]$'),
    re.compile(r'^    (team) --> (resolution)\["([^"]*)"\]$'),
]


def validate(diagram: str) -> list[str]:
    """Strict structural validator; returns the decoded labels in node order."""
    lines = diagram.split("\n")
    assert lines[0] == "flowchart LR"
    assert len(lines) == 5
    labels: list[str] = []
    for line, pattern in zip(lines[1:], LINE_PATTERNS, strict=True):
        match = pattern.fullmatch(line)
        assert match, line
        for node_id in (g for g in match.groups() if g in {"bug", "component", "severity"}):
            assert node_id not in RESERVED
        quoted = re.findall(r'"([^"]*)"', line)
        assert line.count('"') == 2 * len(quoted)
        for label in quoted:
            stripped = re.sub(r"#\d+;", "", label)
            assert not RAW_FORBIDDEN & set(stripped), label
            assert "%%" not in label
            assert "#" not in stripped, label
            assert "&" not in label
            labels.append(decode_mermaid_label(label))
    return labels


def test_exact_diagram_for_a_plain_case() -> None:
    assert build_flow_diagram(sample_report_data()) == "\n".join(
        [
            "flowchart LR",
            '    bug["Bug 3: Checkout button does nothing on Safari 17"]'
            ' --> component["Component: Backend"]',
            '    component --> severity["Severity: Major"]',
            '    severity --> team["Team: Backend"]',
            '    team --> resolution["Resolution: Needs info"]',
        ]
    )


def test_every_enum_combination_is_valid() -> None:
    combinations = list(itertools.product(Component, Severity, Team, ResolutionStatus))
    assert len(combinations) == 768
    for component, severity, team, status in combinations:
        data = sample_report_data(
            component=component, severity=severity, assigned_team=team, resolution_status=status
        )
        labels = validate(build_flow_diagram(data))
        assert labels[1:] == [
            f"Component: {label_of(component)}",
            f"Severity: {label_of(severity)}",
            f"Team: {label_of(team)}",
            f"Resolution: {label_of(status)}",
        ]


@pytest.mark.parametrize(
    "title",
    [
        'Crash on `save` | <b>bold</b> says "no"',
        "%% comment\nend [x] {y} (z); #1; & 'q'",
        "x" * 120,
        "tab\tand\x00control",
    ],
)
def test_hostile_and_long_titles(title: str) -> None:
    labels = validate(build_flow_diagram(sample_report_data(title=title)))
    assert labels[0].startswith("Bug 3: ")


def test_special_labels_are_present_and_valid() -> None:
    data = sample_report_data(
        component=Component.UI_UX, resolution_status=ResolutionStatus.WONT_FIX
    )
    diagram = build_flow_diagram(data)
    assert 'component["Component: UI/UX"]' in diagram
    assert 'resolution["Resolution: Won#39;t fix"]' in diagram
    labels = validate(diagram)
    assert labels[1] == "Component: UI/UX"
    assert labels[4] == "Resolution: Won't fix"
