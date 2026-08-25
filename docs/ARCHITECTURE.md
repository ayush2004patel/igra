# IGRA — Architecture Document

**Companion to:** `PRD.md` (product source of truth — defines WHAT and WHY).
**This document defines HOW.**
**Status:** Draft v1.0 — MVP architecture

---

## 1. Architecture Overview

IGRA is a layered CLI application. Each layer has a single responsibility, and PostgreSQL-specific logic is isolated behind an adapter so the core engine never depends on database-specific detail.

```
                    IGRA CLI
                       │
                       ▼
                Command Layer
                       │
                       ▼
                  State Engine
             ┌─────────┼─────────┐
             ▼         ▼         ▼
          Capture     Diff     Restore
             │         │         │
             └─────────┼─────────┘
                       ▼
             PostgreSQL Adapter
                       │
                       ▼
                  PostgreSQL
```

> **Design decision:** IGRA is **not** a thin wrapper around `pg_dump`/`pg_restore`. Those are used as underlying PostgreSQL primitives. IGRA's actual product is the layer built on top of them: named states, metadata, integrity verification, inspection, comparison, and safe restoration. This distinction governs every decision in this document.

---

## 2. Core Components

| Component | Responsibility |
|---|---|
| CLI | Parses user input, dispatches to Command Layer |
| Command Layer | Translates a CLI command into a State Engine operation; owns user-facing confirmation flows |
| State Engine | Orchestrates capture, diff, and restore; contains no PostgreSQL-specific code |
| Capture | Produces a snapshot from the current database state |
| Diff | Compares two snapshots without requiring a restore |
| Restore | Rebuilds a database from a snapshot, with validation before replacing live data |
| PostgreSQL Adapter | The only component that talks to PostgreSQL directly (via `pg_dump`, `pg_restore`, and SQL queries) |
| Snapshot Storage | Reads/writes snapshot directories on local disk |

---

## 3. Command → State Engine → Adapter Flow

```
igra snapshot create clean-state
        │
        ▼
Command Layer  ──validates args, confirms if needed──▶  State Engine
        │
        ▼
   Capture module
        │
        ▼
PostgreSQL Adapter ──▶ pg_dump -Fc ──▶ dump.pgcustom
        │
        ▼
Snapshot Storage ──▶ writes metadata.json + checksum.sha256
```

Every command follows the same shape: **Command Layer → State Engine → (Capture | Diff | Restore) → PostgreSQL Adapter → Snapshot Storage**. No layer skips ahead — the Command Layer never talks to the adapter directly, and the adapter never writes snapshot files itself.

---

## 4. Snapshot Engine

The snapshot engine has three operations, all built on the same underlying primitive (a custom-format `pg_dump` archive) but using different parts of it:

| Operation | Primitive used | Touches live/target DB? |
|---|---|---|
| Capture | `pg_dump -Fc` | Reads source DB only |
| Diff | Archive table-of-contents + stored metadata | No DB connection required |
| Restore | `pg_restore` into a scratch DB, then validated replacement | Reads scratch DB, then replaces target |

---

## 5. Snapshot Storage Structure

```
.igra/
└── snapshots/
    └── <snapshot-name>/
        ├── dump.pgcustom      # pg_dump custom-format archive (schema + data)
        ├── metadata.json      # snapshot identity, DB info, integrity info
        └── checksum.sha256    # checksum of dump.pgcustom
```

| File | Purpose |
|---|---|
| `dump.pgcustom` | The actual captured state — schema and data, in PostgreSQL's custom archive format |
| `metadata.json` | Everything IGRA needs to `list`, `show`, and `diff` without opening the dump |
| `checksum.sha256` | Verified before any restore is attempted |

`.igra/` lives inside the project directory by default and stores data **only locally** — no snapshot content leaves the machine.

---

## 6. `pg_dump` Custom-Format Integration

IGRA calls `pg_dump` with **custom format** (`-Fc`), not plain SQL and not filesystem/volume snapshots.

| Property | Why it matters to IGRA |
|---|---|
| Compressed | Keeps snapshot size reasonable for typical dev databases |
| Portable | Not tied to source machine, filesystem, or container runtime |
| Selective-restore capable | Enables inspection/validation without a full restore |
| Has an inspectable table of contents | This is what makes schema-level `diff` possible without restoring anything (see §9) |

Filesystem-level snapshotting (e.g. volume/filesystem snapshots) was considered and rejected for MVP — it would tie IGRA to a specific host/storage setup, which conflicts with the local-first, dependency-light principle in the PRD.

---

## 7. Metadata Generation

Captured at snapshot time, alongside the dump, using lightweight queries (not full data reads):

| Field | Source |
|---|---|
| Snapshot name, id, created-at | Command Layer / State Engine |
| Source database name | Adapter connection info |
| PostgreSQL server version | `SHOW server_version` or equivalent |
| `pg_dump` tool version | Adapter, at capture time |
| Per-table row counts | One lightweight query per table |
| Dump file size | Filesystem, after dump completes |

This metadata is what powers `snapshot list`, `snapshot show`, and the row-count portion of `snapshot diff` — all without needing to open or restore the archive.

---

## 8. Checksum / Integrity Verification

- A SHA-256 checksum of `dump.pgcustom` is computed immediately after capture and stored in `checksum.sha256`.
- Before **any** restore, IGRA recomputes the checksum and compares it. A mismatch aborts the restore before touching any database.
- This protects against partial writes, disk corruption, and accidental manual edits to snapshot files.

---

## 9. Diff Engine

Two levels of comparison, both restore-free:

```
Snapshot A                    Snapshot B
    │                              │
    ▼                              ▼
metadata.json               metadata.json
    │                              │
    └──────────► row-count delta per table ◄──────────┘

dump.pgcustom (A)                          dump.pgcustom (B)
    │                                              │
    ▼                                              ▼
pg_restore -l (table of contents)     pg_restore -l (table of contents)
    │                                              │
    └──────────► schema-level diff ◄───────────────┘
```

| Diff level | Method | MVP status |
|---|---|---|
| Schema (tables, indexes, constraints, sequences) | Compare `pg_restore -l` output between archives | In scope |
| Row counts per table | Compare stored `metadata.json` | In scope |
| Row-level data differences (actual value changes) | Would require restoring both snapshots and comparing data | **Out of scope for MVP** — matches PRD's explicit statement that a universal row-level diff is not promised |

---

## 10. Restore Workflow

**Design decision to validate during implementation:** the exact PostgreSQL-level replacement mechanism (e.g. `ALTER DATABASE ... RENAME`, or an alternative such as schema-level swap) needs to be validated against real PostgreSQL behavior — connection handling, permission requirements, and edge cases — before being finalized. The sequence below describes the *intended staged process*, not a guaranteed implementation.

```
1. Verify checksum of dump.pgcustom
        │
        ▼
2. Create a scratch database
        │
        ▼
3. pg_restore into the scratch database
        │
        ▼
4. Validate the scratch database
   (tables present, row counts consistent with metadata.json)
        │
   ┌────┴─────┐
   ▼          ▼
 FAILS      PASSES
   │          │
   ▼          ▼
 Drop        Replace target database with scratch database
 scratch     using a protected replacement step
 DB.         (exact mechanism: implementation decision, see §11)
 Target
 untouched.
```

---

## 11. Restore Safety Model

IGRA does **not** describe restore as atomic. It is a **staged, validated restore with a protected replacement step**:

| Stage | Guarantee |
|---|---|
| Checksum verification | Restore does not begin against a corrupted or tampered archive |
| Scratch-database restore | The target/live database is never modified during this stage |
| Validation | The restored scratch database is checked for structural sanity before it is allowed to replace anything |
| Protected replacement | The target database is only replaced after validation passes; exact mechanism (e.g. rename-based swap) is an implementation decision requiring validation, not a finalized guarantee |
| Failure handling | On failure at any stage before replacement, the target database is left untouched; the scratch database is cleaned up |

This model is intentionally conservative: **if IGRA cannot guarantee safety at a given stage, it stops before the target database is touched**, rather than proceeding on an assumption.

---

## 12. PostgreSQL Adapter Abstraction

The State Engine (Capture, Diff, Restore) contains **no PostgreSQL-specific code**. All database interaction goes through the PostgreSQL Adapter.

```
State Engine
     │
     ▼
Adapter Interface   (database-agnostic contract)
     │
     ▼
PostgreSQL Adapter  (only implementation in MVP)
     │
     ▼
PostgreSQL
```

| Boundary | Rule |
|---|---|
| State Engine → Adapter Interface | State Engine calls generic operations (capture state, restore state, get metadata) — never PostgreSQL-specific commands directly |
| Adapter Interface → PostgreSQL Adapter | The only concrete implementation in MVP; owns all `pg_dump`/`pg_restore`/SQL calls |

This boundary exists so a future adapter (e.g. MariaDB) could be added without changing Capture, Diff, or Restore logic — that is a future extension point, not MVP work.

---

## 13. Error Handling

| Failure point | Behavior |
|---|---|
| Cannot connect to source database | Capture aborts, clear error, no partial snapshot written |
| `pg_dump` fails mid-capture | Partial dump file is discarded, not left as a misleadingly "complete" snapshot |
| Checksum mismatch before restore | Restore aborts before any database is touched |
| Scratch database restore fails | Scratch database is dropped, target database untouched |
| Scratch database fails validation | Scratch database is dropped, target database untouched, reason reported |
| Replacement step fails | Documented as a known risk area pending the implementation decision in §11 — target-database state in this specific failure window must be explicitly tested and documented before release |

---

## 14. Security / Privacy Boundaries

| Boundary | Rule |
|---|---|
| Data location | Snapshot data stays on local disk under `.igra/` — never transmitted externally |
| Credentials | Database connection credentials are never written into snapshot files |
| Telemetry | None. IGRA does not phone home |
| Sensitive data in snapshots | Snapshots contain real captured data by nature of the tool; IGRA does not currently redact or anonymize — this is a known MVP limitation (see §16), not a silent gap |
| Metadata exposure | `metadata.json` and `snapshot show` are designed to avoid unnecessarily exposing full data values while still being useful for inspection |

---

## 15. Portability & PostgreSQL Version Compatibility

- Custom-format dumps are inherently portable across machines and operating systems — this is a property of the format itself, not something IGRA has to build.
- **Major-version compatibility is not guaranteed in reverse.** `pg_restore` generally supports restoring into an equal-or-newer PostgreSQL major version, not older.
- `metadata.json` records the source server's PostgreSQL version so IGRA can warn before attempting a restore likely to fail due to a version mismatch.

---

## 16. MVP Limitations

Stated explicitly, not left implicit:

- No parallel dump/restore — large databases will be slower than a production-grade backup tool.
- No incremental or delta snapshots — every capture is a full logical dump.
- No row-level data diffing — only schema-level and row-count-level comparison.
- No anonymization or PII redaction — snapshots contain real data as captured.
- Optimized for typical dev/test database sizes, not production-scale databases.
- The exact database-replacement mechanism in Restore (§10–11) is not yet finalized or guaranteed atomic.

---

## 17. Future Extension Points

Architecture decisions made now that are intended to make these easier later — none are MVP work:

| Future capability | Enabled by |
|---|---|
| Additional database adapters (e.g. MariaDB) | Adapter Interface boundary (§12) |
| Row-level data diffing | Diff Engine already isolated from Capture/Restore (§9) |
| Incremental/delta snapshots | Snapshot Storage structure is self-contained per snapshot (§5), allowing a future delta format alongside the current full-dump format |
| State sharing between developers | Snapshot directories are already self-contained and portable (§15) |
| Parallel dump/restore for larger databases | Isolated inside the PostgreSQL Adapter (§12) — would not require State Engine changes |

These are explicitly out of scope for MVP and must not be implemented until moved into an active roadmap milestone.