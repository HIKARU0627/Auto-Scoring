"""Extract per-line text and its on-page rectangle from a PDF (Issue #16).

`domain.profile_detection`'s `Marker` boundary expects tagged spans already
located on a page; this adapter is the "real" upstream source that boundary
was always meant to be swapped in for (see
docs/poc-4-multi-layout-profiles.md "検出境界"), reading actual PDF text via
pypdfium2 instead of the PoC's tagged annotation squares
(`adapters.pdf.annotation_markers`).

pdfium does not do layout analysis -- no word/line/paragraph detection (see
`pypdfium2.PdfTextPage`'s own docstring). This module's "line" is the
crudest thing that still works well enough for a first-pass candidate: a run
of characters between the CRLF breaks pdfium's own text extraction already
inserts.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pypdfium2 as pdfium
from pypdfium2 import PdfTextPage
from pypdfium2 import raw as pdfium_raw

RectPt = tuple[float, float, float, float]
"""(left, bottom, right, top) in PDF user-space points, origin bottom-left."""


@dataclass(frozen=True)
class TextLine:
    """One line of extracted text and its bounding rectangle."""

    text: str
    rect_pt: RectPt


def extract_text_lines(source: Path, page_index: int) -> list[TextLine]:
    """Every non-blank line of text on one page, with its bounding rectangle.

    Lines are split on pdfium's own CRLF line breaks (see `PdfTextPage`'s
    docstring: "PDFium's text APIs generally output CRLF style line
    breaks"). A line whose characters produce no text rectangle (e.g. it was
    entirely whitespace pdfium still counted as a "line") is skipped.
    """
    document = pdfium.PdfDocument(str(source))
    try:
        page = document[page_index]
        textpage = page.get_textpage()
        try:
            return _lines_from_textpage(textpage)
        finally:
            textpage.close()
    finally:
        document.close()


def _utf16_length(text: str) -> int:
    """Length of `text` in UTF-16 code units -- what PDFium's text-index
    APIs (`FPDFText_GetCharIndexFromTextIndex`) count in, unlike Python's
    own `len()`, which counts Unicode code points. A non-BMP character (an
    emoji, or a rare CJK ideograph like "\U00020bb7") is one Python `str`
    element but a UTF-16 *surrogate pair* -- two code units -- so
    accumulating plain `len()` into `text_index` drifts out of sync with
    PDFium's own indexing the moment one appears, misassigning every
    following line's rectangle to the wrong span of characters (Issue #16
    review round 8).
    """
    return len(text.encode("utf-16-le")) // 2


def _lines_from_textpage(textpage: PdfTextPage) -> list[TextLine]:
    n_chars = textpage.count_chars()
    if n_chars == 0:
        return []
    full_text = textpage.get_text_range(0, n_chars)
    lines: list[TextLine] = []
    # Position within `full_text`, in UTF-16 code units -- *not* Python
    # code points, and *not* PDFium's internal char list either (`_line_rect`
    # converts each line's own position independently instead of this
    # accumulating into a char-list index, see its docstring).
    text_index = 0
    for raw_line in full_text.split("\r\n"):
        length = _utf16_length(raw_line)
        stripped = raw_line.strip()
        if stripped:
            rect = _line_rect(textpage, text_index, length)
            if rect is not None:
                lines.append(TextLine(text=stripped, rect_pt=rect))
        text_index += length + 2  # skip the "\r\n" itself (2 UTF-16 units)
    return lines


def _line_rect(textpage: PdfTextPage, text_index: int, length: int) -> RectPt | None:
    """The bounding rectangle for the `length` characters of `full_text`
    (`textpage.get_text_range`'s output) starting at `text_index`.

    `count_rects`/`get_rect` index into PDFium's *internal* char list, which
    `get_text_range`'s own docstring warns can exclude or insert characters
    relative to the extracted text -- so treating a position in that text as
    a char-list index directly (as this used to) drifts after the first
    such mismatch, misassigning every following line's rectangle to the
    wrong span of characters (Issue #16 review). Converting each line's own
    `text_index` via `FPDFText_GetCharIndexFromTextIndex` keeps one line's
    drift from propagating into the next.
    """
    if length == 0:
        return None
    start_char = pdfium_raw.FPDFText_GetCharIndexFromTextIndex(textpage, text_index)
    end_char = pdfium_raw.FPDFText_GetCharIndexFromTextIndex(textpage, text_index + length - 1)
    if start_char == -1 or end_char == -1 or end_char < start_char:
        return None
    n_rects = textpage.count_rects(start_char, end_char - start_char + 1)
    if n_rects == 0:
        return None
    lefts: list[float] = []
    bottoms: list[float] = []
    rights: list[float] = []
    tops: list[float] = []
    for i in range(n_rects):
        left, bottom, right, top = textpage.get_rect(i)
        lefts.append(left)
        bottoms.append(bottom)
        rights.append(right)
        tops.append(top)
    return (min(lefts), min(bottoms), max(rights), max(tops))
