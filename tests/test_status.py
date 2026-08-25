"""Integration tests for `igra status` CLI command."""

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


def test_status_success(tmp_path, monkeypatch):
    _init_project(tmp_path, monkeypatch)
    monkeypatch.setenv("IGRA_DB_PASSWORD", "igra_dev_pass")

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0
    assert "connected: true" in result.stdout
    assert "database_name: igra_dev_test" in result.stdout
    assert "postgres_server_version:" in result.stdout
    assert "snapshot_count: 0" in result.stdout


def test_status_wrong_password_fails(tmp_path, monkeypatch):
    _init_project(tmp_path, monkeypatch)
    monkeypatch.setenv("IGRA_DB_PASSWORD", "wrong-password")

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 3


def test_status_not_initialized_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("IGRA_DB_PASSWORD", "irrelevant")

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 3
    assert "igra init" in result.stdout


def test_status_no_password_available_fails(tmp_path, monkeypatch):
    _init_project(tmp_path, monkeypatch)
    monkeypatch.delenv("IGRA_DB_PASSWORD", raising=False)

    result = runner.invoke(app, ["status"], input="")

    assert result.exit_code == 3
