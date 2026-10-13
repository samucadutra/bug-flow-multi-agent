"""Each parity row works through the API with the same effect as its CLI command."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from sqlalchemy import Engine, text

from api_helpers import BASE, PROCESSED_MARKDOWN, add_processed_bug, index_everything
from bugflow.db.engine import session_factory
from bugflow.services.db_admin import init_db, seed_db
from mocks.fake_openai_server import VALID_KEY
from tests_helpers import add_bug, add_bug_with_history

pytestmark = pytest.mark.integration

BACKEND = Path(__file__).resolve().parents[2]
BINARY = Path(sys.executable).parent / "bugflow"


@pytest.fixture
def cli(test_engine, stand_in) -> Callable[..., subprocess.CompletedProcess[str]]:
    url = test_engine.url.render_as_string(hide_password=False)

    def run(*args: str) -> subprocess.CompletedProcess[str]:
        env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith(("DATABASE_", "TEST_DATABASE_", "OPENAI_", "LOG_LEVEL"))
        }
        env.update(
            DATABASE_URL=url, OPENAI_BASE_URL=stand_in.base_url, OPENAI_API_KEY=VALID_KEY, TZ="UTC"
        )
        return subprocess.run(
            [str(BINARY), *args],
            cwd=BACKEND,
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=180,
        )

    return run


def rebuild(engine: Engine, builder: Callable[[], object] | None = None) -> object:
    """Drop everything, initialize the schema and run the builder."""
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    engine.dispose()
    init_db(engine)
    return builder() if builder is not None else None


def snapshot(engine: Engine) -> dict[str, object]:
    """Effects that must be equal: bugs, result rows, embeddings and recorded runs."""
    with engine.connect() as connection:

        def rows(query: str) -> list[tuple]:
            return [tuple(row) for row in connection.execute(text(query))]

        return {
            "bugs": rows("SELECT title, status FROM bugs ORDER BY title"),
            "results": rows(
                "SELECT (SELECT count(*) FROM component_classifications),"
                " (SELECT count(*) FROM severity_classifications),"
                " (SELECT count(*) FROM technical_analyses),"
                " (SELECT count(*) FROM resolution_plans),"
                " (SELECT count(*) FROM bug_reports)"
            ),
            "embeddings": rows("SELECT count(*) FROM bug_embeddings"),
            "runs": rows(
                "SELECT type, status, progress_done, progress_total FROM runs ORDER BY id"
            ),
        }


def finish(client) -> None:
    assert client.app.state.runner.wait_idle(120)


def seed_bugs(engine: Engine) -> None:
    with session_factory(engine)() as session:
        seed_db(session)


def test_seed(cli, make_api, initialized_db):
    rebuild(initialized_db)
    assert cli("db", "seed").returncode == 0
    via_cli = snapshot(initialized_db)
    rebuild(initialized_db)
    api = make_api()
    assert api.post(f"{BASE}/admin/db/seed").status_code == 202
    finish(api)
    assert snapshot(initialized_db) == via_cli
    assert len(via_cli["bugs"]) == 20


def test_index(cli, make_api, initialized_db):
    rebuild(initialized_db, lambda: seed_bugs(initialized_db))
    assert cli("index").returncode == 0
    via_cli = snapshot(initialized_db)
    rebuild(initialized_db, lambda: seed_bugs(initialized_db))
    api = make_api()
    assert api.post(f"{BASE}/admin/index").status_code == 202
    finish(api)
    assert snapshot(initialized_db) == via_cli
    assert via_cli["embeddings"] == [(20,)]


def test_triage(cli, make_api, initialized_db):
    bug_id = rebuild(initialized_db, lambda: add_bug(initialized_db))
    assert cli("triage", "--bug", str(bug_id)).returncode == 0
    via_cli = snapshot(initialized_db)
    bug_id = rebuild(initialized_db, lambda: add_bug(initialized_db))
    api = make_api()
    assert api.post(f"{BASE}/triage-runs", json={"bug_id": bug_id}).status_code == 202
    finish(api)
    assert snapshot(initialized_db) == via_cli
    assert via_cli["results"] == [(1, 1, 1, 1, 1)]


def test_reopen(cli, make_api, initialized_db):
    bug_id = rebuild(initialized_db, lambda: add_bug_with_history(initialized_db, "processed"))
    assert cli("reopen", str(bug_id), "--yes").returncode == 0
    via_cli = snapshot(initialized_db)
    bug_id = rebuild(initialized_db, lambda: add_bug_with_history(initialized_db, "processed"))
    api = make_api()
    assert api.post(f"{BASE}/bugs/{bug_id}/reopen", json={"confirm": True}).status_code == 200
    assert snapshot(initialized_db) == via_cli
    assert via_cli["results"] == [(0, 0, 0, 0, 0)]


def test_report(cli, make_api, initialized_db):
    state = rebuild(initialized_db, lambda: add_processed_bug(initialized_db))
    printed = cli("report", str(state["bug_id"]))
    assert printed.returncode == 0
    api = make_api()
    served = api.get(f"{BASE}/bugs/{state['bug_id']}/report", params={"format": "md"})
    assert served.text == printed.stdout == PROCESSED_MARKDOWN


def test_search(cli, make_api, initialized_db, llm_client, stand_in):
    def build() -> None:
        seed_bugs(initialized_db)
        index_everything(initialized_db, llm_client)

    rebuild(initialized_db, build)
    printed = cli("search", "checkout button", "--limit", "3")
    assert printed.returncode == 0
    lines = printed.stdout.splitlines()[1:]
    api = make_api()
    items = api.get(f"{BASE}/search", params={"q": "checkout button", "limit": 3}).json()["items"]
    assert lines == [
        f"{item['score']:.2f}  {item['bug_id']}  {item['title']}  {item['status']}"
        for item in items
    ]
    assert len(items) == 3


def test_check(cli, make_api, initialized_db):
    printed = cli("check")
    assert printed.returncode == 0
    body = make_api().get(f"{BASE}/health").json()
    assert printed.stdout.splitlines() == [
        "database: ok" if body["database"]["ok"] else "database: failed",
        "vector search: ok" if body["vector_search"]["ok"] else "vector search: failed",
        "llm: ok" if body["llm"]["ok"] else "llm: failed",
    ]
    assert body["ok"] is True


def test_init(cli, make_api_fresh, fresh_schema):
    printed = cli("db", "init")
    assert printed.returncode == 0
    via_cli = printed.stdout.splitlines()
    rebuild_empty(fresh_schema)
    response = make_api_fresh().post(f"{BASE}/admin/db/init")
    assert response.json()["messages"] == via_cli
    assert snapshot(fresh_schema)["runs"] == [("init", "succeeded", 1, 1)]


def rebuild_empty(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    engine.dispose()


def test_reset(cli, make_api, initialized_db):
    rebuild(initialized_db, lambda: add_processed_bug(initialized_db))
    assert cli("db", "reset", "--yes").returncode == 0
    via_cli = snapshot(initialized_db)
    rebuild(initialized_db, lambda: add_processed_bug(initialized_db))
    api = make_api()
    assert api.post(f"{BASE}/admin/db/reset", json={"confirm": True}).status_code == 200
    assert snapshot(initialized_db) == via_cli
    assert via_cli["bugs"] == []
