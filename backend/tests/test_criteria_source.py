"""Tests for turning a registered 採点基準PDF into an extraction request, and
for persisting the draft (Issue #103).

Synthetic PDFs only (Issue #103 acceptance criterion 8).
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfWriter

from auto_scoring.adapters.criteria_extraction.source import (
    MAX_CRITERIA_PAGES,
    build_extraction_request,
    criteria_pdf_path,
)
from auto_scoring.adapters.local.criteria_store import CriteriaStore
from auto_scoring.adapters.local_storage import LocalFileStore
from auto_scoring.adapters.pdf.pdfium_pypdf_engine import PdfiumPypdfEngine
from auto_scoring.domain.criteria_extraction import (
    CriteriaDraft,
    CriteriaError,
    CriteriaQuestion,
    CriteriaStatus,
)


def _write_pdf(path: Path, *, pages: int) -> Path:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=595, height=842)
    buffer = BytesIO()
    writer.write(buffer)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(buffer.getvalue())
    return path


def test_every_page_is_rendered_to_an_image(tmp_path: Path) -> None:
    """Unconditionally, with no "try text first" branch: 6 of the 11 measured
    subjects have no text layer at all, and they are the subjects whose
    answers are formulae."""
    source = _write_pdf(tmp_path / "criteria.pdf", pages=3)
    request = build_extraction_request(PdfiumPypdfEngine(), source)
    assert len(request.page_images) == 3
    assert all(image.startswith(b"\x89PNG") for image in request.page_images)
    # One text entry per page, empty for these blank pages -- the aid is
    # optional, the images are not.
    assert len(request.page_texts) == 3
    assert all(text == "" for text in request.page_texts)


def test_a_document_past_the_page_cap_is_refused_not_truncated(tmp_path: Path) -> None:
    """Sending the first N pages and saying nothing about the rest is the
    silent omission this whole Issue exists to prevent."""
    source = _write_pdf(tmp_path / "criteria.pdf", pages=MAX_CRITERIA_PAGES + 1)
    with pytest.raises(CriteriaError) as error:
        build_extraction_request(PdfiumPypdfEngine(), source)
    assert str(MAX_CRITERIA_PAGES) in str(error.value)


def test_a_missing_file_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        build_extraction_request(PdfiumPypdfEngine(), tmp_path / "absent.pdf")


def test_criteria_pdf_path_points_at_the_registered_manual(tmp_path: Path) -> None:
    """The single seam between this Issue and Issue #101 -- see the
    function's own docstring for what changes after those branches merge."""
    store = LocalFileStore(tmp_path)
    assert criteria_pdf_path(store, "test-1") == store.test_manual_pdf_path("test-1")


def test_store_round_trips_a_draft(tmp_path: Path) -> None:
    store = CriteriaStore(tmp_path)
    draft = CriteriaDraft(
        test_id="test-1",
        questions=(CriteriaQuestion(number="問1", points=None, note="配点不明"),),
        unreadable_pages=(2,),
        extracted=True,
        revision=3,
        status=CriteriaStatus.CONFIRMED,
    )
    store.save(draft)
    loaded = store.load("test-1")
    assert loaded == draft
    # 不明 survives the file, which is where a "just default it to 0"
    # serializer would quietly undo the whole feature.
    assert loaded.questions[0].points is None


def test_store_load_raises_when_nothing_was_ever_saved(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        CriteriaStore(tmp_path).load("test-1")


def test_store_writes_next_to_the_profile(tmp_path: Path) -> None:
    store = CriteriaStore(tmp_path)
    assert store.criteria_path("test-1").name == "criteria.json"
    assert store.criteria_path("test-1").parent.name == "test-1"
