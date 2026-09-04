# PoC 1 — 日本語手書き OCR と Bounding Box 比較検証

## 0. このドキュメントの位置づけ

GitHub Issue #13（親 Issue #3）の PoC。簡易設計書 §8.3 の `OCRProvider` 具体実装、
および業務ルール決定書 §3 (A)（使用する OCR）と §3 (C)（低 Confidence 基準値）の
判断材料を出す。

- これは**技術プローブ**であり本番機能ではない（`AGENTS.md`「Verification」）。
  完了条件は「repro command・期待結果・実測値・決定・削除／昇格条件がすべて記録される」
  こと。本書がその記録である。
- 仕様の正本は簡易設計書。OCR サービスの**最終選定はプロジェクトオーナー**
  （@HIKARU0627）が本 PoC のクローズ時に行う。実装担当は技術評価を補助する。
- 評価データ・API キーが揃うまで**実測値は空欄**とし、「実装段階で判断」に倒さない
  （§8・§9 に基準未達時の扱いを明記する）。

### 0.1 現在のステータス

| 項目                               | 状態                                                             |
| ---------------------------------- | ---------------------------------------------------------------- |
| メトリクス計算・集計パイプライン   | **実装済み**（`backend/src/auto_scoring/domain/ocr_metrics.py`） |
| `OCRProvider` 契約 + contract test | **実装済み**（`backend/tests/test_ocr_provider_contract.py`）    |
| 合成フィクスチャでの集計再現       | **実装済み**（`uv run python poc/run_ocr_eval.py`）              |
| 実 OCR アダプタ（Google/Azure 等） | **未実装**（credentials・評価データセット待ち。§7・§9）          |
| 実測値・採用判断                   | **未実施**（同上）                                               |

---

## 1. 評価データの内訳

実データ・個人情報は**リポジトリにコミットしない**（決定書 §6.7）。実体は組織管理
ストレージの `"<組織管理ストレージ>/auto-scoring/eval-datasets/<dataset-id>/"`
に置き、プロジェクトオーナーが管理する。

### 1.1 必要件数（決定書 §6.2 PoC 1 の下限）

| 区分       | 下限                                                  |
| ---------- | ----------------------------------------------------- |
| 手書き品質 | 綺麗 / 普通 / 汚い の 3 区分                          |
| 設問数     | 各区分 20 設問以上（計 60 設問以上）                  |
| レイアウト | 2 形式以上（1 枚物 / 冊子 / 2 段組 / 別紙）           |
| 教科       | 記述式・短答式中心（決定書 §2 (10) の対象種別に限る） |

### 1.2 各設問サンプルが持つもの

`backend/tests/fixtures/ocr/README.md` のスキーマに従う。

| フィールド            | 内容                                                               |
| --------------------- | ------------------------------------------------------------------ |
| `sample_id`           | 個人を特定しない不透明 ID                                          |
| `reference_text`      | 採点者による回答欄の書き起こし（正解ラベル）                       |
| `keywords`            | 採点上の重要語（決定書 §6.3 準拠の人手ラベル）                     |
| `handwriting_quality` | `clean` / `normal` / `messy`                                       |
| `layout_type`         | `single_sheet` / `booklet` / `two_column` / `separate_answer`      |
| `expected_boxes`      | 添削対象語の正規化 Bounding Box（0.0〜1.0）。Annotation 位置検証用 |

### 1.3 正解ラベル作成（決定書 §6.3）

現役採点者 2 名が独立に書き起こし・重要語付与・Bounding Box 指定を行い、不一致は
3 人目または合議で確定する。採点者間の一次一致率も記録し、Bounding Box 指定の
ばらつき（人間同士の中心誤差）を採用基準の下限根拠にする。

### 1.4 リポジトリに入る合成フィクスチャ

`backend/tests/fixtures/ocr/sample-*.json` は**合成・手作成**のダミー
（生徒データではない）。メトリクス計算と集計表の**再現性確認専用**で、精度評価には
使わない。

---

## 2. 比較候補

第一候補 Google Cloud Vision に加え、比較可能な候補を**最低 1 つ**評価する
（簡易設計書 §8.3、technology-stack.md §3.5）。

| ID      | 候補                                                | 位置づけ                                           |
| ------- | --------------------------------------------------- | -------------------------------------------------- |
| `gcv`   | Google Cloud Vision API `DOCUMENT_TEXT_DETECTION`   | **第一候補**。単語単位 Bounding Box が取れる       |
| `azure` | Azure AI Vision Image Analysis 4.0（Read）          | 対抗候補。手書き対応言語・日本語手書き精度を要確認 |
| `local` | ローカル OCR（PaddleOCR 日本語 / Tesseract 日本語） | クラウド不可時フォールバック。精度下限の確認       |
| `vlm`   | Vision 対応 LLM（PoC 2 の `AIProvider` と共用）     | OCR 単独評価。Bounding Box は弱い想定              |

必須比較: `gcv` + （`azure` または `local` から最低 1 つ）。時間が許せば全候補。

### 2.1 評価モード（Issue #13「OCR 単独と OCR + Vision AI 併用を分けて評価する」）

| モード         | 入力                                                          | 測る狙い                         |
| -------------- | ------------------------------------------------------------- | -------------------------------- |
| `ocr_only`     | 設問画像のみ                                                  | OCR 単体の文字精度・Bounding Box |
| `ocr_plus_vlm` | 設問画像 + OCR テキスト + 模範解答 + 採点基準を Vision LLM へ | 併用時の重要語一致率の改善幅     |

`ocr_plus_vlm` でも **Bounding Box は OCR 由来**を使う（AI に座標を推測させない。
簡易設計書 §12.1）。

---

## 3. 測定指標

すべて**人間の正解ラベルから**算出する（`domain/ocr_metrics.py`）。

| 指標                  | 定義                                                           | 関数                                |
| --------------------- | -------------------------------------------------------------- | ----------------------------------- |
| 文字誤り率 (CER)      | Levenshtein 距離 ÷ 参照文字数。0.0 が完全一致                  | `character_error_rate`              |
| 重要語一致率          | `keywords` のうち認識テキストに逐語一致した割合                | `keyword_match_rate`                |
| Bounding Box 中心誤差 | 期待 box と最良一致 box の中心間ユークリッド距離（正規化単位） | `bounding_box_center_error`         |
| Bounding Box IoU      | 期待 box と最良一致 box の IoU                                 | `BoundingBox.iou`                   |
| latency               | `recognize()` の応答時間（p50 / p95）。ハーネスで計測          | 実アダプタ側                        |
| 概算 cost             | 1,000 設問あたりの API 料金（各社公開単価 × 実リクエスト数）   | 実アダプタ側                        |
| 失敗率                | 例外・空応答・タイムアウトの割合                               | `SampleMetrics.failed` 集計         |
| 低 Confidence 率      | `ConfidenceBand.LOW` トークンを含む設問の割合                  | `BucketSummary.low_confidence_rate` |

集計は `summarize_by_quality()` が手書き品質バケット別に平均し、
`to_markdown_table()` が §8 の結果表を生成する。集計出力は**件数と平均値のみ**で
秘匿情報を含まない。

---

## 4. repro command

### 4.1 秘匿情報なしの集計再現（credentials 不要・いつでも実行可）

```bash
cd backend
uv run python poc/run_ocr_eval.py
```

同一の入力（`tests/fixtures/ocr/*.json`）から §8 と同じ形式の集計表が再生成される
ことを確認する。メトリクス計算自体の検証は:

```bash
cd backend
uv run pytest tests/test_ocr_metrics.py tests/test_ocr.py tests/test_ocr_provider_contract.py
```

### 4.2 実データでの評価（credentials + 評価データセット必要）

```bash
cd backend
# 1) backend/.env.local に §7 の credentials を設定
# 2) 評価データセット（録画済み OcrResult + 人手ラベル）をローカルへ配置
uv run python poc/run_ocr_eval.py --dataset "<local eval-dataset dir>" --out poc-1-results.md
```

実 OCR を叩いて `OcrResult` を録画する live-provider パスは、credentials と
データセットが揃った時点の**昇格 PR**で追加する（§7.3）。録画時も request/response
本文はログに残さない。

---

## 5. 期待結果

- §4.1 が **exit 0** で、`clean` / `normal` / `messy` の 3 バケット行を持つ Markdown
  表を標準出力に出す。
- §4.1 の pytest が全て pass する（メトリクスが人手ラベルから算出されている）。
- 実データ評価（§4.2）では、手書き品質が下がるほど CER が上がり、`messy` で失敗率・
  低 Confidence 率が上がる**単調な傾向**が観測される。

---

## 6. 実測値

**未実施。** 実 OCR アダプタ・API キー・評価データセットが未整備のため
（§0.1・§7）。本 PoC のクローズ時に §8 の表を実データで埋める。合成フィクスチャの
集計（下）は精度評価ではなく、パイプラインの疎通確認である。

```
# uv run python poc/run_ocr_eval.py の出力（合成フィクスチャ / 参考値のみ）
samples: 4
| 手書き品質 | 件数 | 平均CER | 重要語一致率 | BBox中心誤差 | BBox IoU | 低Confidence率 | 失敗率 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| clean | 1 | 0.000 | 1.000 | 0.000 | 1.000 | 0.000 | 0.000 |
| messy | 2 | 0.562 | 0.167 | 0.050 | 0.500 | 0.500 | 0.500 |
| normal | 1 | 0.083 | 0.667 | - | - | 0.000 | 0.000 |
```

---

## 7. credentials と rate limit

### 7.1 credentials 設定方法

`.env.example` の「OCR PoC 1」節を参照。API キーは **Python サイドカー側のみ**が
保持し（technology-stack.md §2）、`backend/.env.local`（git 無視）または OS
キーチェーン（`keyring`）に置く。リポジトリ・ログ・Issue・スクリーンショットに
含めない（`AGENTS.md`「Security」）。

| 候補    | 必要な設定                                                                                                            |
| ------- | --------------------------------------------------------------------------------------------------------------------- |
| `gcv`   | Cloud Vision API のみを許可したサービスアカウント JSON。`GOOGLE_APPLICATION_CREDENTIALS` にパス、`OCR_GCP_PROJECT_ID` |
| `azure` | `OCR_AZURE_VISION_ENDPOINT` + `OCR_AZURE_VISION_KEY`                                                                  |
| `local` | credentials 不要。PaddleOCR / Tesseract 日本語モデルをローカル配置                                                    |

外部送信は**生徒識別情報を除いた設問画像だけ**に限定する（決定書 §2 (2)）。
可能なら各サービスのデータ保持オプトアウト／ゼロデータ保持を有効にする
（決定書 §6.6）。

### 7.2 rate limit 時の扱い（暫定。最終値は §3 E = Issue で確定）

- 指数バックオフ（初期 1s、上限 32s、最大 5 回）で再試行する。
- 恒常的な 429 / quota 超過は**失敗として記録**し、推測で埋めない。当該設問は
  `ConfidenceBand.LOW` 相当の「要確認」に落とす。
- PoC のハーネスは逐次実行（並列度 1）を既定とし、レート制限に当たった候補は
  その旨を結果表の注記に残す。MVP の並列度は PoC 2 後に確定（決定書 §3 E）。

### 7.3 昇格時に追加するもの

- 採用候補の `OCRProvider` 実 アダプタ（`backend/src/auto_scoring/adapters/ocr/`）。
- そのアダプタ用の `OCRProviderContract` サブクラス（実キーは CI に置かず、
  ローカル／手動実行のマーカー付きテストにする）。
- `poc/run_ocr_eval.py` の live-provider パス（画像 → `recognize()` → `OcrResult`
  録画）。

---

## 8. 採用基準と結果表

### 8.1 採用基準（この値を満たせば当該候補を MVP の `OCRProvider` 第一候補にできる）

「重要語一致率」を最重視する（採点の入力に効くため）。Bounding Box は Annotation
配置に効くが、取れない語はコメント退避できる（簡易設計書 §12.4）ため副次指標。

| 指標                  | clean  | normal | messy  |
| --------------------- | ------ | ------ | ------ |
| 重要語一致率          | ≥ 0.95 | ≥ 0.90 | ≥ 0.75 |
| 文字誤り率 (CER)      | ≤ 0.05 | ≤ 0.10 | ≤ 0.25 |
| Bounding Box 中心誤差 | ≤ 0.02 | ≤ 0.03 | ≤ 0.05 |
| Bounding Box IoU      | ≥ 0.70 | ≥ 0.60 | ≥ 0.50 |
| 失敗率                | ≤ 0.02 | ≤ 0.05 | ≤ 0.10 |

共通条件:

- latency: p50 ≤ 3s、p95 ≤ 8s（1 設問画像あたり）。
- 概算 cost: ≤ 1.5 USD / 1,000 設問（第一候補）。
- 低 Confidence の挙動: 認識不能を推測で埋めず `ConfidenceBand.LOW` として候補を
  返す（§10。契約は `test_ocr_provider_contract.py` で検証済み）。
- Bounding Box 中心誤差の下限は、§1.3 で測る**人間同士のばらつき**を下回らなくてよい
  （人間ラベルより厳しくは求めない）。

### 8.2 結果表（実測は本 PoC クローズ時に記入）

| 候補              | モード         | 手書き品質 | 平均CER | 重要語一致率 | BBox中心誤差 | BBox IoU | p50 latency | cost/1k | 失敗率 | 低Conf率 |
| ----------------- | -------------- | ---------- | ------- | ------------ | ------------ | -------- | ----------- | ------- | ------ | -------- |
| `gcv`             | `ocr_only`     | clean      | _TBD_   | _TBD_        | _TBD_        | _TBD_    | _TBD_       | _TBD_   | _TBD_  | _TBD_    |
| `gcv`             | `ocr_only`     | normal     | _TBD_   | _TBD_        | _TBD_        | _TBD_    | _TBD_       | _TBD_   | _TBD_  | _TBD_    |
| `gcv`             | `ocr_only`     | messy      | _TBD_   | _TBD_        | _TBD_        | _TBD_    | _TBD_       | _TBD_   | _TBD_  | _TBD_    |
| `gcv`             | `ocr_plus_vlm` | clean      | _TBD_   | _TBD_        | _TBD_        | _TBD_    | _TBD_       | _TBD_   | _TBD_  | _TBD_    |
| `gcv`             | `ocr_plus_vlm` | normal     | _TBD_   | _TBD_        | _TBD_        | _TBD_    | _TBD_       | _TBD_   | _TBD_  | _TBD_    |
| `gcv`             | `ocr_plus_vlm` | messy      | _TBD_   | _TBD_        | _TBD_        | _TBD_    | _TBD_       | _TBD_   | _TBD_  | _TBD_    |
| `azure` / `local` | `ocr_only`     | clean      | _TBD_   | _TBD_        | _TBD_        | _TBD_    | _TBD_       | _TBD_   | _TBD_  | _TBD_    |
| `azure` / `local` | `ocr_only`     | normal     | _TBD_   | _TBD_        | _TBD_        | _TBD_    | _TBD_       | _TBD_   | _TBD_  | _TBD_    |
| `azure` / `local` | `ocr_only`     | messy      | _TBD_   | _TBD_        | _TBD_        | _TBD_    | _TBD_       | _TBD_   | _TBD_  | _TBD_    |

---

## 9. 基準未達時の扱い（「実装段階で判断」に倒さない）

結果が §8.1 を満たさない場合、以下を**この PoC の追記**として確定する。

### 9.1 追加検証条件

1. `messy` のみ未達なら: 前処理（二値化・傾き補正・コントラスト正規化）を 1 段
   追加して再測定する。1 週間以内に再集計する。
2. Bounding Box だけ未達なら: 行単位 box → 単語単位 box の分割ロジックを噛ませて
   再測定する。それでも未達なら、その品質区分は Annotation を**コメント退避固定**
   （簡易設計書 §12.4）にし、MVP 仕様へ明記する。
3. 全候補が重要語一致率で未達なら: `ocr_plus_vlm` を必須構成とし、PoC 2 の
   `AIProvider` 選定に「OCR 補正込みの一致率」を評価項目として引き継ぐ。

### 9.2 MVP の手動 fallback（基準未達が解消しない場合の既定動作）

- 採用 OCR が低 Confidence または失敗を返した設問は、**自動確定しない**。UI に
  「文字認識要確認」を表示し（簡易設計書 §8.2）、人間が回答欄画像を見て
  OCR テキストを手入力する導線を MVP に含める。
- クラウド OCR が使えない環境（ネットワーク不可・許諾なし）では `local` OCR に
  自動フォールバックし、`local` の実測が §8.1 の `messy` 基準に達しない場合は
  その区分を**全設問「要確認」**で運用する。
- いずれの場合も「どのくらいの割合が手動確認に回るか」を §8 の失敗率＋低
  Confidence 率から見積もり、MVP のリリースノートに記載する。

### 9.3 採用 OCR・fallback・rate limit の決定（本 PoC クローズ時に確定）

| 決定項目                | 記入欄                                                           |
| ----------------------- | ---------------------------------------------------------------- |
| 採用 OCR（第一候補）    | _本 PoC クローズ時に確定（第一候補: `gcv`）_                     |
| クラウド不可時 fallback | _確定（暫定: `local` = PaddleOCR 日本語）_                       |
| rate limit 時の扱い     | §7.2 を確定値として採用（バックオフ + 失敗記録 + 要確認落ち）    |
| 低 Confidence 閾値      | 分布を PoC 2 と合わせて §3 (C) で確定（本 PoC では分布のみ提出） |

---

## 10. 低 Confidence / 認識不能の方針

- OCR は認識不能な範囲も**トークンとして返す**。`ConfidenceBand.LOW` を付け、
  `text` には最良候補（例: `???` や部分推定）を入れる。**欠落させない・黙って
  整形しない**（Issue #13 受入条件）。
- `OcrResult.has_low_confidence` が真の設問は、UI で「文字認識要確認」として提示し、
  自動確定フローに乗せない（簡易設計書 §8.2・§35-2）。
- この契約は `backend/tests/test_ocr_provider_contract.py` の
  `test_unreadable_span_is_low_confidence_not_dropped` で検証する。実アダプタは
  `OCRProviderContract` を継承して同じ契約を満たすこと。

---

## 11. 昇格条件（Issue #13）

本 PoC から MVP 実装へ昇格するのは次のみ:

- 採用された `OCRProvider` アダプタ 1 つ（＋クラウド不可時 fallback アダプタ）。
- `OCRProvider` の contract test（`OCRProviderContract` と採用アダプタ用サブクラス）。
- `domain/ocr.py`（型・ポート）と `domain/ocr_metrics.py`（メトリクス。Confidence
  分布・較正の継続評価に使う）。

昇格しないもの: 不採用候補のアダプタ、`poc/` 配下のハーネス、合成フィクスチャ。
不採用アダプタは削除する。

---

## 12. コミット禁止（決定書 §6.7 / §7.1 再掲）

- 実際の生徒答案 PDF・スキャン画像・ページ画像
- 氏名・生徒 ID・学校名などの識別情報
- 人間の正解ラベルの実データ（実採点値・実書き起こし）
- OCR API の request/response 本文、`app-data/` の中身
- 評価データセットの保管先 URL・認証情報
