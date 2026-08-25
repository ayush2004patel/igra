# IGRA — Data Model

**Companion to:** `PRD.md` (what/why) and `ARCHITECTURE.md` (how).
**This document defines the internal data contracts** — the shape of information IGRA reads, writes, and passes between components. No implementation code.
**Status:** Draft v1.0 — MVP data model

---

## 1. Entity Overview

```
Snapshot
  ├── SnapshotMetadata   (metadata.json)
  ├── DumpArchive         (dump.pgcustom)
  └── IntegrityRecord     (checksum.sha256)

DiffResult
  ├── SchemaDiff
  └── RowCountDiff

RestoreResult
StatusResult
```

Every entity below maps directly to something described in `ARCHITECTURE.md` — this document only defines its *shape*, not how it's produced.

---

## 2. `Snapshot`

The logical unit IGRA operates on. On disk, it is a directory; in memory, it is represented by its metadata plus references to its two companion files.

| Field | Type | Description |
|---|---|---|
| `name` | string | Human-readable, unique identifier (directory name) |
| `metadata` | `SnapshotMetadata` | See §3 |
| `dump_path` | path | Location of `dump.pgcustom` |
| `checksum_path` | path | Location of `checksum.sha256` |

---

## 3. `SnapshotMetadata` (`metadata.json`)

| Field | Type | Description |
|---|---|---|
| `id` | string (UUID) | Unique snapshot identity, independent of name |
| `name` | string | Human-readable name given at creation |
| `created_at` | timestamp (ISO-8601) | Capture time |
| `source_database` | string | Name of the database captured |
| `postgres_server_version` | string | Source server's PostgreSQL version |
| `pg_dump_version` | string | Version of `pg_dump` used at capture time |
| `dump_size_bytes` | integer | Size of `dump.pgcustom` after capture |
| `tables` | list of `TableInfo` | Per-table metadata, see §4 |

> Corresponds to ARCHITECTURE.md §7 (Metadata Generation).

---

## 4. `TableInfo`

One entry per table captured, nested inside `SnapshotMetadata.tables`.

| Field | Type | Description |
|---|---|---|
| `schema_name` | string | e.g. `public` |
| `table_name` | string | Table name |
| `row_count` | integer | Row count at capture time |

This is the sole data source for row-count-level diffing (§7) — no dump inspection needed for that comparison.

---

## 5. `IntegrityRecord` (`checksum.sha256`)

| Field | Type | Description |
|---|---|---|
| `algorithm` | string | Fixed as `sha256` in MVP |
| `checksum` | string (hex) | Digest of `dump.pgcustom` |
| `computed_at` | timestamp | When the checksum was generated (capture time) |

> Corresponds to ARCHITECTURE.md §8 (Checksum / Integrity Verification). Recomputed and compared, never trusted blindly, before any restore.

---

## 6. `DumpArchive` (`dump.pgcustom`)

Not a structure IGRA defines — it is PostgreSQL's own custom archive format, produced by `pg_dump -Fc`. IGRA treats it as opaque except for two operations:

| Operation | What IGRA reads |
|---|---|
| Table-of-contents listing | Table/index/constraint/sequence names — used for schema diff (§7) |
| Restore | Full archive content — used only inside the staged restore workflow (ARCHITECTURE.md §10) |

IGRA never parses or modifies row data inside the archive directly.

---

## 7. `DiffResult`

Produced by `igra snapshot diff <a> <b>`. Composed of two independently-optional parts, per ARCHITECTURE.md §9.

```
DiffResult
  ├── SchemaDiff        (from table-of-contents comparison)
  └── RowCountDiff       (from metadata.json comparison)
```

### 7.1 `SchemaDiff`

| Field | Type | Description |
|---|---|---|
| `added_objects` | list of `SchemaObjectRef` | Present in B, not in A |
| `removed_objects` | list of `SchemaObjectRef` | Present in A, not in B |
| `common_objects` | list of `SchemaObjectRef` | Present in both (informational) |

**`SchemaObjectRef`**

| Field | Type | Description |
|---|---|---|
| `object_type` | string | e.g. `table`, `index`, `constraint`, `sequence` |
| `schema_name` | string | e.g. `public` |
| `object_name` | string | Name of the object |

### 7.2 `RowCountDiff`

| Field | Type | Description |
|---|---|---|
| `table` | `SchemaObjectRef` (type = `table`) | Table being compared |
| `row_count_a` | integer | Row count in snapshot A |
| `row_count_b` | integer | Row count in snapshot B |
| `delta` | integer | `row_count_b - row_count_a` |

**Explicitly not modeled in MVP:** any structure representing row-level value differences. Matches ARCHITECTURE.md §9 and PRD.md §7 — not promised in MVP.

---

## 8. `RestoreResult`

Returned after `igra snapshot restore <name>` completes or aborts. Reflects the staged workflow in ARCHITECTURE.md §10–11 — this structure exists specifically so every stage's outcome is inspectable, not just a final pass/fail.

| Field | Type | Description |
|---|---|---|
| `snapshot_name` | string | Snapshot that was restored |
| `checksum_verified` | boolean | Result of the pre-restore integrity check |
| `scratch_restore_succeeded` | boolean | Whether `pg_restore` into the scratch database completed |
| `validation_passed` | boolean | Whether the scratch database passed structural validation |
| `replacement_completed` | boolean | Whether the target database was replaced |
| `failure_stage` | string or null | Which stage failed, if any (`checksum`, `scratch_restore`, `validation`, `replacement`) |
| `target_database_state` | string | One of: `untouched`, `replaced` — never a third, ambiguous value, per the safety model in ARCHITECTURE.md §11 |

---

## 9. `StatusResult`

Returned by `igra status`.

| Field | Type | Description |
|---|---|---|
| `connected` | boolean | Whether IGRA could connect to the configured database |
| `database_name` | string | Target database name |
| `postgres_server_version` | string | Connected server's version |
| `snapshot_count` | integer | Number of snapshots currently stored locally |

---

## 10. On-Disk Layout Recap

```
.igra/
└── snapshots/
    └── <snapshot-name>/
        ├── dump.pgcustom      →  DumpArchive
        ├── metadata.json      →  SnapshotMetadata (+ nested TableInfo[])
        └── checksum.sha256    →  IntegrityRecord
```

Every file on disk maps to exactly one entity defined above — there is no data stored outside this model.

---

## 11. Explicitly Out of Scope for This Data Model

Per PRD.md §10 and ARCHITECTURE.md §16, the following have **no corresponding entity** in MVP and must not be introduced silently during implementation:

- Row-level data diff structures
- Anonymization/redaction metadata
- Multi-database or adapter-type fields (MVP has exactly one implicit adapter: PostgreSQL)
- Remote storage location fields
- User/team/ownership fields
- Snapshot branching or parent/child relationships between snapshots

Any future need for these must be introduced via an updated `DATA-MODEL.md`, not inferred from code.