"""Integration tests for `igra snapshot show` CLI command."""

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


def test_show_existing_snapshot_displays_metadata(tmp_path, monkeypatch):
    _init_project(tmp_path, monkeypatch)
    monkeypatch.setenv("IGRA_DB_PASSWORD", "igra_dev_pass")

    runner.invoke(app, ["snapshot", "create", "clean-state"])
    result = runner.invoke(app, ["snapshot", "show", "clean-state"])

    assert result.exit_code == 0
    assert "name: clean-state" in result.stdout
    assert "source_database: igra_dev_test" in result.stdout
    assert "public.customers" in result.stdout
    assert "3 rows" in result.stdout


def test_show_does_not_expose_row_level_data(tmp_path, monkeypatch):
    _init_project(tmp_path, monkeypatch)
    monkeypatch.setenv("IGRA_DB_PASSWORD", "igra_dev_pass")

    runner.invoke(app, ["snapshot", "create", "clean-state"])
    result = runner.invoke(app, ["snapshot", "show", "clean-state"])

    # Real row values (e.g. customer names) must never appear - only
    # counts and structural metadata, per ARCHITECTURE.md section 14.
    assert "Alice" not in result.stdout
    assert "Bob" not in result.stdout
    assert "Carol" not in result.stdout


def test_show_nonexistent_snapshot_fails(tmp_path, monkeypatch):
    _init_project(tmp_path, monkeypatch)
    monkeypatch.setenv("IGRA_DB_PASSWORD", "igra_dev_pass")

    result = runner.invoke(app, ["snapshot", "show", "does-not-exist"])

    assert result.exit_code == 3
    assert "does-not-exist" in result.stdout


def test_show_not_initialized_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("IGRA_DB_PASSWORD", "irrelevant")

    result = runner.invoke(app, ["snapshot", "show", "anything"])

    assert result.exit_code == 3
    assert "igra init" in result.stdout
