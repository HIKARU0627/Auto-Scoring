# PoC 2 — AI 採点精度と構造化出力の比較検証

GitHub Issue #14（親 #3）。使用する AI モデル（§33-2）を選定するための技術プローブ。
`business-rules-and-evaluation-data.md` §3 (B) / §9、`technology-stack.md` §3.5 に対応する。

> **プローブの位置づけ**（AGENTS.md「Verification」）: 本書は repro command・期待結果・
> 実測値・採用閾値・比較表・人間採点との不一致例・除去/昇格条件を記録する。
> 昇格するのは Pydantic schema と `AIProvider` contract test のみ（§7）。
>
> **改訂履歴**: 初版レビュー（PR #30 Codex）で「実 provider・実評価データによる比較が
> 未実施」を Blocker 指摘された。本改訂で Gemini / OpenAI 実 API を呼び出し、その結果を
> `poc/fixtures/recorded/{gemini,openai}/` に記録・コミットして §4 を実測値へ更新した。
> ただし業務ルール §6.2 が定める本番規模データセット（2 教科・計 60 答案以上・延べ 300
> 設問以上、実生徒答案・人間ラベル付き）はまだ用意できていない。今回の実測は既存の
> 合成 3 設問 × 2 バリアント fixture に対する実 provider 呼び出しであり、範囲が限定的で
> ある点は §4.4 に明記する。

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
巻き込むかを分離して観察する。**§4.2 の不一致例は、この分離が実際に有効な観察軸である
ことを実データで示している。**

---

## 2. repro command

```bash
# 依存の復元（未実施の場合）
pnpm run bootstrap

# 集計の再生成（既定 = 実 provider の記録済み応答を再生。API キー不要 / 決定的）
cd backend
uv run python -m poc.evaluate --format md      # 比較表 + 不一致例（Markdown）
uv run python -m poc.evaluate --format json    # 機械可読

# 参考: API キー無しの合成データ・ハーネス自己診断（回帰確認用）
uv run python -m poc.evaluate --candidates synthetic-a synthetic-b --format md

# schema 検証・AIProvider contract test・集計テスト（実 provider の決定性含む）
uv run pytest tests/test_ai_grading_schema.py tests/test_ai_provider_contract.py tests/test_poc_metrics.py tests/test_poc_security.py
```

### 期待結果

- 上記コマンドはいずれも終了コード 0 になる。
- `poc.evaluate`（既定候補 = `gemini` / `openai`）の Markdown 出力は §4.2 の比較表・
  不一致例と一致し、JSON 出力は同じ集計値を機械可読形式で返す。
- テストは schema 不適合の拒否、Confidence の分離、`AIProvider` 契約、**実 provider を
  含む**集計の決定性、secret 非流出を通過する。

`poc/fixtures/`（実 provider の記録済み応答を含む）は静的なので `evaluate` は**何度実行
しても同一出力**になる（受入条件「同じデータから集計結果を再生成できる」）。
`test_run_is_reproducible_from_the_same_fixtures` と
`test_real_candidates_are_reproducible_from_recorded_fixtures` が検証する。出力に
secret・答案本文・OCR 本文・生徒識別情報は含めず、provider 例外の詳細も固定コードへ
置換する（`test_report_contains_no_answer_text` / `test_provider_error_details_do_not_reach_report`）。
不一致例は case id・スコア差・criterion の `result` 変化と固定エラーコードのみを載せる。

### 再現条件の記録（prompt / model / version / temperature）

各 provider 実行の再現条件は `AIProvider.descriptor`（`ProviderDescriptor`）として応答に
埋め込む: `provider` / `model` / `version` / `temperature` / `structured_output_mode`
（`json_schema` 等）/ `prompt_id`（プロンプトテンプレートの安定 ID）。記録済み fixture では
`poc/fixtures/recorded/<candidate>/descriptor.json` に保持する。実測（§4）で使った値は
§4.1 の表のとおり。

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

### 4.1 実 API キーによる計測: 実施済み（2026-09-04）

`AUTO_SCORING_GEMINI_API_KEY` / `AUTO_SCORING_OPENAI_API_KEY` を用いて、既存の
`poc/fixtures/cases.json`（3 設問 × `ocr_clean`/`ocr_noisy` = 6 セル）を Gemini・OpenAI
それぞれへ実送信し、応答を `poc/fixtures/recorded/{gemini,openai}/` に記録した
（`_synthetic: false`）。Anthropic キーは未設定のため対象外（Issue #14 の「利用可能な
最低 2 候補」は Gemini / OpenAI で充足）。

再現条件（`descriptor.json`。両候補とも `structured_output_mode: "json_mode"` — provider
側のスキーマ強制機能ではなく、JSON 構文のみを保証する軽量な JSON モードを使い、
構造の妥当性は本リポジトリの Pydantic 層で検証した。プロンプトのみでスキーマ遵守を
指示しており、これは Issue #14 が測ろうとしている「構造化出力の安定性」をより直接に
観測するための意図的な選択である）:

| candidate | provider | model              | temperature | structured_output_mode |
| --------- | -------- | ------------------ | ----------: | ---------------------- |
| gemini    | Gemini   | `gemini-3.6-flash` |         0.0 | `json_mode`            |
| openai    | OpenAI   | `gpt-4o-mini`      |         0.0 | `json_mode`            |

`gemini-2.5-flash` / `gemini-2.5-flash-lite`（当初の第一候補）は API から
`"no longer available to new users"` で 404 になったため、`gemini-3.6-flash`
（API のエラーメッセージが推奨する後継）に切り替えた。モデル可用性は必ず実行時に
確認すること — ドキュメント記載のモデル名を無条件に信頼しない。

### 4.2 実測比較表

<!-- generated: uv run python -m poc.evaluate --format md (default candidates: gemini, openai) -->

| candidate | cells | answered | exact match | within ±tol | criterion agree | schema violation | latency p50 (s) | latency p95 (s) | est. USD / 100 answers |
| --------- | ----: | -------: | ----------: | ----------: | --------------: | ---------------: | --------------: | --------------: | ---------------------: |
| gemini    |     6 |        6 |       33.3% |       66.7% |           50.0% |             0.0% |            4.45 |            5.20 |                    n/a |
| openai    |     6 |        6 |       50.0% |       66.7% |           50.0% |             0.0% |            2.39 |            3.62 |                    n/a |

トークン使用量（`recorded/**/*.json` の `usage` 集計。cost 単価は §6.3 のとおり未確認の
ため `est. USD` は `n/a`）:

| candidate | total input tokens | total output tokens | avg input / answer | avg output / answer |
| --------- | -----------------: | ------------------: | -----------------: | ------------------: |
| gemini    |               2641 |                1141 |              440.2 |               190.2 |
| openai    |               2995 |                1182 |              499.2 |               197.0 |

#### gemini — 人間採点との不一致例（tolerance ±1）

| case             | variant   | human |  AI |   Δ | criterion diffs  |
| ---------------- | --------- | ----: | --: | --: | ---------------- |
| q-fill-blank     | ocr_noisy |     3 |   0 |  -3 | c1: pass→fail    |
| q-photosynthesis | ocr_clean |     4 |   5 |  +1 | c2: partial→pass |
| q-photosynthesis | ocr_noisy |     4 |   5 |  +1 | c2: partial→pass |
| q-symbol-select  | ocr_noisy |     2 |   0 |  -2 | c1: pass→fail    |

#### openai — 人間採点との不一致例（tolerance ±1）

| case             | variant   | human |  AI |   Δ | criterion diffs  |
| ---------------- | --------- | ----: | --: | --: | ---------------- |
| q-fill-blank     | ocr_noisy |     3 |   0 |  -3 | c1: pass→fail    |
| q-photosynthesis | ocr_clean |     4 |   5 |  +1 | c2: partial→pass |
| q-photosynthesis | ocr_noisy |     4 |   4 |   0 | c2: partial→fail |
| q-symbol-select  | ocr_noisy |     2 |   0 |  -2 | c1: pass→fail    |

### 4.3 観察（実データからの所見）

- **OCR 誤認がそのまま採点結果へ伝播する**（両候補共通）: `q-symbol-select` の
  `ocr_noisy`（正解「イ」に対し OCR が「ィ」を誤って認識した想定文字列）で、両候補とも
  `c1` を `fail` と判定しスコアを 2→0 に落とした。両候補とも与えられたテキストをそのまま
  正解と照合しており、「OCR が誤読した可能性」を汲んだ救済判定はしていない。これは
  Issue #14 が要求する「OCR 正解文字と OCR 誤認文字を分けて入力する」設計が実際に
  意味のある差を検出できることの実証でもある。
- **rubric の厳格さ判定が人間より甘い**（両候補共通）: `q-photosynthesis` の `ocr_clean`
  （OCR 誤認なし）でも、人間は `c2`（光エネルギーへの言及）を `partial` としたが、両候補
  とも `pass` として満点を付けた。OCR 品質と無関係に、部分点判定の基準（簡易設計書
  §9 (9)）の解釈が人間より緩い可能性がある。
- **`grading.score` と `criteria[].result` の内部整合性が崩れる例がある**: openai の
  `q-photosynthesis`/`ocr_noisy` で `c2: partial→fail` としながら `grading.score` は
  人間と同じ `4` を返した（`c1` の得点配分だけでは説明が付かない）。両フィールドは
  スキーマ上独立しており、片方が正しくても他方の一貫性は保証されない。
- **任意フィールドの省略が provider によって異なる**（構造化出力の安定性の一側面）:
  openai は 6 件中 3 件で `annotations` フィールド自体を省略した（gemini は毎回出力）。
  本スキーマは `annotations` に既定値 `[]` を持つため schema violation にはならないが、
  「毎回同じ形の JSON を返すか」という安定性の指標としては差がある。
- **schema violation は両候補とも 0 件**。JSON モード（スキーマ強制なし）でも、本
  プロンプト・この 3 設問では構文崩れは発生しなかった。

### 4.4 実測の限界（範囲外の作業として残るもの）

この実測は Issue #14 の「実 provider を最低 2 候補、同一データ・同一 rubric で比較する」
という技術プローブ要件と、「secret と答案本文を出力せず、同じデータから集計結果を
再生成できる」という受入条件を満たす。一方で、業務ルール §6.2 が定める本番規模の
評価データセット（2 教科・各 1 テスト・各 30 答案以上、計 60 答案・延べ 300 設問以上、
現役採点者 2 名の独立採点によるラベル、実生徒答案の手書き品質 3 区分）は**今回のスコープ
外**であり、まだ用意されていない。理由:

- 実生徒答案 PDF・手書き画像の入手には、業務ルール §6.4 の**書面での二次利用許諾**と
  §6.4 の匿名化手順の実施が前提であり、本セッションで新規に取得・生成できるデータでは
  ない。
- 本 PoC は「模範解答・rubric・OCR テキスト」のみをテキストとして送信しており、
  簡易設計書 §9.1 が本来求める**生徒答案画像**は今回は未送信（§5.1 に既知の制約として
  明記）。画像入力による比較は、実答案画像が用意でき次第の追加検証項目とする。

よって §6 の採用可否判断は、この 3 設問 × 2 バリアントの結果を**一次シグナル**として
用いるにとどめ、最終確定は §6.2 データセットでの再検証を条件とする（§6 参照）。

---

## 5. 実 API キー設定後の計測手順

### 5.1 credentials（設定済み）

`.env.local`（コミット禁止。`.gitignore` の `.env*.local` 済み）に設定済み。

| 変数                             | 状態                                        |
| -------------------------------- | ------------------------------------------- |
| `AUTO_SCORING_GEMINI_API_KEY`    | 設定済み（§4 の実測で使用）                 |
| `AUTO_SCORING_OPENAI_API_KEY`    | 設定済み（§4 の実測で使用）                 |
| `AUTO_SCORING_ANTHROPIC_API_KEY` | 未設定（Issue #14 の最低 2 候補は充足済み） |

- クラウド送信ペイロードは設問単位の最小限に絞り、生徒識別情報を含めない（§2 (2)）。
  `GradingRequest` は氏名・ファイル名・ページ全体画像を持てない構造にしてある。実際の
  送信内容も「問題文・rubric・模範解答・OCR テキスト」のみで、生徒答案画像は未送信
  （§4.4）。
- **ゼロデータ保持 / オプトアウト設定（業務ルール §6.6）は各サービスのコンソールでの
  手動設定が必要で、本 PoC のスクリプトからは変更できていない。** MVP 実装前に
  プロジェクトオーナーが両サービスのコンソールで確認・設定すること。
- 送信データはすべて合成データ（架空の理科設問と模範解答）であり、実在の生徒・個人情報は
  一切含まれない。

### 5.2 recorded/ の作り方（実施記録）

実モデルを叩く記録スクリプトは、方針どおり**本 PR にコミットしていない**（block
condition B: モデル固有のプロンプト／パース最適化を本実装に含めない。エージェント作業用
スクラッチ領域で 1 回限り実行し、破棄した）。再現する場合は次を満たす一時スクリプトを
作成する:

1. `.env.local` から `AUTO_SCORING_GEMINI_API_KEY` / `AUTO_SCORING_OPENAI_API_KEY` を
   読む。**キーはクエリパラメータに載せない**（Gemini は `x-goog-api-key` ヘッダー、
   OpenAI は `Authorization: Bearer` ヘッダーを使う）。HTTP エラー時も例外オブジェクトを
   そのまま `print`/ログしない — エラーメッセージが認証情報を含むリクエスト URL を
   埋め込む場合がある（本 PoC 作業で実際に発生し、キーをローテーションして対応した
   運用上の教訓）。
2. `poc/fixtures/cases.json` の各 `case` × `variant` について、問題文・rubric・満点・
   模範解答・当該バリアントの OCR テキストのみをプロンプトに含め、`AIGradingResult`
   （camelCase）と同じ形の JSON 1 個だけを返すよう指示する。
3. 応答を `poc/fixtures/recorded/<candidate>/<variant>/<question_id>.json` に次の形で
   保存する（`raw_response` は応答をパースした JSON オブジェクト、`usage` はトークン数、
   `latency_s` は実測秒）:

   ```json
   {
     "_synthetic": false,
     "raw_response": { "...": "..." },
     "usage": { "input_tokens": 0, "output_tokens": 0 },
     "latency_s": 0.0
   }
   ```

   JSON として parse できない応答は `raw_response` にプレースホルダ（例:
   `{"_unparseable_raw_marker": true}`）を入れて保存する — Pydantic 層が確実に
   `SchemaViolation` として拒否し、握りつぶさない。

4. `poc/fixtures/recorded/<candidate>/descriptor.json` に §2 の再現条件を保存する。
   モデル ID は必ず実行時に一覧 API または実呼び出しで存在確認する（§4.1 の
   `gemini-2.5-flash` 404 の例のとおり、ドキュメント上の名前が使えるとは限らない）。
5. `uv run python -m poc.evaluate` で §4.2 の実測列を再生成し、本書と Issue #14 に反映
   する。

---

## 6. 採用 provider / model・fallback・再試行・cost 上限

### 6.1 §3 閾値との照合（実測、§4.2 に基づく）

| 指標                | 採用閾値    | gemini 実測 | 判定 | openai 実測 | 判定 |
| ------------------- | ----------- | ----------: | :--: | ----------: | :--: |
| schema violation 率 | 0%          |        0.0% |  ✅  |        0.0% |  ✅  |
| 許容点差内率(±1)    | ≥ 90%       |       66.7% |  ❌  |       66.7% |  ❌  |
| 完全一致率（参考）  | ≥ 60%       |       33.3% |  ❌  |       50.0% |  ❌  |
| criterion 別一致率  | ≥ 85%       |       50.0% |  ❌  |       50.0% |  ❌  |
| latency p95         | ≤ 15 s      |      5.20 s |  ✅  |      3.62 s |  ✅  |
| 概算 cost           | ≤ USD 5/100 |         n/a |  –   |         n/a |  –   |

**両候補とも §3 の採用閾値を満たさない**（許容点差内率・完全一致率・criterion 別一致率が
未達）。したがって以下の「採用 provider / model」は**この時点では確定できない**。ただし
サンプルが 3 設問 × 2 バリアントと小さく（§4.4）、統計的な結論を出すには不十分である点に
注意。§6.2 で追加検証を規定する。

### 6.2 基準未達の場合（追加検証条件） — 発動中

§4.2 の実測が §3 の閾値を満たさなかったため、この節を適用する。

1. **データ規模の拡大**（最優先）: 業務ルール §6.2 の規定件数（2 教科・計 60 答案以上・
   延べ 300 設問以上、実答案・人間ラベル付き）で再測定する。今回の 6 セルでは
   criterion 別一致率のようなレートは 1 件のずれで ±17pt 動くため、判定の信頼度が低い。
   実データ入手には業務ルール §6.4 の書面許諾が前提。
2. **画像入力の追加**: 簡易設計書 §9.1 が求める生徒答案画像を実際に送信し、OCR テキスト
   のみの場合との差を測る（§4.4 の既知の制約を埋める）。
3. **rubric 記述の精緻化**: §4.3 で観察した「部分点判定が人間より甘い」傾向に対し、
   `partial` の判定基準をより明示的に rubric へ記述し、再測定で改善するか確認する。
4. **few-shot 例の追加**: 人間が `partial` と判定した具体例を 1〜2 件プロンプトに含め、
   基準の解釈を揃える。
5. 各施策の repro command と before/after を本書へ追記する。それでも未達なら **MVP は
   手動採点 fallback** とする（§7）。

### 6.3 暫定順位と今後の判断（オーナー確定待ち）

§4.2 のこの小標本では、openai が完全一致率で優位（50.0% 対 33.3%）、criterion 別一致率
は同値（50.0%）、latency は openai が優位（p95 3.62s 対 5.20s）。gemini が明確に優位な
指標はない。**この差は統計的に確定的な結論を出すには小さすぎるサンプルであり、暫定的な
参考情報にとどめる。** §6.2 のデータ拡大後にオーナー（@HIKARU0627）が最終確定する。

- **fallback**: 採用モデルが `ProviderUnavailable`（キー欠落・レート制限枯渇・ネットワーク
  障害）のとき第 2 候補へ切替。両者不可なら §7 の手動採点 fallback。
- **再試行条件**: `SchemaViolation` および一時的な `ProviderUnavailable` は指数バックオフで
  **最大 1 回**再試行。再試行後も `SchemaViolation` なら当該設問を「要確認」に落とす
  （自動確定しない、簡易設計書 §24）。
- **cost 上限**: 既定 USD 5 / 100 答案。§4.2 の cost は現時点 `n/a`（単価未確認）。
  オーナーが両サービスの現行単価を確認し、`poc/pricing.py` の `PRICES` に実値を追加した
  上で `uv run python -m poc.evaluate` を再実行して確定する。値は設定化し、コードに
  ハードコードしない。

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

### 除去するもの / 作らないもの（現時点）

- ベンダー固有 adapter（GeminiProvider / ClaudeProvider / OpenAIProvider）は
  **本 PR で作らない**（block condition B）。§6 のとおり採用モデルがまだ確定していない
  ため、「不採用 adapter の削除」は依然として対象なし。
- `backend/poc/`（ハーネス・fixture・`ReplayAIProvider`）はプローブとして**維持する**。
  §6.2 の追加検証や §6.2 データセットでの再測定を、同じハーネス・同じ `AIProviderContract`
  で再利用する前提のため、モデル確定・adapter 実装が完了するまで削除しない。wheel には
  元から含まれない（`pyproject.toml` の `packages`）。
- `poc/fixtures/recorded/{gemini,openai}/` の実測記録は、§4 の実測値の一次ソースとして
  維持する（コミット済み。secret・個人情報は含まない）。

### 手動採点 fallback（基準未達時の MVP 挙動）

- AI 採点を無効化し、レビュー画面は「AI 候補なし」で各設問を人間が採点する
  （簡易設計書 §2 / §16）。
- `AIGradingResult` schema と Review 履歴（§19）はそのまま利用し、`source` を人間にする。
- 後日モデルが閾値を満たしたら AI 採点を feature flag で有効化する。**現時点（§6.1）では
  この fallback が MVP 0.1 の既定挙動になる。**

---

## 8. 検証（受入条件との対応）

| 受入条件                                                  | 対応                                                                                                                   |
| --------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| repro / 期待結果 / 実測値 / 採用閾値 / 比較表 / 不一致例  | §2 / §1・§3 / §4 / §3 / §4.2 / §4.2                                                                                    |
| 実 provider 最低 2 候補・同一データ・同一 rubric で比較   | §4.1（Gemini `gemini-3.6-flash` / OpenAI `gpt-4o-mini`）。§4.4 に規模上の限界を明記                                    |
| 自由文 parse に依存せず schema 不適合をエラー/要確認へ    | `SchemaViolation` → 再試行 → 「要確認」（§6.3）。実測でも 0 件（§4.2）、`ReplayAIProvider` で実証                      |
| 採用 provider/model・fallback・再試行・cost 上限が決定    | 実測の結果、両候補とも§3閾値未達のため**確定に至らず**。判断根拠・追加検証条件・暫定順位を §6 に明記                   |
| 基準未達なら追加検証条件と手動採点 fallback を明記        | §6.2「基準未達の場合」（発動中）/ §7「手動採点 fallback」（現時点の既定挙動）                                          |
| 不採用 adapter を削除し `AIProvider` contract test を残す | ベンダー adapter は未作成（§7、モデル未確定のため）。contract test は昇格                                              |
| secret と答案本文を出力しない                             | §2・§5.1。`test_report_contains_no_answer_text` / `test_provider_error_details_do_not_reach_report`                    |
| 同じデータから集計結果を再生成できる                      | §2。`test_run_is_reproducible_from_the_same_fixtures` / `test_real_candidates_are_reproducible_from_recorded_fixtures` |
