from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from bugflow.db.models import Bug, ComponentClassification, Run, SeverityClassification
from bugflow.enums import BugStatus, Component, Environment, Severity, Team
from bugflow.services.bugs import list_bugs
from bugflow.services.errors import ValidationFailedError
from bugflow.services.schemas import BugListQuery, validate_payload

pytestmark = pytest.mark.integration

COMPONENTS = {1: "backend", 2: "backend", 3: "frontend", 4: "frontend", 5: "security"}
SEVERITIES = {1: "critical", 2: "major", 3: "minor", 4: "critical", 5: "major"}


@pytest.fixture
def listing(session):
    base = datetime(2026, 1, 1, 12, tzinfo=UTC)
    run = Run(type="triage", status="succeeded", finished_at=base)
    session.add(run)
    session.flush()
    for n in range(1, 26):
        title = "Listbug 08 Checkout freezes" if n == 8 else f"Listbug {n:02d}"
        description = (
            "The checkout page is blank after login" if n == 12 else f"Fixture description {n:02d}"
        )
        status = "processed" if n <= 5 else "failed" if n <= 7 else "open"
        session.add(
            Bug(
                id=n,
                title=title,
                description=description,
                reproduction_steps="Steps",
                system_version="web 1.0.0",
                environment="production" if n % 2 else "staging",
                reporting_team="qa" if n <= 10 else "support",
                status=status,
                opened_at=base + timedelta(days=n - 1),
            )
        )
    session.flush()
    for n, component in COMPONENTS.items():
        session.add(
            ComponentClassification(bug_id=n, run_id=run.id, component=component, justification="j")
        )
        session.add(
            SeverityClassification(
                bug_id=n, run_id=run.id, severity=SEVERITIES[n], justification="j", user_impact="u"
            )
        )
    session.commit()
    return session


def titles(page):
    return [item.title for item in page.items]


def query(**kwargs):
    return validate_payload(BugListQuery, kwargs)


def test_default_page(listing):
    page = list_bugs(listing, BugListQuery())
    assert len(page.items) == 20 and page.total == 25 and (page.page, page.page_size) == (1, 20)
    assert titles(page)[0] == "Listbug 25" and titles(page)[-1] == "Listbug 06"


def test_second_page_and_custom_size(listing):
    assert titles(list_bugs(listing, query(page=2))) == [
        f"Listbug {n:02d}" for n in range(5, 0, -1)
    ]
    page = list_bugs(listing, query(page_size=5, page=3))
    assert titles(page) == ["Listbug 15", "Listbug 14", "Listbug 13", "Listbug 12", "Listbug 11"]
    assert page.total == 25


def test_page_past_the_end(listing):
    page = list_bugs(listing, query(page=3))
    assert page.items == [] and page.total == 25


def test_maximum_page_size(listing):
    page = list_bugs(listing, query(page_size=100))
    assert len(page.items) == 25 and page.total == 25


def test_invalid_paging_rejected():
    for payload, field in [({"page_size": 101}, "page_size"), ({"page": 0}, "page")]:
        with pytest.raises(ValidationFailedError) as caught:
            validate_payload(BugListQuery, payload)
        assert caught.value.field_errors[0].field == field


def test_filter_by_status(listing):
    page = list_bugs(listing, BugListQuery(status=BugStatus.FAILED))
    assert page.total == 2 and titles(page) == ["Listbug 07", "Listbug 06"]


def test_filter_by_component(listing):
    page = list_bugs(listing, BugListQuery(component=Component.BACKEND))
    assert page.total == 2 and titles(page) == ["Listbug 02", "Listbug 01"]


def test_filter_by_severity(listing):
    page = list_bugs(listing, BugListQuery(severity=Severity.CRITICAL))
    assert page.total == 2 and titles(page) == ["Listbug 04", "Listbug 01"]


def test_combined_filters(listing):
    page = list_bugs(
        listing, BugListQuery(environment=Environment.PRODUCTION, reporting_team=Team.QA)
    )
    assert page.total == 5
    assert titles(page) == [f"Listbug {n:02d}" for n in (9, 7, 5, 3, 1)]


@pytest.mark.parametrize("search", ["checkout", "CHECKOUT", "  checkout  ".strip()])
def test_search_in_title_and_description_ignores_case(listing, search):
    page = list_bugs(listing, BugListQuery(search=search))
    assert page.total == 2
    assert titles(page) == ["Listbug 12", "Listbug 08 Checkout freezes"]


@pytest.mark.parametrize("search", ["zzz-no-match", "%", "_", "\\", "Listbug 0_"])
def test_search_without_match_and_wildcards_are_literal(listing, search):
    page = list_bugs(listing, BugListQuery(search=search))
    assert page.items == [] and page.total == 0


def test_blank_search_means_no_search(listing):
    assert list_bugs(listing, BugListQuery(search="   ")).total == 25


def test_sort_by_opened_at_both_directions(listing):
    asc = list_bugs(listing, query(sort_dir="asc", page_size=25))
    assert titles(asc)[0] == "Listbug 01" and titles(asc)[-1] == "Listbug 25"
    desc = list_bugs(listing, query(sort_dir="desc", page_size=25))
    assert titles(desc)[0] == "Listbug 25"


def test_sort_by_status_follows_lifecycle(listing):
    page = list_bugs(listing, query(sort_by="status", sort_dir="asc", page_size=25))
    statuses = [item.status.value for item in page.items]
    assert statuses == ["open"] * 18 + ["processed"] * 5 + ["failed"] * 2
    assert titles(page)[0] == "Listbug 25"  # tie-break: opened_at descending
    desc = list_bugs(listing, query(sort_by="status", sort_dir="desc", page_size=25))
    assert desc.items[0].status is BugStatus.FAILED


def test_sort_by_severity_both_directions(listing):
    asc = list_bugs(listing, query(sort_by="severity", sort_dir="asc", page_size=25))
    got = [item.severity.value if item.severity else None for item in asc.items]
    assert got == ["critical"] * 2 + ["major"] * 2 + ["minor"] + [None] * 20
    desc = list_bugs(listing, query(sort_by="severity", sort_dir="desc", page_size=25))
    got = [item.severity.value if item.severity else None for item in desc.items]
    assert got == ["minor"] + ["major"] * 2 + ["critical"] * 2 + [None] * 20


def test_items_carry_component_and_severity(listing):
    page = list_bugs(listing, query(sort_dir="asc", page_size=25))
    first, tenth = page.items[0], page.items[9]
    assert (first.component, first.severity) == (Component.BACKEND, Severity.CRITICAL)
    assert tenth.title == "Listbug 10" and tenth.component is None and tenth.severity is None


def test_total_ignores_paging_and_counts_each_bug_once(listing):
    assert list_bugs(listing, query(page_size=1)).total == 25
    assert listing.scalar(text("SELECT count(*) FROM bugs")) == 25
