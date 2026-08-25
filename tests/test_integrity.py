"""Tests for igra.integrity: SHA-256 checksum generation and verification."""

from __future__ import annotations

import pytest

from igra.integrity import (
    CHECKSUM_ALGORITHM,
    IntegrityError,
    IntegrityRecord,
    build_integrity_record,
    compute_checksum,
    load_integrity_record,
    save_integrity_record,
    verify_checksum,
)


def test_compute_checksum_deterministic(tmp_path):
    f = tmp_path / "data.bin"
    f.write_bytes(b"hello igra")
    checksum_a = compute_checksum(f)
    checksum_b = compute_checksum(f)
    assert checksum_a == checksum_b
    assert len(checksum_a) == 64  # sha256 hex digest length


def test_compute_checksum_differs_for_different_content(tmp_path):
    f1 = tmp_path / "a.bin"
    f2 = tmp_path / "b.bin"
    f1.write_bytes(b"content one")
    f2.write_bytes(b"content two")
    assert compute_checksum(f1) != compute_checksum(f2)


def test_build_integrity_record_shape(tmp_path):
    f = tmp_path / "data.bin"
    f.write_bytes(b"some data")
    record = build_integrity_record(f)
    assert record.algorithm == CHECKSUM_ALGORITHM
    assert record.checksum == compute_checksum(f)


def test_save_and_load_round_trip(tmp_path):
    f = tmp_path / "data.bin"
    f.write_bytes(b"some data")
    record = build_integrity_record(f)

    checksum_file = tmp_path / "checksum.sha256"
    save_integrity_record(record, checksum_file)

    loaded = load_integrity_record(checksum_file)
    assert loaded.algorithm == record.algorithm
    assert loaded.checksum == record.checksum


def test_load_malformed_checksum_file_raises(tmp_path):
    checksum_file = tmp_path / "checksum.sha256"
    checksum_file.write_text("not a valid checksum line")
    with pytest.raises(IntegrityError):
        load_integrity_record(checksum_file)


def test_verify_checksum_passes_for_unmodified_file(tmp_path):
    f = tmp_path / "data.bin"
    f.write_bytes(b"original content")
    record = build_integrity_record(f)
    assert verify_checksum(f, record) is True


def test_verify_checksum_fails_for_modified_file(tmp_path):
    f = tmp_path / "data.bin"
    f.write_bytes(b"original content")
    record = build_integrity_record(f)

    f.write_bytes(b"tampered content")
    assert verify_checksum(f, record) is False


def test_verify_checksum_rejects_unsupported_algorithm(tmp_path):
    f = tmp_path / "data.bin"
    f.write_bytes(b"some data")
    bad_record = IntegrityRecord(
        algorithm="md5", checksum="deadbeef",
        computed_at=build_integrity_record(f).computed_at,
    )
    with pytest.raises(IntegrityError):
        verify_checksum(f, bad_record)


def test_compute_checksum_handles_large_file_in_chunks(tmp_path):
    f = tmp_path / "large.bin"
    # 200KB - larger than the 64KB chunk size, exercises the read loop
    f.write_bytes(b"x" * 200_000)
    checksum = compute_checksum(f)
    assert len(checksum) == 64
