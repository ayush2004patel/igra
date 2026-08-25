"""Tests for igra.validation: post-restore structural validation."""

from __future__ import annotations

import pytest

from igra.adapter.postgres import (
    connect,
    create_database,
    drop_database,
    dump_database,
    restore_database,
)
from igra.config import DatabaseConfig
from igra.metadata import TableInfo, build_metadata
from igra.validation import validate_restored_database


@pytest.fixture
def restored_scratch(test_db_config, test_db_password, tmp_path):
    """Dump the real test DB, restore it into a scratch DB, and yield
    (scratch_config, metadata) for validation tests. Cleans up after.
    """
    dump_path = tmp_path / "dump.pgcustom"
    dump_database(test_db_config, test_db_password, dump_path)

    with connect(test_db_config, test_db_password) as conn:
        metadata = build_metadata(
            "test-snap", test_db_config, conn, dump_path.stat().st_size
        )

    scratch_name = "igra_validation_fixture_scratch"
    create_database(test_db_config, test_db_password, scratch_name)
    restore_database(test_db_config, test_db_password, scratch_name, dump_path)

    scratch_config = DatabaseConfig(
        host=test_db_config.host,
        port=test_db_config.port,
        dbname=scratch_name,
        user=test_db_config.user,
    )
    try:
        yield scratch_config, metadata
    finally:
        drop_database(test_db_config, test_db_password, scratch_name)


def test_validation_passes_for_correct_restore(restored_scratch, test_db_password):
    scratch_config, metadata = restored_scratch
    with connect(scratch_config, test_db_password) as conn:
        result = validate_restored_database(conn, metadata)

    assert result.passed is True
    assert result.missing_tables == []
    assert result.row_count_mismatches == []


def test_validation_fails_on_row_count_mismatch(restored_scratch, test_db_password):
    scratch_config, metadata = restored_scratch
    metadata.tables[0].row_count = 999

    with connect(scratch_config, test_db_password) as conn:
        result = validate_restored_database(conn, metadata)

    assert result.passed is False
    assert len(result.row_count_mismatches) == 1
    assert "expected 999" in result.row_count_mismatches[0]


def test_validation_fails_on_missing_table(restored_scratch, test_db_password):
    scratch_config, metadata = restored_scratch
    metadata.tables.append(
        TableInfo(schema_name="public", table_name="ghost_table", row_count=5)
    )

    with connect(scratch_config, test_db_password) as conn:
        result = validate_restored_database(conn, metadata)

    assert result.passed is False
    assert "public.ghost_table" in result.missing_tables


def test_validation_summary_is_readable(restored_scratch, test_db_password):
    scratch_config, metadata = restored_scratch
    with connect(scratch_config, test_db_password) as conn:
        result = validate_restored_database(conn, metadata)

    assert "passed" in result.summary().lower()


def test_validation_summary_failed_is_readable(restored_scratch, test_db_password):
    scratch_config, metadata = restored_scratch
    metadata.tables[0].row_count = 999

    with connect(scratch_config, test_db_password) as conn:
        result = validate_restored_database(conn, metadata)

    assert "FAILED" in result.summary()
