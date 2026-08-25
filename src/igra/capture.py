"""Snapshot capture: orchestrates dump + metadata + checksum generation.

Per ARCHITECTURE.md section 4 (Capture) and section 13 (Error Handling):
if any stage fails, no partial snapshot is left behind - the snapshot
directory is deleted and the original error is propagated.
"""

from __future__ import annotations

import psycopg

from igra.adapter.postgres import DumpError, dump_database
from igra.config import DatabaseConfig
from igra.integrity import build_integrity_record, save_integrity_record
from igra.metadata import SnapshotMetadata, build_metadata, save_metadata
from igra.storage import (
    SnapshotAlreadyExistsError,
    checksum_path,
    create_snapshot_directory,
    delete_snapshot_directory,
    dump_path,
    metadata_path,
)


class CaptureError(Exception):
    """Raised when snapshot capture fails at any stage."""


def create_snapshot(
    name: str,
    config: DatabaseConfig,
    password: str,
    conn: psycopg.Connection,
) -> SnapshotMetadata:
    """Capture the current database state as a new named snapshot.

    Stages, per ARCHITECTURE.md section 4:
        1. Create snapshot directory (fails fast if name collides)
        2. pg_dump -Fc -> dump.pgcustom
        3. Build and save metadata.json
        4. Compute and save checksum.sha256

    On failure at any stage after directory creation, the partial
    snapshot directory is deleted before the error is raised - the
    project directory is never left with a misleadingly "complete"
    but actually broken snapshot.
    """
    try:
        create_snapshot_directory(name)
    except SnapshotAlreadyExistsError as exc:
        raise CaptureError(str(exc)) from exc

    try:
        dump_target = dump_path(name)
        dump_database(config, password, dump_target)

        metadata = build_metadata(
            name=name,
            config=config,
            conn=conn,
            dump_size_bytes=dump_target.stat().st_size,
        )
        save_metadata(metadata, metadata_path(name))

        integrity_record = build_integrity_record(dump_target)
        save_integrity_record(integrity_record, checksum_path(name))

    except DumpError as exc:
        delete_snapshot_directory(name)
        raise CaptureError(f"Snapshot capture failed during dump: {exc}") from exc
    except Exception as exc:
        delete_snapshot_directory(name)
        raise CaptureError(f"Snapshot capture failed: {exc}") from exc

    return metadata
