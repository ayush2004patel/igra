# IGRA — Roadmap

**Sources of truth:** `PRD.md` (scope), `ARCHITECTURE.md` (technical approach), `DATA-MODEL.md` (entities), `CLI-SPEC.md` (exact commands + open `TBD`s).
**Purpose:** sequence MVP delivery and resolve outstanding `TBD`s at the right point — not before they're needed, not left unresolved past implementation.

---

## 1. Milestone Overview

```
Week 1        Week 2         Week 3          Week 4
Capture   →   Restore   →    Diff + CLI  →   Tests, Docs,
Engine        Safety         Polish           Packaging
```

| Week | Focus | Primary Output |
|---|---|---|
| 1 | Foundation + Capture | `igra init`, `igra status`, `igra snapshot create` working end-to-end |
| 2 | Restore engine | `igra snapshot restore` — staged, validated, per ARCHITECTURE §10–11 |
| 3 | Diff + remaining commands + CLI polish | `igra snapshot diff/list/show/delete`, Rich output |
| 4 | Hardening, tests, docs, release | v0.1.0 on PyPI |

---

## 2. Week 1 — Foundation & Capture

| Task | Reference |
|---|---|
| Project scaffold (`pyproject.toml`, Typer entrypoint, `uv`, Ruff, pytest config) | — |
| PostgreSQL Adapter: connection handling | ARCHITECTURE §12 |
| `.igra/` directory creation | ARCHITECTURE §5 |
| `igra init` — resolve connection-input method (`TBD` in CLI-SPEC §5) | CLI-SPEC §5 |
| `igra status` — implement `StatusResult` | DATA-MODEL §9 / CLI-SPEC §6 |
| Capture module: `pg_dump -Fc` invocation | ARCHITECTURE §4, §6 |
| Metadata generation (`SnapshotMetadata`, `TableInfo`) | DATA-MODEL §3–4 / ARCHITECTURE §7 |
| Checksum generation (`IntegrityRecord`) | DATA-MODEL §5 / ARCHITECTURE §8 |
| `igra snapshot create <name>` — resolve name-collision behavior (`TBD` in CLI-SPEC §7) | CLI-SPEC §7 |

**Week 1 exit criteria:** a developer can run `igra init`, `igra status`, and `igra snapshot create clean-state`, and inspect the resulting `.igra/snapshots/clean-state/` directory manually and see all three files match DATA-MODEL §2–5.

---

## 3. Week 2 — Restore Engine & Safety

| Task | Reference |
|---|---|
| Scratch-database creation | ARCHITECTURE §10 |
| `pg_restore` into scratch DB | ARCHITECTURE §10 |
| Scratch DB structural validation (tables present, row counts vs. metadata) | ARCHITECTURE §10 |
| **Spike: validate replacement mechanism** (e.g. rename-based swap) against real PostgreSQL — connection handling, permissions, edge cases | ARCHITECTURE §10–11 (flagged as implementation decision to validate) |
| Failure-path handling: scratch DB cleanup on any failed stage | ARCHITECTURE §13 |
| `RestoreResult` reporting (`failure_stage`, `target_database_state`) | DATA-MODEL §8 |
| Confirmation prompt before restore | PRD §9 / CLI-SPEC §11 (`TBD` — exact UX) |
| Resolve exit-code mapping for restore stages, including the still-open replacement-failure case | CLI-SPEC §4, §11 |

**Week 2 exit criteria:** a snapshot can be restored successfully; a deliberately corrupted checksum, a deliberately failed scratch restore, and a deliberately failed validation each leave the target database untouched — all three failure paths must be manually verified, not assumed.

> This is the highest-risk week. If the replacement-mechanism spike reveals problems, this week's scope takes priority over Week 3 polish — do not proceed to Week 3 with an unvalidated restore path.

---

## 4. Week 3 — Diff, Remaining Commands, CLI Polish

| Task | Reference |
|---|---|
| Schema diff via `pg_restore -l` comparison | ARCHITECTURE §9 / DATA-MODEL §7.1 |
| Row-count diff via metadata comparison | ARCHITECTURE §9 / DATA-MODEL §7.2 |
| `igra snapshot diff <a> <b>` | CLI-SPEC §10 |
| `igra snapshot list` — resolve output column set (`TBD` in CLI-SPEC §8) | CLI-SPEC §8 |
| `igra snapshot show <name>` | CLI-SPEC §9 |
| `igra snapshot delete <name>` — resolve confirmation requirement (`TBD` in CLI-SPEC §12) | CLI-SPEC §12 |
| Rich terminal output pass across all commands | PRD §13 (product principles) |
| Resolve remaining global `TBD`s: `--version`, verbosity flag, non-interactive bypass for confirmations | CLI-SPEC §3, §13 |

**Week 3 exit criteria:** all eight MVP commands from CLI-SPEC §2 are implemented and manually exercised against a real PostgreSQL dev database in a full workflow (`init` → `create` → modify DB → `create` → `diff` → `restore`).

---

## 5. Week 4 — Testing, Documentation, Packaging

| Task | Reference |
|---|---|
| pytest suite against a real throwaway Postgres (Docker-based fixtures for testing only — not a runtime dependency of IGRA itself) | TESTING.md (next document) |
| Explicit tests for each restore failure path (checksum, scratch restore, validation) | ARCHITECTURE §11, §13 |
| GitHub Actions CI (Postgres service container, lint, type-check, test) | — |
| `README.md` — install, quickstart, before/after demo | — |
| Verify no MVP boundary was silently crossed (re-check against PRD §10 / ARCHITECTURE §16 exclusion lists) | PRD §10 / ARCHITECTURE §16 |
| PyPI packaging, `v0.1.0` tag and release | — |

**Week 4 exit criteria:** `pip install igra` works from a clean environment, CI is green, and the README demo can be reproduced by someone who wasn't involved in building it.

---

## 6. Cross-Cutting: `TBD` Resolution Tracker

Every `TBD` currently open in `CLI-SPEC.md` is resolved by a specific week above, not left to implementation-time improvisation:

| `TBD` | CLI-SPEC location | Resolved in |
|---|---|---|
| `init` connection-input method | §5 | Week 1 |
| Snapshot name-collision behavior on `create` | §7 | Week 1 |
| Confirmation-prompt UX / non-interactive bypass | §3, §11, §12 | Week 2–3 |
| `--json` output mode | §3 | Not resolved in MVP — deferred, see §7 below |
| `snapshot list` output columns | §8 | Week 3 |
| `diff` exit code on differences-found | §10 | Week 3 |
| Restore replacement-failure exit code / resulting state | §11 | Week 2 (spike-dependent) |
| `--version`, verbosity flag | §3 | Week 3 |

---

## 7. Explicitly Deferred Past MVP

Consistent with PRD §12 and ARCHITECTURE §17 — not scheduled in any week above:

- MariaDB/MySQL adapter
- Database branching
- Incremental/delta snapshots
- Row-level data diffing
- State sharing / remote storage
- Anonymization/PII redaction
- `--json` machine-readable output (no prior document commits to this; may be reconsidered post-MVP)
- TUI / API

---

## 8. Release Milestone

| Version | Criteria |
|---|---|
| `v0.1.0` | All Week 1–4 exit criteria met; all MVP commands from CLI-SPEC §2 implemented; restore safety model manually verified against all documented failure stages |

No milestone before `v0.1.0` is intended for public use — internal development builds only.