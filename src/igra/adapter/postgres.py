"""PostgreSQL adapter: the only component that talks to PostgreSQL directly.

Per ARCHITECTURE.md section 12, the State Engine (and higher layers) must
never construct SQL or call psycopg directly - everything goes through here.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import psycopg

from igra.config import DatabaseConfig


class ConnectionError_(Exception):
    """Raised when IGRA cannot connect to the configured database."""


class DumpError(Exception):
    """Raised when pg_dump fails or produces no usable output."""


@dataclass
class TableRowCount:
    schema_name: str
    table_name: str
    row_count: int


def _connection_string(config: DatabaseConfig, password: str) -> str:
    return (
        f"host={config.host} port={config.port} "
        f"dbname={config.dbname} user={config.user} password={password}"
    )


@contextmanager
def connect(config: DatabaseConfig, password: str) -> Iterator[psycopg.Connection]:
    """Open a connection to the configured PostgreSQL database.

    Raises ConnectionError_ with a clear message on failure - never lets
    a raw psycopg exception leak past this boundary.
    """
    conn_str = _connection_string(config, password)
    try:
        conn = psycopg.connect(conn_str)
    except psycopg.OperationalError as exc:
        raise ConnectionError_(
            f"Could not connect to PostgreSQL at {config.host}:{config.port}/"
            f"{config.dbname} as user '{config.user}': {exc}"
        ) from exc
    try:
        yield conn
    finally:
        conn.close()


def get_server_version(conn: psycopg.Connection) -> str:
    """Return the connected server's PostgreSQL version string."""
    with conn.cursor() as cur:
        cur.execute("SHOW server_version;")
        row = cur.fetchone()
        return row[0] if row else "unknown"


def list_user_tables(conn: psycopg.Connection) -> list[tuple[str, str]]:
    """Return (schema_name, table_name) for all user tables.

    Excludes PostgreSQL's own internal schemas (pg_catalog, information_schema).
    """
    query = """
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_type = 'BASE TABLE'
          AND table_schema NOT IN ('pg_catalog', 'information_schema')
        ORDER BY table_schema, table_name;
    """
    with conn.cursor() as cur:
        cur.execute(query)
        return [(row[0], row[1]) for row in cur.fetchall()]


def get_table_row_counts(conn: psycopg.Connection) -> list[TableRowCount]:
    """Return row counts for every user table.

    Uses a direct COUNT(*) per table - accurate but not instant on very
    large tables. Acceptable for MVP dev/test database sizes (ARCHITECTURE
    section 16 limitation).
    """
    results: list[TableRowCount] = []
    tables = list_user_tables(conn)
    with conn.cursor() as cur:
        for schema_name, table_name in tables:
            # Identifiers cannot be parameterized; validated via
            # information_schema lookup above, so this is safe from
            # injection - these are real catalog-sourced names, not
            # user-supplied strings.
            cur.execute(
                f'SELECT COUNT(*) FROM "{schema_name}"."{table_name}";'
            )
            row = cur.fetchone()
            count = row[0] if row else 0
            results.append(
                TableRowCount(
                    schema_name=schema_name, table_name=table_name, row_count=count
                )
            )
    return results


def get_pg_dump_version() -> str:
    """Return the version string of the pg_dump binary on PATH."""
    try:
        result = subprocess.run(
            ["pg_dump", "--version"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise DumpError(f"Could not determine pg_dump version: {exc}") from exc
    return result.stdout.strip()


def dump_database(
    config: DatabaseConfig, password: str, output_path: Path
) -> None:
    """Run `pg_dump -Fc` against the configured database, writing to output_path.

    Per ARCHITECTURE.md section 6: custom format (-Fc), not plain SQL.
    Per ARCHITECTURE.md section 13: on failure, the caller is responsible
    for discarding any partial file - this function does not delete
    output_path itself on failure, so capture.py (Step 10) can inspect
    or clean up as needed.

    Password is passed via the PGPASSWORD environment variable for this
    subprocess call only - never via a command-line argument (which
    would be visible in process listings), and never written to disk.
    """
    env = os.environ.copy()
    env["PGPASSWORD"] = password

    cmd = [
        "pg_dump",
        "-Fc",
        "-h", config.host,
        "-p", str(config.port),
        "-U", config.user,
        "-f", str(output_path),
        config.dbname,
    ]

    try:
        result = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise DumpError(
            "pg_dump was not found on PATH. Is PostgreSQL client tools installed?"
        ) from exc

    if result.returncode != 0:
        raise DumpError(
            f"pg_dump failed (exit code {result.returncode}): {result.stderr.strip()}"
        )

    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise DumpError(
            f"pg_dump reported success but produced no output at {output_path}"
        )



class RestoreError(Exception):
    """Raised when pg_restore fails or the scratch database cannot be created."""


def create_database(
    config: DatabaseConfig, password: str, new_dbname: str
) -> None:
    """Create a new, empty database on the same server as config.dbname.

    Used to create the scratch database for restore (ARCHITECTURE.md
    section 10). Connects to the server's default 'postgres' maintenance
    database to issue CREATE DATABASE, since you cannot create a database
    while connected to it.
    """
    admin_config = DatabaseConfig(
        host=config.host, port=config.port, dbname="postgres", user=config.user
    )
    try:
        with connect(admin_config, password) as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                # Database names cannot be parameterized in DDL; new_dbname
                # is generated internally by IGRA (uuid-based), never
                # user-supplied directly, so this is safe.
                cur.execute(f'CREATE DATABASE "{new_dbname}";')
    except ConnectionError_ as exc:
        raise RestoreError(f"Could not create scratch database: {exc}") from exc
    except psycopg.Error as exc:
        raise RestoreError(f"Could not create scratch database: {exc}") from exc


def drop_database(
    config: DatabaseConfig, password: str, target_dbname: str
) -> None:
    """Drop a database, terminating any existing connections to it first.

    Used both to clean up a scratch database after a failed restore, and
    potentially for other cleanup paths.
    """
    admin_config = DatabaseConfig(
        host=config.host, port=config.port, dbname="postgres", user=config.user
    )
    try:
        with connect(admin_config, password) as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT pg_terminate_backend(pid)
                    FROM pg_stat_activity
                    WHERE datname = %s AND pid <> pg_backend_pid();
                    """,
                    (target_dbname,),
                )
                cur.execute(f'DROP DATABASE IF EXISTS "{target_dbname}";')
    except ConnectionError_ as exc:
        raise RestoreError(f"Could not drop database '{target_dbname}': {exc}") from exc
    except psycopg.Error as exc:
        raise RestoreError(f"Could not drop database '{target_dbname}': {exc}") from exc


def restore_database(
    config: DatabaseConfig,
    password: str,
    target_dbname: str,
    dump_file: Path,
) -> None:
    """Run `pg_restore` from dump_file into target_dbname.

    target_dbname must already exist and be empty (created via
    create_database). This does NOT touch config.dbname - the caller
    is responsible for directing this at a scratch database only.
    """
    env = os.environ.copy()
    env["PGPASSWORD"] = password

    cmd = [
        "pg_restore",
        "-h", config.host,
        "-p", str(config.port),
        "-U", config.user,
        "-d", target_dbname,
        str(dump_file),
    ]

    try:
        result = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RestoreError(
            "pg_restore was not found on PATH. Is PostgreSQL client tools installed?"
        ) from exc

    if result.returncode != 0:
        raise RestoreError(
            f"pg_restore failed (exit code {result.returncode}): {result.stderr.strip()}"
        )


def terminate_connections(
    config: DatabaseConfig, password: str, target_dbname: str
) -> int:
    """Terminate all active connections to target_dbname.

    Required before a rename-based replacement, per the Week 2 spike:
    ALTER DATABASE ... RENAME fails if any session is connected to the
    database being renamed. Returns the number of connections terminated.
    """
    admin_config = DatabaseConfig(
        host=config.host, port=config.port, dbname="postgres", user=config.user
    )
    try:
        with connect(admin_config, password) as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT pg_terminate_backend(pid)
                    FROM pg_stat_activity
                    WHERE datname = %s AND pid <> pg_backend_pid();
                    """,
                    (target_dbname,),
                )
                terminated = cur.fetchall()
                return len(terminated)
    except ConnectionError_ as exc:
        raise RestoreError(
            f"Could not terminate connections to '{target_dbname}': {exc}"
        ) from exc
    except psycopg.Error as exc:
        raise RestoreError(
            f"Could not terminate connections to '{target_dbname}': {exc}"
        ) from exc


def rename_database(
    config: DatabaseConfig, password: str, old_name: str, new_name: str
) -> None:
    """Rename a database. Fails if old_name has active connections -
    call terminate_connections() first (per the Week 2 spike findings).
    """
    admin_config = DatabaseConfig(
        host=config.host, port=config.port, dbname="postgres", user=config.user
    )
    try:
        with connect(admin_config, password) as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(
                    f'ALTER DATABASE "{old_name}" RENAME TO "{new_name}";'
                )
    except ConnectionError_ as exc:
        raise RestoreError(
            f"Could not rename database '{old_name}' to '{new_name}': {exc}"
        ) from exc
    except psycopg.Error as exc:
        raise RestoreError(
            f"Could not rename database '{old_name}' to '{new_name}': {exc}"
        ) from exc


def database_exists(config: DatabaseConfig, password: str, dbname: str) -> bool:
    """Check whether a database with the given name exists on the server."""
    admin_config = DatabaseConfig(
        host=config.host, port=config.port, dbname="postgres", user=config.user
    )
    with connect(admin_config, password) as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s;", (dbname,))
        return cur.fetchone() is not None