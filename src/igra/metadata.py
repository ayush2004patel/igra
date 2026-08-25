"""Snapshot metadata: SnapshotMetadata and TableInfo models.

Per DATA-MODEL.md sections 3-4. Written to metadata.json alongside
each snapshot (ARCHITECTURE.md section 7).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

import psycopg
from pydantic import BaseModel

from igra.adapter.postgres import (
    TableRowCount,
    get_pg_dump_version,
    get_server_version,
    get_table_row_counts,
)
from igra.config import DatabaseConfig


class TableInfo(BaseModel):
    schema_name: str
    table_name: str
    row_count: int


class SnapshotMetadata(BaseModel):
    id: str
    name: str
    created_at: datetime
    source_database: str
    postgres_server_version: str
    pg_dump_version: str
    dump_size_bytes: int
    tables: list[TableInfo]


def _table_info_from_row_counts(counts: list[TableRowCount]) -> list[TableInfo]:
    return [
        TableInfo(
            schema_name=c.schema_name,
            table_name=c.table_name,
            row_count=c.row_count,
        )
        for c in counts
    ]


def build_metadata(
    name: str,
    config: DatabaseConfig,
    conn: psycopg.Connection,
    dump_size_bytes: int,
) -> SnapshotMetadata:
    """Build SnapshotMetadata from a live connection and a completed dump.

    Called by capture.py (Step 10) after dump_database() has already run -
    dump_size_bytes is read from the resulting file, not re-derived here,
    to keep this function focused purely on metadata assembly.
    """
    server_version = get_server_version(conn)
    dump_version = get_pg_dump_version()
    row_counts = get_table_row_counts(conn)

    return SnapshotMetadata(
        id=str(uuid.uuid4()),
        name=name,
        created_at=datetime.now(UTC),
        source_database=config.dbname,
        postgres_server_version=server_version,
        pg_dump_version=dump_version,
        dump_size_bytes=dump_size_bytes,
        tables=_table_info_from_row_counts(row_counts),
    )


def save_metadata(metadata: SnapshotMetadata, path: Path) -> None:
    """Write metadata as JSON to the given path."""
    path.write_text(metadata.model_dump_json(indent=2))


def load_metadata(path: Path) -> SnapshotMetadata:
    """Read and validate metadata JSON from the given path."""
    return SnapshotMetadata.model_validate_json(path.read_text())
