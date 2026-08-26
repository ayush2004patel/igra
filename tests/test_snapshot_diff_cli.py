"""Integration tests for `igra snapshot diff` CLI command."""

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


def test_diff_detects_added_table_and_row_change(
    tmp_path, monkeypatch, test_db_config, test_db_password
):
    _init_project(tmp_path, monkeypatch)
    monkeypatch.setenv("IGRA_DB_PASSWORD", test_db_password)

    runner.invoke(app, ["snapshot", "create", "before"])

    with connect(test_db_config, test_db_password) as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO customers (name) VALUES ('Eve');")
        cur.execute("CREATE TABLE orders (id SERIAL PRIMARY KEY);")
        conn.commit()

    try:
        runner.invoke(app, ["snapshot", "create", "after"])
        result = runner.invoke(app, ["snapshot", "diff", "before", "after"])

        assert result.exit_code == 0
        assert "orders" in result.stdout
        assert "customers" in result.stdout
        assert "3 -> 4" in result.stdout
    finally:
        with connect(test_db_config, test_db_password) as conn, conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS orders;")
            cur.execute("DELETE FROM customers WHERE name = 'Eve';")
            conn.commit()


def test_diff_identical_snapshots_reports_no_differences(tmp_path, monkeypatch):
    _init_project(tmp_path, monkeypatch)
    monkeypatch.setenv("IGRA_DB_PASSWORD", "igra_dev_pass")

    runner.invoke(app, ["snapshot", "create", "a"])
    runner.invoke(app, ["snapshot", "create", "b"])

    result = runner.invoke(app, ["snapshot", "diff", "a", "b"])

    assert result.exit_code == 0
    assert "No differences found" in result.stdout


def test_diff_nonexistent_snapshot_fails(tmp_path, monkeypatch):
    _init_project(tmp_path, monkeypatch)
    monkeypatch.setenv("IGRA_DB_PASSWORD", "igra_dev_pass")

    runner.invoke(app, ["snapshot", "create", "a"])
    result = runner.invoke(app, ["snapshot", "diff", "a", "does-not-exist"])

    assert result.exit_code == 3


def test_diff_not_initialized_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("IGRA_DB_PASSWORD", "irrelevant")

    result = runner.invoke(app, ["snapshot", "diff", "a", "b"])

    assert result.exit_code == 3
    assert "igra init" in result.stdout
