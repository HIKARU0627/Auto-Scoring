"""HTTP boundary for reviewing a test's 誤答カタログ (Issue #209).

The 添削資料 Excel is the *import source*, not the artefact. Issue #106 read it
in the grading job on every run, so a person's correction to a row vanished
the next time grading opened the file. Here the file is read once into
``error_catalogs`` and grading reads only that row (judgment 2).

* ``GET /tests/{test_id}/error-catalog`` -- the reviewed rows, plus a
  ``state`` that tells the three situations Issue #106 collapsed into a log
  line apart: ``not_registered`` (no 添削資料), ``word_only`` (only a
  ``.docx``), ``unreadable`` (an Excel file whose columns the reader does not
  know), ``available``. The screen branches on the value, never on prose
  (judgment 3).
* ``PUT /tests/{test_id}/error-catalog`` -- save a human-edited set. Body
  carries the ``revision`` the reviewer looked at; a save against a stale one
  is rejected with 409 rather than overwriting an edit it never saw (the same
  compare-and-set ``domain.criteria_extraction.CriteriaDraft`` uses).
* ``POST /tests/{test_id}/error-catalog/import`` -- read the registered Excel
  again, on explicit instruction only. ``on_conflict`` must say what happens
  to rows a person edited (``keep_edited`` or ``overwrite``); there is no
  default, so nothing is ever silently overwritten (judgment 2).

Nothing here logs or returns a row's text beyond what the caller saved: the
rows are the school's copyrighted prose (``AGENTS.md`` "Security"), so import
failure reasons carry only a :class:`CatalogUnreadableReason` value, a sheet
number, or an exception class name.
"""

from __future__ import annotations

from collections.abc import Iterator
from enum import StrEnum
from typing import Annotated

import xlrd
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, sessionmaker

from auto_scoring.adapters.excel_error_catalog import (
    SUPPORTED_SUFFIXES,
    UnsupportedCatalogFormat,
    annotation_resource_catalog_path,
    read_error_catalog,
)
from auto_scoring.adapters.local_storage import LocalFileStore
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.domain.error_catalog import (
    CatalogEntry,
    CatalogState,
    CatalogUnreadableReason,
    ErrorCatalogConflict,
    ErrorCatalogDraft,
    ErrorCatalogUnreadable,
    catalog_state,
    merge_import,
)
from auto_scoring.domain.intake_template import MaterialRole
from auto_scoring.domain.models import DomainError, Test
from auto_scoring.domain.test_material import TestMaterial

#: Every integer on this module's wire boundary is strict, for the reason
#: ``api.criteria_router`` documents: Pydantic's lax mode would turn
#: ``"revision": true`` into 1, and a wrong revision here would silently
#: defeat the compare-and-set the whole review flow rests on.
StrictInt = Annotated[int, Field(strict=True)]


class ImportConflictPolicy(StrEnum):
    """What a re-import does with rows a person edited.

    Required, never defaulted: a caller that has not decided must not get a
    choice made for it, because both choices lose something -- ``overwrite``
    loses the edit, ``keep_edited`` can leave a stale row beside a fresh one.
    """

    KEEP_EDITED = "keep_edited"
    OVERWRITE = "overwrite"


class ErrorCatalogEntryModel(BaseModel):
    """One catalogue row over the wire."""

    mistake: str
    red_ink: str
    deduction: str | None = None
    question_label: str | None = None
    round_label: str | None = None
    edited: bool = False

    @classmethod
    def from_domain(cls, entry: CatalogEntry) -> ErrorCatalogEntryModel:
        return cls(
            mistake=entry.mistake,
            red_ink=entry.red_ink,
            deduction=entry.deduction,
            question_label=entry.question_label,
            round_label=entry.round_label,
            edited=entry.edited,
        )


class ErrorCatalogEntryInput(BaseModel):
    """A row as the reviewer saved it. ``edited`` is the server's to set --
    any row that arrives through this route is a human edit by definition, so
    accepting the flag from the body would let a caller claim an AI row it
    never touched."""

    mistake: str
    red_ink: str
    deduction: str | None = None
    question_label: str | None = None
    round_label: str | None = None

    def to_domain(self) -> CatalogEntry:
        return CatalogEntry(
            mistake=self.mistake,
            red_ink=self.red_ink,
            deduction=self.deduction,
            question_label=self.question_label,
            round_label=self.round_label,
        )


class ErrorCatalogResponse(BaseModel):
    """A test's 誤答カタログ, as the review screen sees it."""

    test_id: str
    #: One of ``not_registered`` / ``word_only`` / ``unreadable`` /
    #: ``available``. The screen branches on this, not on any message.
    state: CatalogState
    #: Compare-and-set token for ``PUT`` and ``POST .../import``.
    revision: StrictInt
    #: Whether an import has ever produced entries. Distinguishes "the file
    #: reader ran and understood the columns" from "nobody imported yet".
    imported: bool
    #: Why the last import produced nothing, if it did. A reason word (or an
    #: exception class name), never file text.
    import_error: str | None = None
    entries: list[ErrorCatalogEntryModel]
    entry_count: StrictInt

    @classmethod
    def from_domain(
        cls, draft: ErrorCatalogDraft, *, has_annotation_resource: bool, has_excel: bool
    ) -> ErrorCatalogResponse:
        return cls(
            test_id=draft.test_id,
            state=catalog_state(
                has_annotation_resource=has_annotation_resource,
                has_excel=has_excel,
                imported=draft.imported,
            ),
            revision=draft.revision,
            imported=draft.imported,
            import_error=draft.import_error,
            entries=[ErrorCatalogEntryModel.from_domain(entry) for entry in draft.entries],
            entry_count=len(draft.entries),
        )


class SaveErrorCatalogRequest(BaseModel):
    """The reviewed row set, pinned to the revision the reviewer read."""

    revision: StrictInt
    entries: list[ErrorCatalogEntryInput]


class ImportErrorCatalogRequest(BaseModel):
    """The explicit instruction to read the source file again."""

    on_conflict: ImportConflictPolicy


def build_error_catalog_router(
    session_factory: sessionmaker[Session], store: LocalFileStore
) -> APIRouter:
    """Build the router. One `SqlAlchemyUnitOfWork` is opened per request."""
    router = APIRouter(tags=["error-catalog"])

    def _uow() -> Iterator[SqlAlchemyUnitOfWork]:
        with SqlAlchemyUnitOfWork(session_factory) as uow:
            yield uow

    uow_dependency = Depends(_uow)

    def _get_test_or_404(uow: SqlAlchemyUnitOfWork, test_id: str) -> Test:
        test = uow.tests.get(test_id)
        if test is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"test {test_id!r} not found")
        return test

    def _annotation_materials(
        uow: SqlAlchemyUnitOfWork, test_id: str
    ) -> tuple[list[TestMaterial], bool, bool]:
        """The test's 添削資料, and the two booleans the state needs."""
        resources = [
            material
            for material in uow.test_materials.list_for_test(test_id)
            if material.role is MaterialRole.ANNOTATION_RESOURCE
        ]
        has_excel = any(
            material.stored_path.lower().endswith(SUPPORTED_SUFFIXES) for material in resources
        )
        return resources, bool(resources), has_excel

    def _load(uow: SqlAlchemyUnitOfWork, test_id: str) -> ErrorCatalogDraft:
        return uow.error_catalogs.get(test_id) or ErrorCatalogDraft(test_id=test_id)

    def _import_error_reason(exc: Exception) -> str:
        if isinstance(exc, ErrorCatalogUnreadable):
            detail = ", ".join(f"sheet {p.sheet_number}: {p.reason.value}" for p in exc.problems)
            return detail or CatalogUnreadableReason.NO_SHEETS.value
        # Never the exception's own message: a library's parse error can
        # quote the bytes it choked on, which are the school's material.
        return type(exc).__name__

    @router.get("/tests/{test_id}/error-catalog", response_model=ErrorCatalogResponse)
    def get_error_catalog(
        test_id: str, uow: SqlAlchemyUnitOfWork = uow_dependency
    ) -> ErrorCatalogResponse:
        _get_test_or_404(uow, test_id)
        _, has_resource, has_excel = _annotation_materials(uow, test_id)
        return ErrorCatalogResponse.from_domain(
            _load(uow, test_id),
            has_annotation_resource=has_resource,
            has_excel=has_excel,
        )

    @router.put("/tests/{test_id}/error-catalog", response_model=ErrorCatalogResponse)
    def save_error_catalog(
        test_id: str,
        request: SaveErrorCatalogRequest,
        uow: SqlAlchemyUnitOfWork = uow_dependency,
    ) -> ErrorCatalogResponse:
        """Save a reviewed row set, refused if it is based on a stale revision."""
        _get_test_or_404(uow, test_id)
        persisted = uow.error_catalogs.get(test_id)
        current_revision = persisted.revision if persisted is not None else 1
        if request.revision != current_revision:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=(
                    f"test {test_id!r}'s 誤答カタログ has changed since revision "
                    f"{request.revision} was reviewed (current revision: {current_revision}); "
                    "reload and re-review before saving"
                ),
            )
        try:
            entries = tuple(entry.to_domain() for entry in request.entries)
            updated = (
                persisted.with_edited_entries(entries)
                if persisted is not None
                else ErrorCatalogDraft.new_edited(test_id, entries)
            )
        except (ValueError, DomainError) as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        try:
            uow.error_catalogs.save(
                updated, expected_revision=persisted.revision if persisted is not None else None
            )
        except ErrorCatalogConflict as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        uow.commit()
        _, has_resource, has_excel = _annotation_materials(uow, test_id)
        return ErrorCatalogResponse.from_domain(
            updated, has_annotation_resource=has_resource, has_excel=has_excel
        )

    @router.post("/tests/{test_id}/error-catalog/import", response_model=ErrorCatalogResponse)
    def import_error_catalog(
        test_id: str,
        request: ImportErrorCatalogRequest,
        uow: SqlAlchemyUnitOfWork = uow_dependency,
    ) -> ErrorCatalogResponse:
        """Read the registered 添削資料 Excel into the persisted catalogue.

        The three "we have no catalogue" states are refused with a 409 naming
        which one it is, and an unreadable file is recorded (and answered 422)
        rather than returned as an empty catalogue -- the distinction Issue
        #106 was written to preserve.
        """
        _get_test_or_404(uow, test_id)
        resources, has_resource, has_excel = _annotation_materials(uow, test_id)
        persisted = uow.error_catalogs.get(test_id)
        expected_revision = persisted.revision if persisted is not None else None
        if not has_resource:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="このテストには添削資料が登録されていません。",
            )
        if not has_excel:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="添削資料が Word のため、誤答カタログを取り込めません。",
            )
        path = annotation_resource_catalog_path(store, resources)
        assert path is not None  # has_excel and the path search use the same suffix list
        try:
            catalog = read_error_catalog(path)
        except (
            ErrorCatalogUnreadable,
            UnsupportedCatalogFormat,
            OSError,
            ValueError,
            xlrd.XLRDError,
        ) as exc:
            reason = _import_error_reason(exc)
            failed = (
                persisted.with_import_failure(reason)
                if persisted is not None
                else ErrorCatalogDraft.new_import_failure(test_id, reason)
            )
            try:
                uow.error_catalogs.save(failed, expected_revision=expected_revision)
            except ErrorCatalogConflict as conflict:
                raise HTTPException(status.HTTP_409_CONFLICT, detail=str(conflict)) from conflict
            uow.commit()
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="添削資料の列を解釈できませんでした。誤答カタログは取り込んでいません。",
            ) from None

        entries = merge_import(
            () if persisted is None else persisted.entries,
            catalog.entries,
            overwrite_edited=request.on_conflict is ImportConflictPolicy.OVERWRITE,
        )
        updated = (
            persisted.with_import(entries)
            if persisted is not None
            else ErrorCatalogDraft.new_import(test_id, entries)
        )
        try:
            uow.error_catalogs.save(updated, expected_revision=expected_revision)
        except ErrorCatalogConflict as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        uow.commit()
        return ErrorCatalogResponse.from_domain(
            updated, has_annotation_resource=has_resource, has_excel=has_excel
        )

    return router
