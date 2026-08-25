"""Tests for igra.metadata: SnapshotMetadata / TableInfo construction and I/O."""

from __future__ import annotations

from igra.adapter.postgres import connect, dump_database
from igra.metadata import (
    SnapshotMetadata,
    build_metadata,
    load_metadata,
    save_metadata,
)


def test_build_metadata_against_real_database(test_db_config, test_db_password, tmp_path):
    dump_path = tmp_path / "dump.pgcustom"
    dump_database(test_db_config, test_db_password, dump_path)

    with connect(test_db_config, test_db_password) as conn:
        meta = build_metadata(
            "clean-state", test_db_config, conn, dump_path.stat().st_size
        )

    assert meta.name == "clean-state"
    assert meta.source_database == "igra_dev_test"
    assert meta.dump_size_bytes == dump_path.stat().st_size
    assert len(meta.id) > 0

    customers = [t for t in meta.tables if t.table_name == "customers"]
    assert len(customers) == 1
    assert customers[0].row_count == 3
    assert customers[0].schema_name == "public"


def test_metadata_ids_are_unique(test_db_config, test_db_password, tmp_path):
    dump_path = tmp_path / "dump.pgcustom"
    dump_database(test_db_config, test_db_password, dump_path)

    with connect(test_db_config, test_db_password) as conn:
        meta_a = build_metadata("a", test_db_config, conn, 100)
        meta_b = build_metadata("b", test_db_config, conn, 100)

    assert meta_a.id != meta_b.id


def test_save_and_load_metadata_round_trip(test_db_config, test_db_password, tmp_path):
    dump_path = tmp_path / "dump.pgcustom"
    dump_database(test_db_config, test_db_password, dump_path)

    with connect(test_db_config, test_db_password) as conn:
        meta = build_metadata(
            "clean-state", test_db_config, conn, dump_path.stat().st_size
        )

    meta_path = tmp_path / "metadata.json"
    save_metadata(meta, meta_path)

    loaded = load_metadata(meta_path)
    assert loaded == meta
    assert isinstance(loaded, SnapshotMetadata)


def test_metadata_json_is_human_readable(test_db_config, test_db_password, tmp_path):
    dump_path = tmp_path / "dump.pgcustom"
    dump_database(test_db_config, test_db_password, dump_path)

    with connect(test_db_config, test_db_password) as conn:
        meta = build_metadata(
            "clean-state", test_db_config, conn, dump_path.stat().st_size
        )

    meta_path = tmp_path / "metadata.json"
    save_metadata(meta, meta_path)

    content = meta_path.read_text()
    assert "\n" in content  # indented, not a single line
    assert "clean-state" in content
