"""Tests for igra.capture: snapshot capture orchestration and failure cleanup."""

from __future__ import annotations

import pytest

from igra.adapter.postgres import connect
from igra.capture import CaptureError, create_snapshot
from igra.metadata import SnapshotMetadata
from igra.storage import (
    checksum_path,
    dump_path,
    metadata_path,
    snapshot_exists,
)


def test_create_snapshot_success(test_db_config, test_db_password, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with connect(test_db_config, test_db_password) as conn:
        metadata = create_snapshot(
            "clean-state", test_db_config, test_db_password, conn
        )

    assert isinstance(metadata, SnapshotMetadata)
    assert metadata.name == "clean-state"
    assert dump_path("clean-state").is_file()
    assert metadata_path("clean-state").is_file()
    assert checksum_path("clean-state").is_file()


def test_create_snapshot_files_are_consistent(
    test_db_config, test_db_password, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    with connect(test_db_config, test_db_password) as conn:
        metadata = create_snapshot(
            "clean-state", test_db_config, test_db_password, conn
        )

    dump_size_on_disk = dump_path("clean-state").stat().st_size
    assert metadata.dump_size_bytes == dump_size_on_disk


def test_create_snapshot_name_collision_raises(
    test_db_config, test_db_password, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    with connect(test_db_config, test_db_password) as conn:
        create_snapshot("clean-state", test_db_config, test_db_password, conn)
        with pytest.raises(CaptureError):
            create_snapshot("clean-state", test_db_config, test_db_password, conn)


def test_create_snapshot_wrong_dump_password_cleans_up(
    test_db_config, test_db_password, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    with connect(test_db_config, test_db_password) as conn, pytest.raises(CaptureError):
        create_snapshot("bad-attempt", test_db_config, "wrong-password", conn)

    assert snapshot_exists("bad-attempt") is False
