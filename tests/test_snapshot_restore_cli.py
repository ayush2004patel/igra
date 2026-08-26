"""Integration tests for `igra snapshot restore` CLI command."""

from __future__ import annotations

from typer.testing import CliRunner

from igra.adapter.postgres import connect, drop_database
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


def _cleanup_prev_databases(test_db_config, test_db_password):
    with connect(
        test_db_config.__class__(
            host=test_db_config.host,
            port=test_db_config.port,
            dbname="postgres",
            user=test_db_config.user,
        ),
        test_db_password,
    ) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT datname FROM pg_database WHERE datname LIKE %s;",
            (f"{test_db_config.dbname}_prev_%",),
        )
        names = [row[0] for row in cur.fetchall()]
    for name in names:
        drop_database(test_db_config, test_db_password, name)


def test_restore_with_yes_flag_succeeds(tmp_path, monkeypatch, test_db_config, test_db_password):
    _init_project(tmp_path, monkeypatch)
    monkeypatch.setenv("IGRA_DB_PASSWORD", test_db_password)

    runner.invoke(app, ["snapshot", "create", "clean-state"])

    with connect(test_db_config, test_db_password) as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO customers (name) VALUES ('CLI-MARKER');")
        conn.commit()

    result = runner.invoke(app, ["snapshot", "restore", "clean-state", "--yes"])

    assert result.exit_code == 0
    assert "replaced" in result.stdout

    with connect(test_db_config, test_db_password) as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM customers;")
        assert cur.fetchone()[0] == 3

    _cleanup_prev_databases(test_db_config, test_db_password)


def test_restore_interactive_confirm_yes(tmp_path, monkeypatch, test_db_config, test_db_password):
    _init_project(tmp_path, monkeypatch)
    monkeypatch.setenv("IGRA_DB_PASSWORD", test_db_password)

    runner.invoke(app, ["snapshot", "create", "clean-state"])

    result = runner.invoke(app, ["snapshot", "restore", "clean-state"], input="y\n")

    assert result.exit_code == 0
    assert "restored successfully" in result.stdout

    _cleanup_prev_databases(test_db_config, test_db_password)


def test_restore_interactive_confirm_no_cancels(
    tmp_path, monkeypatch, test_db_config, test_db_password
):
    _init_project(tmp_path, monkeypatch)
    monkeypatch.setenv("IGRA_DB_PASSWORD", test_db_password)

    runner.invoke(app, ["snapshot", "create", "clean-state"])

    result = runner.invoke(app, ["snapshot", "restore", "clean-state"], input="n\n")

    assert result.exit_code == 0
    assert "cancelled" in result.stdout.lower()


def test_restore_nonexistent_snapshot_fails(tmp_path, monkeypatch):
    _init_project(tmp_path, monkeypatch)
    monkeypatch.setenv("IGRA_DB_PASSWORD", "igra_dev_pass")

    result = runner.invoke(app, ["snapshot", "restore", "does-not-exist", "--yes"])

    assert result.exit_code == 3


def test_restore_not_initialized_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("IGRA_DB_PASSWORD", "irrelevant")

    result = runner.invoke(app, ["snapshot", "restore", "anything", "--yes"])

    assert result.exit_code == 3
    assert "igra init" in result.stdout
