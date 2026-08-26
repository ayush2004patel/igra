"""Integration tests for igra.adapter.postgres against a real PostgreSQL DB."""

from __future__ import annotations

import subprocess
import time

import pytest

from igra.adapter.postgres import (
    ConnectionError_,
    DumpError,
    RestoreError,
    connect,
    create_database,
    database_exists,
    drop_database,
    dump_database,
    get_pg_dump_version,
    get_server_version,
    get_table_row_counts,
    list_user_tables,
    rename_database,
    restore_database,
    terminate_connections,
)
from igra.config import DatabaseConfig


def test_connect_success(test_db_config, test_db_password):
    with connect(test_db_config, test_db_password) as conn:
        assert conn.closed == 0


def test_connect_wrong_password_raises(test_db_config):
    with pytest.raises(ConnectionError_), connect(test_db_config, "wrong-password"):
        pass


def test_connect_wrong_dbname_raises(test_db_password):
    bad_config = DatabaseConfig(
        host="localhost", port=5432, dbname="nonexistent_db_xyz", user="igra_dev"
    )
    with pytest.raises(ConnectionError_), connect(bad_config, test_db_password):
        pass


def test_get_server_version_returns_string(test_db_config, test_db_password):
    with connect(test_db_config, test_db_password) as conn:
        version = get_server_version(conn)
    assert isinstance(version, str)
    assert len(version) > 0


def test_list_user_tables_includes_customers(test_db_config, test_db_password):
    with connect(test_db_config, test_db_password) as conn:
        tables = list_user_tables(conn)
    assert ("public", "customers") in tables


def test_get_table_row_counts_matches_known_data(test_db_config, test_db_password):
    with connect(test_db_config, test_db_password) as conn:
        counts = get_table_row_counts(conn)
    customers = [c for c in counts if c.table_name == "customers"]
    assert len(customers) == 1
    assert customers[0].row_count == 3
    assert customers[0].schema_name == "public"




def test_get_pg_dump_version_returns_string():
    version = get_pg_dump_version()
    assert "pg_dump" in version.lower()


def test_dump_database_success(test_db_config, test_db_password, tmp_path):
    output_path = tmp_path / "dump.pgcustom"
    dump_database(test_db_config, test_db_password, output_path)
    assert output_path.is_file()
    assert output_path.stat().st_size > 0


def test_dump_database_is_valid_custom_format(test_db_config, test_db_password, tmp_path):
    import subprocess

    output_path = tmp_path / "dump.pgcustom"
    dump_database(test_db_config, test_db_password, output_path)

    result = subprocess.run(
        ["pg_restore", "-l", str(output_path)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "Format: CUSTOM" in result.stdout
    assert "customers" in result.stdout


def test_dump_database_wrong_password_raises(test_db_config, tmp_path):
    output_path = tmp_path / "dump.pgcustom"
    with pytest.raises(DumpError):
        dump_database(test_db_config, "wrong-password", output_path)


def test_dump_database_wrong_dbname_raises(test_db_password, tmp_path):
    from igra.config import DatabaseConfig

    bad_config = DatabaseConfig(
        host="localhost", port=5432, dbname="nonexistent_db_xyz", user="igra_dev"
    )
    output_path = tmp_path / "dump.pgcustom"
    with pytest.raises(DumpError):
        dump_database(bad_config, test_db_password, output_path)



def test_create_and_drop_database(test_db_config, test_db_password):
    scratch_name = "igra_test_create_drop_xyz"
    create_database(test_db_config, test_db_password, scratch_name)

    with connect(
        DatabaseConfig(
            host=test_db_config.host,
            port=test_db_config.port,
            dbname="postgres",
            user=test_db_config.user,
        ),
        test_db_password,
    ) as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s;", (scratch_name,))
        assert cur.fetchone() is not None

    drop_database(test_db_config, test_db_password, scratch_name)

    with connect(
        DatabaseConfig(
            host=test_db_config.host,
            port=test_db_config.port,
            dbname="postgres",
            user=test_db_config.user,
        ),
        test_db_password,
    ) as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s;", (scratch_name,))
        assert cur.fetchone() is None


def test_create_database_duplicate_raises(test_db_config, test_db_password):
    scratch_name = "igra_test_dup_xyz"
    create_database(test_db_config, test_db_password, scratch_name)
    try:
        with pytest.raises(RestoreError):
            create_database(test_db_config, test_db_password, scratch_name)
    finally:
        drop_database(test_db_config, test_db_password, scratch_name)


def test_drop_nonexistent_database_does_not_raise(test_db_config, test_db_password):
    # DROP DATABASE IF EXISTS - dropping something absent is not an error.
    drop_database(test_db_config, test_db_password, "igra_never_existed_xyz")


def test_restore_database_reproduces_data(test_db_config, test_db_password, tmp_path):
    dump_path = tmp_path / "dump.pgcustom"
    dump_database(test_db_config, test_db_password, dump_path)

    scratch_name = "igra_test_restore_xyz"
    create_database(test_db_config, test_db_password, scratch_name)
    try:
        restore_database(test_db_config, test_db_password, scratch_name, dump_path)

        scratch_config = DatabaseConfig(
            host=test_db_config.host,
            port=test_db_config.port,
            dbname=scratch_name,
            user=test_db_config.user,
        )
        with connect(scratch_config, test_db_password) as conn:
            counts = get_table_row_counts(conn)

        customers = [c for c in counts if c.table_name == "customers"]
        assert len(customers) == 1
        assert customers[0].row_count == 3
    finally:
        drop_database(test_db_config, test_db_password, scratch_name)


def test_restore_database_invalid_dump_raises(test_db_config, test_db_password, tmp_path):
    bad_dump = tmp_path / "corrupt.pgcustom"
    bad_dump.write_bytes(b"not a real pg_dump archive")

    scratch_name = "igra_test_restore_bad_xyz"
    create_database(test_db_config, test_db_password, scratch_name)
    try:
        with pytest.raises(RestoreError):
            restore_database(test_db_config, test_db_password, scratch_name, bad_dump)
    finally:
        drop_database(test_db_config, test_db_password, scratch_name)



def test_database_exists_true_for_real_db(test_db_config, test_db_password):
    assert database_exists(test_db_config, test_db_password, "igra_dev_test") is True


def test_database_exists_false_for_missing_db(test_db_config, test_db_password):
    assert database_exists(test_db_config, test_db_password, "nonexistent_xyz") is False


def test_terminate_connections_returns_zero_when_none_active(
    test_db_config, test_db_password
):
    scratch_name = "igra_test_terminate_idle_xyz"
    create_database(test_db_config, test_db_password, scratch_name)
    try:
        count = terminate_connections(test_db_config, test_db_password, scratch_name)
        assert count == 0
    finally:
        drop_database(test_db_config, test_db_password, scratch_name)


def test_terminate_connections_kills_active_session(test_db_config, test_db_password):
    scratch_name = "igra_test_terminate_active_xyz"
    create_database(test_db_config, test_db_password, scratch_name)
    try:
        proc = subprocess.Popen(
            [
                "psql", "-h", test_db_config.host, "-U", test_db_config.user,
                "-d", scratch_name, "-c", "SELECT pg_sleep(30);",
            ],
            env={"PGPASSWORD": test_db_password},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(1)

        count = terminate_connections(test_db_config, test_db_password, scratch_name)
        assert count == 1

        proc.wait(timeout=5)
    finally:
        drop_database(test_db_config, test_db_password, scratch_name)


def test_rename_database_success(test_db_config, test_db_password):
    original_name = "igra_test_rename_src_xyz"
    renamed_name = "igra_test_rename_dst_xyz"
    create_database(test_db_config, test_db_password, original_name)
    try:
        rename_database(test_db_config, test_db_password, original_name, renamed_name)
        assert database_exists(test_db_config, test_db_password, renamed_name) is True
        assert database_exists(test_db_config, test_db_password, original_name) is False
    finally:
        drop_database(test_db_config, test_db_password, renamed_name)


def test_rename_database_fails_with_active_connection(test_db_config, test_db_password):
    import uuid
    db_name = f"igra_test_rename_blocked_{uuid.uuid4().hex[:8]}"
    create_database(test_db_config, test_db_password, db_name)
    proc = None
    try:
        proc = subprocess.Popen(
            [
                "psql", "-h", test_db_config.host, "-U", test_db_config.user,
                "-d", db_name, "-c", "SELECT pg_sleep(30);",
            ],
            env={"PGPASSWORD": test_db_password},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(1)

        with pytest.raises(RestoreError):
            rename_database(test_db_config, test_db_password, db_name, "irrelevant_xyz")
    finally:
        # Best-effort cleanup only - a cleanup failure here must never
        # mask the test's actual assertion result above.
        try:
            terminate_connections(test_db_config, test_db_password, db_name)
        except RestoreError:
            pass
        if proc:
            proc.terminate()
            proc.wait(timeout=5)
        try:
            drop_database(test_db_config, test_db_password, db_name)
        except RestoreError:
            pass


def test_terminate_then_rename_succeeds(test_db_config, test_db_password):
    db_name = "igra_test_terminate_rename_xyz"
    create_database(test_db_config, test_db_password, db_name)
    proc = None
    try:
        proc = subprocess.Popen(
            [
                "psql", "-h", test_db_config.host, "-U", test_db_config.user,
                "-d", db_name, "-c", "SELECT pg_sleep(30);",
            ],
            env={"PGPASSWORD": test_db_password},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(1)

        terminate_connections(test_db_config, test_db_password, db_name)
        rename_database(test_db_config, test_db_password, db_name, "igra_test_terminate_rename_done_xyz")

        assert database_exists(
            test_db_config, test_db_password, "igra_test_terminate_rename_done_xyz"
        ) is True
        proc.wait(timeout=5)
    finally:
        drop_database(test_db_config, test_db_password, db_name)
        drop_database(
            test_db_config, test_db_password, "igra_test_terminate_rename_done_xyz"
        )