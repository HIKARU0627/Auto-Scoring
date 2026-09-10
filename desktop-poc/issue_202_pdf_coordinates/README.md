# PoC 6 — Electron PDF display coordinate probe

Supports GitHub issue #202. **Not imported by the app or backend.**

Compares Approach A (pdf.js in renderer) vs Approach B (pypdfium2 bitmap from
sidecar) against the PoC 3 coordinate contract (`docs/poc-3-pdf-coordinates.md`).

## Prerequisites

```bash
cd desktop-poc/issue_202_pdf_coordinates/approach_a
npm install   # probe-only: pdfjs-dist + canvas
```

## Repro

```bash
cd backend
uv run python ../desktop-poc/issue_202_pdf_coordinates/report.py
```

Writes `docs/poc-6-pdf-coordinates.md` and generated tables under
`docs/poc-6-pdf-coordinates/`.

Exit code is non-zero if Approach B exceeds tolerance 0.004 (Approach A failures
are recorded in the report but do not fail the script — the decision doc captures them).
