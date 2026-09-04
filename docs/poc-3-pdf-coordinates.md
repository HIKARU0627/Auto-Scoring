# PoC 3: PDF 座標往復と PDF エンジン検証

GitHub Issue [#12](https://github.com/HIKARU0627/Auto-Scoring/issues/12)（親
[#3](https://github.com/HIKARU0627/Auto-Scoring/issues/3)）。簡易設計書 §30 PoC 3 /
技術スタック調査書 §8 の技術リスク「pdfium（Flutter）↔ PyMuPDF/pypdf（Python）間で
0〜1 正規化座標が往復一致するか」を実 PDF で検証し、MVP の PDF エンジンを選定する。

## 結論（先に）

- **座標往復は一致する。** 縦横・回転（0/90/180/270）・ページサイズ差・非ゼロ原点の
  MediaBox・CropBox イン
  セットを含む全 fixture で、正規化座標の往復誤差は最大 **0.0005**（合意許容誤差
  0.004 の 1/8）。render scale（DPI/zoom）には依存しない。
- **PDF エンジンは pypdfium2 + pypdf を採用**する。PyMuPDF はライセンス判断者の承認
  記録が無いため候補から除外した（[§ ライセンス判断](#ライセンス判断)）。
- 採用した座標変換と `PdfEngine` 契約を MVP コードへ昇格した
  （[§ 昇格したもの](#昇格したもの)）。

## 検証対象の座標契約

- アプリ／テストプロファイルは注釈位置を **正規化座標**（`0..1`、原点は「pdfium が
  表示するページ」の左上、x 右・y 下）で保持する（簡易設計書 §5・§12）。
- `PdfEngine` が注釈を描くには **PDF ユーザー空間**（原点は左下、単位 pt、`/Rotate`
  適用前）が要る。
- 変換は `PageGeometry`（`CropBox` を `MediaBox` でクリップした矩形＋`/Rotate`）で
  パラメータ化する。**render DPI / zoom は式に現れない** — 正規化で割り切れるため。
  これが PoC で確認したい不変性。

変換式（`backend/src/auto_scoring/domain/pdf_geometry.py`）:

1. `displayed = (nx · Wd, ny · Hd)`（`Wd,Hd` は表示寸法。90/270 で crop 寸法を入替）
2. `/Rotate` を打ち消して crop ローカル左上座標へ（回転量ごとの分岐）
3. y を反転し `CropBox` 左下オフセットを足してユーザー空間へ

## repro command

```
# 回帰テスト（許容誤差を assert）
uv run pytest tests/test_pdf_geometry.py tests/test_pdf_engine_roundtrip.py

# 差分レポートとサンプル PDF/PNG を再生成（docs/poc-3-pdf-coordinates/ を上書き）
uv run python poc/issue_12_pdf_coordinates/report.py
```

いずれも `backend/` で実行する。`report.py` は決定的で、再実行するとバイト一致の数値を
再生成する。

## fixture と test point

| fixture                    | MediaBox pt             | /Rotate        | CropBox              |
| -------------------------- | ----------------------- | -------------- | -------------------- |
| a4-portrait                | `[0, 0, 595, 842]`      | 0              | full page            |
| a4-rotate-90 / -180 / -270 | `[0, 0, 595, 842]`      | 90 / 180 / 270 | full page            |
| a4-landscape               | `[0, 0, 842, 595]`      | 0              | full page            |
| letter-portrait            | `[0, 0, 612, 792]`      | 0              | full page            |
| a4-mediabox-offset         | `[100, 200, 695, 1042]` | 0              | full page            |
| a4-cropbox-inset           | `[0, 0, 595, 842]`      | 0              | `[30, 40, 565, 800]` |
| a4-cropbox-inset-rotate-90 | `[0, 0, 595, 842]`      | 90             | `[30, 40, 565, 800]` |

各 fixture に正規化座標 `(0.12,0.15) (0.50,0.50) (0.90,0.25) (0.25,0.88)
(0.82,0.80)` を打つ。四隅の非対称な点で、軸の取り違え・回転漏れ・鏡像化を検出できる。

## 期待値・実測値・許容誤差

- **期待値**: 採用変換 `normalized_to_user_space` が返すユーザー空間 pt。
- **実測値**: その pt に赤い矩形を pypdf で重ね、pdfium（`pdfrx` が包むのと同じエンジ
  ン）で scale 2.0 raster 化し、赤マークの bounding-box 中心を正規化し直した値。
- **許容誤差**: **0.004 正規化単位**（A4 で横約 2.4 pt・縦約 3.4 pt、scale 2.0 の
  raster で横約 4.8 px・縦約 6.7 px）。
  ラスタライズと中心丸めの実誤差は約 5e-4。軸取り違えなら約 0.5 ずれるため、両者の
  間に十分収まる閾値。回帰テスト `_TOLERANCE` と `report.py` で共有。

実測サマリ（全 45 ケース、全 PASS）:

| 観点                                      | 最大絶対誤差（正規化）                                  |
| ----------------------------------------- | ------------------------------------------------------- |
| 回転なし（portrait / landscape / letter） | 0.0004                                                  |
| 回転 90 / 180 / 270                       | 0.0005                                                  |
| 非ゼロ原点の MediaBox                     | 0.0004                                                  |
| CropBox インセット（回転あり・なし）      | 0.0005                                                  |
| render scale 1.0 / 2.0 / 3.5 の相互差     | < 0.004（`test_result_is_independent_of_render_scale`） |

ケース別の全数値は
[`poc-3-pdf-coordinates/coordinate-diff-report.md`](./poc-3-pdf-coordinates/coordinate-diff-report.md)。

## サンプル出力

[`poc-3-pdf-coordinates/samples/`](./poc-3-pdf-coordinates/samples/) に fixture ごと
の `.pdf`（5 点を重ねた出力 PDF）と `.png`（scale 2.0 プレビュー）。回転・CropBox の
fixture でもマークが表示ページ上の指定正規化位置へ乗ることを目視できる。

## ライセンス判断

技術スタック調査書 §3.1 のとおり PyMuPDF は **AGPL-3.0 / Artifex 商用のデュアル
ライセンス**で、非公開配布には商用ライセンス購入が要る。本 PoC 時点で
**ライセンス判断者による採用承認の記録は存在しない**。Issue #12 受入条件「PyMuPDF
採用にはライセンス判断者の明示的な承認記録がある。未承認なら代替構成を選ぶ」に従い、
PyMuPDF は実装・比較の対象から外し、OSS 構成を採用した。

承認が後日記録された場合は、`PdfiumPypdfEngine` と同じ `PdfEngine` 契約を実装する
`PyMuPDFEngine` を追加して差し替えられる（変更は adapter 1 個に閉じる）。その際は本
PoC の fixture で同じ往復誤差を測り直すこと。

## 採否理由

| 構成                     | 判定     | 理由                                                                                                                                                                                                          |
| ------------------------ | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **pypdfium2 + pypdf**    | **採用** | ライセンスが寛容（Apache-2.0 / BSD-3-Clause）で商用契約不要。pypdfium2 は `pdfrx` と同じ pdfium で、表示エンジンの解釈差が原理的に出ない。pypdf で元 PDF 非破壊のオーバーレイ生成ができる。往復誤差は許容内。 |
| PyMuPDF                  | 不採用   | ライセンス承認記録なし（上記）。実装しない。                                                                                                                                                                  |
| pypdf 単体でラスタライズ | 不採用   | ラスタライズ機能を持たない。表示側検証に pdfium 相当が必須。                                                                                                                                                  |

## 昇格したもの

MVP コードへ昇格（Issue #12 昇格条件）:

| パス                                                           | 役割                                                                  |
| -------------------------------------------------------------- | --------------------------------------------------------------------- |
| `backend/src/auto_scoring/domain/pdf_geometry.py`              | 採用した座標変換（純 Python・ライブラリ非依存。domain 層に置ける）    |
| `backend/src/auto_scoring/domain/pdf_engine.py`                | `PdfEngine` 契約（Protocol）。PoC が触れた read / render / stamp のみ |
| `backend/src/auto_scoring/adapters/pdf/pdfium_pypdf_engine.py` | 採用構成の実装                                                        |
| `backend/tests/test_pdf_geometry.py`                           | 変換の回帰テスト（純関数・高速）                                      |
| `backend/tests/test_pdf_engine_roundtrip.py`                   | 往復一致・scale 非依存の回帰テスト（repro command 兼用）              |

PoC 固有で残すもの（回帰テストに不要な比較コードは書いていない）:

| パス                                             | 扱い                                                                                                        |
| ------------------------------------------------ | ----------------------------------------------------------------------------------------------------------- |
| `backend/poc/issue_12_pdf_coordinates/report.py` | 差分レポート／サンプル再生成スクリプト。Issue #12「検証」の再現に必要なため保持。MVP コードからは参照しない |
| `docs/poc-3-pdf-coordinates/`                    | 生成物（差分レポート＋サンプル）。証跡として保持                                                            |

## スコープ外（残存リスク）

- **`pdfrx` ウィジェットオーバーレイ**の配置（パン／ズームジェスチャ、ヒットテスト）は
  UI レイヤの課題で本 PoC の対象外。`pdfrx` はオーバーレイを pdfium のページ寸法・
  左上原点で配置するため、本 PoC が検証した raster 座標と同一基準になる。
- 採用adapterが実行時に使う `pypdf` / `pypdfium2` は `backend` の project 依存、証跡生成
  だけに使う `pillow` は dev 依存に分離した。
- 本 fixture は合成 PDF。実答案 PDF 特有の構造（注釈レイヤ、UserUnit）は PoC 4／実装時に
  確認する。
