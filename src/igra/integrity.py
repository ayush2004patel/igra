"""Snapshot integrity: SHA-256 checksum generation and verification.

Per DATA-MODEL.md section 5 (IntegrityRecord) and ARCHITECTURE.md section 8:
computed at capture time, recomputed and compared before any restore.
Never trusted blindly.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

CHECKSUM_ALGORITHM = "sha256"
_CHUNK_SIZE = 65536  # 64KB - avoids loading large dumps fully into memory


class IntegrityRecord(BaseModel):
    algorithm: str
    checksum: str
    computed_at: datetime


class IntegrityError(Exception):
    """Raised when a checksum verification fails."""


def compute_checksum(file_path: Path) -> str:
    """Compute the SHA-256 hex digest of the given file, reading in chunks."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(_CHUNK_SIZE):
            hasher.update(chunk)
    return hasher.hexdigest()


def build_integrity_record(file_path: Path) -> IntegrityRecord:
    """Compute a checksum and wrap it as an IntegrityRecord, timestamped now."""
    return IntegrityRecord(
        algorithm=CHECKSUM_ALGORITHM,
        checksum=compute_checksum(file_path),
        computed_at=datetime.now(UTC),
    )


def save_integrity_record(record: IntegrityRecord, path: Path) -> None:
    """Write the checksum to disk as plain text: '<algorithm>:<checksum>'.

    Kept as a simple plain-text format (not JSON) so it can also be
    inspected/verified with standard shell tools if needed.
    """
    path.write_text(f"{record.algorithm}:{record.checksum}\n")


def load_integrity_record(path: Path) -> IntegrityRecord:
    """Read a checksum file written by save_integrity_record.

    computed_at is not stored in the plain-text format (only algorithm
    and checksum are persisted); this returns the record with
    computed_at set to the file's own modification time as a best-effort
    approximation, since the original computation time is not recoverable
    from this file alone.
    """
    content = path.read_text().strip()
    algorithm, _, checksum = content.partition(":")
    if not algorithm or not checksum:
        raise IntegrityError(f"Malformed checksum file at {path}: {content!r}")
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    return IntegrityRecord(algorithm=algorithm, checksum=checksum, computed_at=mtime)


def verify_checksum(file_path: Path, record: IntegrityRecord) -> bool:
    """Return True if file_path's current checksum matches the record."""
    if record.algorithm != CHECKSUM_ALGORITHM:
        raise IntegrityError(
            f"Unsupported checksum algorithm: {record.algorithm!r}"
        )
    actual = compute_checksum(file_path)
    return actual == record.checksum
