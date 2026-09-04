"""`LocalFileStore`: atomic writes, crash sweep, export naming, path safety."""

from __future__ import annotations

import pytest

from auto_scoring.adapters.local_storage import LocalFileStore


def test_write_atomic_creates_file_and_leaves_no_temp(store: LocalFileStore) -> None:
    target = store.submission_dir("sub-1") / "source.pdf"
    store.write_atomic(target, b"%PDF-1.7 ...")

    assert target.read_bytes() == b"%PDF-1.7 ..."
    assert list(store.root.rglob("*.part")) == []


def test_write_atomic_overwrites_in_place(store: LocalFileStore) -> None:
    target = store.test_dir("t-1") / "profile.json"
    store.write_atomic(target, b'{"v": 1}')
    store.write_atomic(target, b'{"v": 2}')

    assert target.read_bytes() == b'{"v": 2}'


def test_sweep_temp_removes_leftovers_from_interrupted_writes(
    store: LocalFileStore,
) -> None:
    orphan_dir = store.submission_dir("sub-2")
    orphan_dir.mkdir(parents=True)
    leftover = orphan_dir / ".source.pdf.deadbeef.part"
    leftover.write_bytes(b"half written")

    removed = store.sweep_temp()

    assert leftover in removed
    assert not leftover.exists()


def test_allocate_export_path_numbers_collisions(store: LocalFileStore) -> None:
    first = store.allocate_export_path("答案A.pdf")
    assert first.name == "答案A_corrected.pdf"

    first.parent.mkdir(parents=True, exist_ok=True)
    first.write_bytes(b"x")
    second = store.allocate_export_path("答案A.pdf")
    assert second.name == "答案A_corrected_2.pdf"


def test_delete_submission_removes_the_subtree(store: LocalFileStore) -> None:
    store.write_atomic(store.submission_dir("sub-9") / "source.pdf", b"x")
    store.delete_submission("sub-9")
    assert not store.submission_dir("sub-9").exists()


def test_paths_cannot_escape_the_root(store: LocalFileStore) -> None:
    with pytest.raises(ValueError, match="escapes storage root"):
        store.write_atomic(store.root / ".." / "escape.pdf", b"x")


def test_read_bytes_round_trips(store: LocalFileStore) -> None:
    target = store.exports_dir() / "out_corrected.pdf"
    store.write_atomic(target, b"data")
    assert store.read_bytes(target) == b"data"
