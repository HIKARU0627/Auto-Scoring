"""Validate, store, and register a test's material files (Issues #16, #101).

Mirrors `adapters.submission_intake`'s validate-then-store shape. What changed
in Issue #101 is *what* gets registered: not a fixed pair of PDFs (a model
answer and a marking manual) but a **required grading-criteria PDF plus any
number of optional role-tagged files**.

The model-answer PDF is gone as a required input. It does not exist in real
grading material -- the criteria PDF already contains the model answer, and no
document with "the answers written into the answer boxes" is distributed at
all, which is what the old profile-analysis flow assumed (Issue #95 decision
1). A model answer that a reviewer does happen to have is attached as a
`REFERENCE` material like any other extra file.

Writes stay atomic the same way they were: `adapters.atomic
.transactional_operation` commits the DB before any file is written, so a
failure leaves neither a row nor a file behind.

**This module extracts nothing from the files it stores.** Turning a criteria
PDF into per-question points and rubrics is separate work (Issue #95 decision
A) that Issue #101 deliberately does not do -- so a test registered here has
its materials attached but is **not yet gradable**, and callers must not imply
otherwise.
"""

from __future__ import annotations

import hashlib
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from auto_scoring.adapters.atomic import FinalizationError, transactional_operation
from auto_scoring.adapters.local_storage import LocalFileStore
from auto_scoring.adapters.pdf.text_layout_extraction import extract_text_lines
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.domain.intake_template import MaterialRole
from auto_scoring.domain.material_intake import validate_material_upload
from auto_scoring.domain.models import ScoringMethod, Test, TestStatus
from auto_scoring.domain.pdf_engine import PdfEngine
from auto_scoring.domain.pdf_intake import (
    IntakeLimits,
    PdfCorruptedError,
    PdfEncryptedError,
    PdfGeometryError,
    validate_page_count,
)
from auto_scoring.domain.test_material import TestMaterial

#: Marks a `Test` directory as having gone through `register_test` at least
#: once -- written before the DB commit, never removed. Its only purpose is
#: to let `repair_incomplete_test_registrations` tell a test created by
#: this PDF-based registration flow apart from one that predates it entirely
#: (migration 0011 backfills `status='draft'` onto every pre-existing row,
#: none of which were ever registered with files -- see that function's own
#: docstring). A permanent tag, not a "still pending" flag: once the
#: materials are also on disk, the row is a normal, complete registration
#: regardless of whether this file is still there.
_REGISTRATION_MARKER_FILENAME = ".registration-marker"


@dataclass(frozen=True, kw_only=True)
class MaterialUpload:
    """One file being attached, before it has been validated or stored."""

    role: MaterialRole
    filename: str
    data: bytes


def _registration_marker_path(store: LocalFileStore, test_id: str) -> Path:
    return store.test_dir(test_id) / _REGISTRATION_MARKER_FILENAME


def _validate_one_pdf(pdf_engine: PdfEngine, path: Path, limits: IntakeLimits) -> None:
    try:
        encrypted = pdf_engine.is_encrypted(path)
    except Exception as exc:  # pypdf's parse errors are not our concern to enumerate
        raise PdfCorruptedError(f"could not parse PDF: {exc}") from exc
    if encrypted:
        raise PdfEncryptedError("PDF is password protected")
    try:
        page_count = pdf_engine.page_count(path)
    except Exception as exc:
        raise PdfCorruptedError(f"could not parse PDF: {exc}") from exc
    validate_page_count(page_count, limits)
    # Page count alone doesn't catch every malformed PDF: a page whose
    # CropBox/MediaBox don't intersect, or whose /Rotate is not a multiple
    # of 90, makes `PdfEngine.page_geometry` raise a `ValueError` (see
    # `adapters.pdf.pdfium_pypdf_engine.PageGeometry`'s own validation) --
    # but nothing here called it, so registration would persist the test
    # anyway and only discover the problem the first time something rendered
    # it, leaving an unusable draft behind (Issue #16 review).
    for page_index in range(page_count):
        try:
            pdf_engine.page_geometry(path, page_index)
        except ValueError as exc:
            raise PdfGeometryError(f"page {page_index + 1} has invalid geometry: {exc}") from exc
        except Exception as exc:
            # `page_geometry` (pypdf) can fail in ways other than the
            # `ValueError` its own box-validation raises -- e.g. `KeyError`/
            # `TypeError` resolving an inherited MediaBox/CropBox/rotation
            # through a broken page tree. None of those mean "the geometry is
            # invalid"; they mean the page could not be read (Issue #16
            # review round 7).
            raise PdfCorruptedError(
                f"could not determine page {page_index + 1}'s geometry: {exc}"
            ) from exc
        try:
            # The checks above are pypdf-backed, but pdfium is what actually
            # renders and extracts text later, and pypdf can parse -- and
            # silently repair -- a PDF pdfium's stricter parser refuses
            # outright. Exercising that path here keeps "an invalid PDF is
            # rejected at intake" true rather than deferring the failure to
            # whatever first tries to read the file (Issue #16 review round 7).
            extract_text_lines(path, page_index)
        except Exception as exc:
            raise PdfCorruptedError(
                f"page {page_index + 1} could not be parsed with pdfium: {exc}"
            ) from exc


@dataclass(frozen=True, kw_only=True)
class _ValidatedMaterial:
    role: MaterialRole
    filename: str
    extension: str
    data: bytes
    sha256: str


def _validate_uploads(
    pdf_engine: PdfEngine,
    uploads: Sequence[MaterialUpload],
    limits: IntakeLimits,
) -> list[_ValidatedMaterial]:
    """Validate every upload before any of them is written.

    All-or-nothing on purpose: a batch that would fail on its third file must
    not leave the first two attached, because the reviewer's retry would then
    have to reason about which half landed.
    """
    validated: list[_ValidatedMaterial] = []
    with tempfile.TemporaryDirectory(prefix="auto-scoring-test-intake-") as scratch_dir:
        for index, upload in enumerate(uploads):
            extension = validate_material_upload(
                role=upload.role,
                filename=upload.filename,
                data=upload.data,
                limits=limits,
            )
            if extension == "pdf":
                # Word/Excel are stored as opaque bytes: nothing in this app
                # opens them yet (Issue #95 decision 3 registers them so a
                # reviewer can quote from them, and the LLM extraction that
                # would read them is separate work). Their signature check in
                # `validate_material_upload` is all that is claimed about
                # them, and no more is implied here.
                scratch = Path(scratch_dir) / f"material-{index}.pdf"
                scratch.write_bytes(upload.data)
                _validate_one_pdf(pdf_engine, scratch, limits)
            validated.append(
                _ValidatedMaterial(
                    role=upload.role,
                    filename=upload.filename,
                    extension=extension,
                    data=upload.data,
                    sha256=hashlib.sha256(upload.data).hexdigest(),
                )
            )
    return validated


def register_test(
    uow: SqlAlchemyUnitOfWork,
    store: LocalFileStore,
    pdf_engine: PdfEngine,
    *,
    name: str,
    subject: str | None,
    materials: Sequence[MaterialUpload],
    limits: IntakeLimits | None = None,
    now: datetime,
    id_factory: Callable[[], str] = lambda: uuid4().hex,
) -> tuple[Test, list[TestMaterial]]:
    """Validate every material, then create the `Test` row and store the files.

    ``materials`` must include exactly one
    :attr:`~auto_scoring.domain.intake_template.MaterialRole.GRADING_CRITERIA`
    file -- the one required input (Issue #95 decision 1). The caller's own
    signature is what makes that unmissable at the HTTP boundary; the check
    here is what makes it true for every caller.

    Raises a validation error for any material -- no file is stored and no
    `Test` row is created in that case.
    """
    limits = limits or IntakeLimits()
    validated = _validate_uploads(pdf_engine, materials, limits)

    criteria_count = sum(1 for item in validated if item.role is MaterialRole.GRADING_CRITERIA)
    if criteria_count != 1:
        raise ValueError(
            f"a test must be registered with exactly one grading-criteria file, "
            f"got {criteria_count}"
        )

    test = Test(
        id=id_factory(),
        name=name,
        subject=subject,
        default_scoring_method=ScoringMethod.ADDITIVE,
        created_at=now,
    )
    # Written before the DB commit below (and independent of the materials'
    # own staged writes) so it exists even if this attempt gets no further
    # than that commit -- see `_REGISTRATION_MARKER_FILENAME`'s docstring.
    store.write_atomic(_registration_marker_path(store, test.id), b"")

    stored: list[TestMaterial] = []
    try:
        with transactional_operation(uow, store) as staged:
            uow.tests.add(test)
            for item in validated:
                material_id = id_factory()
                path = store.test_material_path(test.id, material_id, item.extension)
                material = TestMaterial(
                    id=material_id,
                    test_id=test.id,
                    role=item.role,
                    stored_path=store.relative_path(path),
                    sha256=item.sha256,
                    size_bytes=len(item.data),
                    original_filename=item.filename,
                    created_at=now,
                )
                uow.test_materials.add(material)
                staged.add(path, item.data)
                stored.append(material)
    except FinalizationError:
        # The rows already committed (transactional_operation only guarantees
        # "DB commit before file write", not that the write also succeeds)
        # but one or more files failed to reach disk. Left alone, this id
        # would linger forever as a `draft` test with missing files --
        # unusable, and unreachable for a retry since the caller never
        # received the id (the request is about to raise). Compensate by
        # removing the row in a fresh transaction on the same session, and
        # any partial file that did land -- an orphaned file with no owning
        # row would never be cleaned up by anything else.
        uow.tests.delete(test.id)
        uow.commit()
        store.delete_test(test.id)
        raise

    return test, stored


def attach_materials(
    uow: SqlAlchemyUnitOfWork,
    store: LocalFileStore,
    pdf_engine: PdfEngine,
    *,
    test_id: str,
    materials: Sequence[MaterialUpload],
    limits: IntakeLimits | None = None,
    now: datetime,
    id_factory: Callable[[], str] = lambda: uuid4().hex,
) -> list[TestMaterial]:
    """Add materials to a test that already exists.

    This is what makes the weekly flow work in both directions: answers for an
    already-registered test arrive as submissions, and a 添削資料 that turns up
    later can still be attached without re-registering the test (Issue #101).

    Re-attaching a file that is already there under the same role returns the
    existing material rather than a second copy: the intake screen retries only
    the rows that failed, and a row can fail *after* its write committed.

    Two further cases this has to get right, both reachable from one ordinary
    retry:

    * **the same content twice in one request.** Collapsed before any write --
      otherwise the unique constraint rejects the second insert and takes every
      other material in the request down with it.
    * **a row whose file is missing.** Re-staged rather than reported as
      already-attached, so an interrupted earlier attempt heals instead of
      leaving a material that can never be opened.

    Returns one material per distinct (role, content), so the result can be
    shorter than ``materials``.
    """
    limits = limits or IntakeLimits()
    validated = _validate_uploads(pdf_engine, materials, limits)

    # De-duplicated by (role, content) before anything is looked up or written.
    # Two files with different names but identical bytes are one material under
    # `uq_test_materials_test_role_hash`, and without collapsing them here both
    # would be inserted and the *whole* attach would fail on the constraint --
    # taking the other, unrelated materials in the same request with it. Real
    # material makes this reachable: a subject folder can ship the same
    # document twice under two names.
    unique: dict[tuple[MaterialRole, str], _ValidatedMaterial] = {}
    for item in validated:
        unique.setdefault((item.role, item.sha256), item)

    fresh: list[_ValidatedMaterial] = []
    repairs: list[tuple[TestMaterial, _ValidatedMaterial]] = []
    attached: list[TestMaterial] = []
    for item in unique.values():
        existing = uow.test_materials.find_by_content(test_id, role=item.role, sha256=item.sha256)
        if existing is None:
            fresh.append(item)
        elif store.resolve_stored_path(existing.stored_path).is_file():
            attached.append(existing)
        else:
            # The row is there but its file is not. `transactional_operation`
            # commits the DB *before* writing, so a crash or a full disk
            # between the two leaves exactly this -- and the plain
            # "already attached, nothing to do" answer would report success
            # for a material that cannot be opened, permanently. Re-stage the
            # bytes to the path the row already names, which is the one repair
            # that leaves the row and the file agreeing.
            repairs.append((existing, item))

    if not fresh and not repairs:
        return attached

    with transactional_operation(uow, store) as staged:
        for existing, item in repairs:
            staged.add(store.resolve_stored_path(existing.stored_path), item.data)
            attached.append(existing)
        for item in fresh:
            material_id = id_factory()
            path = store.test_material_path(test_id, material_id, item.extension)
            material = TestMaterial(
                id=material_id,
                test_id=test_id,
                role=item.role,
                stored_path=store.relative_path(path),
                sha256=item.sha256,
                size_bytes=len(item.data),
                original_filename=item.filename,
                created_at=now,
            )
            uow.test_materials.add(material)
            staged.add(path, item.data)
            attached.append(material)
    return attached


def repair_incomplete_test_registrations(
    uow: SqlAlchemyUnitOfWork, store: LocalFileStore
) -> list[str]:
    """Delete any `DRAFT` test that went through `register_test` but whose
    grading-criteria file is missing on disk.

    `register_test`'s own `FinalizationError` handler already compensates for
    a failed file write within the same request -- but a process crash or
    power loss between `transactional_operation`'s DB commit and those writes
    completing leaves the same broken state with no exception handler ever
    running to notice, exactly like
    `submission_intake.repair_incomplete_submissions` covers for submissions.
    Unlike a `Submission`, `Test` has no intermediate `error` state to move
    into: a test whose criteria file is gone cannot be analyzed at all, so
    (matching what `register_test`'s compensation does) the only usable
    recovery is to delete the row outright. Call this once at startup.

    Gated on `_REGISTRATION_MARKER_FILENAME`, not merely "a file is missing":
    migration 0011 backfills `status='draft'` onto every `Test` row that
    predates PDF-based registration, and migration 0015 gives every row
    material entries for the two legacy paths whether or not those files were
    ever written. An earlier version of this function used "files missing"
    alone as the trigger, which classified every such pre-existing row as an
    interrupted registration and deleted it -- cascading to its Questions and
    Submissions -- on the first startup after upgrading (Issue #16 review
    round 5, data-loss). Only a row the marker says went through
    `register_test` is ever a candidate here.

    Only ever considers `DRAFT` tests: a `READY` test's materials were already
    read to confirm its profile, so one missing a file now is a different,
    later problem this sweep does not attempt to diagnose.

    Returns the ids removed this way.
    """
    removed: list[str] = []
    for test in uow.tests.list_all():
        if test.status is not TestStatus.DRAFT:
            continue
        if not _registration_marker_path(store, test.id).is_file():
            continue
        criteria = [
            material
            for material in uow.test_materials.list_for_test(test.id)
            if material.role is MaterialRole.GRADING_CRITERIA
        ]
        if criteria and all(
            store.resolve_stored_path(material.stored_path).is_file() for material in criteria
        ):
            continue
        uow.tests.delete(test.id)
        uow.commit()
        store.delete_test(test.id)
        removed.append(test.id)
    return removed
