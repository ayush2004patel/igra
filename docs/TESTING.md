# IGRA — Testing Strategy

**Sources of truth:** `PRD.md` (safety requirements), `ARCHITECTURE.md` (failure modes, restore stages), `DATA-MODEL.md` (result shapes to assert against), `CLI-SPEC.md` (exit codes), `ROADMAP.md` (Week 4 scope).
**Purpose:** define what must be tested and why — not test code itself.

---

## 1. Testing Principles

| Principle | Meaning | Source |
|---|---|---|
| Safety is proven, not assumed | Every restore failure path in ARCHITECTURE §11 must have a corresponding test, not just manual spot-checks | ARCHITECTURE §11 / ROADMAP §5 |
| Real PostgreSQL, not mocks, for engine tests | `pg_dump`/`pg_restore` behavior is the product — mocking it would test nothing meaningful | ARCHITECTURE §6, §10 |
| Result shapes are contracts | Tests assert against the exact fields in DATA-MODEL §7–9, not incidental output text | DATA-MODEL §7–9 |
| No test may leave a real database at risk | Tests run against disposable, throwaway databases only | PRD §9 (local-first, safe by default) |

---

## 2. Test Levels

```
Unit tests
   │  metadata parsing, checksum logic, diff computation on fixture data
   ▼
Integration tests
   │  Capture / Restore / Diff against a real throwaway PostgreSQL
   ▼
CLI tests
   │  command parsing, exit codes, confirmation flows
   ▼
Safety tests
      restore failure paths — the highest-priority test category
```

| Level | What it exercises | Requires live Postgres? |
|---|---|---:|
| Unit | Metadata generation logic, checksum computation/comparison, `DiffResult` construction from fixture archives | No |
| Integration | Full capture → restore → diff cycle against a real database | Yes |
| CLI | Argument parsing, help output, exit codes per CLI-SPEC §4 | Depends on command |
| Safety | Every failure path in ARCHITECTURE §11 and §13 | Yes |

---

## 3. Test Environment

| Requirement | Detail |
|---|---|
| Database | A disposable, local PostgreSQL instance used only for tests — never a developer's real project database |
| Provisioning | Test-only concern; not a runtime dependency of IGRA itself (per ARCHITECTURE — IGRA has no Docker dependency in its product scope) |
| Isolation | Each test run uses its own database name/schema to avoid cross-test interference |
| CI | GitHub Actions with a Postgres service container, per ROADMAP §5 |

---

## 4. Fixtures Needed

| Fixture | Purpose |
|---|---|
| Small seeded database (a handful of tables, known row counts) | Baseline for capture/restore/diff tests |
| Database with no tables | Edge case — empty schema capture |
| Two related databases with known schema differences (one table added, one column-equivalent object removed) | `SchemaDiff` correctness (DATA-MODEL §7.1) |
| Two snapshots of the same schema with different row counts | `RowCountDiff` correctness (DATA-MODEL §7.2) |
| A snapshot with a deliberately corrupted `dump.pgcustom` (bit-flipped after capture) | Checksum-mismatch path (ARCHITECTURE §8) |
| A snapshot with a truncated/invalid `dump.pgcustom` | `pg_restore`-into-scratch failure path |
| A snapshot whose metadata row counts don't match a normal restore's actual result | Validation-failure path (ARCHITECTURE §10) |

---

## 5. Unit Test Coverage

| Area | Cases |
|---|---|
| `SnapshotMetadata` generation | Correct fields populated per DATA-MODEL §3; `TableInfo` entries match source tables |
| Checksum | Same file → same checksum; modified file → different checksum |
| Schema diff logic | Added/removed/common object classification correct given two fixture table-of-contents listings |
| Row-count diff logic | Delta computed correctly, including zero-delta and negative-delta cases |

---

## 6. Integration Test Coverage

| Command | Cases |
|---|---|
| `igra snapshot create` | Snapshot directory created with all three files (DATA-MODEL §2); metadata matches actual source database state; fails cleanly if source unreachable (ARCHITECTURE §13) |
| `igra snapshot list` | Reflects all snapshots present on disk |
| `igra snapshot show` | Returns full metadata; does not expose row-level data (ARCHITECTURE §14) |
| `igra snapshot diff` | Correct `SchemaDiff` and `RowCountDiff` against known fixture pairs |
| `igra snapshot restore` (success path) | Target database matches snapshot state after restore; `RestoreResult.target_database_state == "replaced"` |
| `igra snapshot delete` | Snapshot removed from disk; active/target database unaffected (explicit PRD §7 constraint) |

---

## 7. Safety Test Coverage — Highest Priority

Directly enumerated from ARCHITECTURE §11 and §13. Each row below is a required test, not optional coverage.

| Failure injected | Expected `RestoreResult` | Expected target DB state | Reference |
|---|---|---|---|
| Checksum mismatch | `failure_stage = "checksum"` | `untouched` | ARCHITECTURE §8, §10 |
| Scratch database restore fails (corrupt/truncated archive) | `failure_stage = "scratch_restore"` | `untouched` | ARCHITECTURE §10, §13 |
| Scratch database fails structural validation | `failure_stage = "validation"` | `untouched` | ARCHITECTURE §10 |
| Source database unreachable during capture | No snapshot written (no partial state) | N/A (capture, not restore) | ARCHITECTURE §13 |
| `pg_dump` fails mid-capture | Partial dump discarded | N/A | ARCHITECTURE §13 |

**Explicitly required, per ROADMAP §3:** a test attempting to observe behavior during the **replacement stage** itself, since ARCHITECTURE §13 flags this as an unresolved risk area. This test's job is to characterize actual behavior (even if imperfect) so `CLI-SPEC.md §11`'s `TBD` on replacement-failure exit code can be resolved with evidence, not guesswork.

---

## 8. CLI Test Coverage

| Area | Cases |
|---|---|
| Exit codes | Each mapping in CLI-SPEC §4 verified for at least one real scenario |
| Confirmation prompts | `restore` and any command requiring confirmation cannot proceed without it (PRD §9) |
| Invalid usage | Bad arguments/flags produce exit code `2` |
| Help output | `--help` available at root and per-subcommand |

---

## 9. Explicitly Out of Scope for MVP Testing

Consistent with ARCHITECTURE §16 and PRD §10 — do not build test coverage for features that don't exist in MVP:

- Row-level data diff correctness
- MariaDB/MySQL adapter behavior
- Performance/load testing against production-scale databases
- Incremental/delta snapshot correctness
- Anonymization/redaction correctness

---

## 10. Coverage Expectation

| Area | Expectation |
|---|---|
| Safety-critical paths (§7) | 100% of enumerated failure paths must have a passing test before `v0.1.0` |
| Core commands (§6) | Every MVP command has at least one integration test |
| Unit-testable logic (§5) | High coverage expected; exact percentage not mandated |

`v0.1.0` (per ROADMAP §8) must not ship if any safety test in §7 is failing or missing.