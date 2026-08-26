"""IGRA CLI entrypoint.

Week 1 scaffold: --help, --version, and `igra init` are functional.
Remaining subcommands (status, snapshot) are added in later steps.
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

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

console = Console()

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
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=3) from exc

    try:
        password = resolve_db_password()
    except Exception as exc:
        console.print(f"[red]Could not resolve database password: {exc}[/red]")
        raise typer.Exit(code=3) from exc

    try:
        with connect(config.database, password) as conn:
            version = get_server_version(conn)
    except ConnectionError_ as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=3) from exc

    snapshot_count = _count_snapshots()

    table = Table(show_header=False, box=None)
    table.add_column(style="bold")
    table.add_column()
    table.add_row("Connected", "[green]true[/green]")
    table.add_row("Database", config.database.dbname)
    table.add_row("PostgreSQL version", version)
    table.add_row("Snapshots", str(snapshot_count))
    console.print(table)

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

    console.print(f"[green]Snapshot '{name}' created.[/green]")
    table = Table(show_header=False, box=None)
    table.add_column(style="bold")
    table.add_column()
    table.add_row("ID", metadata.id)
    table.add_row("Created", str(metadata.created_at))
    table.add_row("Size", f"{metadata.dump_size_bytes} bytes")
    table.add_row("Tables", str(len(metadata.tables)))
    console.print(table)
    
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

    def _mark(value: bool) -> str:
        return "[green]yes[/green]" if value else "[red]no[/red]"

    table = Table(show_header=False, box=None)
    table.add_column(style="bold")
    table.add_column()
    table.add_row("Checksum verified", _mark(result.checksum_verified))
    table.add_row("Scratch restore succeeded", _mark(result.scratch_restore_succeeded))
    table.add_row("Validation passed", _mark(result.validation_passed))
    table.add_row("Replacement completed", _mark(result.replacement_completed))
    table.add_row("Target database state", result.target_database_state)
    console.print(table)

    if result.replacement_completed:
        console.print(f"[green]Snapshot '{name}' restored successfully.[/green]")
        raise typer.Exit(code=0)

    console.print(
        f"[red]Restore did not complete. Failed at stage: {result.failure_stage}[/red]"
    )
    raise typer.Exit(code=1)
    
@snapshot_app.command("list")
def snapshot_list() -> None:
    """List all stored snapshots."""
    try:
        load_config()
    except ConfigError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=3) from exc

    names = list_snapshot_names()

    if not names:
        console.print("No snapshots found.")
        raise typer.Exit(code=0)

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Name")
    table.add_column("Created")
    table.add_column("Size (bytes)", justify="right")

    for name in names:
        try:
            meta = load_metadata(metadata_path(name))
            table.add_row(meta.name, str(meta.created_at), str(meta.dump_size_bytes))
        except (OSError, ValueError):
            # OSError: metadata.json missing/unreadable. ValueError: JSON
            # parse or pydantic validation failure. Either way, don't let
            # one broken snapshot's metadata crash the whole list command.
            table.add_row(name, "[dim](metadata unreadable)[/dim]", "-")

    console.print(table)

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

    info_table = Table(show_header=False, box=None)
    info_table.add_column(style="bold")
    info_table.add_column()
    info_table.add_row("Name", meta.name)
    info_table.add_row("ID", meta.id)
    info_table.add_row("Created", str(meta.created_at))
    info_table.add_row("Source database", meta.source_database)
    info_table.add_row("PostgreSQL version", meta.postgres_server_version)
    info_table.add_row("pg_dump version", meta.pg_dump_version)
    info_table.add_row("Dump size", f"{meta.dump_size_bytes} bytes")
    console.print(info_table)

    tables_table = Table(show_header=True, header_style="bold cyan", title="Tables")
    tables_table.add_column("Table")
    tables_table.add_column("Rows", justify="right")
    for table in meta.tables:
        tables_table.add_row(f"{table.schema_name}.{table.table_name}", str(table.row_count))
    console.print(tables_table)

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

    console.print(f"Comparing [bold]'{snapshot_a}'[/bold] -> [bold]'{snapshot_b}'[/bold]\n")

    changed_row_counts = [d for d in row_diffs if d.delta != 0]
    has_differences = (
        schema_result.added_objects or schema_result.removed_objects or changed_row_counts
    )

    if schema_result.added_objects:
        console.print("[bold green]Added:[/bold green]")
        for obj in schema_result.added_objects:
            console.print(f"  [green]+ {obj.object_type} {obj.schema_name}.{obj.object_name}[/green]")

    if schema_result.removed_objects:
        console.print("[bold red]Removed:[/bold red]")
        for obj in schema_result.removed_objects:
            console.print(f"  [red]- {obj.object_type} {obj.schema_name}.{obj.object_name}[/red]")

    if changed_row_counts:
        table = Table(show_header=True, header_style="bold yellow", title="Row count changes")
        table.add_column("Table")
        table.add_column("Before", justify="right")
        table.add_column("After", justify="right")
        table.add_column("Delta", justify="right")
        for d in changed_row_counts:
            sign = "+" if d.delta > 0 else ""
            table.add_row(
                f"{d.table.schema_name}.{d.table.object_name}",
                str(d.row_count_a),
                str(d.row_count_b),
                f"{sign}{d.delta}",
            )
        console.print(table)

    if not has_differences:
        console.print("No differences found.")

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
        console.print(f"[red]No snapshot named '{name}' exists.[/red]")
        raise typer.Exit(code=3)

    if not yes:
        confirmed = typer.confirm(f"Delete snapshot '{name}'? This cannot be undone.")
        if not confirmed:
            console.print("Delete cancelled.")
            raise typer.Exit(code=0)

    try:
        delete_snapshot_directory(name)
    except SnapshotNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=3) from exc

    console.print(f"[green]Snapshot '{name}' deleted.[/green]")
    
if __name__ == "__main__":
    app()
