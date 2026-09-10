"""Reading a 添削資料 Excel workbook off disk (Issue #106).

The boundary half of ``domain.error_catalog``: everything here is I/O and
vendor libraries, and all it produces is a plain grid of strings for the
domain to interpret. Splitting it this way is what lets the column-layout
search -- the part that is actually hard, and that
docs/grading-material-structure.md section 5.1 says must survive 4 different
layouts -- be tested without a single binary fixture.

**Why two new dependencies.** The real material is ``.xls`` 6 files and
``.xlsx`` 1 file, and those are two unrelated formats: ``.xlsx`` is a ZIP of
XML parts, ``.xls`` is the pre-2007 OLE2/BIFF binary. The standard library
reads neither (``zipfile`` gets into an ``.xlsx`` but SpreadsheetML's shared
string table, inline strings, styles and cell-reference grid are the actual
work, and nothing in the standard library touches OLE2 at all), and no
already-declared dependency does either -- ``pypdf``/``pypdfium2`` are PDF,
``openpyxl`` is the ``.xlsx`` reader and explicitly refuses ``.xls``. Dropping
``.xls`` was not an option: it is 6 of the 7 files. So ``openpyxl`` and
``xlrd`` (``AGENTS.md``: a new dependency only when nothing present can meet
the requirement).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import date, datetime, time
from pathlib import Path

import openpyxl
import xlrd

from auto_scoring.adapters.local_storage import LocalFileStore
from auto_scoring.domain.error_catalog import (
    CellGrid,
    ErrorCatalog,
    ErrorCatalogUnreadable,
    build_error_catalog,
)
from auto_scoring.domain.intake_template import MaterialRole
from auto_scoring.domain.test_material import TestMaterial

logger = logging.getLogger(__name__)

#: Extensions this module can open, lower-cased. ``.docx`` is deliberately
#: absent: Issue #106 rules Word out of scope, and the 4 subjects whose only
#: 添削資料 is a Word file therefore get no catalogue at all
#: (docs/grading-material-structure.md section 5.4).
SUPPORTED_SUFFIXES = (".xls", ".xlsx")


class UnsupportedCatalogFormat(ValueError):
    """The file is not one of :data:`SUPPORTED_SUFFIXES`.

    Its own type rather than a generic error, because "we cannot open this
    format" and "we opened it and did not understand its columns"
    (:class:`~auto_scoring.domain.error_catalog.ErrorCatalogUnreadable`) are
    different answers for whoever registered the file.
    """


def read_error_catalog(path: Path) -> ErrorCatalog:
    """Read one workbook into a catalogue, or raise.

    Raises :class:`UnsupportedCatalogFormat` for a non-Excel file,
    :class:`~auto_scoring.domain.error_catalog.ErrorCatalogUnreadable` when no
    sheet held a readable table, and whatever the underlying library raises
    for a corrupt or unopenable file. Never returns an empty catalogue.
    """
    suffix = path.suffix.lower()
    if suffix == ".xlsx":
        sheets = _xlsx_grid(path)
    elif suffix == ".xls":
        sheets = _xls_grid(path)
    else:
        raise UnsupportedCatalogFormat(f"not a 添削資料 Excel file: {suffix!r}")
    return build_error_catalog(sheets)


def annotation_resource_catalog(
    store: LocalFileStore, materials: Sequence[TestMaterial]
) -> ErrorCatalog | None:
    """The catalogue for a test's registered 添削資料, or ``None`` with a
    logged reason.

    ``None`` here is a *policy* decision that belongs at this layer and
    nowhere below it: a 添削資料 is optional but recommended
    (business-rules-and-evaluation-data.md section 2 (18), Issue #95 decision
    3), so a test that has none, or has a Word one, or has one whose columns
    this reader does not understand, still gets graded -- less well, which is
    exactly what decision 3 predicts. The reader itself stays strict; what is
    forbidden is losing the difference silently, so every ``None`` that is not
    "no material registered" is logged with the reason, and the reason names
    no cell contents (``AGENTS.md`` "Security").

    Oldest material first and Excel only, mirroring
    ``adapters.criteria_extraction.source.criteria_pdf_path``: a test may hold
    several 添削資料 and quietly switching between them when another is
    attached would change grading input with nobody asking for it.
    """
    path = _annotation_resource_path(store, materials)
    if path is None:
        return None
    try:
        catalog = read_error_catalog(path)
    except ErrorCatalogUnreadable as exc:
        logger.warning(
            "添削資料 registered but no catalogue could be read (%s); grading without it",
            ", ".join(f"sheet {p.sheet_number}: {p.reason.value}" for p in exc.problems),
        )
        return None
    except (UnsupportedCatalogFormat, OSError, ValueError, xlrd.XLRDError) as exc:
        # Never the exception's own message: a library's parse error can quote
        # the bytes it choked on. The type name says enough to act on.
        logger.warning("添削資料 could not be opened (%s); grading without it", type(exc).__name__)
        return None
    if catalog.unreadable_sheets:
        # A partial read is still a read, but "5 rows" must not be reported as
        # the whole file when a sheet of it was not understood.
        logger.warning(
            "添削資料 read with %d entries, but %s could not be read",
            len(catalog.entries),
            ", ".join(
                f"sheet {p.sheet_number}: {p.reason.value}" for p in catalog.unreadable_sheets
            ),
        )
    return catalog


def _annotation_resource_path(
    store: LocalFileStore, materials: Sequence[TestMaterial]
) -> Path | None:
    for material in materials:
        if (
            material.role is MaterialRole.ANNOTATION_RESOURCE
            and material.stored_path.lower().endswith(SUPPORTED_SUFFIXES)
        ):
            return store.resolve_stored_path(material.stored_path)
    return None


def _xlsx_grid(path: Path) -> CellGrid:
    """``data_only=True`` so a formula cell yields its last cached *value*.
    A catalogue is prose, not arithmetic; a sheet that computes a label with a
    formula should still hand over the label."""
    workbook = openpyxl.load_workbook(path, data_only=True, read_only=True)
    try:
        return tuple(
            tuple(tuple(_text(cell) for cell in row) for row in sheet.iter_rows(values_only=True))
            for sheet in workbook.worksheets
        )
    finally:
        workbook.close()


def _xls_grid(path: Path) -> CellGrid:
    book = xlrd.open_workbook(path)
    return tuple(
        tuple(
            tuple(_text(sheet.cell_value(row, column)) for column in range(sheet.ncols))
            for row in range(sheet.nrows)
        )
        for sheet in book.sheets()
    )


def _text(value: object) -> str:
    """One cell as text, for both libraries' value types.

    A whole-number float becomes ``"5"``, not ``"5.0"``: 問題番号 arrives as a
    number in the ``.xlsx`` file, and 「問5.0」 is not what the sheet says. No
    other rounding happens -- a genuinely fractional number keeps its digits.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    return str(value)
