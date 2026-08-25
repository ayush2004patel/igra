"""IGRA configuration: read/write .igra/config.toml and resolve DB password.

Password resolution order (approved for Week 1):
IGRA_DB_PASSWORD env var -> interactive TTY prompt -> clear error.
Password is never written to config.toml or any snapshot file.
"""

from __future__ import annotations

import getpass
import os
import sys
import tomllib
from pathlib import Path

import tomli_w
from pydantic import BaseModel

IGRA_DIR_NAME = ".igra"
CONFIG_FILE_NAME = "config.toml"
PASSWORD_ENV_VAR = "IGRA_DB_PASSWORD"


class DatabaseConfig(BaseModel):
    host: str = "localhost"
    port: int = 5432
    dbname: str
    user: str


class IgraConfig(BaseModel):
    database: DatabaseConfig


class ConfigError(Exception):
    """Raised for missing or invalid configuration."""


class PasswordResolutionError(Exception):
    """Raised when no password source is available."""


def igra_dir(project_dir: Path | None = None) -> Path:
    base = project_dir or Path.cwd()
    return base / IGRA_DIR_NAME


def config_path(project_dir: Path | None = None) -> Path:
    return igra_dir(project_dir) / CONFIG_FILE_NAME


def config_exists(project_dir: Path | None = None) -> bool:
    return config_path(project_dir).is_file()


def save_config(config: IgraConfig, project_dir: Path | None = None) -> Path:
    """Write config to .igra/config.toml, creating .igra/ if needed.

    Password is never written - IgraConfig has no password field by design.
    """
    target_dir = igra_dir(project_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    path = config_path(project_dir)
    data = config.model_dump(mode="json")
    with open(path, "wb") as f:
        tomli_w.dump(data, f)
    return path


def load_config(project_dir: Path | None = None) -> IgraConfig:
    path = config_path(project_dir)
    if not path.is_file():
        raise ConfigError(
            f"No IGRA configuration found at {path}. Run 'igra init' first."
        )
    try:
        with open(path, "rb") as f:
            raw = tomllib.load(f)
        return IgraConfig.model_validate(raw)
    except (tomllib.TOMLDecodeError, Exception) as exc:
        raise ConfigError(f"Invalid configuration at {path}: {exc}") from exc


def resolve_db_password(interactive: bool | None = None) -> str:
    """Resolve the database password.

    Order: IGRA_DB_PASSWORD env var -> interactive TTY prompt -> error.
    """
    env_password = os.environ.get(PASSWORD_ENV_VAR)
    if env_password:
        return env_password

    is_tty = sys.stdin.isatty() if interactive is None else interactive
    if is_tty:
        password = getpass.getpass("PostgreSQL password: ")
        if password:
            return password
        raise PasswordResolutionError(
            "No password entered. Set IGRA_DB_PASSWORD or enter a "
            "password when prompted."
        )

    raise PasswordResolutionError(
        f"No password available. Set the {PASSWORD_ENV_VAR} environment "
        "variable, or run interactively to be prompted."
    )
