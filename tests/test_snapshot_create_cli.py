"""Integration tests for `igra snapshot create` CLI command."""

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


def test_snapshot_create_success(tmp_path, monkeypatch):
    _init_project(tmp_path, monkeypatch)
    monkeypatch.setenv("IGRA_DB_PASSWORD", "igra_dev_pass")

    result = runner.invoke(app, ["snapshot", "create", "clean-state"])

    assert result.exit_code == 0
    assert "Snapshot 'clean-state' created." in result.stdout
    assert "2748 bytes" in result.stdout or "bytes" in result.stdout

    snapshot_dir = tmp_path / ".igra" / "snapshots" / "clean-state"
    assert (snapshot_dir / "dump.pgcustom").is_file()
    assert (snapshot_dir / "metadata.json").is_file()
    assert (snapshot_dir / "checksum.sha256").is_file()


def test_snapshot_create_updates_status_count(tmp_path, monkeypatch):
    _init_project(tmp_path, monkeypatch)
    monkeypatch.setenv("IGRA_DB_PASSWORD", "igra_dev_pass")

    runner.invoke(app, ["snapshot", "create", "clean-state"])
    result = runner.invoke(app, ["status"])

    assert "Snapshots" in result.stdout and "1" in result.stdout


def test_snapshot_create_name_collision_rejected(tmp_path, monkeypatch):
    _init_project(tmp_path, monkeypatch)
    monkeypatch.setenv("IGRA_DB_PASSWORD", "igra_dev_pass")

    first = runner.invoke(app, ["snapshot", "create", "clean-state"])
    assert first.exit_code == 0

    second = runner.invoke(app, ["snapshot", "create", "clean-state"])
    assert second.exit_code == 2
    assert "already exists" in second.stdout


def test_snapshot_create_not_initialized_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("IGRA_DB_PASSWORD", "irrelevant")

    result = runner.invoke(app, ["snapshot", "create", "clean-state"])

    assert result.exit_code == 3
    assert "igra init" in result.stdout


def test_snapshot_create_wrong_password_fails_and_no_partial_dir(tmp_path, monkeypatch):
    _init_project(tmp_path, monkeypatch)
    monkeypatch.setenv("IGRA_DB_PASSWORD", "wrong-password")

    result = runner.invoke(app, ["snapshot", "create", "clean-state"])

    assert result.exit_code == 3
    snapshot_dir = tmp_path / ".igra" / "snapshots" / "clean-state"
    assert not snapshot_dir.exists()
