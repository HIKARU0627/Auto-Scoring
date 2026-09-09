"""Turning a test's registered 採点基準PDF into a
`CriteriaExtractionRequest` (Issue #103).

Two jobs, both of which are boundary work and so live here rather than in
the domain: finding the file, and rendering it.

**Images first, text as an aid.** 6 of the 11 measured subjects' criteria
PDFs yield 0 extractable characters, and those 6 are the subjects whose
answers are formulae -- so this renders *every* page to PNG unconditionally
and only then adds whatever text layer happens to exist. There is no
"try text, fall back to images" branch: that branch would take the text path
for the 5 subjects where it is weakest (a PDF text extractor's reading of a
dense marking scheme) and the image path only where nothing else was
possible.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from auto_scoring.adapters.local_storage import LocalFileStore
from auto_scoring.adapters.pdf.text_layout_extraction import extract_text_lines
from auto_scoring.domain.criteria_extraction import CriteriaError, CriteriaExtractionRequest
from auto_scoring.domain.intake_template import MaterialRole
from auto_scoring.domain.pdf_engine import PdfEngine
from auto_scoring.domain.test_material import TestMaterial

#: Render scale for a page image. 2.0 doubles PDF user-space points into
#: pixels (~144 DPI for a page authored at 72 DPI), which is what made the
#: measured scans' handwriting-sized annotations and small 配点 digits legible
#: at all; 1.0 did not. Higher costs request size on every page of every
#: subject for no measured gain.
PAGE_RENDER_SCALE = 2.0

#: Refuse rather than silently truncate. The measured documents run 1-8
#: pages, so this is far above real material; a document past it is either
#: not a marking scheme or a bundle that should have been split, and sending
#: the first 30 pages while saying nothing about the rest is exactly the
#: silent-omission failure this Issue exists to prevent.
MAX_CRITERIA_PAGES = 30


def criteria_pdf_path(store: LocalFileStore, materials: Sequence[TestMaterial]) -> Path | None:
    """The 採点基準PDF among this test's registered materials, or ``None``.

    Issue #101 replaced the fixed two-PDF registration with a list of
    role-tagged materials, so the criteria document is the one carrying
    :attr:`~auto_scoring.domain.intake_template.MaterialRole.GRADING_CRITERIA`.
    Tests registered before that keep working without a special case here:
    migration 0015 backfills their ``tests/<id>/manual.pdf`` under exactly
    that role.

    **Oldest first, and PDFs only** -- the same two rules
    `api.test_registration_router` applies when it picks a material:

    * oldest, so the choice is stable. A test may hold several materials of
      one role, and silently switching documents when another is attached
      would change what an extraction reads without anyone asking for it.
    * PDF only, because this module hands the file to PDFium.
      ``GRADING_CRITERIA`` is not restricted to PDFs by the model, and a
      reviewer can attach anything to it through ``POST /materials``.

    ``None`` rather than a guessed path: a test with no criteria material has
    nothing to extract from, and saying so is more useful than failing later
    on a file that was never there.
    """
    for material in materials:
        if material.role is MaterialRole.GRADING_CRITERIA and material.stored_path.endswith(".pdf"):
            return store.resolve_stored_path(material.stored_path)
    return None


def build_extraction_request(pdf_engine: PdfEngine, source: Path) -> CriteriaExtractionRequest:
    """Render every page of ``source`` and collect its text layer.

    Raises ``FileNotFoundError`` if the registered file is gone, and
    :class:`~auto_scoring.domain.criteria_extraction.CriteriaError` for a
    document with no pages or more than :data:`MAX_CRITERIA_PAGES`.
    """
    if not source.exists():
        raise FileNotFoundError(source)
    page_count = pdf_engine.page_count(source)
    if page_count < 1:
        raise CriteriaError("採点基準PDFにページがありません。")
    if page_count > MAX_CRITERIA_PAGES:
        raise CriteriaError(
            f"採点基準PDFが {page_count} ページあります。"
            f"一度に読めるのは {MAX_CRITERIA_PAGES} ページまでです。"
            "ファイルを分割してから取り込んでください。"
        )

    images = tuple(
        pdf_engine.render_page_png(source, page_index, scale=PAGE_RENDER_SCALE)
        for page_index in range(page_count)
    )
    texts = tuple(_page_text(source, page_index) for page_index in range(page_count))
    return CriteriaExtractionRequest(page_images=images, page_texts=texts)


def _page_text(source: Path, page_index: int) -> str:
    """One page's text layer, or ``""``.

    A failure to read the text layer is deliberately swallowed: the images
    are the real input, and losing the optional aid must not lose the
    extraction. A failure to *render* is not swallowed -- that one is fatal
    and propagates.
    """
    try:
        return "\n".join(line.text for line in extract_text_lines(source, page_index))
    except Exception:
        return ""
