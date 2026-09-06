"""Adapter tests for the PdfEngine.page_count / is_encrypted additions (Issue #17)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pypdf import PdfWriter
from pypdf.errors import PdfReadError

from auto_scoring.adapters.pdf import PdfiumPypdfEngine


def _write_pdf(path: Path, *, pages: int = 1) -> None:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=300)
    with path.open("wb") as handle:
        writer.write(handle)


def test_page_count_reads_a_multi_page_pdf(tmp_path: Path) -> None:
    path = tmp_path / "doc.pdf"
    _write_pdf(path, pages=3)
    assert PdfiumPypdfEngine().page_count(path) == 3


def test_is_encrypted_is_false_for_a_plain_pdf(tmp_path: Path) -> None:
    path = tmp_path / "doc.pdf"
    _write_pdf(path)
    assert PdfiumPypdfEngine().is_encrypted(path) is False


def test_is_encrypted_is_true_for_a_password_protected_pdf(tmp_path: Path) -> None:
    path = tmp_path / "doc.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=300)
    writer.encrypt(user_password="secret")
    with path.open("wb") as handle:
        writer.write(handle)

    assert PdfiumPypdfEngine().is_encrypted(path) is True


def test_page_count_raises_on_corrupted_pdf(tmp_path: Path) -> None:
    path = tmp_path / "corrupt.pdf"
    path.write_bytes(b"%PDF-1.7\nnot really a pdf body")
    with pytest.raises(PdfReadError):
        PdfiumPypdfEngine().page_count(path)
