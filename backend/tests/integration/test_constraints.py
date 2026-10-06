import json

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DataError, IntegrityError

pytestmark = pytest.mark.integration

BUG_INSERT = (
    "INSERT INTO bugs (title, description, reproduction_steps, system_version, environment, "
    "reporting_team, status) VALUES (:title, 'd', 's', 'v1', :environment, :team, :status)"
)

PROFILE = json.dumps({"role": "engineer", "seniority": "senior", "skills": ["python"]})


def _bug_params(**overrides):
    params = {
        "title": "t",
        "environment": "testing",
        "team": "qa",
        "status": "open",
    }
    params.update(overrides)
    return params


def _plan_params(bug_id, run_id, **overrides):
    params = {
        "bug_id": bug_id,
        "run_id": run_id,
        "status": "planned",
        "team": "backend",
        "profile": PROFILE,
        "days": 5,
        "priority": "high",
    }
    params.update(overrides)
    return params


PLAN_INSERT = (
    "INSERT INTO resolution_plans (bug_id, run_id, resolution_status, assigned_team, "
    "assignee_profile, target_days, priority) VALUES "
    "(:bug_id, :run_id, :status, :team, CAST(:profile AS jsonb), :days, :priority)"
)


def _violation(engine, statement, params, error=IntegrityError):
    with pytest.raises(error) as info:
        with engine.begin() as connection:
            connection.execute(text(statement), params)
    return info.value.orig


def _expect_check(engine, statement, params, constraint):
    orig = _violation(engine, statement, params)
    assert orig.sqlstate == "23514"
    assert orig.diag.constraint_name == constraint


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"environment": "sandbox"}, "ck_bugs_environment"),
        ({"team": "marketing"}, "ck_bugs_reporting_team"),
        ({"status": "closed"}, "ck_bugs_status"),
    ],
)
def test_bug_enum_columns_reject_unknown_codes(initialized_db, overrides, constraint):
    _expect_check(initialized_db, BUG_INSERT, _bug_params(**overrides), constraint)
    with initialized_db.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM bugs")).scalar_one() == 0


@pytest.mark.parametrize(
    ("statement", "constraint"),
    [
        ("INSERT INTO runs (type) VALUES ('deploy')", "ck_runs_type"),
        ("INSERT INTO runs (type, status) VALUES ('triage', 'done')", "ck_runs_status"),
        (
            "INSERT INTO runs (type, progress_done) VALUES ('triage', -1)",
            "ck_runs_progress_done",
        ),
        (
            "INSERT INTO runs (type, progress_total) VALUES ('triage', -1)",
            "ck_runs_progress_total",
        ),
    ],
)
def test_run_checks(initialized_db, statement, constraint):
    _expect_check(initialized_db, statement, {}, constraint)


@pytest.mark.parametrize(
    ("statement", "constraint"),
    [
        (
            "INSERT INTO run_steps (run_id, position, agent_key, status) "
            "VALUES (:run_id, 1, 'ag1', 'waiting')",
            "ck_run_steps_status",
        ),
        (
            "INSERT INTO run_steps (run_id, position, agent_key) VALUES (:run_id, 0, 'ag1')",
            "ck_run_steps_position",
        ),
        (
            "INSERT INTO run_steps (run_id, position, agent_key, duration_ms) "
            "VALUES (:run_id, 1, 'ag1', -5)",
            "ck_run_steps_duration_ms",
        ),
    ],
)
def test_run_step_checks(initialized_db, probe_run, statement, constraint):
    _expect_check(initialized_db, statement, {"run_id": probe_run}, constraint)


@pytest.mark.parametrize(
    ("table", "column", "bad_value"),
    [
        ("component_classifications", "component", "mobile"),
        ("severity_classifications", "severity", "high"),
    ],
)
def test_classification_enum_columns_reject_unknown_codes(
    initialized_db, probe_bug, probe_run, table, column, bad_value
):
    extra = ", user_impact" if table == "severity_classifications" else ""
    extra_value = ", 'impact'" if table == "severity_classifications" else ""
    statement = (
        f"INSERT INTO {table} (bug_id, run_id, {column}, justification{extra}) "  # noqa: S608
        f"VALUES (:bug_id, :run_id, :value, 'j'{extra_value})"
    )
    params = {"bug_id": probe_bug, "run_id": probe_run, "value": bad_value}
    _expect_check(initialized_db, statement, params, f"ck_{table}_{column}")


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"status": "resolved"}, "ck_resolution_plans_resolution_status"),
        ({"team": "marketing"}, "ck_resolution_plans_assigned_team"),
        ({"priority": "critical"}, "ck_resolution_plans_priority"),
        (
            {"profile": json.dumps({"role": "r", "seniority": "principal", "skills": []})},
            "ck_resolution_plans_assignee_seniority",
        ),
        ({"profile": json.dumps(["x"])}, "ck_resolution_plans_assignee_profile"),
        ({"days": 0}, "ck_resolution_plans_target_days"),
        ({"days": 91}, "ck_resolution_plans_target_days"),
    ],
)
def test_resolution_plan_rejections(initialized_db, probe_bug, probe_run, overrides, constraint):
    params = _plan_params(probe_bug, probe_run, **overrides)
    _expect_check(initialized_db, PLAN_INSERT, params, constraint)


def test_valid_codes_accepted(initialized_db, probe_bug, probe_run):
    with initialized_db.begin() as connection:
        connection.execute(text(BUG_INSERT), _bug_params(title="ok", status="processing"))
        connection.execute(text(PLAN_INSERT), _plan_params(probe_bug, probe_run))


def test_target_days_bounds(initialized_db, probe_bug, probe_run):
    for days in (1, 90):
        with initialized_db.begin() as connection:
            connection.execute(text("DELETE FROM resolution_plans"))
            connection.execute(text(PLAN_INSERT), _plan_params(probe_bug, probe_run, days=days))


def test_bug_defaults(initialized_db):
    with initialized_db.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO bugs (title, description, reproduction_steps, system_version, "
                "environment, reporting_team) VALUES ('t', 'd', 's', 'v', 'testing', 'qa')"
            )
        )
        row = connection.execute(text("SELECT status, opened_at, updated_at FROM bugs")).one()
    assert row.status == "open"
    assert row.opened_at is not None
    assert row.updated_at is not None


def test_title_over_length_rejected(initialized_db):
    orig = _violation(initialized_db, BUG_INSERT, _bug_params(title="x" * 121), DataError)
    assert orig.sqlstate == "22001"
    with initialized_db.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM bugs")).scalar_one() == 0


def test_description_over_length_rejected(initialized_db):
    statement = BUG_INSERT.replace("'d'", ":description")
    params = _bug_params() | {"description": "x" * 5001}
    assert _violation(initialized_db, statement, params, DataError).sqlstate == "22001"


def test_embedding_dimension_enforced(initialized_db, probe_bug):
    statement = (
        "INSERT INTO bug_embeddings (bug_id, embedding, text_hash) "
        "VALUES (:bug_id, CAST('[1,2,3]' AS vector), 'h')"
    )
    orig = _violation(initialized_db, statement, {"bug_id": probe_bug}, Exception)
    assert "dimensions" in str(orig)
    with initialized_db.connect() as connection:
        count = connection.execute(text("SELECT count(*) FROM bug_embeddings")).scalar_one()
    assert count == 0


def test_one_result_row_per_bug(initialized_db, probe_bug, probe_run):
    statement = (
        "INSERT INTO component_classifications (bug_id, run_id, component, justification) "
        "VALUES (:bug_id, :run_id, 'backend', 'j')"
    )
    params = {"bug_id": probe_bug, "run_id": probe_run}
    with initialized_db.begin() as connection:
        connection.execute(text(statement), params)
    orig = _violation(initialized_db, statement, params)
    assert orig.sqlstate == "23505"
    assert orig.diag.constraint_name == "pk_component_classifications"
    with initialized_db.connect() as connection:
        count = connection.execute(
            text("SELECT count(*) FROM component_classifications")
        ).scalar_one()
    assert count == 1


@pytest.mark.parametrize(
    ("table", "column"),
    [
        ("technical_analyses", "debugging_approach"),
        ("technical_analyses", "side_effects"),
        ("technical_analyses", "referenced_similar_bug_ids"),
        ("bug_reports", "key_takeaways"),
        ("bug_reports", "next_steps"),
    ],
)
def test_json_array_columns_reject_objects(initialized_db, probe_bug, probe_run, table, column):
    if table == "technical_analyses":
        columns = {
            "debugging_approach": "[]",
            "side_effects": "[]",
            "referenced_similar_bug_ids": "[]",
        }
        fixed = "root_cause, technical_impact, proposed_solution"
        fixed_values = "'r', 'i', 's'"
    else:
        columns = {"key_takeaways": "[]", "next_steps": "[]"}
        fixed = "executive_summary"
        fixed_values = "'e'"
    columns[column] = "{}"
    names = ", ".join(columns)
    values = ", ".join(f"CAST('{value}' AS jsonb)" for value in columns.values())
    statement = (
        f"INSERT INTO {table} (bug_id, run_id, {fixed}, {names}) "  # noqa: S608
        f"VALUES (:bug_id, :run_id, {fixed_values}, {values})"
    )
    _expect_check(
        initialized_db,
        statement,
        {"bug_id": probe_bug, "run_id": probe_run},
        f"ck_{table}_{column}",
    )


def test_run_step_position_unique(initialized_db, probe_run):
    statement = "INSERT INTO run_steps (run_id, position, agent_key) VALUES (:run_id, 1, 'ag1')"
    with initialized_db.begin() as connection:
        connection.execute(text(statement), {"run_id": probe_run})
    orig = _violation(initialized_db, statement, {"run_id": probe_run})
    assert orig.sqlstate == "23505"
    assert orig.diag.constraint_name == "uq_run_steps_run_id_position"
