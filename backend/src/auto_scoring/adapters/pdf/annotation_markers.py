"""PoC-only reader for tagged square annotation rectangles.

This deterministic stand-in must be replaced by the real extraction adapter;
see docs/poc-4-multi-layout-profiles.md. Page geometry (CropBox/MediaBox and
``/Rotate``) is read via :class:`~auto_scoring.adapters.pdf.PdfiumPypdfEngine`
(PoC 3 / Issue #12's adopted ``PdfEngine``), not by reading ``mediabox``
directly, so a rotated or CropBox-inset page still normalizes correctly.
"""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

from auto_scoring.adapters.pdf.pdfium_pypdf_engine import PdfiumPypdfEngine
from auto_scoring.domain.pdf_geometry import PageGeometry
from auto_scoring.domain.profile import FormatSignature, PageFormat
from auto_scoring.domain.profile_detection import Marker

_engine = PdfiumPypdfEngine()


def read_markers(
    pdf_path: Path,
) -> tuple[list[Marker], FormatSignature, tuple[PageGeometry, ...]]:
    """Return tagged square annotations, the document's format signature, and per-page geometry.

    The signature's page sizes are the *displayed* dimensions
    (:attr:`PageGeometry.displayed_width`/``displayed_height``), so a page
    rotated 90/270 degrees reports its visually swapped size, matching what a
    human (or pdfium) actually sees.
    """
    reader = PdfReader(pdf_path)
    page_geometries = tuple(
        _engine.page_geometry(pdf_path, page_index) for page_index in range(len(reader.pages))
    )
    signature = FormatSignature(
        pages=tuple(
            PageFormat(width_pt=geometry.displayed_width, height_pt=geometry.displayed_height)
            for geometry in page_geometries
        )
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
    return markers, signature, page_geometries
