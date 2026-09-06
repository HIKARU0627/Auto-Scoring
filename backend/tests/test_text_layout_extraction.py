"""`adapters.pdf.text_layout_extraction.extract_text_lines` against a real PDF.

Builds a minimal single-page PDF with a handful of text lines placed at known
positions (the same "write a tiny PDF by hand" approach
`adapters.pdf.pdfium_pypdf_engine._overlay_pdf` uses), and checks that each
line's text and approximate position are recovered.
"""

from __future__ import annotations

from pathlib import Path

from auto_scoring.adapters.pdf.text_layout_extraction import _utf16_length, extract_text_lines

_WIDTH, _HEIGHT = 595.0, 842.0


def _text_pdf(lines: list[tuple[str, float, float]]) -> bytes:
    """A one-page PDF with each ``(text, x, y)`` drawn via ``Tj`` at that
    PDF-user-space point (bottom-left origin, Helvetica 12pt).
    """
    ops = []
    for text, x, y in lines:
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        ops.append(f"BT /F1 12 Tf {x:.2f} {y:.2f} Td ({escaped}) Tj ET")
    content = "\n".join(ops).encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {_WIDTH:.4f} {_HEIGHT:.4f}] "
            "/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>"
        ).encode("latin-1"),
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
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


def test_extracts_each_line_with_its_text_and_position(tmp_path: Path) -> None:
    path = tmp_path / "lines.pdf"
    path.write_bytes(
        _text_pdf(
            [
                ("Q1 Prompt text", 72.0, 750.0),
                ("Student answer line one", 72.0, 700.0),
            ]
        )
    )

    lines = extract_text_lines(path, 0)

    texts = [line.text for line in lines]
    assert texts == ["Q1 Prompt text", "Student answer line one"]
    # Each line's rectangle should sit near the y where it was drawn (within
    # a font-size-ish margin) and have a positive width covering its text.
    for line, (_, x, y) in zip(
        lines,
        [("", 72.0, 750.0), ("", 72.0, 700.0)],
        strict=True,
    ):
        left, bottom, right, top = line.rect_pt
        assert right > left
        assert top > bottom
        assert bottom <= y <= top + 14  # baseline sits at/below y, ascent above it
        assert abs(left - x) < 5.0


def test_blank_page_has_no_lines(tmp_path: Path) -> None:
    path = tmp_path / "blank.pdf"
    path.write_bytes(_text_pdf([]))

    assert extract_text_lines(path, 0) == []


def test_utf16_length_counts_surrogate_pairs_for_non_bmp_characters() -> None:
    """A non-BMP character (an emoji, or a rare CJK ideograph) is one
    Python `str` element but a UTF-16 *surrogate pair* -- two code units,
    which is what PDFium's own text-index APIs
    (`FPDFText_GetCharIndexFromTextIndex`) count in. Accumulating plain
    `len()` instead would drift `text_index` out of sync with PDFium's own
    indexing the moment one such character appears, misassigning every
    following line's rectangle (Issue #16 review round 8).
    """
    assert _utf16_length("ab") == len("ab") == 2
    non_bmp = "\U0001f600"  # an emoji outside the Basic Multilingual Plane
    assert len(non_bmp) == 1
    assert _utf16_length(non_bmp) == 2
    assert _utf16_length(f"a{non_bmp}b") == 4
