
IGRA is **not** a backup tool. It's a developer workflow layer on top of PostgreSQL's own primitives — for capturing, naming, comparing, and safely returning to database states while you work.

---

## Features

- **Safe, staged restore** — every restore verifies checksums, restores into a scratch database, and validates structural integrity *before* ever touching your real database. On failure, your database is untouched.
- **Schema + row-count diffing** — compare two snapshots without ever restoring them.
- **Local-first** — no cloud accounts, no telemetry, no data leaves your machine.
- **Safe by default** — destructive operations always require confirmation.

---

## Installation

Requires Python 3.12+ and PostgreSQL client tools (`pg_dump`, `pg_restore`) on your `PATH`.

```bash
pip install igra
```

*(Not yet published to PyPI — see [Development install](#development-install) below, or use Docker.)*

### Docker

```bash
docker build -t igra:0.1.0 .
```

Run it with `--network host` (to reach a PostgreSQL server on your machine) and a volume mount (so snapshots persist between runs):

```bash
docker run --rm --network host -v "$(pwd):/workspace" igra:0.1.0 init \
  --host localhost --port 5432 --dbname myapp_dev --user myapp

docker run --rm --network host -v "$(pwd):/workspace" \
  -e IGRA_DB_PASSWORD=your-password \
  igra:0.1.0 snapshot create clean-state
```

Since `.igra/` is written into the mounted `/workspace`, snapshots persist on your host filesystem across container runs.

---

## Quickstart

```bash
# Initialize IGRA for your project's database
igra init --host localhost --port 5432 --dbname myapp_dev --user myapp

# Set your database password (never stored on disk)
export IGRA_DB_PASSWORD=your-password

# Check connectivity
igra status

# Capture a snapshot before making risky changes
igra snapshot create clean-state

# ... develop, run migrations, break things ...

# See exactly what changed
igra snapshot diff clean-state after-changes

# Safely restore to the known-good state
igra snapshot restore clean-state
```

---

## Commands

| Command | Description |
|---|---|
| `igra init` | Configure IGRA for a PostgreSQL database |
| `igra status` | Check connectivity and see snapshot count |
| `igra snapshot create <name>` | Capture the current database state |
| `igra snapshot list` | List all stored snapshots |
| `igra snapshot show <name>` | Inspect a snapshot's metadata |
| `igra snapshot diff <a> <b>` | Compare two snapshots |
| `igra snapshot restore <name>` | Restore the database to a snapshot's state |
| `igra snapshot delete <name>` | Delete a stored snapshot |

---

## How restore safety works

Restore is a **staged, validated process** — never described or implemented as atomic:

1. Verify the snapshot's checksum
2. Restore into a disposable scratch database (your real database is untouched at this point)
3. Validate the scratch database's structure against the snapshot's recorded metadata
4. Only if validation passes: terminate connections to your database and swap it with the validated scratch database

If any step fails, your database is left exactly as it was. See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full design.

---

## Development install

```bash
git clone https://github.com/ayush2004patel/igra.git
cd igra
python3.13 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Running tests

Tests run against a real PostgreSQL database (not mocks) — see [`docs/TESTING.md`](docs/TESTING.md).

```bash
# Requires a local PostgreSQL instance with:
#   user: igra_dev / password: igra_dev_pass
#   database: igra_dev_test (with a seeded `customers` table)

pytest tests/ -v
ruff check src/ tests/
```

---

## Documentation

Full spec-driven planning documentation is in [`docs/`](docs/):

- [`PRD.md`](docs/PRD.md) — what IGRA is and why
- [`ARCHITECTURE.md`](docs/ARCHITECTURE.md) — how it works
- [`DATA-MODEL.md`](docs/DATA-MODEL.md) — internal data contracts
- [`CLI-SPEC.md`](docs/CLI-SPEC.md) — exact CLI behavior
- [`ROADMAP.md`](docs/ROADMAP.md) — development milestones
- [`TESTING.md`](docs/TESTING.md) — test strategy

## Status

IGRA is in active development. Current scope is PostgreSQL only — see [`docs/PRD.md`](docs/PRD.md) for MVP boundaries and future direction.

## License

MIT