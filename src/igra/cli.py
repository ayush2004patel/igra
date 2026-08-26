"""IGRA CLI entrypoint.

Week 1 scaffold: --help, --version, and `igra init` are functional.
Remaining subcommands (status, snapshot) are added in later steps.
"""

from __future__ import annotations

import typer

from igra import __version__
from igra.adapter.postgres import (
    ConnectionError_,
    connect,
    get_server_version,
)
from igra.capture import CaptureError, create_snapshot
from igra.config import (
    ConfigError,
    DatabaseConfig,
    IgraConfig,
    config_exists,
    load_config,
    resolve_db_password,
    save_config,
)
from igra.diff import (
    DiffError,
    compute_row_count_diff,
    compute_schema_diff,
    get_toc_entries,
)
from igra.metadata import load_metadata
from igra.restore import restore_snapshot
from igra.storage import (
    SnapshotNotFoundError,
    delete_snapshot_directory,
    dump_path,
    list_snapshot_names,
    metadata_path,
    snapshot_exists,
)

app = typer.Typer(
    name="igra",
    help="Isolated Generation & Recovery Architecture - "
    "local-first PostgreSQL database state management for developers.",
    no_args_is_help=True,
)

snapshot_app = typer.Typer(
    name="snapshot",
    help="Manage database state snapshots.",
)
app.add_typer(snapshot_app, name="snapshot")

def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"igra {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        help="Show the IGRA version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """IGRA - local-first PostgreSQL database state management."""


@app.command()
def init(
    host: str = typer.Option(None, "--host", help="PostgreSQL host."),
    port: int = typer.Option(None, "--port", help="PostgreSQL port."),
    dbname: str = typer.Option(None, "--dbname", help="Database name."),
    user: str = typer.Option(None, "--user", help="Database user."),
) -> None:
    """Initialize IGRA in the current project (creates .igra/config.toml)."""
    if config_exists():
        typer.secho(
            "IGRA is already initialized in this project (.igra/config.toml exists).",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=2)

    if host is None:
        host = typer.prompt("PostgreSQL host", default="localhost")
    if port is None:
        port = typer.prompt("PostgreSQL port", default=5432, type=int)
    if dbname is None:
        dbname = typer.prompt("Database name")
    if user is None:
        user = typer.prompt("Database user")

    config = IgraConfig(
        database=DatabaseConfig(host=host, port=port, dbname=dbname, user=user)
    )

    try:
        path = save_config(config)
    except ConfigError as exc:
        typer.secho(f"Failed to initialize IGRA: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=3) from exc

    typer.secho(f"IGRA initialized. Configuration written to {path}", fg=typer.colors.GREEN)
    typer.echo("Note: database password is not stored. Set IGRA_DB_PASSWORD "
               "or you will be prompted when needed.")

def _count_snapshots() -> int:
    from pathlib import Path

    snapshots_dir = Path.cwd() / ".igra" / "snapshots"
    if not snapshots_dir.is_dir():
        return 0
    return len([p for p in snapshots_dir.iterdir() if p.is_dir()])


@app.command()
def status() -> None:
    """Show IGRA connectivity and basic database info."""
    try:
        config = load_config()
    except ConfigError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=3) from exc

    try:
        password = resolve_db_password()
    except Exception as exc:
        typer.secho(f"Could not resolve database password: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=3) from exc

    try:
        with connect(config.database, password) as conn:
            version = get_server_version(conn)
    except ConnectionError_ as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=3) from exc

    snapshot_count = _count_snapshots()

    typer.secho("connected: true", fg=typer.colors.GREEN)
    typer.echo(f"database_name: {config.database.dbname}")
    typer.echo(f"postgres_server_version: {version}")
    typer.echo(f"snapshot_count: {snapshot_count}")

@snapshot_app.command("create")
def snapshot_create(
    name: str = typer.Argument(..., help="Name for the new snapshot."),
) -> None:
    """Capture the current database state as a named snapshot."""
    try:
        config = load_config()
    except ConfigError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=3) from exc

    try:
        password = resolve_db_password()
    except Exception as exc:
        typer.secho(f"Could not resolve database password: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=3) from exc

    try:
        with connect(config.database, password) as conn:
            metadata = create_snapshot(name, config.database, password, conn)
    except ConnectionError_ as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=3) from exc
    except CaptureError as exc:
        typer.secho(f"Snapshot creation failed: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=2) from exc

    typer.secho(f"Snapshot '{name}' created.", fg=typer.colors.GREEN)
    typer.echo(f"id: {metadata.id}")
    typer.echo(f"created_at: {metadata.created_at}")
    typer.echo(f"dump_size_bytes: {metadata.dump_size_bytes}")
    typer.echo(f"tables: {len(metadata.tables)}")
    
@snapshot_app.command("restore")
def snapshot_restore(
    name: str = typer.Argument(..., help="Name of the snapshot to restore."),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip the confirmation prompt."
    ),
) -> None:
    """Restore the database to the state captured in a snapshot.

    This is a destructive operation on the current database state.
    Per ARCHITECTURE.md, this is a staged, validated restore - NOT
    atomic. See the printed result for exactly which stage completed.
    """
    try:
        config = load_config()
    except ConfigError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=3) from exc

    if not yes:
        confirmed = typer.confirm(
            f"This will replace the current contents of database "
            f"'{config.database.dbname}' with snapshot '{name}'. Continue?"
        )
        if not confirmed:
            typer.echo("Restore cancelled.")
            raise typer.Exit(code=0)

    try:
        password = resolve_db_password()
    except Exception as exc:
        typer.secho(f"Could not resolve database password: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=3) from exc

    try:
        result = restore_snapshot(name, config.database, password)
    except SnapshotNotFoundError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=3) from exc

    typer.echo(f"checksum_verified: {result.checksum_verified}")
    typer.echo(f"scratch_restore_succeeded: {result.scratch_restore_succeeded}")
    typer.echo(f"validation_passed: {result.validation_passed}")
    typer.echo(f"replacement_completed: {result.replacement_completed}")
    typer.echo(f"target_database_state: {result.target_database_state}")

    if result.replacement_completed:
        typer.secho(f"Snapshot '{name}' restored successfully.", fg=typer.colors.GREEN)
        raise typer.Exit(code=0)

    typer.secho(
        f"Restore did not complete. Failed at stage: {result.failure_stage}",
        fg=typer.colors.RED,
    )
    raise typer.Exit(code=1)
    
@snapshot_app.command("list")
def snapshot_list() -> None:
    """List all stored snapshots."""
    try:
        load_config()
    except ConfigError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=3) from exc

    names = list_snapshot_names()

    if not names:
        typer.echo("No snapshots found.")
        raise typer.Exit(code=0)

    typer.echo(f"{'NAME':<30} {'CREATED':<26} {'SIZE (bytes)':<12}")
    for name in names:
        try:
            meta = load_metadata(metadata_path(name))
            typer.echo(
                f"{meta.name:<30} {meta.created_at!s:<26} {meta.dump_size_bytes:<12}"
            )
        except (OSError, ValueError):
            # OSError: metadata.json missing/unreadable. ValueError: JSON
            # parse or pydantic validation failure. Either way, don't let
            # one broken snapshot's metadata crash the whole list command.
            typer.echo(f"{name:<30} (metadata unreadable)")

@snapshot_app.command("show")
def snapshot_show(
    name: str = typer.Argument(..., help="Name of the snapshot to inspect."),
) -> None:
    """Show detailed metadata for a single snapshot."""
    try:
        load_config()
    except ConfigError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=3) from exc

    if not snapshot_exists(name):
        typer.secho(f"No snapshot named '{name}' exists.", fg=typer.colors.RED)
        raise typer.Exit(code=3)

    try:
        meta = load_metadata(metadata_path(name))
    except (OSError, ValueError) as exc:
        typer.secho(f"Could not read metadata for '{name}': {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=3) from exc

    typer.echo(f"name: {meta.name}")
    typer.echo(f"id: {meta.id}")
    typer.echo(f"created_at: {meta.created_at}")
    typer.echo(f"source_database: {meta.source_database}")
    typer.echo(f"postgres_server_version: {meta.postgres_server_version}")
    typer.echo(f"pg_dump_version: {meta.pg_dump_version}")
    typer.echo(f"dump_size_bytes: {meta.dump_size_bytes}")
    typer.echo("tables:")
    for table in meta.tables:
        typer.echo(
            f"  {table.schema_name}.{table.table_name}  ({table.row_count} rows)"
        )

@snapshot_app.command("diff")
def snapshot_diff(
    snapshot_a: str = typer.Argument(..., help="First snapshot name."),
    snapshot_b: str = typer.Argument(..., help="Second snapshot name."),
) -> None:
    """Compare two snapshots: schema differences and row count changes."""
    try:
        load_config()
    except ConfigError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=3) from exc

    for name in (snapshot_a, snapshot_b):
        if not snapshot_exists(name):
            typer.secho(f"No snapshot named '{name}' exists.", fg=typer.colors.RED)
            raise typer.Exit(code=3)

    try:
        entries_a = get_toc_entries(dump_path(snapshot_a))
        entries_b = get_toc_entries(dump_path(snapshot_b))
    except DiffError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=3) from exc

    schema_result = compute_schema_diff(entries_a, entries_b)

    meta_a = load_metadata(metadata_path(snapshot_a))
    meta_b = load_metadata(metadata_path(snapshot_b))
    row_diffs = compute_row_count_diff(meta_a, meta_b)

    typer.echo(f"Comparing '{snapshot_a}' -> '{snapshot_b}'")
    typer.echo("")

    if schema_result.added_objects:
        typer.secho("Added:", fg=typer.colors.GREEN)
        for obj in schema_result.added_objects:
            typer.echo(f"  + {obj.object_type} {obj.schema_name}.{obj.object_name}")

    if schema_result.removed_objects:
        typer.secho("Removed:", fg=typer.colors.RED)
        for obj in schema_result.removed_objects:
            typer.echo(f"  - {obj.object_type} {obj.schema_name}.{obj.object_name}")

    changed_row_counts = [d for d in row_diffs if d.delta != 0]
    if changed_row_counts:
        typer.secho("Row count changes:", fg=typer.colors.YELLOW)
        for d in changed_row_counts:
            sign = "+" if d.delta > 0 else ""
            typer.echo(
                f"  {d.table.schema_name}.{d.table.object_name}: "
                f"{d.row_count_a} -> {d.row_count_b} ({sign}{d.delta})"
            )

    if (
        not schema_result.added_objects
        and not schema_result.removed_objects
        and not changed_row_counts
    ):
        typer.echo("No differences found.")

@snapshot_app.command("delete")
def snapshot_delete(
    name: str = typer.Argument(..., help="Name of the snapshot to delete."),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip the confirmation prompt."
    ),
) -> None:
    """Delete a stored snapshot. Does not modify the active database."""
    try:
        load_config()
    except ConfigError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=3) from exc

    if not snapshot_exists(name):
        typer.secho(f"No snapshot named '{name}' exists.", fg=typer.colors.RED)
        raise typer.Exit(code=3)

    if not yes:
        confirmed = typer.confirm(f"Delete snapshot '{name}'? This cannot be undone.")
        if not confirmed:
            typer.echo("Delete cancelled.")
            raise typer.Exit(code=0)

    try:
        delete_snapshot_directory(name)
    except SnapshotNotFoundError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=3) from exc

    typer.secho(f"Snapshot '{name}' deleted.", fg=typer.colors.GREEN)
    
if __name__ == "__main__":
    app()
