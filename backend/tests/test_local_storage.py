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


def test_allocate_export_path_also_skips_reserved_paths_with_no_file_on_disk(
    store: LocalFileStore,
) -> None:
    """Issue #23 P1 review, round 3: a path some `Export` row already
    names -- e.g. one whose own file write failed after its DB commit --
    must stay off-limits even though nothing exists there yet for the
    plain `.exists()` check (covered by the test above) to catch."""
    first = store.allocate_export_path("答案A.pdf")
    assert first.name == "答案A_corrected.pdf"
    reserved = {"exports/答案A_corrected.pdf"}

    second = store.allocate_export_path("答案A.pdf", reserved=reserved)

    assert second.name == "答案A_corrected_2.pdf"
    assert not second.exists()


def test_delete_submission_removes_the_subtree(store: LocalFileStore) -> None:
    store.write_atomic(store.submission_dir("sub-9") / "source.pdf", b"x")
    store.delete_submission("sub-9")
    assert not store.submission_dir("sub-9").exists()


def test_delete_submission_reports_filesystem_failure(
    store: LocalFileStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = store.submission_dir("sub-9")
    store.write_atomic(target / "source.pdf", b"x")

    def fail_delete(_path: object) -> None:
        raise PermissionError("injected delete failure")

    monkeypatch.setattr("auto_scoring.adapters.local_storage.shutil.rmtree", fail_delete)

    with pytest.raises(PermissionError, match="injected delete failure"):
        store.delete_submission("sub-9")


def test_paths_cannot_escape_the_root(store: LocalFileStore) -> None:
    with pytest.raises(ValueError, match="escapes storage root"):
        store.write_atomic(store.root / ".." / "escape.pdf", b"x")


def test_a_submission_id_containing_a_path_separator_is_rejected(store: LocalFileStore) -> None:
    with pytest.raises(ValueError, match="unsafe path segment"):
        store.submission_dir("../tests")


def test_a_question_id_containing_a_path_separator_is_encoded_safely(
    store: LocalFileStore,
) -> None:
    """A Question.id like "../pages/page-1" would, if used verbatim, resolve
    inside submissions/<sub>/pages/ instead of submissions/<sub>/questions/
    -- landing on (and silently overwriting) the page preview image, not
    merely escaping the store root (which _ensure_within_root already
    blocks). Question.id is only required to be non-empty, so this and every
    other case below is encoded rather than validated against a blocklist:
    the resulting path must stay under questions/, whatever the id contains.
    """
    path = store.submission_question_image_path("sub-1", "../pages/page-1")
    assert path.parent == store.submission_dir("sub-1") / "questions"


def test_a_question_id_containing_a_backslash_is_encoded_safely(store: LocalFileStore) -> None:
    path = store.submission_question_image_path("sub-1", "..\\pages\\page-1")
    assert path.parent == store.submission_dir("sub-1") / "questions"


def test_a_question_id_shaped_like_a_windows_drive_relative_path_is_encoded_safely(
    store: LocalFileStore,
) -> None:
    """On Windows, ``Path.joinpath(root, "C:foo.png")`` resolves to the same
    path as plain ``"foo.png"`` if used verbatim -- no "/" or "\\" involved.
    """
    path = store.submission_question_image_path("sub-1", "C:foo")
    assert path.parent == store.submission_dir("sub-1") / "questions"
    assert path.name != "foo.png"


def test_a_question_id_matching_a_windows_reserved_device_name_is_encoded_safely(
    store: LocalFileStore,
) -> None:
    """``CON``, ``COM1``, etc. would address a reserved device via most Win32
    APIs regardless of extension if used verbatim (``CON.png`` still means
    ``CON``), making every write fail.
    """
    path = store.submission_question_image_path("sub-1", "CON")
    assert path.stem not in {"CON", "con"}


def test_question_ids_differing_only_by_case_do_not_collide(store: LocalFileStore) -> None:
    """NTFS resolves filenames case-insensitively: two Question rows whose
    ids differ only by case must not address the same file, or one row's
    crop would silently overwrite the other's despite both existing in the
    DB.
    """
    upper = store.submission_question_image_path("sub-1", "Q-1")
    lower = store.submission_question_image_path("sub-1", "q-1")
    assert upper != lower


def test_question_image_path_encoding_is_deterministic(store: LocalFileStore) -> None:
    first = store.submission_question_image_path("sub-1", "q-1")
    second = store.submission_question_image_path("sub-1", "q-1")
    assert first == second


def test_read_bytes_round_trips(store: LocalFileStore) -> None:
    target = store.exports_dir() / "out_corrected.pdf"
    store.write_atomic(target, b"data")
    assert store.read_bytes(target) == b"data"
