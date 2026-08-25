"""Tests for igra.storage: snapshot directory layout management."""

from __future__ import annotations

import pytest

from igra.storage import (
    SnapshotAlreadyExistsError,
    SnapshotNotFoundError,
    checksum_path,
    create_snapshot_directory,
    delete_snapshot_directory,
    dump_path,
    list_snapshot_names,
    metadata_path,
    snapshot_dir,
    snapshot_exists,
    snapshots_root,
)


def test_snapshots_root_location(tmp_path):
    assert snapshots_root(tmp_path) == tmp_path / ".igra" / "snapshots"


def test_create_snapshot_directory_creates_dir(tmp_path):
    path = create_snapshot_directory("clean-state", project_dir=tmp_path)
    assert path.is_dir()
    assert path == tmp_path / ".igra" / "snapshots" / "clean-state"


def test_create_snapshot_directory_collision_raises(tmp_path):
    create_snapshot_directory("clean-state", project_dir=tmp_path)
    with pytest.raises(SnapshotAlreadyExistsError):
        create_snapshot_directory("clean-state", project_dir=tmp_path)


def test_snapshot_exists_false_when_absent(tmp_path):
    assert snapshot_exists("nope", project_dir=tmp_path) is False


def test_snapshot_exists_true_after_create(tmp_path):
    create_snapshot_directory("clean-state", project_dir=tmp_path)
    assert snapshot_exists("clean-state", project_dir=tmp_path) is True


def test_list_snapshot_names_empty_when_no_snapshots(tmp_path):
    assert list_snapshot_names(project_dir=tmp_path) == []


def test_list_snapshot_names_returns_sorted_names(tmp_path):
    create_snapshot_directory("zeta", project_dir=tmp_path)
    create_snapshot_directory("alpha", project_dir=tmp_path)
    assert list_snapshot_names(project_dir=tmp_path) == ["alpha", "zeta"]


def test_file_path_helpers(tmp_path):
    base = snapshot_dir("clean-state", project_dir=tmp_path)
    assert dump_path("clean-state", project_dir=tmp_path) == base / "dump.pgcustom"
    assert metadata_path("clean-state", project_dir=tmp_path) == base / "metadata.json"
    assert checksum_path("clean-state", project_dir=tmp_path) == base / "checksum.sha256"


def test_delete_snapshot_directory_removes_it(tmp_path):
    create_snapshot_directory("clean-state", project_dir=tmp_path)
    delete_snapshot_directory("clean-state", project_dir=tmp_path)
    assert snapshot_exists("clean-state", project_dir=tmp_path) is False


def test_delete_snapshot_directory_missing_raises(tmp_path):
    with pytest.raises(SnapshotNotFoundError):
        delete_snapshot_directory("nope", project_dir=tmp_path)


def test_delete_removes_partial_contents_too(tmp_path):
    path = create_snapshot_directory("clean-state", project_dir=tmp_path)
    (path / "dump.pgcustom").write_bytes(b"partial data")
    delete_snapshot_directory("clean-state", project_dir=tmp_path)
    assert not path.exists()
