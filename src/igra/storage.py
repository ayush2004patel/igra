"""Snapshot storage: manages .igra/snapshots/<name>/ on disk.

Per ARCHITECTURE.md section 5:
    .igra/snapshots/<snapshot-name>/
        dump.pgcustom
        metadata.json
        checksum.sha256

Per the approved Week 1 decision: snapshot name collisions are rejected
outright (exit code 2 at the CLI layer) - no --force/overwrite in Week 1.
"""

from __future__ import annotations

import shutil
from pathlib import Path

SNAPSHOTS_DIR_NAME = "snapshots"
DUMP_FILE_NAME = "dump.pgcustom"
METADATA_FILE_NAME = "metadata.json"
CHECKSUM_FILE_NAME = "checksum.sha256"


class SnapshotAlreadyExistsError(Exception):
    """Raised when a snapshot with the given name already exists."""


class SnapshotNotFoundError(Exception):
    """Raised when a requested snapshot does not exist."""


def snapshots_root(project_dir: Path | None = None) -> Path:
    base = project_dir or Path.cwd()
    return base / ".igra" / SNAPSHOTS_DIR_NAME


def snapshot_dir(name: str, project_dir: Path | None = None) -> Path:
    return snapshots_root(project_dir) / name


def dump_path(name: str, project_dir: Path | None = None) -> Path:
    return snapshot_dir(name, project_dir) / DUMP_FILE_NAME


def metadata_path(name: str, project_dir: Path | None = None) -> Path:
    return snapshot_dir(name, project_dir) / METADATA_FILE_NAME


def checksum_path(name: str, project_dir: Path | None = None) -> Path:
    return snapshot_dir(name, project_dir) / CHECKSUM_FILE_NAME


def snapshot_exists(name: str, project_dir: Path | None = None) -> bool:
    return snapshot_dir(name, project_dir).is_dir()


def list_snapshot_names(project_dir: Path | None = None) -> list[str]:
    root = snapshots_root(project_dir)
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir())


def create_snapshot_directory(name: str, project_dir: Path | None = None) -> Path:
    """Create an empty snapshot directory for `name`.

    Raises SnapshotAlreadyExistsError if the name is already taken.
    The caller (capture.py, Step 10) is responsible for populating the
    three files and for calling delete_snapshot_directory on failure.
    """
    if snapshot_exists(name, project_dir):
        raise SnapshotAlreadyExistsError(
            f"A snapshot named '{name}' already exists."
        )
    target = snapshot_dir(name, project_dir)
    target.mkdir(parents=True, exist_ok=False)
    return target


def delete_snapshot_directory(name: str, project_dir: Path | None = None) -> None:
    """Delete a snapshot directory entirely.

    Used both for normal `igra snapshot delete` (future step) and for
    cleaning up a partially-written snapshot after a failed capture
    (ARCHITECTURE.md section 13).
    """
    target = snapshot_dir(name, project_dir)
    if not target.is_dir():
        raise SnapshotNotFoundError(f"No snapshot named '{name}' exists.")
    shutil.rmtree(target)
