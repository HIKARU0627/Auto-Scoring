# PoC 4: 複数テスト形式のプロファイル生成と再適用

GitHub Issue [#15](https://github.com/HIKARU0627/Auto-Scoring/issues/15)（親
[#3](https://github.com/HIKARU0627/Auto-Scoring/issues/3)）。異なるPDF形式でも
「プロファイル生成 → 人間修正 → 答案への再適用」で設問と回答欄を安定して扱えるか
を検証する。

依存: [#12 PoC 3](https://github.com/HIKARU0627/Auto-Scoring/issues/12)（PDF座標
往復とPDFエンジン）。PR [#31](https://github.com/HIKARU0627/Auto-Scoring/pull/31)
は本PoC時点で未マージのため、`pdf_geometry.py` の CropBox/`/Rotate` 対応の座標変換
は直接依存しない。本PoCの fixture は回転もCropBoxインセットも使わないため、正規化
（左上原点・0〜1・DPI/zoom非依存）↔ PDFユーザー空間の変換はページ幅高さのみを使う
最小実装（`domain/profile_detection.py::_rect_to_bbox`）に留めた。PR #31 がマージさ
れ次第、`pdf_geometry.py` の一般化された変換に置き換える（[§ 昇格したもの／PoC
限定のもの](#昇格したものpoc限定のもの)）。

## 結論（先に）

- **プロファイルの往復再適用は成立する。** ページ数・向き・設問配置・回答欄形状が
  異なる4形式（A/B/C/D、各形式 × 学生答案5部 = 20 fixture）で、保存した正規化座標は
  許容誤差 **0.01**（実測最大 **0.0008**）内で答案へ再適用された
  （`docs/business-rules-and-evaluation-data.md` §6.2 の「4形式 × 各5答案以上」を
  満たす）。
- **候補は必ず未確認（DRAFT）で保存され、人間の確認（`Profile.confirm`）を経ないと
  `reapply_profile` の対象にならない。** `Profile.from_candidates` は渡された
  region の `confirmed` を強制的に `False` にする（不正な入力でも候補が誤って
  確定扱いにならない）。
- **自動検出困難な形式（自由記述の答案用紙、マーカーなし）は検出条件を明示し、
  手動領域指定へのフォールバックで完了できる。** 未知タグの存在
  （`unrecognized_tags`）とQUESTION/ANSWER_AREA候補ゼロが検出条件。人間が直接
  `Region` を作成して確認すれば、以降の再適用は自動検出に依存しない。
- 採用したプロファイルschema・検出境界・fixtureをMVPコード＋回帰testへ昇格した
  （[§ 昇格したもの／PoC限定のもの](#昇格したものpoc限定のもの)）。

## 検証対象の契約（プロファイルschema）

`backend/src/auto_scoring/domain/profile.py`:

- `RegionKind`: `question` / `answer_area` / `annotation_area` / `score` /
  `rubric` / `model_answer`（簡易設計書・Issue #15 が挙げる6種）。
- `NormalizedBBox`: 正規化座標（原点左上、`0..1`、DPI/zoom非依存）。範囲外・面積0は
  構築時に拒否する。
- `Region`: `region_id` / `kind` / `page_index` / `bbox` / `label` /
  `confirmed`（既定 `False`）。
- `FormatSignature`: ページ数＋各ページの `width_pt`/`height_pt`。
  `matches(other, tolerance_pt)` で「同一テスト形式」を判定する（本PoCの許容誤差は
  `1.0pt`）。
- `Profile`: `status` は `DRAFT` → `CONFIRMED` の一方向。
  - `Profile.from_candidates(...)`: 自動検出の出力を保存する唯一の入口。
    渡された region の `confirmed` を無条件で `False` に上書きする。
  - `Profile.confirm(reviewed_regions)`: 人間の確認結果を受け取る。1件でも
    `confirmed=False` の region があれば `ValueError`。

`backend/src/auto_scoring/domain/profile_apply.py`:

- `reapply_profile(profile, target_format_id, target_signature, tolerance_pt)`
  - `profile.status != CONFIRMED` → `ProfileNotConfirmedError`
  - `signature` 不一致（ページ数 or サイズが `tolerance_pt` 超） →
    `FormatMismatchError`
  - 一致すれば `AppliedProfile`（regionをそのまま束縛）を返す。

## 検出境界（この PoC がテキスト/画像検出そのものを扱わない理由）

Issue #15 の技術プローブは「模範解答PDFと採点マニュアルPDFから候補を生成する」こと
だが、実際のOCR/レイアウト解析は別スコープ（Issue #13 PoC OCR、または後続MVP
Issue）である。本PoCはその境界を `Marker`（`domain/profile_detection.py`）として
明示的に切り出した:

```python
class Marker:
    page_index: int
    tag: str          # 上流の抽出層が付けたタグ
    rect_pt: RectPt    # PDFユーザー空間の矩形
```

`generate_candidates` はタグを正規表現で `RegionKind` に分類する
（`Q\d+` → question、`ANSWER(_\d+)?` → answer_area 等）。本PoCの
`adapters/pdf/annotation_markers.py` は、PDFの Square 注釈の `/Contents`（タグ）と
`/Rect`（矩形）を `Marker` として読み出す — 実際のテキスト/画像検出エンジンが
供給するはずの入力を、決定的で検証しやすい形で代替している。タグが既知パターンに
一致しない場合、`unrecognized_tags` がそれを返す。

## repro command

```
cd backend
# 回帰テスト（許容誤差を assert）
uv run pytest tests/test_profile.py tests/test_profile_apply.py tests/test_profile_round_trip.py
# 往復レポートとサンプルPDFを再生成
uv run python poc/issue_15_multi_layout_profile/report.py
```

`report.py` は決定的で、再実行すると同じ数値・成果物を再生成する。

## fixture: ページ数・向き・設問配置・回答欄形状の違い

| fixture                                 | ページ数                    | 向き | 設問配置                           | 回答欄形状                                   |
| --------------------------------------- | --------------------------- | ---- | ---------------------------------- | -------------------------------------------- |
| format-a-single-page-stacked            | 1 (A4)                      | 縦   | 2問を縦に積む                      | 各問直下の短い箱                             |
| format-b-two-page-landscape-2col        | 2 (A4横)                    | 横   | 2カラム、ページまたぎ              | 大きな自由記述の箱                           |
| format-c-three-page-mixed-split-answers | 3（A4縦・A4横・B5縦が混在） | 混在 | 1ページ1問の疎な配置               | 小問ごとの分割された複数箱                   |
| format-d-single-page-2x2-grid           | 1 (A4)                      | 縦   | 4問を2×2グリッド配置               | グリッドセルの回答欄＋設問ごとの小さな注釈欄 |
| format-freeform-essay（手動fallback用） | 1 (A4)                      | 縦   | マーカーなし（自由記述の答案用紙） | 未定義（人間が指定）                         |

A/B/C/D の各 model fixture は question / answer_area / annotation_area / score /
rubric / model_answer の6タグすべてを含む（Dは設問ごとに複数の answer_area /
annotation_area を持つ）。学生答案 fixture（各形式5部）は score / rubric /
model_answer を含まない（白紙の答案用紙にそれらは印刷されない）うえ、印刷・スキャン
の位置ずれを模した最大 ±0.4pt のジッターを与えている。

## 期待値・実測値・許容誤差

- **期待値**: 確定済みプロファイルの region を、学生答案の signature が一致すれば
  そのまま再適用できる（`reapply_profile` は region を変更しない）。
- **実測値**: 再適用された region の bbox と、学生答案そのものから独立に再検出した
  region の bbox との最大コーナー差（`NormalizedBBox.max_corner_distance`）。
- **許容誤差**: **0.01 正規化単位**（498〜842ptのページ幅高さに対し ±0.4pt の
  ジッター ≈ 最大0.0008 の理論値の12倍以上の余裕）。軸取り違えなら誤差は約0.5に
  なるため、十分な分離マージンがある。
- 人間による修正（1問目の右端を0.01縮める）は、学生答案側の印刷内容と意図的に
  異なる値になるため、上記の「学生答案との差」比較から除外し、代わりに
  「再適用後も修正値のまま残っているか」を厳密一致で検証する。

実測サマリ（4形式 × 学生答案5部、全 PASS）:

| 観点                                     | 最大絶対誤差（正規化） |
| ---------------------------------------- | ---------------------- |
| 単ページ縦・2問縦積み（format-a）        | 0.0007                 |
| 複数ページ横・2カラム（format-b）        | 0.0007                 |
| 混在ページサイズ・分割回答欄（format-c） | 0.0008                 |
| 単ページ縦・2×2グリッド（format-d）      | 0.0007                 |
| 人間修正の再適用後の保持（全形式共通）   | 0.0000（厳密一致）     |

ケース別の全行は
[`poc-4-multi-layout-profiles/round-trip-report.md`](./poc-4-multi-layout-profiles/round-trip-report.md)。
サンプルPDFは
[`poc-4-multi-layout-profiles/samples/`](./poc-4-multi-layout-profiles/samples/)。

## 自動検出困難な形式と手動fallback

**検出条件**（このいずれかで「自動検出に失敗した」と判定し、登録を止める）:

1. `unrecognized_tags(markers)` が空でない（未知のタグがある）。
2. `generate_candidates(...).regions` に `question` または `answer_area` が
   1件も含まれない。

format-freeform-essay で両方を確認した（`NOTES` タグは未認識、自動候補は0件）。

**手動fallback**: 人間が `Region` を直接作成し（検出結果を経由しない）、
`Profile.from_candidates` → `Profile.confirm` で確定させる。確定後の再適用は
`FormatSignature`（ページ数・サイズ）だけを見るため、対象の答案が
format-freeform-essayのようにマーカーを持たない自由記述用紙であっても、以降ずっと
自動検出に依存せず動作する（`test_hard_to_detect_format_falls_back_to_manual_region`
で検証）。

## 受入条件との対応

| Issue #15 受入条件                                                          | 対応                                                                                                                                                                                                             |
| --------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| repro command・期待結果・実測値・成功/失敗判定・形式別の差が `docs/` にある | 本ファイル＋`poc-4-multi-layout-profiles/round-trip-report.md`                                                                                                                                                   |
| 正規化座標で保存したプロファイルが同一形式の答案へ許容誤差内で再適用される  | `test_profile_round_trip_reapplies_within_tolerance`（4形式・全PASS）                                                                                                                                            |
| 生成候補は必ず未確認状態で保存され、人間確認なしに登録完了にならない        | `Profile.from_candidates` が `confirmed` を強制 `False`、`reapply_profile` は `status != CONFIRMED` を拒否（`test_from_candidates_is_always_draft_and_unconfirmed`、`test_reapply_rejects_unconfirmed_profile`） |
| 自動化困難な形式は検出条件と手動fallbackを具体化する                        | [§ 自動検出困難な形式と手動fallback](#自動検出困難な形式と手動fallback)                                                                                                                                          |
| PoC用UI/コードを削除するか、後続MVP Issueへ昇格する範囲を明記する           | [§ 昇格したもの／PoC限定のもの](#昇格したものpoc限定のもの)                                                                                                                                                      |

## 昇格したもの／PoC限定のもの

昇格（MVPコード＋回帰testとして残す）:

- `domain/profile.py`（`RegionKind` / `NormalizedBBox` / `Region` /
  `FormatSignature` / `ProfileStatus` / `Profile`）
- `domain/profile_detection.py`（`Marker` 契約・タグ分類・候補生成）
- `domain/profile_apply.py`（`reapply_profile` とそのエラー型）
- `adapters/pdf/annotation_markers.py`（`Marker` を供給する現状唯一の実装）
- `tests/test_profile.py` / `test_profile_apply.py` / `test_profile_round_trip.py`

PoC限定（本PoCの検証にのみ必要。次のMVP Issueで置き換え/新規実装、または削除）:

- **`adapters/pdf/annotation_markers.py` は実運用のテキスト/画像検出ではない。**
  実際の模範解答PDF・採点マニュアルPDFからOCR/レイアウト解析でタグ付きspanを
  作る層（Issue #13 PoC OCR、または新規MVP Issue）に置き換える必要がある。
  `Marker` という境界はそのまま使えるため、置き換えは新しいアダプタの追加で閉じる
  想定。
  - 削除条件: 実OCR/レイアウト解析アダプタが実装され、本アダプタを使うテストが
    すべてそちらに移行した時点で `annotation_markers.py` とその専用テストを削除
    できる。
  - タグの正規表現（`_TAG_PATTERNS`）は模範解答内の構造化タグという簡略化であり、
    実データでの分類精度は未検証。
- **UIは未実装。** プロファイル候補のプレビュー・人間による修正・確認操作、複数
  答案への一括再適用操作はいずれもFlutter側のUIとして次のMVP Issueで新規実装する
  必要がある。本PoCはドメイン層のAPI呼び出しだけで「生成→確認→再適用」を検証した。
  UI設計は本PoCのスコープ外。
- **座標変換の簡略化。** `_rect_to_bbox` はページ幅高さのみを使う（回転・CropBox
  非対応）。PR #31（PoC 3）がマージされたら `domain/pdf_geometry.py` の一般化された
  変換に差し替える。差し替えは `profile_detection.py` 内に閉じる想定。
- **`backend/poc/issue_15_multi_layout_profile/report.py` はPoCのエビデンス生成
  専用。** アプリ本体からは参照しない。合否判定の正はpytestテスト側にある。
- **`pypdf` は現状 dev 依存グループのまま。** PDF機能を実装するMVP Issueで project
  依存へ昇格するか、PoC 3 の採用構成（`pypdfium2` + `pypdf`）と統合して整理する。

## 依存関係の変更

- `backend/pyproject.toml` の dev グループに `pypdf>=6.16.2` を追加（PoC 3 採用と
  同じライブラリ・同系統バージョン）。
- `.gitattributes` に `*.pdf binary` を追加。
- `.prettierignore` に生成物ディレクトリ `docs/poc-4-multi-layout-profiles/` を
  追加。
