"""Bug endpoints: create, list, detail, edit, similar, runs, reopen and report."""

from __future__ import annotations

import pytest
from sqlalchemy import Engine

from api_helpers import BASE, PROCESSED_HTML, PROCESSED_MARKDOWN, create_body, index_everything
from bugflow.db.engine import session_factory
from bugflow.db.models import Bug, BugReport
from tests_helpers import add_bug, bug_row, result_row_counts, stored_status

pytestmark = pytest.mark.integration

MISSING = 999999


def count_bugs(engine: Engine) -> int:
    with session_factory(engine)() as session:
        return session.query(Bug).count()


# --- create ---


def test_create_bug(api, initialized_db):
    body = create_body(
        title="Login page shows blank screen",
        environment="staging",
        reporting_team="qa",
    )
    response = api.post(f"{BASE}/bugs", json=body)
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "open"
    assert (data["title"], data["environment"], data["reporting_team"]) == (
        "Login page shows blank screen",
        "staging",
        "qa",
    )
    assert count_bugs(initialized_db) == 1


def test_create_invalid_fields_report_per_field(api, initialized_db):
    response = api.post(f"{BASE}/bugs", json=create_body(title="t" * 121, environment="moon"))
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    details = {item["field"]: item["message"] for item in error["details"]}
    assert set(details) == {"title", "environment"}
    assert "production, staging, development, testing" in details["environment"]
    assert count_bugs(initialized_db) == 0


def test_create_without_body_and_malformed_json(api, initialized_db):
    missing = api.post(f"{BASE}/bugs")
    assert missing.status_code == 422
    assert [d["field"] for d in missing.json()["error"]["details"]] == ["body"]
    broken = api.post(
        f"{BASE}/bugs", content="{not json", headers={"Content-Type": "application/json"}
    )
    assert broken.status_code == 400
    assert broken.json()["error"]["code"] == "bad_request"
    assert count_bugs(initialized_db) == 0


# --- list ---


def test_list_default_and_filter(api, initialized_db, processed_state):
    add_bug(initialized_db)
    add_bug(initialized_db, status="processing", title="Busy checkout bug")
    everything = api.get(f"{BASE}/bugs").json()
    assert (everything["total"], everything["page"], everything["page_size"]) == (3, 1, 20)
    processed = api.get(f"{BASE}/bugs", params={"status": "processed"}).json()
    assert processed["total"] == 1
    item = processed["items"][0]
    assert (item["id"], item["component"], item["severity"]) == (
        processed_state["bug_id"],
        "frontend",
        "major",
    )


def test_list_page_size_above_maximum(api):
    response = api.get(f"{BASE}/bugs", params={"page_size": 101})
    assert response.status_code == 422
    assert "page_size" in [d["field"] for d in response.json()["error"]["details"]]


# --- detail ---


def test_detail_of_a_processed_bug(api, processed_state):
    data = api.get(f"{BASE}/bugs/{processed_state['bug_id']}").json()
    assert data["status"] == "processed"
    results = data["results"]
    assert results["component"]["component"] == "frontend"
    assert results["severity"]["severity"] == "major"
    assert results["plan"]["resolution_status"] == "planned"
    assert results["plan"]["assigned_team"] == "frontend"
    assert results["plan"]["target_days"] == 5
    assert results["plan"]["priority"] == "high"
    assert results["analysis"]["root_cause"] == "Handler missing"
    assert results["report"]["has_markdown"] is True
    assert results["report"]["has_html"] is True
    assert results["report"]["executive_summary"]
    assert data["latest_run"]["id"] == processed_state["run_id"]
    assert data["latest_run"]["status"] == "succeeded"


def test_detail_of_an_open_bug_has_no_results(api, open_bug):
    data = api.get(f"{BASE}/bugs/{open_bug}").json()
    assert data["status"] == "open"
    assert data["results"] == {
        "component": None,
        "severity": None,
        "analysis": None,
        "plan": None,
        "report": None,
    }
    assert data["latest_run"] is None


def test_detail_of_an_unknown_bug(api):
    response = api.get(f"{BASE}/bugs/{MISSING}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
    assert response.json()["error"]["message"] == "Bug 999999 not found"


# --- edit ---


def test_edit_an_open_bug(api, open_bug):
    response = api.patch(f"{BASE}/bugs/{open_bug}", json={"title": "Checkout button dead"})
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Checkout button dead"
    assert data["status"] == "open"
    assert data["system_version"] == "web 3.8.2"


def test_edit_a_processed_bug_is_a_conflict(api, initialized_db, processed_state):
    before = bug_row(initialized_db, processed_state["bug_id"])
    response = api.patch(f"{BASE}/bugs/{processed_state['bug_id']}", json={"title": "New title"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "state_conflict"
    assert bug_row(initialized_db, processed_state["bug_id"]) == before


def test_empty_edit_is_rejected(api, open_bug):
    response = api.patch(f"{BASE}/bugs/{open_bug}", json={})
    assert response.status_code == 422
    messages = [d["message"] for d in response.json()["error"]["details"]]
    assert "at least one field is required" in messages


def test_edit_an_unknown_bug(api):
    assert api.patch(f"{BASE}/bugs/{MISSING}", json={"title": "x"}).status_code == 404


# --- similar ---


def test_similar_excludes_the_bug_itself(
    api, initialized_db, open_bug, second_open_bug, processed_state, llm_client
):
    index_everything(initialized_db, llm_client)
    response = api.get(f"{BASE}/bugs/{open_bug}/similar", params={"limit": 5})
    assert response.status_code == 200
    items = response.json()["items"]
    assert 0 < len(items) <= 2
    assert open_bug not in [item["bug_id"] for item in items]
    assert [item["score"] for item in items] == sorted((i["score"] for i in items), reverse=True)
    assert set(items[0]) == {"bug_id", "title", "status", "score"}


def test_similar_without_a_key(make_api, open_bug):
    client = make_api(env={"OPENAI_API_KEY": None})
    response = client.get(f"{BASE}/bugs/{open_bug}/similar")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "service_unavailable"
    assert response.json()["error"]["message"] == "OPENAI_API_KEY is not set"


# --- runs of a bug ---


def test_bug_runs(api, processed_state):
    items = api.get(f"{BASE}/bugs/{processed_state['bug_id']}/runs").json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == processed_state["run_id"]
    assert (items[0]["type"], items[0]["status"]) == ("triage", "succeeded")
    assert (items[0]["progress_done"], items[0]["progress_total"]) == (5, 5)


def test_bug_runs_of_an_unknown_bug(api):
    assert api.get(f"{BASE}/bugs/{MISSING}/runs").status_code == 404


# --- reopen ---


def test_confirmed_reopen(api, initialized_db, processed_state):
    bug_id = processed_state["bug_id"]
    response = api.post(f"{BASE}/bugs/{bug_id}/reopen", json={"confirm": True})
    assert response.status_code == 200
    assert response.json()["status"] == "open"
    assert set(result_row_counts(initialized_db, bug_id).values()) == {0}
    runs = api.get(f"{BASE}/bugs/{bug_id}/runs").json()["items"]
    assert [run["id"] for run in runs] == [processed_state["run_id"]]
    assert len(api.get(f"{BASE}/runs/{processed_state['run_id']}").json()["steps"]) == 5


def test_unconfirmed_reopen_changes_nothing(api, initialized_db, processed_state):
    bug_id = processed_state["bug_id"]
    response = api.post(f"{BASE}/bugs/{bug_id}/reopen", json={"confirm": False})
    assert response.status_code == 422
    assert "confirm" in [d["field"] for d in response.json()["error"]["details"]]
    assert stored_status(initialized_db, bug_id) == "processed"
    assert set(result_row_counts(initialized_db, bug_id).values()) == {1}


def test_reopen_of_a_processing_bug(api, initialized_db):
    bug_id = add_bug(initialized_db, status="processing", title="Busy checkout bug")
    response = api.post(f"{BASE}/bugs/{bug_id}/reopen", json={"confirm": True})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "state_conflict"
    assert stored_status(initialized_db, bug_id) == "processing"


def test_reopen_of_an_unknown_bug(api):
    response = api.post(f"{BASE}/bugs/{MISSING}/reopen", json={"confirm": True})
    assert response.status_code == 404


# --- report ---


def test_markdown_report(api, processed_state):
    response = api.get(f"{BASE}/bugs/{processed_state['bug_id']}/report", params={"format": "md"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.text == PROCESSED_MARKDOWN
    assert response.text.startswith("# Processed checkout bug")


def test_html_report(api, processed_state):
    response = api.get(f"{BASE}/bugs/{processed_state['bug_id']}/report", params={"format": "html"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.text == PROCESSED_HTML


def test_json_report_is_the_default(api, processed_state):
    response = api.get(f"{BASE}/bugs/{processed_state['bug_id']}/report")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {
        "bug_id": processed_state["bug_id"],
        "markdown": PROCESSED_MARKDOWN,
        "html": PROCESSED_HTML,
    }


def test_report_of_an_unprocessed_bug(api, open_bug):
    response = api.get(f"{BASE}/bugs/{open_bug}/report", params={"format": "md"})
    assert response.status_code == 404
    assert response.json()["error"]["message"] == f"Bug {open_bug} has no report; triage it first"


def test_report_with_an_unknown_format(api, processed_state):
    response = api.get(f"{BASE}/bugs/{processed_state['bug_id']}/report", params={"format": "pdf"})
    assert response.status_code == 422
    assert "format" in [d["field"] for d in response.json()["error"]["details"]]


def test_missing_report_text_is_rendered_and_committed(api, initialized_db, processed_state):
    bug_id = processed_state["bug_id"]
    with session_factory(initialized_db)() as session:
        row = session.get(BugReport, bug_id)
        row.markdown = None
        row.html = None
        session.commit()
    response = api.get(f"{BASE}/bugs/{bug_id}/report", params={"format": "md"})
    assert response.status_code == 200
    assert response.text.startswith("# Processed checkout bug")
    with session_factory(initialized_db)() as session:
        assert session.get(BugReport, bug_id).markdown == response.text
