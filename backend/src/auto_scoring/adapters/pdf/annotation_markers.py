"""Reads tagged annotation rectangles from a PDF as `Marker`s.

Stands in for a real text/vision extraction layer for this PoC (see
`auto_scoring.domain.profile_detection`): each marker's tag and rectangle come
straight from a PDF Square annotation's `/Contents` and `/Rect`, rather than
from OCR or layout analysis. Only this module imports `pypdf` -- the domain
layer stays library-free (see `AGENTS.md` "Architecture").
"""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

from auto_scoring.domain.profile import FormatSignature, PageFormat
from auto_scoring.domain.profile_detection import Marker


def read_markers(pdf_path: Path) -> tuple[list[Marker], FormatSignature]:
    """Return every tagged annotation in `pdf_path`, plus the document's format signature."""
    reader = PdfReader(pdf_path)
    pages = tuple(
        PageFormat(width_pt=float(page.mediabox.width), height_pt=float(page.mediabox.height))
        for page in reader.pages
    )

    markers: list[Marker] = []
    for page_index, page in enumerate(reader.pages):
        for annotation in page.get("/Annots", []):
            obj = annotation.get_object()
            tag = str(obj.get("/Contents", "")).strip()
            if not tag:
                continue
            rect = obj["/Rect"]
            markers.append(
                Marker(
                    page_index=page_index,
                    tag=tag,
                    rect_pt=(float(rect[0]), float(rect[1]), float(rect[2]), float(rect[3])),
                )
            )
    return markers, FormatSignature(pages=pages)
