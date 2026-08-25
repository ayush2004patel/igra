# IGRA CLI Specification

**Sources of truth:** `PRD.md` (what/why), `ARCHITECTURE.md` (how), `DATA-MODEL.md` (data shapes).
**Rule for this document:** every command, flag, output field, and exit code below must trace back to something already established in those three documents. Where no prior document supports a specific detail, it is marked `TBD` rather than invented here.

---

## 1. CLI Design Principles

| Principle | Behavior | Source |
|---|---|---|
| Safe by default | Destructive operations require deliberate action | PRD §9 |
| Local-first | No network calls, no telemetry | PRD §9 / ARCHITECTURE §14 |
| Inspectable | Snapshots can be understood without restoring them | PRD §4 / ARCHITECTURE §9 |
| Non-destructive on failure | Target database is untouched unless replacement stage completes | ARCHITECTURE §11 |
| Predictable | Same snapshot state produces the same command output | PRD §13 |

---

## 2. Command Overview

| Command | Purpose | Modifies DB? | Modifies Snapshots? | Source |
|---|---|---:|---:|---|
| `igra init` | Initialize IGRA in a project (create `.igra/`, configure connection) | No | No | PRD §6 |
| `igra status` | Show connectivity and basic database info | No | No | PRD §7 / DATA-MODEL §9 |
| `igra snapshot create <name>` | Capture current DB state as a named snapshot | No | Yes (creates) | PRD §7 / ARCHITECTURE §4,§6,§7,§8 |
| `igra snapshot list` | List stored snapshots | No | No | PRD §7 |
| `igra snapshot show <name>` | Inspect a snapshot's metadata | No | No | PRD §7 / DATA-MODEL §3 |
| `igra snapshot diff <a> <b>` | Compare two snapshots | No | No | PRD §7 / ARCHITECTURE §9 / DATA-MODEL §7 |
| `igra snapshot restore <name>` | Restore DB to a snapshot's state | Yes | No | PRD §7 / ARCHITECTURE §10,§11 / DATA-MODEL §8 |
| `igra snapshot delete <name>` | Delete a stored snapshot | No | Yes (removes) | PRD §7 |

```
igra
├── init
├── status
└── snapshot
    ├── create <name>
    ├── list
    ├── show <name>
    ├── diff <snapshot-a> <snapshot-b>
    ├── restore <name>
    └── delete <name>
```
This tree matches the command concept already specified in PRD §6 exactly — no commands added or removed here.

---

## 3. Global CLI Behavior

| Aspect | Behavior | Status |
|---|---|---|
| `--help` | Available on root and every subcommand | Standard, not previously specified — included as baseline CLI convention |
| `--version` | Prints IGRA version | Standard, not previously specified — included as baseline CLI convention |
| Confirmation prompts | Required before any destructive operation (`restore`, `delete`) | PRD §9 requires this; exact prompt UX is `TBD` |
| Non-interactive/CI use | Whether a flag exists to skip confirmation (e.g. for scripting) | `TBD` — not addressed in PRD/ARCHITECTURE |
| Verbosity flag | Whether `-v`/`--verbose` exists | `TBD` |
| Output format | Human-readable by default; machine-readable (JSON) mode | `TBD` — DATA-MODEL defines result shapes that *could* back a `--json` flag, but no such flag is specified in PRD/ARCHITECTURE |
| Config location | Where connection configuration is read from (`.igra/` per ARCHITECTURE §5) | Established: lives under `.igra/` in the project directory |

Anything marked `TBD` must be resolved in a future revision of this document — it must not be decided during implementation.

---

## 4. Exit Codes

| Code | Meaning | Source |
|---:|---|---|
| `0` | Success | Baseline |
| `1` | Operation failed at a defined stage (e.g. restore validation failed, diff found target unreachable) | ARCHITECTURE §13 (per-stage failures) |
| `2` | Invalid CLI usage (bad arguments/flags) | Baseline |
| `3` | Database connection or configuration error | PRD §7 (`status`), ARCHITECTURE §13 |
| `4` | Snapshot integrity failure (checksum mismatch) | ARCHITECTURE §8,§10 |
| `5` | Unexpected/internal error | Baseline |

**Restore-specific exit code mapping is intentionally not finalized here.** `RestoreResult.failure_stage` (DATA-MODEL §8) has four possible values (`checksum`, `scratch_restore`, `validation`, `replacement`); whether each maps to a distinct exit code or all collapse to code `1` is `TBD`.

---

## 5. `igra init`

**Syntax:**
```bash
igra init
```

**Behavior (per PRD §7, feature 1):** configures IGRA for a PostgreSQL development database and creates the `.igra/` directory structure defined in ARCHITECTURE §5.

| Detail | Status |
|---|---|
| Connection input method (flags vs. interactive prompt vs. config file) | `TBD` — not specified in any prior document |
| Behavior if `.igra/` already exists | `TBD` |

**Exit codes used:** `0`, `2`, `3`

---

## 6. `igra status`

**Syntax:**
```bash
igra status
```

**Output fields** — exactly the `StatusResult` structure from DATA-MODEL §9, no additions:

| Field | Description |
|---|---|
| `connected` | Whether IGRA could connect |
| `database_name` | Target database name |
| `postgres_server_version` | Connected server's version |
| `snapshot_count` | Number of snapshots stored locally |

**Exit codes used:** `0` (connected), `3` (cannot connect)

---

## 7. `igra snapshot create <name>`

**Syntax:**
```bash
igra snapshot create <name>
```

**Behavior (per ARCHITECTURE §4, §6, §7, §8):** runs `pg_dump -Fc` against the source database, writes `dump.pgcustom`, generates `metadata.json` (per DATA-MODEL §3–4), and writes `checksum.sha256` (per DATA-MODEL §5).

| Condition | Result | Source |
|---|---|---|
| Name does not already exist | Snapshot created | PRD §7 |
| Name already exists | `TBD` — PRD/ARCHITECTURE do not specify overwrite behavior; must not be assumed | — |
| Source database unreachable | Capture aborts, no partial snapshot written | ARCHITECTURE §13 |
| `pg_dump` fails mid-capture | Partial dump discarded | ARCHITECTURE §13 |

**Exit codes used:** `0`, `1`, `3`

---

## 8. `igra snapshot list`

**Syntax:**
```bash
igra snapshot list
```

**Output:** one row per stored snapshot, drawn from `SnapshotMetadata` (DATA-MODEL §3) — at minimum `name`, `created_at`, `dump_size_bytes`. Exact column set beyond these three is `TBD`.

**Exit codes used:** `0`

---

## 9. `igra snapshot show <name>`

**Syntax:**
```bash
igra snapshot show <name>
```

**Output:** the full `SnapshotMetadata` structure (DATA-MODEL §3), including nested `TableInfo` entries (DATA-MODEL §4).

| Constraint | Source |
|---|---|
| Must not unnecessarily expose sensitive data | PRD §7 (feature 5), ARCHITECTURE §14 |
| Does not display row-level data content | ARCHITECTURE §6 (dump treated as opaque except TOC and restore) |

**Exit codes used:** `0`, `3` (snapshot name not found)

---

## 10. `igra snapshot diff <snapshot-a> <snapshot-b>`

**Syntax:**
```bash
igra snapshot diff <snapshot-a> <snapshot-b>
```

**Output:** the `DiffResult` structure (DATA-MODEL §7) — `SchemaDiff` (added/removed/common objects) and `RowCountDiff` (per-table deltas). No row-level value differences are computed or displayed, per PRD §7 and ARCHITECTURE §9.

**Exit codes used:** `0` (diff computed successfully, regardless of whether differences exist), `3` (a named snapshot does not exist)

Whether the presence of differences itself should produce a non-zero exit code (for CI use) is `TBD` — not addressed in PRD/ARCHITECTURE.

---

## 11. `igra snapshot restore <name>`

**Syntax:**
```bash
igra snapshot restore <name>
```

**Behavior:** executes the staged restore workflow exactly as defined in ARCHITECTURE §10–11 — checksum verification → scratch database restore → validation → protected replacement. Result is reportable as the `RestoreResult` structure (DATA-MODEL §8).

**Explicit constraint carried over from ARCHITECTURE §11:** this command must **never** be described or implemented as atomic. Output must make clear which stage the operation reached.

| Stage reached | `target_database_state` | Exit code |
|---|---|---|
| Checksum failed | `untouched` | `4` |
| Scratch restore failed | `untouched` | `1` |
| Validation failed | `untouched` | `1` |
| Replacement failed | `TBD` — ARCHITECTURE §13 flags this as a known risk area requiring explicit testing before release; exact resulting state is not yet guaranteed | `TBD` |
| Replacement succeeded | `replaced` | `0` |

**Confirmation requirement:** must prompt for explicit confirmation before proceeding, per PRD §9. Exact prompt wording/flag to skip it is `TBD`.

---

## 12. `igra snapshot delete <name>`

**Syntax:**
```bash
igra snapshot delete <name>
```

**Behavior (per PRD §7, feature 8):** removes the snapshot directory. Must not modify the active/target database — this is an explicit PRD constraint, not an assumption.

| Detail | Status |
|---|---|
| Confirmation required before delete | `TBD` — PRD requires confirmation for "destructive operations" generally (§9); whether delete counts as destructive in the same sense as restore is not explicitly stated |

**Exit codes used:** `0`, `3` (snapshot not found)

---

## 13. Explicitly Not Defined Here

The following are intentionally left undefined in this document because no prior document supports specific behavior for them. They must not be implemented until resolved:

- Exact confirmation-prompt UX and any non-interactive bypass flag
- `--json` or other machine-readable output mode
- Overwrite behavior when a snapshot name collides with an existing one
- Exit code(s) for a failed replacement stage during restore
- Whether `diff` differences alone should affect exit code
- Verbosity flags
- `init` connection-configuration input method

---

## 14. Consistency Check

Every command, field, and constraint above was cross-referenced against:

- `PRD.md` §6–9 (MVP scope, features, workflow, safety)
- `ARCHITECTURE.md` §4–13 (engine behavior, storage, restore safety, error handling)
- `DATA-MODEL.md` §2–9 (entity shapes)

No flags, exit codes, or behaviors were introduced beyond what these three documents already establish or explicitly defer.