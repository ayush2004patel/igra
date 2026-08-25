"""Tests for igra.restore: staged restore workflow and safety guarantees.

Per TESTING.md section 7, these are the highest-priority tests in the
project - every documented failure stage must be proven, not assumed.
"""

from __future__ import annotations

import pytest

from igra.adapter.postgres import connect
from igra.capture import create_snapshot
from igra.restore import (
    FAILURE_STAGE_CHECKSUM,
    FAILURE_STAGE_SCRATCH_RESTORE,
    TARGET_STATE_UNTOUCHED,
    restore_snapshot,
)
from igra.storage import SnapshotNotFoundError, checksum_path, dump_path


@pytest.fixture
def snapshot_in_project(test_db_config, test_db_password, tmp_path, monkeypatch):
    """Create a real snapshot of the test DB inside a fresh project dir."""
    monkeypatch.chdir(tmp_path)
    with connect(test_db_config, test_db_password) as conn:
        create_snapshot("clean-state", test_db_config, test_db_password, conn)
    return tmp_path


def test_restore_success_reproduces_data(
    snapshot_in_project, test_db_config, test_db_password
):
    with connect(test_db_config, test_db_password) as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO customers (name) VALUES ('MARKER-TEST');")
        conn.commit()

    result = restore_snapshot("clean-state", test_db_config, test_db_password)

    assert result.checksum_verified is True
    assert result.scratch_restore_succeeded is True
    assert result.validation_passed is True
    assert result.replacement_completed is True
    assert result.failure_stage is None
    assert result.target_database_state == "replaced"

    with connect(test_db_config, test_db_password) as conn, conn.cursor() as cur:
        cur.execute("SELECT name FROM customers WHERE name = 'MARKER-TEST';")
        assert cur.fetchone() is None

    # Clean up the timestamped "previous" database left as a safety net.
    _cleanup_prev_databases(test_db_config, test_db_password)


def test_restore_nonexistent_snapshot_raises(
    tmp_path, monkeypatch, test_db_config, test_db_password
):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SnapshotNotFoundError):
        restore_snapshot("does-not-exist", test_db_config, test_db_password)


def test_restore_checksum_mismatch_leaves_target_untouched(
    snapshot_in_project, test_db_config, test_db_password
):
    # Tamper with the dump after capture - checksum will no longer match.
    dump_file = dump_path("clean-state")
    with open(dump_file, "ab") as f:
        f.write(b"corrupted-bytes")

    result = restore_snapshot("clean-state", test_db_config, test_db_password)

    assert result.checksum_verified is False
    assert result.failure_stage == FAILURE_STAGE_CHECKSUM
    assert result.target_database_state == TARGET_STATE_UNTOUCHED

    with connect(test_db_config, test_db_password) as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM customers;")
        assert cur.fetchone()[0] == 3


def test_restore_corrupt_dump_with_valid_checksum_fails_at_scratch_restore(
    snapshot_in_project, test_db_config, test_db_password
):
    from igra.integrity import build_integrity_record, save_integrity_record

    # Corrupt the dump, then regenerate a checksum that matches the
    # corrupted content - this simulates a dump that passes integrity
    # verification but is not a valid pg_dump archive (e.g. truncated
    # during an earlier interrupted write, then checksummed after).
    dump_file = dump_path("clean-state")
    dump_file.write_bytes(b"not a real pg_dump archive at all")
    new_record = build_integrity_record(dump_file)
    save_integrity_record(new_record, checksum_path("clean-state"))

    result = restore_snapshot("clean-state", test_db_config, test_db_password)

    assert result.checksum_verified is True
    assert result.scratch_restore_succeeded is False
    assert result.failure_stage == FAILURE_STAGE_SCRATCH_RESTORE
    assert result.target_database_state == TARGET_STATE_UNTOUCHED

    with connect(test_db_config, test_db_password) as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM customers;")
        assert cur.fetchone()[0] == 3


def test_restore_does_not_leave_scratch_database_behind_on_failure(
    snapshot_in_project, test_db_config, test_db_password
):
    dump_file = dump_path("clean-state")
    with open(dump_file, "ab") as f:
        f.write(b"corrupted-bytes")

    before = _list_scratch_databases(test_db_config, test_db_password)
    restore_snapshot("clean-state", test_db_config, test_db_password)
    after = _list_scratch_databases(test_db_config, test_db_password)

    assert before == after == []


def _list_scratch_databases(config, password) -> list[str]:
    with connect(
        config.__class__(
            host=config.host, port=config.port, dbname="postgres", user=config.user
        ),
        password,
    ) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT datname FROM pg_database WHERE datname LIKE 'igra_scratch_%';"
        )
        return [row[0] for row in cur.fetchall()]


def _cleanup_prev_databases(config, password) -> None:
    from igra.adapter.postgres import drop_database

    with connect(
        config.__class__(
            host=config.host, port=config.port, dbname="postgres", user=config.user
        ),
        password,
    ) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT datname FROM pg_database WHERE datname LIKE %s;",
            (f"{config.dbname}_prev_%",),
        )
        names = [row[0] for row in cur.fetchall()]
    for name in names:
        drop_database(config, password, name)
