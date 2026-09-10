# PoC 6 Approach B round-trip (generated)

Engine: **pypdfium2** bitmap (same as `PdfiumPypdfEngine.render_page_png`).

- fixtures: 9
- points per fixture: 5
- total measurements: 45 (= 9 × 5)
- render scale: 2.0
- tolerance: 0.004 normalized
- worst error: 0.0005 -> **PASS**

## Performance (synthetic A4 portrait, median of 5 runs)

| scale | render ms (1 page) |
| ----- | ------------------ |
| 1.0   | 5.1                |
| 2.0   | 20.8               |
| 3.5   | 78.6               |

## 40-page transfer (scale 2.0 PNG, sequential render)

- total PNG bytes: 382,360 (0.36 MiB)
- wall time (render only): 877 ms
- per page: 9,559 bytes PNG

Cache: at scale 2.0 each page is ~9 KiB PNG; 40 pages ≈ 0.36 MiB. Zoom changes invalidate scale — cache key must include `(document_id, page_index, scale)`. Without cache, every zoom step re-fetches all visible pages from the sidecar.

| fixture                    | normalized (x,y) | measured (x,y)   | abs error |
| -------------------------- | ---------------- | ---------------- | --------- |
| a4-portrait                | (0.12, 0.15)     | (0.1202, 0.1502) | 0.0002    |
| a4-portrait                | (0.50, 0.50)     | (0.5000, 0.5000) | 0.0000    |
| a4-portrait                | (0.90, 0.25)     | (0.9000, 0.2500) | 0.0000    |
| a4-portrait                | (0.25, 0.88)     | (0.2496, 0.8800) | 0.0004    |
| a4-portrait                | (0.82, 0.80)     | (0.8202, 0.7999) | 0.0002    |
| a4-rotate-90               | (0.12, 0.15)     | (0.1200, 0.1496) | 0.0004    |
| a4-rotate-90               | (0.50, 0.50)     | (0.5000, 0.5000) | 0.0000    |
| a4-rotate-90               | (0.90, 0.25)     | (0.9002, 0.2496) | 0.0004    |
| a4-rotate-90               | (0.25, 0.88)     | (0.2500, 0.8798) | 0.0002    |
| a4-rotate-90               | (0.82, 0.80)     | (0.8201, 0.8000) | 0.0001    |
| a4-rotate-180              | (0.12, 0.15)     | (0.1202, 0.1502) | 0.0002    |
| a4-rotate-180              | (0.50, 0.50)     | (0.5000, 0.5000) | 0.0000    |
| a4-rotate-180              | (0.90, 0.25)     | (0.9000, 0.2500) | 0.0000    |
| a4-rotate-180              | (0.25, 0.88)     | (0.2496, 0.8800) | 0.0004    |
| a4-rotate-180              | (0.82, 0.80)     | (0.8202, 0.7999) | 0.0002    |
| a4-rotate-270              | (0.12, 0.15)     | (0.1200, 0.1496) | 0.0004    |
| a4-rotate-270              | (0.50, 0.50)     | (0.5000, 0.5000) | 0.0000    |
| a4-rotate-270              | (0.90, 0.25)     | (0.9002, 0.2496) | 0.0004    |
| a4-rotate-270              | (0.25, 0.88)     | (0.2500, 0.8798) | 0.0002    |
| a4-rotate-270              | (0.82, 0.80)     | (0.8201, 0.8000) | 0.0001    |
| a4-landscape               | (0.12, 0.15)     | (0.1200, 0.1496) | 0.0004    |
| a4-landscape               | (0.50, 0.50)     | (0.5000, 0.5000) | 0.0000    |
| a4-landscape               | (0.90, 0.25)     | (0.9002, 0.2496) | 0.0004    |
| a4-landscape               | (0.25, 0.88)     | (0.2500, 0.8798) | 0.0002    |
| a4-landscape               | (0.82, 0.80)     | (0.8201, 0.8000) | 0.0001    |
| letter-portrait            | (0.12, 0.15)     | (0.1201, 0.1503) | 0.0003    |
| letter-portrait            | (0.50, 0.50)     | (0.5000, 0.5000) | 0.0000    |
| letter-portrait            | (0.90, 0.25)     | (0.9003, 0.2500) | 0.0003    |
| letter-portrait            | (0.25, 0.88)     | (0.2500, 0.8801) | 0.0001    |
| letter-portrait            | (0.82, 0.80)     | (0.8203, 0.7999) | 0.0003    |
| a4-mediabox-offset         | (0.12, 0.15)     | (0.1202, 0.1502) | 0.0002    |
| a4-mediabox-offset         | (0.50, 0.50)     | (0.5000, 0.5000) | 0.0000    |
| a4-mediabox-offset         | (0.90, 0.25)     | (0.9000, 0.2500) | 0.0000    |
| a4-mediabox-offset         | (0.25, 0.88)     | (0.2496, 0.8800) | 0.0004    |
| a4-mediabox-offset         | (0.82, 0.80)     | (0.8202, 0.7999) | 0.0002    |
| a4-cropbox-inset           | (0.12, 0.15)     | (0.1196, 0.1500) | 0.0004    |
| a4-cropbox-inset           | (0.50, 0.50)     | (0.5000, 0.5000) | 0.0000    |
| a4-cropbox-inset           | (0.90, 0.25)     | (0.9000, 0.2500) | 0.0000    |
| a4-cropbox-inset           | (0.25, 0.88)     | (0.2495, 0.8803) | 0.0005    |
| a4-cropbox-inset           | (0.82, 0.80)     | (0.8196, 0.8000) | 0.0004    |
| a4-cropbox-inset-rotate-90 | (0.12, 0.15)     | (0.1197, 0.1495) | 0.0005    |
| a4-cropbox-inset-rotate-90 | (0.50, 0.50)     | (0.5000, 0.5000) | 0.0000    |
| a4-cropbox-inset-rotate-90 | (0.90, 0.25)     | (0.9000, 0.2495) | 0.0005    |
| a4-cropbox-inset-rotate-90 | (0.25, 0.88)     | (0.2500, 0.8804) | 0.0004    |
| a4-cropbox-inset-rotate-90 | (0.82, 0.80)     | (0.8197, 0.8000) | 0.0003    |
