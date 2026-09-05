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


def _lines_from_textpage(textpage: PdfTextPage) -> list[TextLine]:
    n_chars = textpage.count_chars()
    if n_chars == 0:
        return []
    full_text = textpage.get_text_range(0, n_chars)
    lines: list[TextLine] = []
    char_index = 0
    for raw_line in full_text.split("\r\n"):
        length = len(raw_line)
        stripped = raw_line.strip()
        if stripped:
            rect = _line_rect(textpage, char_index, length)
            if rect is not None:
                lines.append(TextLine(text=stripped, rect_pt=rect))
        char_index += length + 2  # skip the "\r\n" itself
    return lines


def _line_rect(textpage: PdfTextPage, index: int, count: int) -> RectPt | None:
    n_rects = textpage.count_rects(index, count)
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
