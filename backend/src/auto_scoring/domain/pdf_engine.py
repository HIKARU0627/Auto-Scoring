"""Port for the PDF read / render / annotate operations the app needs.

Adopted from PoC 3 (GitHub issue #12, PR #31 -- copied verbatim from branch
``HIKARU0627/issue-12-pdf-coords-poc``; see ``docs/poc-4-multi-layout-profiles.md``
for why this PoC carries its own copy while PR #31 is still open). Implementations
live in ``adapters/``; the domain only ever sees this protocol and
:mod:`auto_scoring.domain.pdf_geometry`.

PoC 3 selected **pypdfium2 + pypdf** as the implementation (see
``docs/poc-3-pdf-coordinates.md``): PyMuPDF stays out until a licence-decision
owner records approval, and the protocol keeps that swap to one adapter.

The signatures cover only what PoC 3 exercised -- read page geometry, rasterize a
page, and stamp a mark at a normalized point. The annotation feature issue will
widen ``stamp_markers`` into real ``maru`` / ``batsu`` / comment glyphs.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol

from auto_scoring.domain.pdf_geometry import NormalizedPoint, PageGeometry


class PdfEngine(Protocol):
    """Everything the core needs from a PDF toolkit."""

    def page_geometry(self, source: Path, page_index: int) -> PageGeometry:
        """Return the crop box and rotation pdfium uses to display the page."""
        ...

    def render_page_png(self, source: Path, page_index: int, *, scale: float) -> bytes:
        """Rasterize one page to PNG bytes at ``scale`` pixels per point."""
        ...

    def stamp_markers(
        self,
        source: Path,
        destination: Path,
        markers: Mapping[int, Sequence[NormalizedPoint]],
        *,
        mark_size_pt: float = 8.0,
    ) -> None:
        """Write ``source`` to ``destination`` with a mark at each normalized point.

        ``markers`` maps a 0-based page index to the points to stamp on it. The
        source file is never modified (simplified design spec sec. 35-4).
        """
        ...
