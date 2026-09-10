# PoC 6 Approach A round-trip (generated)

Engine: **pdf.js** `5.7.284` via npm (`desktop-poc/.../approach_a/package.json`).
Acquisition: probe-only npm install — **not** added to product root `package.json`.

- fixtures: 9
- points per fixture: 5
- total round-trip measurements: 45
- render scale: 2.0
- tolerance: 0.004 normalized

## Viewport vs pdfium contract (`PageGeometry.displayed_*`)

pdf.js viewport at scale 1.0 must match the displayed page size pdfium uses.

- worst width/height delta: **0.0000 pt** -> **PASS**

| fixture                    | expected W×H pt | pdf.js W×H pt | ΔW     | ΔH     |
| -------------------------- | --------------- | ------------- | ------ | ------ |
| a4-portrait                | 595.0×842.0     | 595.0×842.0   | 0.0000 | 0.0000 |
| a4-rotate-90               | 842.0×595.0     | 842.0×595.0   | 0.0000 | 0.0000 |
| a4-rotate-180              | 595.0×842.0     | 595.0×842.0   | 0.0000 | 0.0000 |
| a4-rotate-270              | 842.0×595.0     | 842.0×595.0   | 0.0000 | 0.0000 |
| a4-landscape               | 842.0×595.0     | 842.0×595.0   | 0.0000 | 0.0000 |
| letter-portrait            | 612.0×792.0     | 612.0×792.0   | 0.0000 | 0.0000 |
| a4-mediabox-offset         | 595.0×842.0     | 595.0×842.0   | 0.0000 | 0.0000 |
| a4-cropbox-inset           | 535.0×760.0     | 535.0×760.0   | 0.0000 | 0.0000 |
| a4-cropbox-inset-rotate-90 | 760.0×535.0     | 760.0×535.0   | 0.0000 | 0.0000 |

## Round-trip (stamp with adopted transform, rasterize with pdf.js, read mark)

- worst error: **0.0002** -> **PASS**

| fixture                    | normalized (x,y) | measured (x,y)   | abs error |
| -------------------------- | ---------------- | ---------------- | --------- |
| a4-portrait                | (0.12, 0.15)     | (0.1202, 0.1499) | 0.0002    |
| a4-portrait                | (0.50, 0.50)     | (0.5000, 0.5000) | 0.0000    |
| a4-portrait                | (0.90, 0.25)     | (0.9000, 0.2500) | 0.0000    |
| a4-portrait                | (0.25, 0.88)     | (0.2500, 0.8800) | 0.0000    |
| a4-portrait                | (0.82, 0.80)     | (0.8202, 0.7999) | 0.0002    |
| a4-rotate-90               | (0.12, 0.15)     | (0.1200, 0.1500) | 0.0000    |
| a4-rotate-90               | (0.50, 0.50)     | (0.5000, 0.5000) | 0.0000    |
| a4-rotate-90               | (0.90, 0.25)     | (0.8999, 0.2500) | 0.0001    |
| a4-rotate-90               | (0.25, 0.88)     | (0.2500, 0.8798) | 0.0002    |
| a4-rotate-90               | (0.82, 0.80)     | (0.8201, 0.8000) | 0.0001    |
| a4-rotate-180              | (0.12, 0.15)     | (0.1202, 0.1499) | 0.0002    |
| a4-rotate-180              | (0.50, 0.50)     | (0.5000, 0.5000) | 0.0000    |
| a4-rotate-180              | (0.90, 0.25)     | (0.9000, 0.2500) | 0.0000    |
| a4-rotate-180              | (0.25, 0.88)     | (0.2500, 0.8800) | 0.0000    |
| a4-rotate-180              | (0.82, 0.80)     | (0.8202, 0.7999) | 0.0002    |
| a4-rotate-270              | (0.12, 0.15)     | (0.1200, 0.1500) | 0.0000    |
| a4-rotate-270              | (0.50, 0.50)     | (0.5000, 0.5000) | 0.0000    |
| a4-rotate-270              | (0.90, 0.25)     | (0.8999, 0.2500) | 0.0001    |
| a4-rotate-270              | (0.25, 0.88)     | (0.2500, 0.8798) | 0.0002    |
| a4-rotate-270              | (0.82, 0.80)     | (0.8201, 0.8000) | 0.0001    |
| a4-landscape               | (0.12, 0.15)     | (0.1200, 0.1500) | 0.0000    |
| a4-landscape               | (0.50, 0.50)     | (0.5000, 0.5000) | 0.0000    |
| a4-landscape               | (0.90, 0.25)     | (0.8999, 0.2500) | 0.0001    |
| a4-landscape               | (0.25, 0.88)     | (0.2500, 0.8798) | 0.0002    |
| a4-landscape               | (0.82, 0.80)     | (0.8201, 0.8000) | 0.0001    |
| letter-portrait            | (0.12, 0.15)     | (0.1201, 0.1499) | 0.0001    |
| letter-portrait            | (0.50, 0.50)     | (0.5000, 0.5000) | 0.0000    |
| letter-portrait            | (0.90, 0.25)     | (0.8999, 0.2500) | 0.0001    |
| letter-portrait            | (0.25, 0.88)     | (0.2500, 0.8801) | 0.0001    |
| letter-portrait            | (0.82, 0.80)     | (0.8199, 0.7999) | 0.0001    |
| a4-mediabox-offset         | (0.12, 0.15)     | (0.1202, 0.1499) | 0.0002    |
| a4-mediabox-offset         | (0.50, 0.50)     | (0.5000, 0.5000) | 0.0000    |
| a4-mediabox-offset         | (0.90, 0.25)     | (0.9000, 0.2500) | 0.0000    |
| a4-mediabox-offset         | (0.25, 0.88)     | (0.2500, 0.8800) | 0.0000    |
| a4-mediabox-offset         | (0.82, 0.80)     | (0.8202, 0.7999) | 0.0002    |
| a4-cropbox-inset           | (0.12, 0.15)     | (0.1201, 0.1500) | 0.0001    |
| a4-cropbox-inset           | (0.50, 0.50)     | (0.5000, 0.5000) | 0.0000    |
| a4-cropbox-inset           | (0.90, 0.25)     | (0.9000, 0.2500) | 0.0000    |
| a4-cropbox-inset           | (0.25, 0.88)     | (0.2500, 0.8799) | 0.0001    |
| a4-cropbox-inset           | (0.82, 0.80)     | (0.8201, 0.8000) | 0.0001    |
| a4-cropbox-inset-rotate-90 | (0.12, 0.15)     | (0.1201, 0.1500) | 0.0001    |
| a4-cropbox-inset-rotate-90 | (0.50, 0.50)     | (0.5000, 0.5000) | 0.0000    |
| a4-cropbox-inset-rotate-90 | (0.90, 0.25)     | (0.9000, 0.2500) | 0.0000    |
| a4-cropbox-inset-rotate-90 | (0.25, 0.88)     | (0.2500, 0.8799) | 0.0001    |
| a4-cropbox-inset-rotate-90 | (0.82, 0.80)     | (0.8201, 0.8000) | 0.0001    |
