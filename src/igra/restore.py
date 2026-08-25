"""Snapshot restore: orchestrates the staged, validated restore workflow.

Per ARCHITECTURE.md sections 10-11: this is explicitly NOT atomic.
Every stage is checked before proceeding; on failure at any stage
before replacement, the target database is left untouched.

Sequence (per the Week 2 spike, ARCHITECTURE.md section 10):
    1. Verify checksum of dump.pgcustom
    2. Create a scratch database
    3. pg_restore into the scratch database
    4. Validate the scratch database against snapshot metadata
    5. On failure at any of the above: drop scratch DB, target untouched
    6. On success: terminate connections to target, rename target to a
       timestamped previous-name, rename scratch to target's name
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from igra.adapter.postgres import (
    ConnectionError_,
    RestoreError,
    connect,
    create_database,
    drop_database,
    rename_database,
    restore_database,
    terminate_connections,
)
from igra.config import DatabaseConfig
from igra.integrity import IntegrityError, load_integrity_record, verify_checksum
from igra.metadata import SnapshotMetadata, load_metadata
from igra.storage import (
    SnapshotNotFoundError,
    checksum_path,
    dump_path,
    metadata_path,
    snapshot_exists,
)
from igra.validation import validate_restored_database

FAILURE_STAGE_CHECKSUM = "checksum"
FAILURE_STAGE_SCRATCH_RESTORE = "scratch_restore"
FAILURE_STAGE_VALIDATION = "validation"
FAILURE_STAGE_REPLACEMENT = "replacement"

TARGET_STATE_UNTOUCHED = "untouched"
TARGET_STATE_REPLACED = "replaced"


@dataclass
class RestoreResult:
    """Per DATA-MODEL.md section 8."""

    snapshot_name: str
    checksum_verified: bool
    scratch_restore_succeeded: bool
    validation_passed: bool
    replacement_completed: bool
    failure_stage: str | None
    target_database_state: str


def _scratch_db_name(snapshot_name: str) -> str:
    return f"igra_scratch_{uuid.uuid4().hex[:12]}"


def _prev_db_name(target_dbname: str) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    return f"{target_dbname}_prev_{timestamp}"


def restore_snapshot(
    name: str, config: DatabaseConfig, password: str
) -> RestoreResult:
    """Restore the target database to the state captured in snapshot `name`.

    Never described or implemented as atomic (ARCHITECTURE.md section 11).
    Returns a RestoreResult reflecting exactly which stage was reached,
    regardless of success or failure.
    """
    if not snapshot_exists(name):
        raise SnapshotNotFoundError(f"No snapshot named '{name}' exists.")

    dump_file = dump_path(name)
    checksum_file = checksum_path(name)
    meta_file = metadata_path(name)

    # --- Stage 1: checksum verification ---
    try:
        record = load_integrity_record(checksum_file)
        checksum_ok = verify_checksum(dump_file, record)
    except (IntegrityError, OSError):
        return RestoreResult(
            snapshot_name=name,
            checksum_verified=False,
            scratch_restore_succeeded=False,
            validation_passed=False,
            replacement_completed=False,
            failure_stage=FAILURE_STAGE_CHECKSUM,
            target_database_state=TARGET_STATE_UNTOUCHED,
        )

    if not checksum_ok:
        return RestoreResult(
            snapshot_name=name,
            checksum_verified=False,
            scratch_restore_succeeded=False,
            validation_passed=False,
            replacement_completed=False,
            failure_stage=FAILURE_STAGE_CHECKSUM,
            target_database_state=TARGET_STATE_UNTOUCHED,
        )

    metadata: SnapshotMetadata = load_metadata(meta_file)
    scratch_name = _scratch_db_name(name)

    # --- Stage 2 + 3: create scratch DB, pg_restore into it ---
    try:
        create_database(config, password, scratch_name)
        restore_database(config, password, scratch_name, dump_file)
    except (RestoreError, ConnectionError_):
        _safe_drop(config, password, scratch_name)
        return RestoreResult(
            snapshot_name=name,
            checksum_verified=True,
            scratch_restore_succeeded=False,
            validation_passed=False,
            replacement_completed=False,
            failure_stage=FAILURE_STAGE_SCRATCH_RESTORE,
            target_database_state=TARGET_STATE_UNTOUCHED,
        )

    # --- Stage 4: validation ---
    scratch_config = DatabaseConfig(
        host=config.host, port=config.port, dbname=scratch_name, user=config.user
    )
    try:
        with connect(scratch_config, password) as conn:
            validation = validate_restored_database(conn, metadata)
    except ConnectionError_:
        _safe_drop(config, password, scratch_name)
        return RestoreResult(
            snapshot_name=name,
            checksum_verified=True,
            scratch_restore_succeeded=True,
            validation_passed=False,
            replacement_completed=False,
            failure_stage=FAILURE_STAGE_VALIDATION,
            target_database_state=TARGET_STATE_UNTOUCHED,
        )

    if not validation.passed:
        _safe_drop(config, password, scratch_name)
        return RestoreResult(
            snapshot_name=name,
            checksum_verified=True,
            scratch_restore_succeeded=True,
            validation_passed=False,
            replacement_completed=False,
            failure_stage=FAILURE_STAGE_VALIDATION,
            target_database_state=TARGET_STATE_UNTOUCHED,
        )

    # --- Stage 5: protected replacement ---
    prev_name = _prev_db_name(config.dbname)
    try:
        terminate_connections(config, password, config.dbname)
        rename_database(config, password, config.dbname, prev_name)
        rename_database(config, password, scratch_name, config.dbname)
    except (RestoreError, ConnectionError_):
        # Per ARCHITECTURE.md section 13: this is a known risk area.
        # Target-database state in this exact failure window is not
        # yet guaranteed - reported honestly, not glossed over.
        return RestoreResult(
            snapshot_name=name,
            checksum_verified=True,
            scratch_restore_succeeded=True,
            validation_passed=True,
            replacement_completed=False,
            failure_stage=FAILURE_STAGE_REPLACEMENT,
            target_database_state="unknown",
        )

    return RestoreResult(
        snapshot_name=name,
        checksum_verified=True,
        scratch_restore_succeeded=True,
        validation_passed=True,
        replacement_completed=True,
        failure_stage=None,
        target_database_state=TARGET_STATE_REPLACED,
    )

def _safe_drop(config: DatabaseConfig, password: str, dbname: str) -> None:
    """Best-effort scratch DB cleanup - never lets a cleanup failure mask
    the original error that triggered it."""
    try:
        drop_database(config, password, dbname)
    except RestoreError:
        # Intentionally swallowed: this is best-effort cleanup after a
        # restore has already failed. Raising here would mask the real
        # failure that triggered this cleanup in the first place.
        pass