"""``PdfEngine`` backed by pypdfium2 (rasterize) and pypdf (overlay / stamp).

Selected by PoC 3 (GitHub issue #12) as the licence-clean alternative to
PyMuPDF. Both libraries are permissively licensed (pypdfium2: Apache-2.0 /
BSD-3-Clause; pypdf: BSD-3-Clause) and need no commercial agreement.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from io import BytesIO
from pathlib import Path

import pypdfium2 as pdfium
from pypdf import PageObject, PdfReader, PdfWriter

from auto_scoring.domain.pdf_geometry import (
    NormalizedPoint,
    PageGeometry,
    UserSpacePoint,
    normalized_to_user_space,
)


class PdfiumPypdfEngine:
    """Concrete :class:`~auto_scoring.domain.pdf_engine.PdfEngine`."""

    def page_geometry(self, source: Path, page_index: int) -> PageGeometry:
        reader = PdfReader(str(source))
        page = reader.pages[page_index]
        media, crop = page.mediabox, page.cropbox
        # pdfium displays CropBox intersected with MediaBox.
        left = max(float(crop.left), float(media.left))
        bottom = max(float(crop.bottom), float(media.bottom))
        right = min(float(crop.right), float(media.right))
        top = min(float(crop.top), float(media.top))
        return PageGeometry(
            crop_width=right - left,
            crop_height=top - bottom,
            crop_offset_x=left,
            crop_offset_y=bottom,
            rotation=int(page.rotation),
        )

    def render_page_png(self, source: Path, page_index: int, *, scale: float) -> bytes:
        document = pdfium.PdfDocument(str(source))
        try:
            image = document[page_index].render(scale=scale).to_pil()
            buffer = BytesIO()
            image.save(buffer, format="PNG")
            return buffer.getvalue()
        finally:
            document.close()

    def stamp_markers(
        self,
        source: Path,
        destination: Path,
        markers: Mapping[int, Sequence[NormalizedPoint]],
        *,
        mark_size_pt: float = 8.0,
    ) -> None:
        writer = PdfWriter()
        writer.append(PdfReader(str(source)))
        for page_index, points in markers.items():
            geometry = self.page_geometry(source, page_index)
            page = writer.pages[page_index]
            content = "\n".join(
                _filled_square(normalized_to_user_space(point, geometry), mark_size_pt)
                for point in points
            )
            overlay = PdfReader(BytesIO(_overlay_pdf(page, content))).pages[0]
            page.merge_page(overlay)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("wb") as handle:
            writer.write(handle)


def _filled_square(center: UserSpacePoint, size_pt: float) -> str:
    """A PDF content-stream op set: a red square of ``size_pt`` centred on ``center``."""
    x = center.x - size_pt / 2.0
    y = center.y - size_pt / 2.0
    return f"q 1 0 0 rg {x:.4f} {y:.4f} {size_pt:.4f} {size_pt:.4f} re f Q"


def _overlay_pdf(reference_page: PageObject, content: str) -> bytes:
    """A one-page PDF sized like ``reference_page`` that draws ``content``.

    Used as a pypdf overlay: ``merge_page`` concatenates its content stream onto
    the target page in the same user-space coordinates.
    """
    box = reference_page.mediabox
    width = float(box.width)
    height = float(box.height)
    body = content.encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width:.4f} {height:.4f}] "
            f"/Contents 4 0 R >>"
        ).encode("latin-1"),
        b"<< /Length %d >>\nstream\n" % len(body) + body + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: list[int] = []
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + obj + b"\nendobj\n"
    startxref = len(out)
    out += b"xref\n0 %d\n" % (len(objects) + 1)
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\n" % (len(objects) + 1)
    out += b"startxref\n%d\n%%%%EOF" % startxref
    return bytes(out)
