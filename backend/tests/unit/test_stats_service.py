"""Zero filling of the dashboard counts."""

from __future__ import annotations

from bugflow.enums import BugStatus, Component, Severity, codes
from bugflow.services.stats import assemble_stats, zero_filled


def test_every_code_is_present_with_zero():
    stats = assemble_stats([], [], [])
    assert stats.total == 0
    assert list(stats.by_status) == codes(BugStatus)
    assert list(stats.by_component) == codes(Component)
    assert list(stats.by_severity) == codes(Severity)
    assert set(stats.by_status.values()) == {0}


def test_counts_are_assembled_and_total_is_the_status_sum():
    stats = assemble_stats(
        [("open", 18), ("processed", 2)], [("frontend", 1), ("backend", 1)], [("major", 2)]
    )
    assert stats.total == 20
    assert stats.by_status["open"] == 18
    assert stats.by_status["failed"] == 0
    assert stats.by_component["frontend"] == 1
    assert stats.by_component["database"] == 0
    assert stats.by_severity == {"critical": 0, "major": 2, "minor": 0}


def test_unknown_codes_are_ignored():
    assert zero_filled(Severity, [("bogus", 3)]) == {"critical": 0, "major": 0, "minor": 0}
