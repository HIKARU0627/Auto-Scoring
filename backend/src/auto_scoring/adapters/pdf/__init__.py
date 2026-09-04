"""PDF-facing adapters. Domain code never imports this package's dependencies."""

from auto_scoring.adapters.pdf.annotation_markers import read_markers
from auto_scoring.adapters.pdf.pdfium_pypdf_engine import PdfiumPypdfEngine

__all__ = ["PdfiumPypdfEngine", "read_markers"]
