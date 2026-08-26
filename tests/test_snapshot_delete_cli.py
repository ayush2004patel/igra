"""Integration tests for `igra snapshot delete` CLI command."""

from __future__ import annotations

from typer.testing import CliRunner

from igra.adapter.postgres import connect
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


def test_delete_with_yes_flag_removes_snapshot(tmp_path, monkeypatch):
    _init_project(tmp_path, monkeypatch)
    monkeypatch.setenv("IGRA_DB_PASSWORD", "igra_dev_pass")

    runner.invoke(app, ["snapshot", "create", "clean-state"])
    result = runner.invoke(app, ["snapshot", "delete", "clean-state", "--yes"])

    assert result.exit_code == 0
    assert "deleted" in result.stdout

    snapshot_dir = tmp_path / ".igra" / "snapshots" / "clean-state"
    assert not snapshot_dir.exists()


def test_delete_does_not_modify_database(
    tmp_path, monkeypatch, test_db_config, test_db_password
):
    _init_project(tmp_path, monkeypatch)
    monkeypatch.setenv("IGRA_DB_PASSWORD", test_db_password)

    runner.invoke(app, ["snapshot", "create", "clean-state"])
    runner.invoke(app, ["snapshot", "delete", "clean-state", "--yes"])

    with connect(test_db_config, test_db_password) as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM customers;")
        assert cur.fetchone()[0] == 3


def test_delete_interactive_confirm_yes(tmp_path, monkeypatch):
    _init_project(tmp_path, monkeypatch)
    monkeypatch.setenv("IGRA_DB_PASSWORD", "igra_dev_pass")

    runner.invoke(app, ["snapshot", "create", "clean-state"])
    result = runner.invoke(app, ["snapshot", "delete", "clean-state"], input="y\n")

    assert result.exit_code == 0
    assert "deleted" in result.stdout


def test_delete_interactive_confirm_no_cancels(tmp_path, monkeypatch):
    _init_project(tmp_path, monkeypatch)
    monkeypatch.setenv("IGRA_DB_PASSWORD", "igra_dev_pass")

    runner.invoke(app, ["snapshot", "create", "clean-state"])
    result = runner.invoke(app, ["snapshot", "delete", "clean-state"], input="n\n")

    assert result.exit_code == 0
    assert "cancelled" in result.stdout.lower()

    snapshot_dir = tmp_path / ".igra" / "snapshots" / "clean-state"
    assert snapshot_dir.exists()


def test_delete_nonexistent_snapshot_fails(tmp_path, monkeypatch):
    _init_project(tmp_path, monkeypatch)
    monkeypatch.setenv("IGRA_DB_PASSWORD", "igra_dev_pass")

    result = runner.invoke(app, ["snapshot", "delete", "does-not-exist", "--yes"])

    assert result.exit_code == 3


def test_delete_not_initialized_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("IGRA_DB_PASSWORD", "irrelevant")

    result = runner.invoke(app, ["snapshot", "delete", "anything", "--yes"])

    assert result.exit_code == 3
    assert "igra init" in result.stdout
