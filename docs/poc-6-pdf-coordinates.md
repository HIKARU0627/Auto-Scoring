# PoC 6: Electron UI の PDF 表示と正規化座標

GitHub Issue [#202](https://github.com/HIKARU0627/Auto-Scoring/issues/202)（親
[#201](https://github.com/HIKARU0627/Auto-Scoring/issues/201)）。移行後 UI が
「pdfium が表示するページ」と同じ絵の上で `0..1` 正規化座標を作れるかを、案 A
（renderer で pdf.js）と案 B（サイドカーが pypdfium2 でページ PNG を返す）で
**実測**して選ぶ。

座標契約の正本: [`poc-3-pdf-coordinates.md`](./poc-3-pdf-coordinates.md) /
`backend/src/auto_scoring/domain/pdf_geometry.py`（**本 PoC では変更しない**）。

## 結論（先に）

- **案 B（pypdfium2 ビットマップ）を採用**。理由は実測精度の差ではない —
  worst 往復誤差 0.0002（案 A）と 0.0005（案 B）はどちらも許容誤差 0.004 の
  1/8 以下で、45 測点は案 A と案 B を精度で分離していない。採用理由は
  [§ 決定](#決定) の対比（観測されなかった／構造的に起こりえない）による。
  40 ページ転送 ≈ 0.36 MiB、scale 2.0 再描画中央値 21 ms/ページも許容範囲。
- 往復許容誤差 **0.004**（PoC 3 と同じ）。分母: **9 fixtures ×
  5 点 = 45 測点**。
- 案 A worst 往復誤差: **0.0002**（viewport 最大 Δ: 0.0000 pt）。
  **案 A も全 45 測点 PASS。**
- 案 B worst 往復誤差: **0.0005**（pdfium、PoC 3 再確認）。
- **残存リスク**: 実答案 PDF は実機検証 Issue #6 で幾何・画像寸法・座標往復を検証済み（着手制限解除）。未測定項目などの詳細は [§ 残存リスク](#残存リスク)。

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

案 A も合成 fixture 45 測点すべて許容内（往復 worst 0.0002、viewport 完全一致）であり、
実測は案 A と案 B を精度で分離していない。worst 往復誤差 0.0002 と 0.0005 の差は
雑音であって信号ではない — 実測が示したのは「案 A が座標契約を壊すという懸念の
否定」であって、案 B の優位ではない。

採用理由は次の対比にある。案 A は「9 つの合成 fixture では食い違いが観測されなかった」。
案 B は「食い違いが構造的に起こりえない」。同じ pdfium が raster 化と座標変換の
両方を担うので、pdf.js の更新でも renderer の差分でも契約はずれない。サイドカーの
`PdfiumPypdfEngine` が座標変換（`page_geometry`）と raster 化の双方で pdfium を使う
ため、将来の pdf.js アップデートや Electron renderer 差分で契約がずれる余地を残さ
ない。性能面（40 ページ ≈ 0.36 MiB、scale 2.0 で 21 ms/ページ）も許容可能。pdf.js を
product root に足す必要もない。

案 B で描画 API（`GET /pages/{n}/render` 等）が要る場合、**本 Issue では実装しない**。
OpenAPI の変更は最高責任者の承認事項であり、必要な API 形状は別 Issue で起票する。

**起票と実装は済んでいる**: Issue #207 が形を承認され、`api.page_image_router` として
実装された（`GET /submissions/{id}/pages{,/{n}/image}` と
`GET /tests/{id}/answer-layout/pages{,/{n}/image}`）。renderer が守る規則
（正規化座標は画像の画素寸法だけから作る）は [`sidecar-api.md`](./sidecar-api.md) §7。

## 残存リスク

### 実機検証（Issue #6）の測定結果と着手制限の解除

最高責任者による実機検証 Issue #6 が完了し、実答案 PDF を用いた測定により幾何前提の成立および画像寸法の一致が確認された。これにより、**回答欄エディタおよび採点レビューのオーバーレイを含め、着手制限は解除された**（「着手しない」という制限は終了）。

実答案データの幾何集計値（リポジトリ外の実データから集計）:

| 項目                                                 | 検査数 / 測点数 | 許容超過 / 失敗   | worst 誤差   | 備考                                                            |
| ---------------------------------------------------- | --------------- | ----------------- | ------------ | --------------------------------------------------------------- |
| **座標往復**（正規化 → ユーザ空間 → 正規化）         | **284 測点**    | **0**             | **1.11e-16** | 許容 0.004。うち実際の回答欄由来が 115 測点                     |
| **画像寸法一致**（画素寸法 ＝ 表示ページ）           | **39 件**       | **0**             | **0.96 px**  | 13 ページ × スケール 3 種（1.0 / 2.0 / 1.3333）                 |
| **幾何前提**（非ゼロ MediaBox / CropBox インセット） | 13 ページ       | 対象なし（0 / 0） | -            | 教科 11 / 13 ページ（回転あり 4 ページ: 270 度 × 3、90 度 × 1） |

- **分母の区別**: 口頭で流通した要約に「39/39 測点」という表現があったが、**39 は画像寸法の検査数**（13 ページ × 3 スケール）であり、**座標往復の測点は 284**（回答欄由来 115 測点を含む）である。どちらも全数パス（許容内）しているが、検査対象が異なるため混同せず区別して記録する。
- **案 B 採用理由との関係**: Issue #6 が確かめたのは「実答案の幾何が仮定どおりであること」および「画像の画素寸法が表示ページと一致すること」であり、**案 B の優位を実証したわけではない**。案 B の採用理由はあくまで [§ 決定](#決定) にあるとおり「案 A は 9 つの合成 fixture で食い違いが観測されなかったのに対し、案 B は同一エンジン起用により食い違いが構造的に起こりえない」という対比に基づく。

### 未測定として残る項目

実データ側（幾何記録）に該当フィールドが存在しないことが確認されており、以下の 3 点は依然として未測定である。

1. **UserUnit**: 実データに記録が存在しないため未測定（PoC 6 が名指しした残存リスクの 1 つ）。
2. **注釈レイヤ（Annots）**: スキャン由来等の注釈レイヤの記録が存在しないため未測定（同上）。
3. **インクレベルの往復**: Issue #6 の往復誤差 1.11e-16 は「正規化 → ユーザ空間 → 正規化」という**計算上の変換往復**を測った値である。PoC 6 の実測（worst 0.0002〜0.0005）のように「スタンプ描画 → raster 化 → 赤マーク中心を画像検出 → 正規化し直す」という検出段を含むインクレベルの往復突き合わせは、実データに対しては実施していない。

## 撤去または昇格の条件

| パス                                     | 扱い                                                                                    |
| ---------------------------------------- | --------------------------------------------------------------------------------------- |
| `desktop-poc/issue_202_pdf_coordinates/` | PoC 完了後も repro 用に保持。プロダクトから import しない                               |
| `docs/poc-6-pdf-coordinates/`            | 証跡として保持                                                                          |
| `docs/poc-6-pdf-coordinates.md`          | Electron PDF 表示方式の決定記録として昇格（`docs/frontend-migration.md` Phase 1 参照）  |
| 案 B 採用時の sidecar render API         | **昇格済み** —— Issue #207 で `api.page_image_router` として実装（`sidecar-api.md` §7） |

## スコープ外

- Electron / React UI の実装（Phase 2 以降）
- `pdf_geometry.py` の変更
- 実答案 PDF（合成 fixture のみ）
