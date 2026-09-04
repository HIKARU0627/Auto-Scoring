"""PDF-facing adapters (pypdf-based). Domain code never imports this package's dependencies."""

from auto_scoring.adapters.pdf.annotation_markers import read_markers

__all__ = ["read_markers"]
