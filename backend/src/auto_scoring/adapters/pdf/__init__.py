"""PDF engine adapters. PoC 3 (issue #12) selected :mod:`.pdfium_pypdf_engine`."""

from auto_scoring.adapters.pdf.annotation_markers import read_markers
from auto_scoring.adapters.pdf.pdfium_pypdf_engine import PdfiumPypdfEngine

__all__ = ["PdfiumPypdfEngine", "read_markers"]
