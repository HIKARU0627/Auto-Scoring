"""Unit tests for `adapters.test_intake` (Issues #16, #101).

Registration takes a list of role-tagged materials now, not a fixed pair of
PDFs -- the grading criteria is the one required file and the model answer
is gone entirely (Issue #95 decision 1). File names here are synthetic.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfWriter
from sqlalchemy.orm import Session, sessionmaker

from auto_scoring.adapters.atomic import FinalizationError
from auto_scoring.adapters.local_storage import LocalFileStore
from auto_scoring.adapters.pdf import PdfiumPypdfEngine
from auto_scoring.adapters.test_intake import (
    MaterialUpload,
    attach_materials,
    register_test,
    repair_incomplete_test_registrations,
)
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.domain.intake_template import MaterialRole
from auto_scoring.domain.material_intake import MaterialIntakeError
from auto_scoring.domain.pdf_engine import AnnotationMark, PdfEngine
from auto_scoring.domain.pdf_geometry import NormalizedPoint, PageGeometry
from auto_scoring.domain.pdf_intake import PdfCorruptedError, PdfGeometryError
from tests.support import at, make_test

_ENGINE = PdfiumPypdfEngine()


class _BadGeometryPdfEngine:
    """Delegates to a real `PdfEngine`, but `page_geometry` always raises
    `exc` -- standing in for a PDF whose CropBox/MediaBox don't intersect,
    or whose `/Rotate` isn't a multiple of 90 (`PageGeometry.__post_init__`,
    a `ValueError`), or one whose page tree is broken in some other way
    pypdf's own box/rotation lookups surface as a different exception type
    entirely (`KeyError`, `TypeError`, one of pypdf's own parse errors --
    Issue #16 review round 7).
    """

    def __init__(self, delegate: PdfEngine, *, exc: Exception | None = None) -> None:
        self._delegate = delegate
        self._exc = exc or ValueError("crop dimensions must be positive")

    def page_count(self, source: Path) -> int:
        return self._delegate.page_count(source)

    def is_encrypted(self, source: Path) -> bool:
        return self._delegate.is_encrypted(source)

    def page_geometry(self, source: Path, page_index: int) -> PageGeometry:
        raise self._exc

    def render_page_png(self, source: Path, page_index: int, *, scale: float) -> bytes:
        return self._delegate.render_page_png(source, page_index, scale=scale)

    def stamp_markers(
        self,
        source: Path,
        destination: Path,
        markers: Mapping[int, Sequence[NormalizedPoint]],
        *,
        mark_size_pt: float = 8.0,
    ) -> None:
        self._delegate.stamp_markers(source, destination, markers, mark_size_pt=mark_size_pt)

    def render_annotations(
        self,
        source: Path,
        destination: Path,
        marks: Mapping[int, Sequence[AnnotationMark]],
    ) -> None:
        self._delegate.render_annotations(source, destination, marks)


#: A ZIP container's leading bytes. `domain.material_intake` checks the
#: signature, not that the archive is a well-formed workbook -- nothing in this
#: app opens Word/Excel yet, so claiming more would be claiming more than is
#: true.
_XLSX_BYTES = b"PK\x03\x04" + b"\x00" * 64


def _pdf_bytes(*, pages: int = 1) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=595, height=842)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _default_materials() -> list[MaterialUpload]:
    """The required criteria PDF plus one reference PDF.

    Two files rather than one so the tests below can still fail the *second*
    staged write and observe the compensation, which is what several of them
    are about.
    """
    return [
        MaterialUpload(
            role=MaterialRole.GRADING_CRITERIA,
            filename="02_criteria.pdf",
            data=_pdf_bytes(),
        ),
        MaterialUpload(
            role=MaterialRole.REFERENCE,
            filename="reference.pdf",
            data=_pdf_bytes(),
        ),
    ]


#: How many material files `failing_write_atomic` has seen this test. Reset
#: per test by `_is_second_material`'s own caller creating a fresh list --
#: materials are named by a random id now, so "fail on the manual PDF" is no
#: longer expressible by name and "fail on the second one" is the equivalent.
_STAGED: list[str] = []


def _is_second_material(path: Path) -> bool:
    if path.parent.name != "materials":
        return False
    _STAGED.append(path.name)
    return len(_STAGED) == 2


def test_a_finalization_failure_does_not_leave_a_permanently_broken_draft(
    store: LocalFileStore,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Simulates a disk-full/permissions failure writing one of the registered
    materials, after the `Test` row already committed. Unlike a `Submission`
    (which has an `error` state to retry into), a `Test` has no such state --
    so the only way to avoid a permanently unusable, file-less draft is to
    compensate by removing the row itself (Issue #16 review).
    """
    _STAGED.clear()
    real_write_atomic = LocalFileStore.write_atomic

    def failing_write_atomic(self: LocalFileStore, path: Path, data: bytes) -> Path:
        if _is_second_material(path):
            raise OSError("simulated disk-full failure")
        return real_write_atomic(self, path, data)

    monkeypatch.setattr(LocalFileStore, "write_atomic", failing_write_atomic)

    with SqlAlchemyUnitOfWork(session_factory) as uow, pytest.raises(FinalizationError):
        register_test(
            uow,
            store,
            _ENGINE,
            name="国語",
            subject=None,
            materials=_default_materials(),
            now=at(),
        )

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert uow.tests.list_all() == []


def test_a_finalization_failure_does_not_leave_orphaned_files(
    store: LocalFileStore,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The first material (staged before the failing second one) must not be
    left on disk once the compensating delete removes the `Test` row it
    belonged to -- an orphaned file with no owning row would never be
    cleaned up by anything.
    """
    _STAGED.clear()
    real_write_atomic = LocalFileStore.write_atomic
    written_test_ids: list[str] = []

    def failing_write_atomic(self: LocalFileStore, path: Path, data: bytes) -> Path:
        if _is_second_material(path):
            raise OSError("simulated disk-full failure")
        if path.parent.name == "materials":
            # `tests/<test-id>/materials/<material-id>.pdf`
            written_test_ids.append(path.parent.parent.name)
        return real_write_atomic(self, path, data)

    monkeypatch.setattr(LocalFileStore, "write_atomic", failing_write_atomic)

    with SqlAlchemyUnitOfWork(session_factory) as uow, pytest.raises(FinalizationError):
        register_test(
            uow,
            store,
            _ENGINE,
            name="国語",
            subject=None,
            materials=_default_materials(),
            now=at(),
        )

    assert len(written_test_ids) == 1
    assert not (store.root / "tests" / written_test_ids[0]).exists()


def test_rejects_a_pdf_with_invalid_page_geometry(
    store: LocalFileStore, session_factory: sessionmaker[Session]
) -> None:
    """Page count alone doesn't catch a CropBox/MediaBox that don't
    intersect or an invalid `/Rotate` -- without validating geometry at
    intake, registration would persist the test anyway and only discover
    the problem the first time `/profile/analyze` calls `page_geometry`
    and hits an unhandled 500 (Issue #16 review round 4).
    """
    with (
        SqlAlchemyUnitOfWork(session_factory) as uow,
        pytest.raises(PdfGeometryError),
    ):
        register_test(
            uow,
            store,
            _BadGeometryPdfEngine(_ENGINE),
            name="国語",
            subject=None,
            materials=_default_materials(),
            now=at(),
        )

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert uow.tests.list_all() == []


@pytest.mark.parametrize("exc", [KeyError("/MediaBox"), TypeError("not a rectangle")])
def test_rejects_a_pdf_whose_geometry_lookup_fails_with_a_non_value_error(
    store: LocalFileStore, session_factory: sessionmaker[Session], exc: Exception
) -> None:
    """`page_geometry` (pypdf) can fail resolving an inherited MediaBox/
    CropBox/rotation through a broken page tree with something other than
    the `ValueError` its own box-validation raises. Before this, such a
    failure sailed past the `except ValueError` guard entirely and
    surfaced as an unhandled 500 from `POST /tests` (Issue #16 review
    round 7).
    """
    with (
        SqlAlchemyUnitOfWork(session_factory) as uow,
        pytest.raises(PdfCorruptedError),
    ):
        register_test(
            uow,
            store,
            _BadGeometryPdfEngine(_ENGINE, exc=exc),
            name="国語",
            subject=None,
            materials=_default_materials(),
            now=at(),
        )

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert uow.tests.list_all() == []


def test_rejects_a_pdf_pypdf_accepts_but_pdfium_cannot_extract_text_from(
    store: LocalFileStore,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """pypdf can parse -- and silently repair -- a PDF whose structure
    pypdfium2 refuses outright. `generate_profile_candidates` (the first
    thing that actually reads this file's text, once `/profile/analyze` is
    called) uses pypdfium2 directly, not the `PdfEngine` abstraction
    exercised above -- so a file that only pypdfium2 rejects must be
    caught at intake too, before the `Test` row and its PDFs are
    persisted, or the resulting draft has no profile and no documented way
    back in (Issue #16 review round 7).
    """
    import auto_scoring.adapters.test_intake as test_intake_module

    def failing_extract_text_lines(path: Path, page_index: int) -> list[object]:
        raise RuntimeError("simulated pdfium parse failure")

    monkeypatch.setattr(test_intake_module, "extract_text_lines", failing_extract_text_lines)

    with (
        SqlAlchemyUnitOfWork(session_factory) as uow,
        pytest.raises(PdfCorruptedError),
    ):
        register_test(
            uow,
            store,
            _ENGINE,
            name="国語",
            subject=None,
            materials=_default_materials(),
            now=at(),
        )

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert uow.tests.list_all() == []


def test_happy_path_registers_a_draft_test(
    store: LocalFileStore, session_factory: sessionmaker[Session]
) -> None:
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        test, materials = register_test(
            uow,
            store,
            _ENGINE,
            name="国語",
            subject="国語",
            materials=_default_materials(),
            now=at(),
        )

    assert [material.role for material in materials] == [
        MaterialRole.GRADING_CRITERIA,
        MaterialRole.REFERENCE,
    ]
    for material in materials:
        assert store.resolve_stored_path(material.stored_path).is_file()
    # The reviewer's own file name survives, so "which of my files became the
    # 採点基準?" stays answerable after import.
    assert materials[0].original_filename == "02_criteria.pdf"
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert uow.tests.get(test.id) is not None
        assert len(uow.test_materials.list_for_test(test.id)) == 2
    # `repair_incomplete_test_registrations` relies on this marker to tell a
    # test created through this flow apart from one that predates it
    # entirely (Issue #16 review round 5) -- a normal registration must
    # leave it behind.
    assert (store.test_dir(test.id) / ".registration-marker").is_file()


def test_repair_leaves_a_pre_existing_test_without_the_marker_alone(
    store: LocalFileStore, session_factory: sessionmaker[Session]
) -> None:
    """Migration 0011 backfills `status='draft'` onto every `Test` row that
    predates this Issue's PDF-based registration flow, none of which ever
    went through `register_test` -- so none of them have its registration
    marker, and none of them ever had PDFs to begin with. An earlier version
    of this sweep used "PDFs missing" alone as its trigger, which classified
    every such pre-existing row as an interrupted registration and deleted
    it -- cascading to its Questions and Submissions -- on the first startup
    after upgrading a production database past that migration (Issue #16
    review round 5, data loss).
    """
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.tests.add(make_test(id="legacy-test"))
        uow.commit()

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        removed = repair_incomplete_test_registrations(uow, store)

    assert removed == []
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert uow.tests.get("legacy-test") is not None


def test_repair_removes_a_marked_test_left_incomplete_by_a_prior_crash(
    store: LocalFileStore, session_factory: sessionmaker[Session]
) -> None:
    """Unlike the pre-existing-row case above, a test that *does* carry the
    registration marker but is still missing its criteria file really did go
    through
    `register_test` and really was interrupted -- the sweep must still
    catch that (this is `repair_incomplete_test_registrations` itself,
    isolated from the process-crash simulation
    `test_a_finalization_failure_does_not_leave_a_permanently_broken_draft`
    already covers via a failing `write_atomic`).
    """
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        test, materials = register_test(
            uow,
            store,
            _ENGINE,
            name="国語",
            subject=None,
            materials=_default_materials(),
            now=at(),
        )
    criteria = next(m for m in materials if m.role is MaterialRole.GRADING_CRITERIA)
    store.resolve_stored_path(criteria.stored_path).unlink()

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        removed = repair_incomplete_test_registrations(uow, store)

    assert removed == [test.id]
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert uow.tests.get(test.id) is None


# --------------------------------------------------------------------------- #
# Issue #101: role-tagged materials
# --------------------------------------------------------------------------- #
def test_a_test_can_be_registered_without_a_model_answer(
    store: LocalFileStore, session_factory: sessionmaker[Session]
) -> None:
    """Acceptance criterion 3. The model-answer PDF does not exist in real
    grading material, and requiring it is what made registration unusable.
    """
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        test, materials = register_test(
            uow,
            store,
            _ENGINE,
            name="模範解答なし",
            subject=None,
            materials=[
                MaterialUpload(
                    role=MaterialRole.GRADING_CRITERIA,
                    filename="02_criteria.pdf",
                    data=_pdf_bytes(),
                )
            ],
            now=at(),
        )

    assert [material.role for material in materials] == [MaterialRole.GRADING_CRITERIA]
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert uow.tests.get(test.id) is not None


def test_registering_without_grading_criteria_is_refused(
    store: LocalFileStore, session_factory: sessionmaker[Session]
) -> None:
    with SqlAlchemyUnitOfWork(session_factory) as uow, pytest.raises(ValueError):
        register_test(
            uow,
            store,
            _ENGINE,
            name="基準なし",
            subject=None,
            materials=[
                MaterialUpload(
                    role=MaterialRole.REFERENCE, filename="reference.pdf", data=_pdf_bytes()
                )
            ],
            now=at(),
        )


def test_a_spreadsheet_can_be_attached_as_an_annotation_resource(
    store: LocalFileStore, session_factory: sessionmaker[Session]
) -> None:
    """添削資料 arrive as Word or Excel in real material, and are the single
    most useful optional input -- rejecting them would drop the reviewer's own
    comment wording on the floor (Issue #95 decision 3).
    """
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        _, materials = register_test(
            uow,
            store,
            _ENGINE,
            name="添削資料つき",
            subject=None,
            materials=[
                MaterialUpload(
                    role=MaterialRole.GRADING_CRITERIA,
                    filename="02_criteria.pdf",
                    data=_pdf_bytes(),
                ),
                MaterialUpload(
                    role=MaterialRole.ANNOTATION_RESOURCE,
                    filename="03_resource.xlsx",
                    data=_XLSX_BYTES,
                ),
            ],
            now=at(),
        )

    resource = next(m for m in materials if m.role is MaterialRole.ANNOTATION_RESOURCE)
    assert store.resolve_stored_path(resource.stored_path).is_file()
    assert resource.stored_path.endswith(".xlsx")


def test_a_spreadsheet_cannot_be_registered_as_the_grading_criteria(
    store: LocalFileStore, session_factory: sessionmaker[Session]
) -> None:
    """Everything downstream opens the criteria as a PDF. Accepting a
    spreadsheet here would register something unusable and only surface it
    much later.
    """
    with SqlAlchemyUnitOfWork(session_factory) as uow, pytest.raises(MaterialIntakeError):
        register_test(
            uow,
            store,
            _ENGINE,
            name="表計算の基準",
            subject=None,
            materials=[
                MaterialUpload(
                    role=MaterialRole.GRADING_CRITERIA,
                    filename="02_criteria.xlsx",
                    data=_XLSX_BYTES,
                )
            ],
            now=at(),
        )


def test_content_that_does_not_match_its_extension_is_refused(
    store: LocalFileStore, session_factory: sessionmaker[Session]
) -> None:
    with SqlAlchemyUnitOfWork(session_factory) as uow, pytest.raises(MaterialIntakeError):
        register_test(
            uow,
            store,
            _ENGINE,
            name="偽装",
            subject=None,
            materials=[
                MaterialUpload(
                    role=MaterialRole.GRADING_CRITERIA,
                    filename="02_criteria.pdf",
                    data=_pdf_bytes(),
                ),
                MaterialUpload(
                    role=MaterialRole.ANNOTATION_RESOURCE,
                    filename="03_resource.xlsx",
                    data=b"MZ\x90\x00 not a spreadsheet",
                ),
            ],
            now=at(),
        )


def test_reattaching_the_same_file_returns_the_existing_material(
    store: LocalFileStore, session_factory: sessionmaker[Session]
) -> None:
    """Retrying a batch that failed part-way through must not multiply
    materials: a row can fail *after* its write committed, so the retry has
    to recognize its own earlier success (Issue #101: 成功した分は残る).
    """
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        test, _ = register_test(
            uow,
            store,
            _ENGINE,
            name="再送",
            subject=None,
            materials=[
                MaterialUpload(
                    role=MaterialRole.GRADING_CRITERIA,
                    filename="02_criteria.pdf",
                    data=_pdf_bytes(),
                )
            ],
            now=at(),
        )

    sample = MaterialUpload(
        role=MaterialRole.ANNOTATION_SAMPLE, filename="04_1_sample.pdf", data=_pdf_bytes()
    )
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        first = attach_materials(uow, store, _ENGINE, test_id=test.id, materials=[sample], now=at())
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        second = attach_materials(
            uow, store, _ENGINE, test_id=test.id, materials=[sample], now=at()
        )

    assert [material.id for material in first] == [material.id for material in second]
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert len(uow.test_materials.list_for_test(test.id)) == 2


def test_two_identical_files_in_one_request_become_one_material(
    store: LocalFileStore, session_factory: sessionmaker[Session]
) -> None:
    """Same bytes, same role, two names -- one material.

    Without collapsing them the unique constraint rejects the second insert and
    the *whole* attach fails, taking unrelated materials in the same request
    with it. A subject folder shipping the same document twice under two names
    is ordinary, not exotic.
    """
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        test, _ = register_test(
            uow,
            store,
            _ENGINE,
            name="重複",
            subject=None,
            materials=[
                MaterialUpload(
                    role=MaterialRole.GRADING_CRITERIA,
                    filename="02_criteria.pdf",
                    data=_pdf_bytes(),
                )
            ],
            now=at(),
        )

    same = _pdf_bytes(pages=2)
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        attached = attach_materials(
            uow,
            store,
            _ENGINE,
            test_id=test.id,
            materials=[
                MaterialUpload(
                    role=MaterialRole.ANNOTATION_SAMPLE,
                    filename="04_1_sample.pdf",
                    data=same,
                ),
                MaterialUpload(
                    role=MaterialRole.ANNOTATION_SAMPLE,
                    filename="04_2_sample.pdf",
                    data=same,
                ),
                MaterialUpload(
                    role=MaterialRole.REFERENCE,
                    filename="reference.pdf",
                    data=_pdf_bytes(),
                ),
            ],
            now=at(),
        )

    assert len(attached) == 2
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        roles = [m.role for m in uow.test_materials.list_for_test(test.id)]
    assert sorted(role.value for role in roles) == [
        "annotation_sample",
        "grading_criteria",
        "reference",
    ]


def test_a_material_row_whose_file_is_missing_is_repaired_not_reported_done(
    store: LocalFileStore, session_factory: sessionmaker[Session]
) -> None:
    """`transactional_operation` commits the DB before writing files, so a
    crash between the two leaves a row with no file.

    Answering the retry with "already attached" would report success for a
    material that can never be opened -- permanently, because every later
    attempt gets the same answer. The retry must re-stage the bytes instead.
    """
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        test, _ = register_test(
            uow,
            store,
            _ENGINE,
            name="欠損",
            subject=None,
            materials=[
                MaterialUpload(
                    role=MaterialRole.GRADING_CRITERIA,
                    filename="02_criteria.pdf",
                    data=_pdf_bytes(),
                )
            ],
            now=at(),
        )

    sample = MaterialUpload(
        role=MaterialRole.ANNOTATION_SAMPLE, filename="04_1_sample.pdf", data=_pdf_bytes()
    )
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        [attached] = attach_materials(
            uow, store, _ENGINE, test_id=test.id, materials=[sample], now=at()
        )

    # Simulate the interrupted write: the row survived, the file did not.
    store.resolve_stored_path(attached.stored_path).unlink()

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        [repaired] = attach_materials(
            uow, store, _ENGINE, test_id=test.id, materials=[sample], now=at()
        )

    assert repaired.id == attached.id
    assert store.resolve_stored_path(repaired.stored_path).is_file()
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert len(uow.test_materials.list_for_test(test.id)) == 2
