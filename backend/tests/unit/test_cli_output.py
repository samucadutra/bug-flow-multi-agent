import io

import pytest
import typer

from bugflow.cli import context as context_module
from bugflow.cli import output
from bugflow.config import ConfigError
from bugflow.db.errors import DatabaseUnavailableError
from bugflow.services.errors import NotFoundError


def test_print_helpers_use_the_right_streams(capsys):
    output.echo("result")
    output.echo_error("problem")
    captured = capsys.readouterr()
    assert captured.out == "result\n" and captured.err == "problem\n"


@pytest.mark.parametrize(
    ("answer", "expected"),
    [("yes\n", True), ("YES\n", True), ("  Yes  \n", True), ("no\n", False), ("", False)],
)
def test_confirm_typed(monkeypatch, capsys, answer, expected):
    monkeypatch.setattr("sys.stdin", io.StringIO(answer))
    assert output.confirm_typed("Sure?") is expected
    assert capsys.readouterr().out.startswith("Sure? ")


def test_confirm_returns_false_without_stdin(monkeypatch):
    monkeypatch.setattr("sys.stdin", None)
    assert output.confirm_typed("Sure?") is False


def test_known_errors_print_their_fixed_message():
    for error in (
        ConfigError("X", "X is invalid"),
        DatabaseUnavailableError(),
        NotFoundError("Bug 1 not found"),
    ):
        assert output.error_message(error) == str(error)


def test_unexpected_error_text_is_redacted(canary_api_key, canary_db_password):
    output.register_secrets([canary_api_key, canary_db_password])
    try:
        message = output.error_message(RuntimeError(f"{canary_api_key} {canary_db_password}"))
    finally:
        output.register_secrets([])
    assert message == "Unexpected error: *** ***"


def test_guarded_maps_errors_and_keeps_exit(capsys):
    @output.guarded
    def fail():
        raise NotFoundError("Bug 1 not found")

    @output.guarded
    def leave():
        raise typer.Exit(3)

    with pytest.raises(typer.Exit) as caught:
        fail()
    assert caught.value.exit_code == 1 and capsys.readouterr().err == "Bug 1 not found\n"
    with pytest.raises(typer.Exit) as caught:
        leave()
    assert caught.value.exit_code == 3


def test_bootstrap_builds_engine_and_logging_only_when_called(
    clean_env, canary_db_url, monkeypatch
):
    configured = []
    monkeypatch.setattr(
        context_module, "configure_logging", lambda settings: configured.append(settings)
    )
    assert configured == []
    clean_env.setenv("DATABASE_URL", canary_db_url)
    monkeypatch.setattr(
        context_module, "load_settings", lambda: context_module.Settings(_env_file=None)
    )
    ctx = context_module.bootstrap()
    assert len(configured) == 1 and ctx.engine.url.database == "bugflow"
    assert ctx.redactor.redact("pw s3cretpw") == "pw ***"
    ctx.close()
