"""誤答パターン → 減点量 → 赤入れ案 read out of a 添削資料 Excel sheet
(Issue #106).

A 添削資料 is the one registered material that carries what a 採点基準 PDF
does not: the mistakes real students made on this material, the deduction the
instructor applied, and the wording they proposed writing in red
(docs/grading-material-structure.md section 5). Issue #103 deliberately left
it unread; this module is the reading half's pure core.

**Why the reading is a search, not a schema.** The 7 measured Excel files hold
**4 different column layouts** (section 5.1): 6-11 columns, a 場所 column in
some, a 採点基準 column that becomes 減点の有無・幅 or disappears entirely,
重要度/頻度 present or absent, and the same meaning spelled two ways
(生徒の誤り方・現状 / 生徒の誤りの例, 赤入れ案 / 赤入れ例). The header row is
**not row 1** -- row 1 is a course title -- and the sheet name is not fixed
either. A fixed column-index mapping, or an equality match on header labels,
is wrong for at least one of the four. So :func:`build_error_catalog` searches
the top of each sheet for a row that names both required roles, and maps
columns by role marker rather than by position or by exact name.

**Not being able to read is a result, not an absence.** The failure this
module is written against is the one the project keeps hitting -- a tool that
answers "0 entries" when it means "I did not understand this file". Every path
that fails to produce entries raises :class:`ErrorCatalogUnreadable` carrying
*which* sheets failed and *why*; a sheet that fails inside a workbook whose
other sheets read fine is recorded on :attr:`ErrorCatalog.unreadable_sheets`
rather than dropped. There is no code path that returns an empty catalogue.

**What this deliberately does not read.** 「伝えるべきこと」 (present in 3 of
the 4 layouts) and 重要度/頻度 are not extracted: Issue #106 names the triple
誤答パターン → 減点量 → 赤入れ案, and columns nobody asked for are columns
nobody has checked the meaning of. Word (.docx) 添削資料 are out of scope for
Issue #106 entirely -- see ``docs/grading-material-structure.md`` section 5.4
for what that costs, which is not nothing.

Framework-free (``AGENTS.md`` "Architecture"): the Excel libraries live in
``adapters.excel_error_catalog``, which hands this module a plain grid of
strings. ``tests/test_architecture.py`` holds that boundary.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any

from auto_scoring.domain.models import DomainError

#: A grid of already-stringified cells: sheets -> rows -> cells. Rows are not
#: padded to a common width (a real sheet's rows are ragged), so every read
#: goes through :func:`_cell`.
CellGrid = Sequence[Sequence[Sequence[str]]]

#: How far down a sheet to look for the header row. The measured files all
#: put it at index 1, under a one-line course title, but
#: docs/grading-material-structure.md section 5.1 says the position is not
#: fixed and this module must not assume it is. 10 covers a title block
#: several lines deep while still failing loudly on a sheet that simply has
#: no header -- searching the whole sheet would instead find a *data* row
#: that happens to mention 赤入れ and report nonsense as success.
HEADER_SEARCH_ROWS = 10

#: Substrings that identify a column's role in a header cell, matched against
#: :func:`_normalize`d text. Substrings rather than equality because the
#: measured layouts append qualifiers to the same label
#: (「重要度（◎、〇、△）」, 「伝えるべきこと（添削者が共有しておくべきこと）」)
#: and spell the same role two ways. Order within a tuple is irrelevant;
#: order *between* roles is not -- see :func:`_map_columns`.
_MISTAKE_MARKERS = ("誤り", "誤答")
_RED_INK_MARKERS = ("赤入れ",)
_DEDUCTION_MARKERS = ("減点", "採点基準", "配点")
_QUESTION_MARKERS = ("問題番号", "設問番号", "小問", "設問")
_ROUND_MARKERS = ("回数", "実施回")

#: Whitespace to strip from a cell. ``str.strip()`` already covers U+3000 in
#: CPython, but the measured files pad values with it specifically
#: (docs/grading-material-structure.md section 5.1, 「末尾に全角空白が付く」),
#: so it is named here rather than left to depend on that.
_TRIM = " \t\r\n　"


class CatalogUnreadableReason(StrEnum):
    """Why a sheet, or a whole workbook, yielded no catalogue.

    Deliberately coarse and content-free: these values reach logs and error
    messages, and the real material's cell contents are the tutoring school's
    copyrighted text (``AGENTS.md`` "Security"). A reason says what shape the
    file had, never what it said.
    """

    #: No row in the first :data:`HEADER_SEARCH_ROWS` named both a 誤答 column
    #: and a 赤入れ column. The sheet may be a legend, a cover sheet, or a
    #: layout this module has not been taught.
    NO_HEADER_ROW = "no_header_row"
    #: A header row was found, but every row under it was blank in both
    #: required columns.
    NO_DATA_ROWS = "no_data_rows"
    #: The workbook held no sheets at all.
    NO_SHEETS = "no_sheets"


@dataclass(frozen=True, kw_only=True)
class SheetProblem:
    """One sheet that could not be read, by 1-based position and reason.

    **Position, not name.** A sheet name is content out of the source file --
    the measured ones are innocuous (「赤入れ案」「第1回」「Sheet1」) but the
    next school's need not be, and this value is written to logs. The index
    is enough to find the sheet and cannot leak anything.
    """

    sheet_number: int
    reason: CatalogUnreadableReason


class ErrorCatalogUnreadable(DomainError):
    """No sheet in the workbook yielded a single entry.

    Raised instead of returning an empty :class:`ErrorCatalog` so that "this
    file's columns are not what we expected" can never be mistaken for "this
    material records no mistakes" -- the two call for completely different
    actions from whoever registered the file.
    """

    def __init__(self, problems: Sequence[SheetProblem]) -> None:
        detail = ", ".join(f"sheet {p.sheet_number}: {p.reason.value}" for p in problems) or (
            CatalogUnreadableReason.NO_SHEETS.value
        )
        super().__init__(f"no 添削資料 catalogue could be read ({detail})")
        self.problems: tuple[SheetProblem, ...] = tuple(problems)


@dataclass(frozen=True, kw_only=True)
class CatalogEntry:
    """One row: a mistake, what it cost, and the red-pen wording proposed.

    ``deduction``, ``question_label`` and ``round_label`` are ``None`` when the
    layout has no such column or the cell was blank -- absent, never guessed
    and never defaulted to 0 (the same rule
    ``domain.criteria_extraction`` applies to points it could not read).

    ``mistake`` and ``red_ink`` may individually be empty, because a real row
    sometimes fills only one of them, but not both at once: a row with neither
    is not a row, and :func:`build_error_catalog` skips it rather than emitting
    a blank entry.

    ``edited`` is ``False`` for a row exactly as the Excel reader produced it
    and ``True`` once a person has saved it through the review API (Issue
    #209). It is what a re-import consults before replacing a row, so a human
    correction is never silently overwritten by the next read of the source
    (judgment 2; see :func:`merge_import`).
    """

    mistake: str
    red_ink: str
    deduction: str | None = None
    question_label: str | None = None
    round_label: str | None = None
    edited: bool = False

    def __post_init__(self) -> None:
        if not self.mistake and not self.red_ink:
            raise ValueError("CatalogEntry needs at least one of mistake / red_ink")

    def to_dict(self) -> dict[str, Any]:
        return {
            "mistake": self.mistake,
            "red_ink": self.red_ink,
            "deduction": self.deduction,
            "question_label": self.question_label,
            "round_label": self.round_label,
            "edited": self.edited,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CatalogEntry:
        return cls(
            mistake=str(data["mistake"]),
            red_ink=str(data["red_ink"]),
            deduction=_optional_str(data.get("deduction")),
            question_label=_optional_str(data.get("question_label")),
            round_label=_optional_str(data.get("round_label")),
            edited=bool(data.get("edited", False)),
        )


@dataclass(frozen=True, kw_only=True)
class ErrorCatalog:
    """Every entry read from one 添削資料 workbook.

    ``unreadable_sheets`` is the visible half of a partial read: a workbook
    whose second sheet is a legend still produces a catalogue, and the sheet
    that produced nothing is named here rather than silently dropped. A caller
    that wants to warn has something to warn about; a caller that does not
    still cannot mistake the result for a complete read.
    """

    entries: tuple[CatalogEntry, ...]
    unreadable_sheets: tuple[SheetProblem, ...] = ()

    def __post_init__(self) -> None:
        if not self.entries:
            raise ValueError("ErrorCatalog must hold at least one entry")


def build_error_catalog(sheets: CellGrid) -> ErrorCatalog:
    """Read every sheet of one workbook, or raise.

    Raises :class:`ErrorCatalogUnreadable` when no sheet yields an entry --
    including the empty-workbook case, which is a failure of the same kind
    and not an empty success.
    """
    entries: list[CatalogEntry] = []
    problems: list[SheetProblem] = []
    for index, rows in enumerate(sheets, start=1):
        sheet_entries, reason = _read_sheet(rows)
        if reason is not None:
            problems.append(SheetProblem(sheet_number=index, reason=reason))
        entries.extend(sheet_entries)
    if not entries:
        raise ErrorCatalogUnreadable(problems)
    return ErrorCatalog(entries=tuple(entries), unreadable_sheets=tuple(problems))


def _read_sheet(
    rows: Sequence[Sequence[str]],
) -> tuple[tuple[CatalogEntry, ...], CatalogUnreadableReason | None]:
    """``(entries, None)`` or ``((), reason)`` -- never both."""
    header = _find_header(rows)
    if header is None:
        return (), CatalogUnreadableReason.NO_HEADER_ROW
    header_index, columns = header
    entries = tuple(
        entry for row in rows[header_index + 1 :] if (entry := _read_row(row, columns)) is not None
    )
    if not entries:
        return (), CatalogUnreadableReason.NO_DATA_ROWS
    return entries, None


@dataclass(frozen=True, kw_only=True)
class _Columns:
    """Column index per role. ``mistake``/``red_ink`` are always resolved --
    a header row is only recognized as one when both are present."""

    mistake: int
    red_ink: int
    deduction: int | None
    question: int | None
    round: int | None


def _find_header(rows: Sequence[Sequence[str]]) -> tuple[int, _Columns] | None:
    """The first row near the top that maps to both required roles, with its
    column mapping. ``None`` if no row near the top does.

    Recognizing the header and mapping its columns is one decision, not two:
    a row "names 誤答 and 赤入れ" exactly when :func:`_map_columns` can claim a
    distinct column for each. Splitting them would let a header naming both
    roles in a *single* label pass the recognition test and then have no
    column left for the second role.

    Requiring both roles is what keeps the course-title row (which in the
    measured files carries a 重要度/頻度 legend with embedded newlines) and a
    stray data row from being taken for the header.
    """
    for index, row in enumerate(rows[:HEADER_SEARCH_ROWS]):
        columns = _map_columns(row)
        if columns is not None:
            return index, columns
    return None


def _map_columns(header: Sequence[str]) -> _Columns | None:
    """Role -> column index for a candidate header row, or ``None`` when it
    does not carry both required roles in separate columns.

    Roles are resolved in a fixed order and a column is claimed at most once,
    so a label matching two roles' markers goes to whichever role is resolved
    first. Today no two roles' markers overlap; the order is stated anyway, so
    that adding a marker later cannot silently re-point an existing column.

    Unmatched columns -- the decorative 「⇒」 column, 重要度, 頻度, 場所,
    備考, 伝えるべきこと -- are simply not claimed. That is why an unknown
    extra column costs nothing, while a *missing required* column costs a
    :data:`CatalogUnreadableReason.NO_HEADER_ROW`.
    """
    claimed: set[int] = set()

    def claim(markers: Sequence[str]) -> int | None:
        index = _first_match(header, markers, skip=claimed)
        if index is not None:
            claimed.add(index)
        return index

    mistake = claim(_MISTAKE_MARKERS)
    red_ink = claim(_RED_INK_MARKERS)
    if mistake is None or red_ink is None:
        return None
    return _Columns(
        mistake=mistake,
        red_ink=red_ink,
        deduction=claim(_DEDUCTION_MARKERS),
        question=claim(_QUESTION_MARKERS),
        round=claim(_ROUND_MARKERS),
    )


def _read_row(row: Sequence[str], columns: _Columns) -> CatalogEntry | None:
    """One data row, or ``None`` for a row that is blank in both required
    columns (a spacer, or a trailing row the sheet's used range includes)."""
    mistake = _cell(row, columns.mistake)
    red_ink = _cell(row, columns.red_ink)
    if not mistake and not red_ink:
        return None
    return CatalogEntry(
        mistake=mistake,
        red_ink=red_ink,
        deduction=_optional_cell(row, columns.deduction),
        question_label=_optional_cell(row, columns.question),
        round_label=_optional_cell(row, columns.round),
    )


def _first_match(
    row: Sequence[str], markers: Sequence[str], *, skip: set[int] | None = None
) -> int | None:
    for index, cell in enumerate(row):
        if skip is not None and index in skip:
            continue
        normalized = _normalize(cell)
        if normalized and any(marker in normalized for marker in markers):
            return index
    return None


def _normalize(text: str) -> str:
    """Header text with the noise the measured files carry stripped out.

    NFKC folds the half-width/full-width mix that is present *within a single
    file* (section 5.1); whitespace goes entirely, because a header label is
    split across lines in some of the files and the marker must match either
    way.
    """
    return "".join(unicodedata.normalize("NFKC", text).split())


def _cell(row: Sequence[str], index: int) -> str:
    """``row[index]`` trimmed, or ``""`` for a row shorter than the header."""
    if index >= len(row):
        return ""
    return row[index].strip(_TRIM)


def _optional_cell(row: Sequence[str], index: int | None) -> str | None:
    """``None`` for "this layout has no such column" *and* for "the cell was
    blank" -- both mean the same thing to a reader of the catalogue, and
    neither may become an empty string that looks like a value."""
    if index is None:
        return None
    return _cell(row, index) or None


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)


class CatalogState(StrEnum):
    """Why a test has, or has not, a usable 誤答カタログ (Issue #209).

    The three situations Issue #106's logging used to collapse into one are
    now three distinct wire values, because a person deciding what to do next
    needs to tell "we never received the file" from "we received it and could
    not understand it": the first means attach a 添削資料, the second means
    the one already attached is not a layout this reader knows.

    ============================ ================================================
    value                        meaning
    ============================ ================================================
    ``not_registered``           no 添削資料 of any kind is attached (a)
    ``word_only``                a 添削資料 is attached, but none is .xls/.xlsx (b)
    ``unreadable``               an Excel 添削資料 is attached but yielded no entries (c)
    ``available``                entries were imported from the attached Excel
    ============================ ================================================
    """

    NOT_REGISTERED = "not_registered"
    WORD_ONLY = "word_only"
    UNREADABLE = "unreadable"
    AVAILABLE = "available"


class ErrorCatalogConflict(DomainError):
    """A save was based on a revision the catalogue has since moved past.

    Mirrors ``CriteriaDraft.revision``'s compare-and-set: a second client's
    save landing between this reviewer's read and their write must be
    rejected, not silently overwritten. The catalogue's rows carry the
    deduction and the red-ink wording, so an unseen overwrite grades later
    submissions against a number nobody approved -- the same weight of
    accident ``CriteriaDraft``'s docstring describes for points.
    """


class ErrorCatalogError(DomainError):
    """An error catalogue draft could not be described or edited."""


@dataclass(frozen=True, kw_only=True)
class ErrorCatalogDraft:
    """A test's 誤答カタログ as a person reviews it, persisted as one row.

    Same flow as :class:`~auto_scoring.domain.criteria_extraction.
    CriteriaDraft`: a machine proposes rows (here, the Excel import), a
    person edits them, and ``revision`` is the compare-and-set token that
    makes "this is the set I looked at" mean something. Keeping human edits
    across a re-import is :func:`merge_import`'s job; this type only holds
    the state.

    ``imported`` is ``False`` until an import produced at least one entry;
    ``import_error`` names why the last import failed (a
    :class:`CatalogUnreadableReason` value or an exception class name --
    never any cell content). Both are read by :func:`catalog_state`.
    """

    test_id: str
    entries: tuple[CatalogEntry, ...] = ()
    revision: int = 1
    imported: bool = False
    import_error: str | None = None
    note: str | None = None

    def __post_init__(self) -> None:
        if not self.test_id.strip():
            raise ErrorCatalogError("ErrorCatalogDraft.test_id must be a non-blank string")
        if self.revision < 1:
            raise ErrorCatalogError("ErrorCatalogDraft.revision must be >= 1")

    def with_edited_entries(self, entries: Sequence[CatalogEntry]) -> ErrorCatalogDraft:
        """The next revision carrying a human-reviewed set.

        Every row saved through the review API is marked ``edited`` -- the
        person is the author of the saved set, and that is what protects it
        from the next import.
        """
        return replace(
            self,
            entries=tuple(replace(entry, edited=True) for entry in entries),
            revision=self.revision + 1,
        )

    @classmethod
    def new_edited(cls, test_id: str, entries: Sequence[CatalogEntry]) -> ErrorCatalogDraft:
        """A first human save on a test with no stored catalogue (revision 1)."""
        return cls(
            test_id=test_id,
            entries=tuple(replace(entry, edited=True) for entry in entries),
            revision=1,
        )

    @classmethod
    def new_import(cls, test_id: str, entries: Sequence[CatalogEntry]) -> ErrorCatalogDraft:
        """A first successful import on a test with no stored catalogue."""
        return cls(test_id=test_id, entries=tuple(entries), revision=1, imported=True)

    @classmethod
    def new_import_failure(cls, test_id: str, reason: str) -> ErrorCatalogDraft:
        """A first, failed import on a test with no stored catalogue."""
        return cls(test_id=test_id, revision=1, imported=False, import_error=reason)

    def with_import(self, entries: Sequence[CatalogEntry]) -> ErrorCatalogDraft:
        """The next revision after a source file was read successfully.

        ``entries`` already carries the mixing :func:`merge_import` decided
        (human-edited rows kept or discarded, fresh rows in their place), so
        this only records that an import produced rows and clears the
        previous failure reason.
        """
        return replace(
            self,
            entries=tuple(entries),
            revision=self.revision + 1,
            imported=True,
            import_error=None,
        )

    def with_import_failure(self, reason: str) -> ErrorCatalogDraft:
        """The next revision after an import could not be read.

        The prior entries are left where they are -- deleting rows nobody
        agreed to delete because the *file* stopped being readable would be
        worse than the failure -- but ``imported`` drops so the state reads
        ``unreadable`` until a person settles it.
        """
        return replace(self, revision=self.revision + 1, imported=False, import_error=reason)

    def to_dict(self) -> dict[str, Any]:
        return {
            "test_id": self.test_id,
            "entries": [entry.to_dict() for entry in self.entries],
            "revision": self.revision,
            "imported": self.imported,
            "import_error": self.import_error,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ErrorCatalogDraft:
        return cls(
            test_id=str(data["test_id"]),
            entries=tuple(CatalogEntry.from_dict(entry) for entry in data.get("entries", ())),
            revision=int(data["revision"]),
            imported=bool(data.get("imported", False)),
            import_error=_optional_str(data.get("import_error")),
            note=_optional_str(data.get("note")),
        )


def catalog_state(
    *, has_annotation_resource: bool, has_excel: bool, imported: bool
) -> CatalogState:
    """The wire value for a test's catalogue, from its materials and import.

    Pure and content-free on purpose: the caller supplies only booleans, so
    nothing about the file's text can influence the answer (``AGENTS.md``
    "Security").
    """
    if not has_annotation_resource:
        return CatalogState.NOT_REGISTERED
    if not has_excel:
        return CatalogState.WORD_ONLY
    return CatalogState.AVAILABLE if imported else CatalogState.UNREADABLE


def merge_import(
    existing: Sequence[CatalogEntry],
    imported: Sequence[CatalogEntry],
    *,
    overwrite_edited: bool,
) -> tuple[CatalogEntry, ...]:
    """The rows to persist after reading the source file again.

    ``overwrite_edited=True`` takes the file as the whole truth and discards
    every human edit -- the explicit choice a caller must make, never a
    default (judgment 2: 「無言で上書きしない」). ``False`` keeps each
    existing row that a person edited and takes the fresh import for every
    other slot.

    Rows are matched by position, not by content: an Excel row has no stable
    identity to match on (two lines may read identically, and editing a row
    changes its text). A shifted source layout can therefore pair an edited
    row with the wrong fresh row, so the *edited* row is always the one kept
    when positions collide -- a wrong-looking catalogue a person can fix
    beats silently reverting a correction nobody was told about. Edited rows
    past the end of the fresh import are appended rather than dropped.
    """
    if overwrite_edited:
        return tuple(replace(entry, edited=False) for entry in imported)
    kept: list[CatalogEntry] = []
    for index, fresh in enumerate(imported):
        if index < len(existing) and existing[index].edited:
            kept.append(existing[index])
        else:
            kept.append(fresh)
    kept.extend(entry for entry in existing[len(imported) :] if entry.edited)
    return tuple(kept)
