"""Tests for igra.diff: schema and row-count comparison between snapshots."""

from __future__ import annotations

from igra.adapter.postgres import connect
from igra.capture import create_snapshot
from igra.diff import (
    compute_row_count_diff,
    compute_schema_diff,
    get_toc_entries,
)
from igra.metadata import load_metadata
from igra.storage import dump_path, metadata_path


def _create_two_snapshots(test_db_config, test_db_password, tmp_path, monkeypatch):
    """Create 'before' and 'after' snapshots with a real schema+data change
    between them: a new row in customers, and a new orders table.
    """
    monkeypatch.chdir(tmp_path)
    with connect(test_db_config, test_db_password) as conn:
        create_snapshot("before", test_db_config, test_db_password, conn)

    with connect(test_db_config, test_db_password) as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO customers (name) VALUES ('Dave');")
        cur.execute(
            "CREATE TABLE orders (id SERIAL PRIMARY KEY, customer_id INT);"
        )
        conn.commit()

    try:
        with connect(test_db_config, test_db_password) as conn:
            create_snapshot("after", test_db_config, test_db_password, conn)
        yield
    finally:
        with connect(test_db_config, test_db_password) as conn, conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS orders;")
            cur.execute("DELETE FROM customers WHERE name = 'Dave';")
            conn.commit()


def test_schema_diff_detects_added_table(
    test_db_config, test_db_password, tmp_path, monkeypatch
):
    gen = _create_two_snapshots(test_db_config, test_db_password, tmp_path, monkeypatch)
    next(gen, None)
    try:
        entries_before = get_toc_entries(dump_path("before"))
        entries_after = get_toc_entries(dump_path("after"))
        result = compute_schema_diff(entries_before, entries_after)

        added_names = {obj.object_name for obj in result.added_objects}
        assert "orders" in added_names
        assert result.removed_objects == []
    finally:
        next(gen, None)


def test_schema_diff_common_objects_include_unchanged_table(
    test_db_config, test_db_password, tmp_path, monkeypatch
):
    gen = _create_two_snapshots(test_db_config, test_db_password, tmp_path, monkeypatch)
    next(gen, None)
    try:
        entries_before = get_toc_entries(dump_path("before"))
        entries_after = get_toc_entries(dump_path("after"))
        result = compute_schema_diff(entries_before, entries_after)

        common_names = {obj.object_name for obj in result.common_objects}
        assert "customers" in common_names
    finally:
        next(gen, None)


def test_row_count_diff_detects_change(
    test_db_config, test_db_password, tmp_path, monkeypatch
):
    gen = _create_two_snapshots(test_db_config, test_db_password, tmp_path, monkeypatch)
    next(gen, None)
    try:
        meta_before = load_metadata(metadata_path("before"))
        meta_after = load_metadata(metadata_path("after"))
        diffs = compute_row_count_diff(meta_before, meta_after)

        customers_diff = [d for d in diffs if d.table.object_name == "customers"]
        assert len(customers_diff) == 1
        assert customers_diff[0].row_count_a == 3
        assert customers_diff[0].row_count_b == 4
        assert customers_diff[0].delta == 1
    finally:
        next(gen, None)


def test_identical_snapshots_have_no_differences(
    test_db_config, test_db_password, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    with connect(test_db_config, test_db_password) as conn:
        create_snapshot("snap-a", test_db_config, test_db_password, conn)
        create_snapshot("snap-b", test_db_config, test_db_password, conn)

    entries_a = get_toc_entries(dump_path("snap-a"))
    entries_b = get_toc_entries(dump_path("snap-b"))
    schema_result = compute_schema_diff(entries_a, entries_b)

    assert schema_result.added_objects == []
    assert schema_result.removed_objects == []

    meta_a = load_metadata(metadata_path("snap-a"))
    meta_b = load_metadata(metadata_path("snap-b"))
    row_diffs = compute_row_count_diff(meta_a, meta_b)

    assert all(d.delta == 0 for d in row_diffs)
