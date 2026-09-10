# PoC 6: Electron UI の PDF 表示と正規化座標

GitHub Issue [#202](https://github.com/HIKARU0627/Auto-Scoring/issues/202)（親
[#201](https://github.com/HIKARU0627/Auto-Scoring/issues/201)）。移行後 UI が
「pdfium が表示するページ」と同じ絵の上で `0..1` 正規化座標を作れるかを、案 A
（renderer で pdf.js）と案 B（サイドカーが pypdfium2 でページ PNG を返す）で
**実測**して選ぶ。

座標契約の正本: [`poc-3-pdf-coordinates.md`](./poc-3-pdf-coordinates.md) /
`backend/src/auto_scoring/domain/pdf_geometry.py`（**本 PoC では変更しない**）。

## 結論（先に）

- **案 B（pypdfium2 ビットマップ）を採用**。案 A も 9 fixture × 5 点 = 45 測点すべて
  PASS（worst 0.0002、viewport Δ 0 pt）だが、案 B は座標契約と同一 pdfium エンジンが
  「表示するページ」を定義するため二重解釈リスクがない。40 ページ転送 ≈ 0.36 MiB、
  scale 2.0 再描画中央値 21 ms/ページも許容範囲。
- 往復許容誤差 **0.004**（PoC 3 と同じ）。分母: **9 fixtures ×
  5 点 = 45 測点**。
- 案 A worst 往復誤差: **0.0002**
  （viewport 最大 Δ: 0.0000 pt）。
- 案 B worst 往復誤差: **0.0005**（pdfium、PoC 3 再確認）。

## repro command

```bash
# 1. probe-only npm deps（pdf.js — プロダクト root には入れない）
cd desktop-poc/issue_202_pdf_coordinates/approach_a && npm install

# 2. 測定 + レポート生成（backend の uv 環境で pypdfium2 / pypdf を使う）
cd ../../../backend
uv run python ../desktop-poc/issue_202_pdf_coordinates/report.py
```

生成物:

- [`poc-6-pdf-coordinates/approach-a-round-trip.md`](./poc-6-pdf-coordinates/approach-a-round-trip.md)
- [`poc-6-pdf-coordinates/approach-b-round-trip.md`](./poc-6-pdf-coordinates/approach-b-round-trip.md)

## 期待値

- **表示領域**: pdf.js / pypdfium2 いずれも `PageGeometry.displayed_width` /
  `displayed_height`（CropBox∩MediaBox、`/Rotate` 適用後）と一致すること。
- **往復**: 既知正規化点 → `pdf_geometry` → ユーザー空間スタンプ → 表示エンジンで
  raster 化 → 赤マーク中心を正規化し直し、元点との差 ≤ **0.004**。
- fixture: PoC 3 と同じ 9 種（縦/横、Rotate 0/90/180/270、letter、非ゼロ MediaBox、
  CropBox インセット）。

## 実測値

| 案  | 表示エンジン         | 測点数 | worst 往復誤差 | viewport Δ (pt) | 判定 |
| --- | -------------------- | ------ | -------------- | --------------- | ---- |
| A   | pdf.js 5.7.284 (npm) | 45     | 0.0002         | 0.0000          | PASS |
| B   | pypdfium2 PNG        | 45     | 0.0005         | 0（定義上同一） | PASS |

### 案 B 追加項目（数値）

| 項目                              | 値                                                                                   |
| --------------------------------- | ------------------------------------------------------------------------------------ |
| scale 1.0 再描画（中央値）        | 5.1 ms / ページ                                                                      |
| scale 2.0 再描画（中央値）        | 20.8 ms / ページ                                                                     |
| scale 3.5 再描画（中央値）        | 78.6 ms / ページ                                                                     |
| 40 ページ PNG 転送量（scale 2.0） | 382,360 bytes (0.36 MiB)                                                             |
| 40 ページレンダ wall time         | 877 ms                                                                               |
| キャッシュ                        | `(doc, page, scale)` キー必須。ズーム毎に全ページ再取得すると 40 ページで約 0.36 MiB |

### 案 A 追加項目

- pdf.js 取得: `desktop-poc/.../approach_a/package.json` の `pdfjs-dist` + `@napi-rs/canvas`
  （npm、probe-only）。Node 上では `canvas`（node-canvas）ではなく `@napi-rs/canvas` が必須
  （pdf.js 5.x の NodeCanvasFactory 要件）。
- **全 fixture PASS** — CropBox / 非ゼロ MediaBox / `/Rotate` で viewport 不一致は検出されず。
- 詳細:
  [`approach-a-round-trip.md`](./poc-6-pdf-coordinates/approach-a-round-trip.md)

## 決定

**案 B（pypdfium2 ビットマップ）を採用**。

案 A も合成 fixture 45 測点すべて許容内（往復 worst 0.0002、viewport 完全一致）だが、
採用理由は実測による座標精度ではなく **エンジン単一化**: サイドカーの
`PdfiumPypdfEngine` が座標変換（`page_geometry`）と raster 化の双方で pdfium を使うため、
将来の pdf.js アップデートや Electron renderer 差分で契約がずれる余地を残さない。
性能面（40 ページ ≈ 0.36 MiB、scale 2.0 で 21 ms/ページ）
も許容可能。pdf.js を product root に足す必要もない。

案 B で描画 API（`GET /pages/{n}/render` 等）が要る場合、**本 Issue では実装しない**。
必要な API 形状は Phase 2 の `desktop/` 土台 Issue で起票する。

## 撤去または昇格の条件

| パス                                     | 扱い                                                                                   |
| ---------------------------------------- | -------------------------------------------------------------------------------------- |
| `desktop-poc/issue_202_pdf_coordinates/` | PoC 完了後も repro 用に保持。プロダクトから import しない                              |
| `docs/poc-6-pdf-coordinates/`            | 証跡として保持                                                                         |
| `docs/poc-6-pdf-coordinates.md`          | Electron PDF 表示方式の決定記録として昇格（`docs/frontend-migration.md` Phase 1 参照） |
| 案 B 採用時の sidecar render API         | 別 Issue（Phase 2 土台）で昇格                                                         |

## スコープ外

- Electron / React UI の実装（Phase 2 以降）
- `pdf_geometry.py` の変更
- 実答案 PDF（合成 fixture のみ）
