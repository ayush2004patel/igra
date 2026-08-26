"""Snapshot diff: schema and row-count comparison without a live restore.

Per ARCHITECTURE.md section 9: two independent comparison levels, both
achieved without ever restoring a snapshot.
  - Schema diff: table-of-contents comparison via `pg_restore -l`
  - Row-count diff: comparison of stored metadata.json row counts

Per PRD.md section 7 and ARCHITECTURE.md section 9: row-level data
value differences are explicitly out of scope for MVP.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from igra.metadata import SnapshotMetadata

# Schema object types this diff engine understands. Other pg_restore -l
# entry types (TABLE DATA, SEQUENCE OWNED BY, ACL, COMMENT, etc.) are
# informational/ownership/data entries, not schema-defining objects,
# and are intentionally excluded from the schema diff.
_RECOGNIZED_TYPES = {"TABLE", "SEQUENCE", "INDEX", "CONSTRAINT", "VIEW"}


class DiffError(Exception):
    """Raised when a snapshot's table of contents cannot be read."""


@dataclass(frozen=True)
class SchemaObjectRef:
    object_type: str
    schema_name: str
    object_name: str


@dataclass
class SchemaDiff:
    added_objects: list[SchemaObjectRef] = field(default_factory=list)
    removed_objects: list[SchemaObjectRef] = field(default_factory=list)
    common_objects: list[SchemaObjectRef] = field(default_factory=list)


@dataclass
class RowCountDiff:
    table: SchemaObjectRef
    row_count_a: int
    row_count_b: int
    delta: int


@dataclass
class DiffResult:
    snapshot_a: str
    snapshot_b: str
    schema_diff: SchemaDiff
    row_count_diffs: list[RowCountDiff]


def get_toc_entries(dump_path: Path) -> list[SchemaObjectRef]:
    """Return the recognized schema objects in a dump's table of contents.

    Uses `pg_restore -l`, which lists archive contents without ever
    restoring anything (ARCHITECTURE.md section 9).
    """
    try:
        result = subprocess.run(
            ["pg_restore", "-l", str(dump_path)],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise DiffError(
            "pg_restore was not found on PATH. Is PostgreSQL client tools installed?"
        ) from exc

    if result.returncode != 0:
        raise DiffError(
            f"pg_restore -l failed (exit code {result.returncode}): {result.stderr.strip()}"
        )

    entries: list[SchemaObjectRef] = []
    for line in result.stdout.splitlines():
        entry = _parse_toc_line(line)
        if entry is not None:
            entries.append(entry)
    return entries


# Multi-word entry types in pg_restore -l output that must be excluded
# BEFORE single-word type matching - otherwise "TABLE DATA" would be
# misread as a "TABLE" schema entry (a real bug caught during manual
# testing against live snapshots).
_EXCLUDED_MULTIWORD_PREFIXES = [
    ("TABLE", "DATA"),
    ("SEQUENCE", "SET"),
    ("SEQUENCE", "OWNED", "BY"),
]


def _parse_toc_line(line: str) -> SchemaObjectRef | None:
    """Parse one pg_restore -l line into a SchemaObjectRef, or None.

    Returns None for comment lines, blank lines, and entry types this
    diff engine doesn't track (data rows, ownership, ACLs, comments).
    """
    if not line.strip() or line.lstrip().startswith(";"):
        return None

    _dump_id, _, remainder = line.partition(";")
    if not remainder:
        return None

    tokens = remainder.split()
    if len(tokens) < 5:
        return None

    # tokens[0:2] are numeric catalog/oid identifiers; the type starts
    # at tokens[2] and may itself be multiple words.
    for prefix in _EXCLUDED_MULTIWORD_PREFIXES:
        if tuple(tokens[2 : 2 + len(prefix)]) == prefix:
            return None

    object_type = tokens[2]
    if object_type not in _RECOGNIZED_TYPES:
        return None

    rest = tokens[3:-1]  # everything between type and owner
    if len(rest) == 2:
        schema_name, object_name = rest
    elif len(rest) == 3:
        # e.g. CONSTRAINT/INDEX entries: schema, table, name
        schema_name, table_name, name = rest
        object_name = f"{table_name}.{name}"
    else:
        return None

    return SchemaObjectRef(
        object_type=object_type, schema_name=schema_name, object_name=object_name
    )


def compute_schema_diff(
    entries_a: list[SchemaObjectRef], entries_b: list[SchemaObjectRef]
) -> SchemaDiff:
    set_a = set(entries_a)
    set_b = set(entries_b)

    return SchemaDiff(
        added_objects=sorted(
            set_b - set_a, key=lambda o: (o.schema_name, o.object_name)
        ),
        removed_objects=sorted(
            set_a - set_b, key=lambda o: (o.schema_name, o.object_name)
        ),
        common_objects=sorted(
            set_a & set_b, key=lambda o: (o.schema_name, o.object_name)
        ),
    )


def compute_row_count_diff(
    metadata_a: SnapshotMetadata, metadata_b: SnapshotMetadata
) -> list[RowCountDiff]:
    """Compare row counts per table between two snapshots' metadata.

    Only tables present in both snapshots are compared - a table's
    mere presence/absence is already covered by the schema diff.
    """
    tables_a = {(t.schema_name, t.table_name): t.row_count for t in metadata_a.tables}
    tables_b = {(t.schema_name, t.table_name): t.row_count for t in metadata_b.tables}

    diffs: list[RowCountDiff] = []
    for key in sorted(set(tables_a) & set(tables_b)):
        schema_name, table_name = key
        count_a = tables_a[key]
        count_b = tables_b[key]
        diffs.append(
            RowCountDiff(
                table=SchemaObjectRef(
                    object_type="TABLE",
                    schema_name=schema_name,
                    object_name=table_name,
                ),
                row_count_a=count_a,
                row_count_b=count_b,
                delta=count_b - count_a,
            )
        )
    return diffs
