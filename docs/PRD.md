# IGRA — Product Requirements Document

**Full name:** Isolated Generation & Recovery Architecture
**CLI command:** `igra`
**Status:** Draft v1.0 — MVP scope
**Document type:** Product Requirements (WHAT and WHY, not HOW)

---

## 1. Product Overview

IGRA is a developer-focused, local-first database state management tool. It lets developers capture, inspect, compare, and restore meaningful PostgreSQL database states while developing, testing, and debugging.

IGRA is **not** a backup tool, a disaster recovery system, a wrapper around `pg_dump`, a database administration GUI, or an AI database assistant. It treats useful database states as reproducible development artifacts — a workflow layer on top of existing database primitives, not a replacement for them.

---

## 2. Problem Statement

Developers frequently need a specific database state to develop against, test, or debug — for example:

> "This bug only happens when customer X exists, has these orders, one order has this payment status, and these related records exist."

Recreating that exact state today typically means some combination of manual test data creation, seed scripts, full database dumps/restores, copying whole development databases, or manually re-editing data and hoping to recreate what was there before.

The problem is not *"how do I back up my database"* — Postgres already solves that. The problem is:

> **"How can a developer conveniently capture, identify, inspect, compare, reproduce, and work with useful database states during development and debugging?"**

That distinction is the foundation of this product.

---

## 3. Target Users

**Primary:**
- Backend developers working against a local/dev PostgreSQL database
- Developers debugging state-dependent bugs
- QA/test engineers who need to repeatedly reproduce specific data conditions

**Secondary:**
- Small teams sharing reproducible bug states informally (e.g., via a snapshot file)
- Open-source contributors debugging issues reported against specific data conditions

---

## 4. Core Concept

```
PostgreSQL
    |
    v
Capture State
    |
    v
IGRA Snapshot
   / | \
  /  |  \
show diff restore
    |
    v
Reproducible State
```

A **snapshot** is a named, timestamped, inspectable capture of a database's meaningful state. Snapshots can be listed, inspected, compared against each other, and restored to — safely, and under the developer's explicit control.

IGRA is conceptually adjacent to how developers think about versioned code states, but the MVP does **not** attempt database branching or a "Git for databases" experience. The MVP goal is reliable, safe state capture and restoration.

---

## 5. Product Goals

| Goal | Description |
|---|---|
| Reliable capture | A snapshot faithfully represents the database state at capture time |
| Safe restoration | Restoring never silently destroys the current state |
| Inspectable snapshots | Developers can understand what a snapshot contains without restoring it |
| Useful comparison | Developers can see meaningful differences between two snapshots |
| Local-first | No cloud dependency, no external data transmission |
| Extensible foundation | Database-specific logic is isolated so future adapters (e.g. MariaDB) don't require rewriting the core engine |

---

## 6. MVP Scope

**Database:** PostgreSQL only. MariaDB, MySQL, SQLite, and MongoDB are explicitly out of scope for MVP.

**Architecture note (product-level):** database-specific functionality must be isolated behind an adapter/interface so future database support doesn't require rewriting the core state-management engine. Exact adapter design belongs in `ARCHITECTURE.md`.

**Initial command concept** (not a finalized spec — see `CLI-SPEC.md`):

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

---

## 7. MVP Features

| # | Feature | Description |
|---|---|---|
| 1 | PostgreSQL connection/configuration | Developer configures IGRA against a development database |
| 2 | Status | `igra status` — confirms connectivity and shows basic database info |
| 3 | Snapshot creation | `igra snapshot create <name>` — captures current state with unique identity, name, timestamp, database metadata, and integrity information |
| 4 | Snapshot listing | `igra snapshot list` — concise metadata for all available snapshots |
| 5 | Snapshot inspection | `igra snapshot show <name>` — explains what a snapshot represents without unnecessarily exposing sensitive data |
| 6 | State comparison | `igra snapshot diff <a> <b>` — meaningful state-level differences (schema changes, table presence, row counts, other relevant metadata) |
| 7 | State restoration | `igra snapshot restore <name>` — destructive; requires deliberate confirmation |
| 8 | Snapshot deletion | `igra snapshot delete <name>` — removes a snapshot without touching the active database |
| 9 | Safety & integrity | Confirmation for destructive actions, integrity validation, compatibility checks, safe failure handling |

**Note on diffing:** the MVP provides *useful* state-level differences. It does not promise a perfect, universal, row-level diff across every PostgreSQL data type. The exact diff algorithm is an architecture decision, not a product commitment made here.

**Note on restoration:** the exact snapshot storage/restoration mechanism is an architecture decision. The MVP does not assume this is simply a `pg_dump`/`pg_restore` wrapper.

---

## 8. Core User Workflow

```
igra snapshot create clean-state

# developer changes the database

igra snapshot create after-feature

igra snapshot diff clean-state after-feature

# developer wants to return to the earlier state

igra snapshot restore clean-state
```

**End-to-end MVP proof:**

1. Developer connects IGRA to a PostgreSQL development database.
2. Developer captures a meaningful database state and names it.
3. Developer can inspect previously captured states.
4. Developer can compare captured states.
5. Developer modifies the development database.
6. Developer safely returns to a captured state.
7. Developer continues working from that restored state.

---

## 9. Safety & Privacy

| Principle | Requirement |
|---|---|
| Destructive-operation confirmation | Restoration must never happen silently |
| Snapshot integrity | Snapshots must be validated before use |
| No silent overwrite | Existing snapshots/state are never overwritten without explicit action |
| Local-only | No cloud accounts, hosted services, external APIs, telemetry, or remote storage in the MVP |
| Meaningful errors | Failures are safe and clearly explained, not silent or cryptic |

Database state remains entirely under the developer's control at all times.

---

## 10. Out of Scope (MVP)

Explicitly excluded from MVP — these may become future scope, but are not part of this product's current requirements:

- MariaDB / MySQL / SQLite / MongoDB support
- Cloud storage
- Team collaboration features
- Authentication
- Web dashboard
- TUI
- Kubernetes integration
- Docker integration
- GitHub integration
- Automatic production synchronization
- Automatic PII detection/anonymization
- AI features
- Bug tracker integration
- Incremental/delta snapshots
- Automatic bug reproduction
- Distributed database support
- Database branching

---

## 11. Success Criteria

The MVP is successful if a developer can:

- Connect IGRA to a local PostgreSQL development database
- Capture a named, meaningful snapshot of the current state
- List and inspect existing snapshots without restoring them
- Compare two snapshots and understand meaningful differences
- Modify the database, then safely restore to a prior snapshot
- Continue development work from the restored state
- Trust that IGRA never silently destroys data

The project should also have, by MVP completion: automated tests, documented CLI behavior, predictable and safe failure handling, clean and extensible architecture, working CI, and packaging/distribution readiness.

---

## 12. Future Direction

Possible post-MVP directions (not MVP requirements, must not expand MVP scope):

- MariaDB / MySQL adapters
- Database state branching
- Selective / table-level state capture
- Incremental snapshots
- State sharing between developers
- Remote storage
- Anonymization
- CI integration
- Bug reproduction workflows
- TUI
- API

---

## 13. Product Principles

| Principle | Meaning |
|---|---|
| Developer-first | Designed around development/debugging workflows |
| Local-first | Data remains local by default |
| Safe by default | Destructive operations require deliberate action |
| Reproducible | Captured states should be usable again |
| Inspectable | Developers should understand what IGRA is doing |
| Extensible | Database-specific logic is isolated |
| Scriptable | CLI behavior should eventually be predictable |
| Minimal | Avoid unnecessary MVP features |

---

## 14. Open Questions / Decisions

These are intentionally unresolved at the product level and must be answered in the appropriate document before implementation:

- [ ] Exact snapshot storage mechanism (full dump, filesystem-level copy, logical export, or other) — `ARCHITECTURE.md`
- [ ] Exact diff algorithm and what "meaningful difference" includes at the row level — `ARCHITECTURE.md`
- [ ] Exact restoration mechanism and how safety confirmation is implemented — `ARCHITECTURE.md` / `CLI-SPEC.md`
- [ ] Snapshot storage location and format — `DATA-MODEL.md`
- [ ] What "database metadata" and "integrity information" precisely consist of per snapshot — `DATA-MODEL.md`
- [ ] Exact CLI flags, exit codes, and output formatting — `CLI-SPEC.md`
- [ ] How large databases are handled within MVP performance expectations — `ARCHITECTURE.md`

---

## 15. Related Specification Documents

This PRD defines **what** IGRA is and **why** it exists. The following documents define supporting detail and are authoritative for their respective domains once written:

- **`CLI-SPEC.md`** — exact commands, arguments, options, exit codes, output formatting, and error behavior.
- **`DATA-MODEL.md`** — internal entities, snapshot metadata structures, diff structures.
- **`ARCHITECTURE.md`** — repository structure, modules, adapter design, snapshot/restore mechanism, technology justification.
- **`TESTING.md`** — test strategy, fixtures, unit/integration/CLI tests, edge cases, and coverage expectations.
- **`ROADMAP.md`** — development milestones and scope boundaries.

Any requirement marked open above is intentional and must be resolved in the appropriate document before the relevant feature is implemented.