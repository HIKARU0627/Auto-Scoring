"""Unit tests for domain.pdf_intake: everything checkable without opening a PDF."""

from __future__ import annotations

import pytest

from auto_scoring.domain.pdf_intake import (
    ALLOWED_MIME_TYPES,
    IntakeLimits,
    PdfEmptyError,
    PdfInvalidTypeError,
    PdfPageLimitExceededError,
    PdfPageTooLargeError,
    PdfTooLargeError,
    sniff_magic_bytes,
    validate_declared_mime,
    validate_filename,
    validate_page_count,
    validate_render_dimensions,
    validate_size,
    validate_upload_bytes,
)

_PDF_BYTES = b"%PDF-1.7\n...\n%%EOF"


def test_validate_filename_accepts_pdf() -> None:
    validate_filename("answer.pdf")
    validate_filename("Answer.PDF")


@pytest.mark.parametrize(
    "filename",
    ["", "   ", "answer.txt", "answer", "../../etc/passwd.pdf", "a/b.pdf", "a\\b.pdf", ".", ".."],
)
def test_validate_filename_rejects(filename: str) -> None:
    with pytest.raises(PdfInvalidTypeError):
        validate_filename(filename)


def test_validate_declared_mime_accepts_pdf_and_missing() -> None:
    validate_declared_mime("application/pdf")
    validate_declared_mime("application/pdf; charset=binary")
    validate_declared_mime(None)


def test_validate_declared_mime_rejects_other_types() -> None:
    with pytest.raises(PdfInvalidTypeError):
        validate_declared_mime("image/png")


def test_allowed_mime_types_is_pdf_only() -> None:
    assert frozenset({"application/pdf"}) == ALLOWED_MIME_TYPES


def test_sniff_magic_bytes_accepts_pdf_signature() -> None:
    sniff_magic_bytes(_PDF_BYTES)


def test_sniff_magic_bytes_rejects_non_pdf() -> None:
    with pytest.raises(PdfInvalidTypeError):
        sniff_magic_bytes(b"not a pdf at all")


def test_validate_size_rejects_empty() -> None:
    with pytest.raises(PdfEmptyError):
        validate_size(b"", IntakeLimits())


def test_validate_size_rejects_over_limit() -> None:
    limits = IntakeLimits(max_size_bytes=10)
    with pytest.raises(PdfTooLargeError):
        validate_size(b"0123456789ABCDEF", limits)


def test_validate_size_accepts_within_limit() -> None:
    validate_size(_PDF_BYTES, IntakeLimits(max_size_bytes=1024))


def test_validate_page_count_rejects_zero() -> None:
    with pytest.raises(PdfEmptyError):
        validate_page_count(0, IntakeLimits())


def test_validate_page_count_rejects_over_limit() -> None:
    with pytest.raises(PdfPageLimitExceededError):
        validate_page_count(101, IntakeLimits(max_pages=100))


def test_validate_page_count_accepts_within_limit() -> None:
    validate_page_count(5, IntakeLimits(max_pages=100))


def test_validate_upload_bytes_end_to_end() -> None:
    validate_upload_bytes(
        filename="answer.pdf",
        declared_mime="application/pdf",
        data=_PDF_BYTES,
        limits=IntakeLimits(),
    )


def test_validate_upload_bytes_rejects_first_failure_it_hits() -> None:
    with pytest.raises(PdfInvalidTypeError):
        validate_upload_bytes(
            filename="answer.txt",
            declared_mime="application/pdf",
            data=_PDF_BYTES,
            limits=IntakeLimits(),
        )


def test_intake_limits_rejects_non_positive_values() -> None:
    with pytest.raises(ValueError, match="max_size_bytes"):
        IntakeLimits(max_size_bytes=0)
    with pytest.raises(ValueError, match="max_pages"):
        IntakeLimits(max_pages=0)
    with pytest.raises(ValueError, match="max_render_dimension_px"):
        IntakeLimits(max_render_dimension_px=0)
    with pytest.raises(ValueError, match="max_render_pixels"):
        IntakeLimits(max_render_pixels=0)


def test_validate_render_dimensions_accepts_a_normal_page() -> None:
    # A4 at the intake pipeline's render scale (2.0): ~1190x1684px.
    validate_render_dimensions(1190, 1684, IntakeLimits())


def test_validate_render_dimensions_rejects_non_positive_size() -> None:
    with pytest.raises(PdfPageTooLargeError):
        validate_render_dimensions(0, 100, IntakeLimits())
    with pytest.raises(PdfPageTooLargeError):
        validate_render_dimensions(100, -1, IntakeLimits())


def test_validate_render_dimensions_rejects_an_oversize_single_dimension() -> None:
    limits = IntakeLimits(max_render_dimension_px=1000, max_render_pixels=10_000_000)
    with pytest.raises(PdfPageTooLargeError):
        validate_render_dimensions(2000, 100, limits)


def test_validate_render_dimensions_rejects_an_oversize_area() -> None:
    # Neither side alone exceeds a generous per-side cap, but the area does.
    limits = IntakeLimits(max_render_dimension_px=20_000, max_render_pixels=1_000_000)
    with pytest.raises(PdfPageTooLargeError):
        validate_render_dimensions(5000, 5000, limits)
