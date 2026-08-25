"""Tests for `igra init` CLI command."""

from __future__ import annotations

import tomllib

from typer.testing import CliRunner

from igra.cli import app

runner = CliRunner()


def test_init_with_flags_creates_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        [
            "init",
            "--host", "localhost",
            "--port", "5432",
            "--dbname", "testdb",
            "--user", "testuser",
        ],
    )
    assert result.exit_code == 0
    config_file = tmp_path / ".igra" / "config.toml"
    assert config_file.is_file()

    with open(config_file, "rb") as f:
        data = tomllib.load(f)
    assert data["database"]["host"] == "localhost"
    assert data["database"]["port"] == 5432
    assert data["database"]["dbname"] == "testdb"
    assert data["database"]["user"] == "testuser"


def test_init_never_writes_password(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner.invoke(
        app,
        [
            "init",
            "--host", "localhost",
            "--port", "5432",
            "--dbname", "testdb",
            "--user", "testuser",
        ],
    )
    config_file = tmp_path / ".igra" / "config.toml"
    content = config_file.read_text()
    assert "password" not in content.lower()


def test_init_already_initialized_rejects(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    args = [
        "init",
        "--host", "localhost",
        "--port", "5432",
        "--dbname", "testdb",
        "--user", "testuser",
    ]
    first = runner.invoke(app, args)
    assert first.exit_code == 0

    second = runner.invoke(app, args)
    assert second.exit_code == 2
