"""Mermaid flow diagram with a fixed five-node shape; only encoded label text varies."""

from __future__ import annotations

from bugflow.enums import label_of
from bugflow.reports.data import ReportData
from bugflow.reports.escape import mermaid_label


def build_flow_diagram(data: ReportData) -> str:
    """Bug -> component -> severity -> assigned team -> resolution status."""
    bug = mermaid_label(f"Bug {data.bug_id}: {data.title}")
    component = mermaid_label(f"Component: {label_of(data.component)}")
    severity = mermaid_label(f"Severity: {label_of(data.severity)}")
    team = mermaid_label(f"Team: {label_of(data.assigned_team)}")
    resolution = mermaid_label(f"Resolution: {label_of(data.resolution_status)}")
    return "\n".join(
        [
            "flowchart LR",
            f'    bug["{bug}"] --> component["{component}"]',
            f'    component --> severity["{severity}"]',
            f'    severity --> team["{team}"]',
            f'    team --> resolution["{resolution}"]',
        ]
    )
