# PoC 3 — PDF coordinate round-trip harness

Supports GitHub issue #12. Not imported by the app.

`report.py` regenerates the coordinate-diff report and the sample PDFs / PNGs
under `docs/poc-3-pdf-coordinates/`. Run it from `backend/`:

```
uv run python poc/issue_12_pdf_coordinates/report.py
```

It builds a fixture PDF per orientation / rotation / page size / CropBox, stamps a
mark at known normalized points using the **adopted** transform
(`auto_scoring.domain.pdf_geometry` via
`auto_scoring.adapters.pdf.PdfiumPypdfEngine`), rasterizes with pdfium, reads each
mark back, and tabulates expected vs measured. Exit code is non-zero if any point
lands outside the tolerance that `backend/tests/test_pdf_engine_roundtrip.py`
asserts.

The pass/fail check itself lives in that test — this script only produces the
human-inspectable evidence. See `docs/poc-3-pdf-coordinates.md` for the decision
record.
