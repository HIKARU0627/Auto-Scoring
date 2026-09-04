"""PoC-only reader for tagged square annotation rectangles.

This deterministic stand-in must be replaced by the real extraction adapter;
see docs/poc-4-multi-layout-profiles.md.
"""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

from auto_scoring.domain.profile import FormatSignature, PageFormat
from auto_scoring.domain.profile_detection import Marker


def read_markers(pdf_path: Path) -> tuple[list[Marker], FormatSignature]:
    """Return tagged square annotations and the document's simple format signature."""
    reader = PdfReader(pdf_path)
    pages = tuple(
        PageFormat(width_pt=float(page.mediabox.width), height_pt=float(page.mediabox.height))
        for page in reader.pages
    )

    markers: list[Marker] = []
    for page_index, page in enumerate(reader.pages):
        for annotation in page.get("/Annots", []):
            obj = annotation.get_object()
            if obj.get("/Subtype") != "/Square":
                continue
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
