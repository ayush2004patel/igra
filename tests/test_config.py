"""Tests for igra.config: read/write .igra/config.toml and password resolution."""

from __future__ import annotations

import pytest

from igra.config import (
    PASSWORD_ENV_VAR,
    ConfigError,
    DatabaseConfig,
    IgraConfig,
    PasswordResolutionError,
    config_exists,
    load_config,
    resolve_db_password,
    save_config,
)


def test_save_and_load_round_trip(tmp_path):
    config = IgraConfig(
        database=DatabaseConfig(
            host="localhost", port=5432, dbname="myapp_dev", user="postgres"
        )
    )
    save_config(config, project_dir=tmp_path)

    assert config_exists(project_dir=tmp_path)
    loaded = load_config(project_dir=tmp_path)
    assert loaded == config


def test_save_config_never_writes_password(tmp_path):
    config = IgraConfig(database=DatabaseConfig(dbname="myapp_dev", user="postgres"))
    path = save_config(config, project_dir=tmp_path)
    content = path.read_text()
    assert "password" not in content.lower()


def test_load_config_missing_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(project_dir=tmp_path)


def test_load_config_invalid_raises(tmp_path):
    igra_subdir = tmp_path / ".igra"
    igra_subdir.mkdir()
    (igra_subdir / "config.toml").write_text("not = valid = toml = here\n")
    with pytest.raises(ConfigError):
        load_config(project_dir=tmp_path)


def test_resolve_password_from_env(monkeypatch):
    monkeypatch.setenv(PASSWORD_ENV_VAR, "secret123")
    assert resolve_db_password() == "secret123"


def test_resolve_password_prompts_when_tty(monkeypatch):
    monkeypatch.delenv(PASSWORD_ENV_VAR, raising=False)
    monkeypatch.setattr("igra.config.getpass.getpass", lambda prompt="": "typed-secret")
    assert resolve_db_password(interactive=True) == "typed-secret"


def test_resolve_password_empty_prompt_raises(monkeypatch):
    monkeypatch.delenv(PASSWORD_ENV_VAR, raising=False)
    monkeypatch.setattr("igra.config.getpass.getpass", lambda prompt="": "")
    with pytest.raises(PasswordResolutionError):
        resolve_db_password(interactive=True)


def test_resolve_password_non_interactive_no_env_raises(monkeypatch):
    monkeypatch.delenv(PASSWORD_ENV_VAR, raising=False)
    with pytest.raises(PasswordResolutionError):
        resolve_db_password(interactive=False)
