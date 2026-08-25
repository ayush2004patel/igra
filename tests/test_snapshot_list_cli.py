"""Integration tests for `igra snapshot list` CLI command."""

from __future__ import annotations

from typer.testing import CliRunner

from igra.cli import app

runner = CliRunner()


def _init_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner.invoke(
        app,
        [
            "init",
            "--host", "localhost",
            "--port", "5432",
            "--dbname", "igra_dev_test",
            "--user", "igra_dev",
        ],
    )


def test_list_empty_shows_no_snapshots_message(tmp_path, monkeypatch):
    _init_project(tmp_path, monkeypatch)
    monkeypatch.setenv("IGRA_DB_PASSWORD", "igra_dev_pass")

    result = runner.invoke(app, ["snapshot", "list"])

    assert result.exit_code == 0
    assert "No snapshots found" in result.stdout


def test_list_shows_created_snapshots(tmp_path, monkeypatch):
    _init_project(tmp_path, monkeypatch)
    monkeypatch.setenv("IGRA_DB_PASSWORD", "igra_dev_pass")

    runner.invoke(app, ["snapshot", "create", "alpha"])
    runner.invoke(app, ["snapshot", "create", "beta"])

    result = runner.invoke(app, ["snapshot", "list"])

    assert result.exit_code == 0
    assert "alpha" in result.stdout
    assert "beta" in result.stdout


def test_list_not_initialized_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("IGRA_DB_PASSWORD", "irrelevant")

    result = runner.invoke(app, ["snapshot", "list"])

    assert result.exit_code == 3
    assert "igra init" in result.stdout
