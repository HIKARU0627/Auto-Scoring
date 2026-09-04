# PoC 2 — AI 採点精度と構造化出力の比較検証

GitHub Issue #14（親 #3）。使用する AI モデル（§33-2）を選定するための技術プローブ。
`business-rules-and-evaluation-data.md` §3 (B) / §9、`technology-stack.md` §3.5 に対応する。

> **プローブの位置づけ**（AGENTS.md「Verification」）: 本書は repro command・期待結果・
> 実測値・採用閾値・比較表・人間採点との不一致例・除去/昇格条件を記録する。
> 昇格するのは Pydantic schema と `AIProvider` contract test のみ（§7）。

---

## 1. 目的と検証項目

模範解答・採点マニュアル・答案を同一データ・同一 rubric で複数モデルに与え、次を測る。

| 指標                | 定義                                                                                             |
| ------------------- | ------------------------------------------------------------------------------------------------ |
| 完全一致率          | AI の設問スコア == 人間確定スコア のセル割合                                                     |
| 許容点差内率        | AI スコアと人間スコアの差の絶対値 ≤ 許容点差（既定 ±1.0 点）のセル割合                           |
| criterion 別一致率  | 応答済みセルの人間ラベル全 criterion について `result` が一致した割合。AI 応答からの欠落は不一致 |
| schema violation 率 | Pydantic 検証に失敗した応答の割合（全セル基準）                                                  |
| latency             | `grade()` 1 回の所要秒。p50 / p95                                                                |
| 概算 cost           | `poc/pricing.py` の単価 × トークン使用量。100 答案あたり USD                                     |

補助的に **Grading Confidence の較正**（低 Confidence 帯で不一致が増えるか）と、
**OCR 品質による劣化**（`ocr_clean` と `ocr_noisy` の差）を不一致例から確認する。

### Recognition Confidence と Grading Confidence の分離（簡易設計書 §10）

`AIGradingResult.recognition.confidence`（文字を正しく読めた可能性）と
`AIGradingResult.grading.confidence`（読んだ内容に対する採点の正しさ）は別フィールドで、
本 PoC でも混同しない。「文字認識 98% / 採点判断 63%」という状態を許容する。
schema テスト `test_recognition_and_grading_confidence_are_independent` がこの分離を保証する。

### OCR 正解文字 / OCR 誤認文字を分けて入力する

各評価ケースは `ocr_clean`（正しく認識できた文字列）と `ocr_noisy`（誤認・字形崩れを
混ぜた文字列）の 2 バリアントを持つ（`poc/fixtures/cases.json` の `variants`）。
両方を同一設問・同一 rubric で採点させ、Recognition の劣化が Grading をどれだけ
巻き込むかを分離して観察する。

---

## 2. repro command

```bash
# 依存の復元（未実施の場合）
pnpm run bootstrap

# 集計の再生成（API キー不要 / 決定的）
cd backend
uv run python -m poc.evaluate --format md      # 比較表 + 不一致例（Markdown）
uv run python -m poc.evaluate --format json    # 機械可読

# schema 検証・AIProvider contract test
uv run pytest tests/test_ai_grading_schema.py tests/test_ai_provider_contract.py tests/test_poc_metrics.py
```

### 期待結果

- 集計・テストの 3 コマンドはいずれも終了コード 0 になる。
- Markdown 出力は §4.2 の比較表・不一致例と一致し、JSON 出力は同じ集計値を機械可読形式で返す。
- テストは schema 不適合の拒否、Confidence の分離、`AIProvider` 契約、集計の決定性を通過する。

`poc/fixtures/` は静的なので `evaluate` は**何度実行しても同一出力**になる
（受入条件「同じデータから集計結果を再生成できる」）。`test_run_is_reproducible_from_the_same_fixtures`
が検証する。出力に secret・答案本文・OCR 本文・生徒識別情報は含めず、provider 例外の
詳細も固定コードへ置換する（`test_report_contains_no_answer_text` /
`test_provider_error_details_do_not_reach_report`）。不一致例は case id・スコア差・criterion の
`result` 変化と固定エラーコードのみを載せる。

### 再現条件の記録（prompt / model / version / temperature）

各 provider 実行の再現条件は `AIProvider.descriptor`（`ProviderDescriptor`）として応答に
埋め込む: `provider` / `model` / `version` / `temperature` / `structured_output_mode`
（`json_schema` 等）/ `prompt_id`（プロンプトテンプレートの安定 ID）。
replay fixture では `poc/fixtures/recorded/<candidate>/descriptor.json` に保持する。

---

## 3. 採用閾値（MVP 昇格の判定基準）

PoC 2 完了時、採用候補が**すべて**満たすことを求める下限。人間採点者どうしの一次一致率
（業務ルール §6.3）をベースラインとし、それを大きく下回らないこと。

| 指標                | 採用閾値（暫定）                               | 根拠                                     |
| ------------------- | ---------------------------------------------- | ---------------------------------------- |
| schema violation 率 | **0%**（再試行 1 回込みで 0%）                 | 自由文 parse に依存しない設計の前提      |
| 許容点差内率(±1)    | **≥ 90%**                                      | 人間レビュー前提でも実用に足る下限       |
| 完全一致率          | **≥ 60%**                                      | 参考値。人間どうしの一致率と比較して評価 |
| criterion 別一致率  | **≥ 85%**                                      | 部分点判定（§2 (9)）の信頼性             |
| latency p95         | **≤ 15 s / 設問**                              | 並列 2〜3（§3 E）で 1 答案が実用時間内   |
| 概算 cost           | **≤ USD 5 / 100 答案**（要オーナー承認で上限） | 運用コストの上限管理                     |

> これらは PoC 実行前の**目標値**。実データでの分布が出た時点でオーナー（@HIKARU0627）が
> 確定する。Confidence 閾値そのものは §33-19 / PoC 1・2 合流後に別途決定（ハードコード禁止）。

---

## 4. 実測値

### 4.1 実 API キーによる計測: 未実施

本 PoC のリポジトリ環境には Gemini / Claude / OpenAI いずれの API キーも設定されていない。
実モデルの一致率・latency・cost は**未計測**。以下の比較表の実測列は `n/a` とし、
キー設定後に §5 の手順で `recorded/` を差し替えて再集計する。

### 4.2 replay（合成データ）ハーネス検証結果

API キー無しでも、schema 検証・指標計算・不一致抽出・決定性・秘匿性の各経路は
`ReplayAIProvider` と合成 fixture（`_synthetic: true`）で通しで確認できる。
`synthetic-a` は安定・高一致、`synthetic-b` は不安定（criterion 取りこぼし 1、
schema violation 1）を模したダミー応答。**数値はダミーであり採用判断には使わない。**

<!-- generated: uv run python -m poc.evaluate --format md -->

| candidate   | cells | answered | exact match | within ±tol | criterion agree | schema violation | latency p50 (s) | latency p95 (s) | est. USD / 100 answers |
| ----------- | ----: | -------: | ----------: | ----------: | --------------: | ---------------: | --------------: | --------------: | ---------------------: |
| synthetic-a |     6 |        6 |       83.3% |      100.0% |           87.5% |             0.0% |            1.60 |            3.40 |                   0.23 |
| synthetic-b |     6 |        5 |       50.0% |       66.7% |           66.7% |            16.7% |            2.40 |            5.20 |                   0.54 |

#### synthetic-a — 人間採点との不一致例（tolerance ±1）

| case             | variant   | human | AI  |   Δ | criterion diffs  | note |
| ---------------- | --------- | ----: | --- | --: | ---------------- | ---- |
| q-photosynthesis | ocr_noisy |     4 | 3   |  -1 | c2: partial→fail | -    |

`ocr_noisy` で Recognition Confidence が 0.58 に低下し、光エネルギーの記述を読めず
criterion c2 を `partial→fail`、スコアを 1 点下振れ。許容点差内だが完全一致は外れる。

#### synthetic-b — 人間採点との不一致例（tolerance ±1）

| case             | variant   | human | AI  |   Δ | criterion diffs  | note             |
| ---------------- | --------- | ----: | --- | --: | ---------------- | ---------------- |
| q-fill-blank     | ocr_clean |     3 | 2   |  -1 | c1: pass→partial | -                |
| q-fill-blank     | ocr_noisy |     3 | 1   |  -2 | c1: pass→fail    | -                |
| q-photosynthesis | ocr_noisy |     4 | n/a | n/a | -                | schema_violation |

3 行目は fixture の応答から `grading.rationale` が欠落したケース。`ReplayAIProvider` が
`SchemaViolation` を送出し、ハーネスは provider の例外詳細を出力せず、**スコアを推測せず**
「未応答（要確認へ送る対象）」として集計する（受入条件「schema 不適合をエラーまたは
要確認へ送れる」）。

---

## 5. 実 API キー設定後の計測手順

### 5.1 必要な credentials

`.env.local`（コミット禁止。`.gitignore` の `.env*.local` 済み）または OS キーチェーン
（`keyring`）に設定する。`.env.example` にプレースホルダのみ記載。

| 変数                             | 用途                                |
| -------------------------------- | ----------------------------------- |
| `AUTO_SCORING_GEMINI_API_KEY`    | Google Gemini（Vision 対応）候補    |
| `AUTO_SCORING_ANTHROPIC_API_KEY` | Anthropic Claude（Vision 対応）候補 |
| `AUTO_SCORING_OPENAI_API_KEY`    | OpenAI GPT（Vision 対応）候補       |

- 各サービスで**ゼロデータ保持 / オプトアウト**設定を有効化する（業務ルール §6.6）。
- クラウド送信ペイロードは設問単位の最小限に絞り、生徒識別情報を含めない（§2 (2)）。
  `GradingRequest` は氏名・ファイル名・ページ全体画像を持てない構造にしてある。

### 5.2 recorded/ の作り方

実モデルを叩く薄い記録スクリプトは**本 PR には含めない**（block condition B: モデル固有の
プロンプト／パース最適化を本実装しない）。キー設定後に次を満たす一時スクリプトで
`poc/fixtures/recorded/<candidate>/<variant>/<question_id>.json` を生成する:

- `raw_response`: モデルの structured-output をそのまま（camelCase 可）。
- `usage`: `{ "input_tokens", "output_tokens" }`。
- `latency_s`: 実測秒。
- `descriptor.json`: §2 の再現条件。

その後 `uv run python -m poc.evaluate` で §4.1 の実測列を埋め、本書と Issue #14 に記録する。

---

## 6. 採用 provider / model・fallback・再試行・cost 上限

**現時点で確定できない**（実測が無いため）。決定は次の形で行う。

- **採用 provider / model**: §3 の全閾値を満たす候補のうち、`criterion 別一致率` →
  `許容点差内率` → `概算 cost` の優先順で最良のもの。オーナー（@HIKARU0627）が確定。
- **fallback**: 採用モデルが `ProviderUnavailable`（キー欠落・レート制限枯渇・ネットワーク
  障害）のとき第 2 候補へ切替。両者不可なら §7 の手動採点 fallback。
- **再試行条件**: `SchemaViolation` および一時的な `ProviderUnavailable` は指数バックオフで
  **最大 1 回**再試行。再試行後も `SchemaViolation` なら当該設問を「要確認」に落とす
  （自動確定しない、簡易設計書 §24）。
- **cost 上限**: 既定 USD 5 / 100 答案。超過見込みで警告、明示承認で継続。
  値は設定化し、コードにハードコードしない。

### 基準未達の場合（追加検証条件）

いずれかの候補も §3 を満たさないとき:

1. 追加検証: (a) few-shot 例の追加、(b) rubric の粒度調整、(c) OCR テキストと画像の
   同時入力（現 fixture は OCR テキストのみ）、(d) 候補モデルの上位版、を 1 つずつ
   加えて再測定。各施策の repro command と before/after を本書へ追記する。
2. それでも未達なら **MVP は手動採点 fallback** とする（下記 §7）。

---

## 7. MVP への昇格 / 手動採点 fallback

### 昇格するもの（このリポジトリに残す）

| 対象                                          | 位置                                             |
| --------------------------------------------- | ------------------------------------------------ |
| 構造化出力 Pydantic schema                    | `backend/src/auto_scoring/domain/ai_grading.py`  |
| `AIProvider` ポート + 入出力モデル            | `backend/src/auto_scoring/domain/ai_provider.py` |
| schema テスト / `AIProvider` contract test    | `backend/tests/test_ai_grading_schema.py` 他     |
| データ無し JSON Schema（人間ラベル形式 §6.3） | `docs/schema/ai-grading-result.schema.json`      |

`AIProviderContract`（`tests/test_ai_provider_contract.py`）は基底クラスで、将来の
実 adapter（GeminiProvider 等）はこれを継承して同じ振る舞い検証を受ける。

### 除去するもの / 作らないもの

- ベンダー固有 adapter（GeminiProvider / ClaudeProvider / OpenAIProvider）は
  **本 PR で作らない**（block condition B）。よって「不採用 adapter の削除」は対象なし。
- `backend/poc/`（ハーネス・合成 fixture・`ReplayAIProvider`）はプローブ。モデル確定後に
  実 recorded データで再集計したら、`poc/` ごと削除し本書の数値表だけを残す。
  wheel には元から含まれない（`pyproject.toml` の `packages`）。

### 手動採点 fallback（基準未達時の MVP 挙動）

- AI 採点を無効化し、レビュー画面は「AI 候補なし」で各設問を人間が採点する
  （簡易設計書 §2 / §16）。
- `AIGradingResult` schema と Review 履歴（§19）はそのまま利用し、`source` を人間にする。
- 後日モデルが閾値を満たしたら AI 採点を feature flag で有効化する。

---

## 8. 検証（受入条件との対応）

| 受入条件                                                  | 対応                                                                     |
| --------------------------------------------------------- | ------------------------------------------------------------------------ |
| repro / 期待結果 / 実測値 / 採用閾値 / 比較表 / 不一致例  | §2 / §1・§3 / §4 / §3 / §4.2 / §4.2                                      |
| 自由文 parse に依存せず schema 不適合をエラー/要確認へ    | `SchemaViolation` → 再試行 → 「要確認」（§6）。`ReplayAIProvider` で実証 |
| 採用 provider/model・fallback・再試行・cost 上限が決定    | 実測未取得のため**保留**。決定手順と基準を §6 に明記                     |
| 基準未達なら追加検証条件と手動採点 fallback を明記        | §6「基準未達の場合」/ §7「手動採点 fallback」                            |
| 不採用 adapter を削除し `AIProvider` contract test を残す | ベンダー adapter は未作成（§7）。contract test は昇格                    |
| secret と答案本文を出力しない                             | §2。`test_report_contains_no_answer_text`                                |
| 同じデータから集計結果を再生成できる                      | §2。`test_run_is_reproducible_from_the_same_fixtures`                    |
