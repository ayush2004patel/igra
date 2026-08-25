"""Restore validation: verify a restored scratch database matches metadata.

Per ARCHITECTURE.md section 10: the scratch database is checked for
structural sanity (tables present, row counts consistent with
metadata.json) before it is allowed to replace anything. This is a
safety gate, not a guarantee of byte-for-byte correctness - it exists
to catch a restore that silently produced an incomplete or wrong
database, not to prove perfect fidelity.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import psycopg

from igra.adapter.postgres import get_table_row_counts
from igra.metadata import SnapshotMetadata


@dataclass
class ValidationResult:
    passed: bool
    missing_tables: list[str] = field(default_factory=list)
    row_count_mismatches: list[str] = field(default_factory=list)
    unexpected_tables: list[str] = field(default_factory=list)

    def summary(self) -> str:
        if self.passed:
            return "Validation passed: scratch database matches snapshot metadata."
        lines = ["Validation FAILED:"]
        if self.missing_tables:
            lines.append(f"  missing tables: {', '.join(self.missing_tables)}")
        if self.row_count_mismatches:
            lines.append(f"  row count mismatches: {', '.join(self.row_count_mismatches)}")
        if self.unexpected_tables:
            lines.append(f"  unexpected tables: {', '.join(self.unexpected_tables)}")
        return "\n".join(lines)


def validate_restored_database(
    conn: psycopg.Connection, expected: SnapshotMetadata
) -> ValidationResult:
    """Compare the scratch database's actual state against snapshot metadata.

    Checks:
      - every table in the snapshot's metadata exists in the scratch DB
      - every such table's row count matches what metadata recorded
      - no unexpected extra tables exist (informational, not currently
        a failure condition on its own - see note below)
    """
    actual_counts = get_table_row_counts(conn)
    actual_by_key = {
        (c.schema_name, c.table_name): c.row_count for c in actual_counts
    }

    missing_tables: list[str] = []
    row_count_mismatches: list[str] = []

    expected_keys = set()
    for table in expected.tables:
        key = (table.schema_name, table.table_name)
        expected_keys.add(key)
        qualified_name = f"{table.schema_name}.{table.table_name}"

        if key not in actual_by_key:
            missing_tables.append(qualified_name)
            continue

        actual_count = actual_by_key[key]
        if actual_count != table.row_count:
            row_count_mismatches.append(
                f"{qualified_name} (expected {table.row_count}, got {actual_count})"
            )

    # Unexpected tables are recorded but do not currently fail validation -
    # a scratch DB having *more* than expected is not itself dangerous the
    # way missing/mismatched data is. Surfaced for visibility only.
    unexpected_tables = [
        f"{schema}.{table}"
        for (schema, table) in actual_by_key
        if (schema, table) not in expected_keys
    ]

    passed = not missing_tables and not row_count_mismatches

    return ValidationResult(
        passed=passed,
        missing_tables=missing_tables,
        row_count_mismatches=row_count_mismatches,
        unexpected_tables=unexpected_tables,
    )
