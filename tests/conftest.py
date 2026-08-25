"""Shared pytest fixtures: connection to a real throwaway PostgreSQL database.

Per TESTING.md section 3: tests use a disposable local PostgreSQL instance,
never a developer's real project database.
"""

from __future__ import annotations

import pytest

from igra.config import DatabaseConfig

TEST_DB_CONFIG = DatabaseConfig(
    host="localhost", port=5432, dbname="igra_dev_test", user="igra_dev"
)
TEST_DB_PASSWORD = "igra_dev_pass"


@pytest.fixture
def test_db_config() -> DatabaseConfig:
    return TEST_DB_CONFIG


@pytest.fixture
def test_db_password() -> str:
    return TEST_DB_PASSWORD
