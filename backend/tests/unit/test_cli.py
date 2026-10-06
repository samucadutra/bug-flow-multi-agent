from typer.testing import CliRunner

import bugflow
from bugflow.cli import app

runner = CliRunner()


def test_version_flag(clean_env):
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.output == f"bugflow {bugflow.__version__}\n"


def test_version_does_not_load_settings(clean_env, monkeypatch):
    import bugflow.config as config

    def boom(*args, **kwargs):
        raise AssertionError("settings must not load")

    monkeypatch.setattr(config, "get_settings", boom)
    monkeypatch.setattr(config, "load_settings", boom)
    assert runner.invoke(app, ["--version"]).exit_code == 0


def test_help_is_english(clean_env):
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "--version" in result.output
    assert "BugFlow" in result.output
