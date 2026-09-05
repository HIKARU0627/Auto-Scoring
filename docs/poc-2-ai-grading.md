# PoC 2 — AI採点精度と構造化出力の比較検証

## 0. このドキュメントの位置づけ

GitHub Issue #14（親 Issue #3）の PoC。簡易設計書 §9.2 / §10 の `AIProvider` 具体実装、
および業務ルール決定書 §3 (B)（使用する AI モデル）の判断材料を出す。

- これは**技術プローブ**であり本番機能ではない（`AGENTS.md`「Verification」）。
  完了条件は「repro command・期待結果・実測値・決定・削除／昇格条件がすべて記録される」
  こと。本書がその記録である。
- 仕様の正本は簡易設計書。AI モデルの**最終選定はプロジェクトオーナー**
  （@HIKARU0627）が本 PoC のクローズ時に行う。実装担当は技術評価を補助する。
- 評価データ・API キーが揃うまで**実測値は空欄**とし、「実装段階で判断」に倒さない
  （§6・§9 に基準未達時の扱いを明記する）。`docs/poc-1-japanese-handwriting-ocr.md`
  と同じ章立て・同じ誠実さの方針を踏襲する。

### 0.1 現在のステータス

| 項目                                          | 状態                                                                    |
| --------------------------------------------- | ----------------------------------------------------------------------- |
| Pydantic 構造化出力スキーマ                   | **実装済み**（`backend/src/auto_scoring/domain/ai_grading.py`）         |
| `AIProvider` ポート + contract test           | **実装済み**（`backend/tests/test_ai_provider_contract.py`）            |
| メトリクス計算・集計パイプライン              | **実装済み**（`backend/src/auto_scoring/domain/ai_grading_metrics.py`） |
| 合成フィクスチャでの集計再現                  | **実装済み**（`uv run python poc/issue_14_ai_grading/report.py`）       |
| 実データ（2教科×問1）の書き起こし・接地       | **実施済み（予備調査、§6 参照）**。5 件・のべ 5 設問                    |
| 実 AI プロバイダアダプタ（Gemini/Claude/GPT） | **未実装**（credentials 待ち。§7・§9）                                  |
| 実データでの AI 呼び出し・実測値・採用判断    | **未実施**（同上）                                                      |

---

## 1. 評価データの内訳

実データ・個人情報は**リポジトリにコミットしない**（決定書 §6.7）。実体は組織管理
ストレージの `"<組織管理ストレージ>/auto-scoring/eval-datasets/<dataset-id>/"`
に置き、プロジェクトオーナーが管理する。本 PoC の予備調査データは、それに準じて
このワークツリー外のローカルディレクトリに置いた（§6 参照）。

### 1.1 必要件数（決定書 §6.2 PoC 2 の下限）

| 区分   | 下限                                                           |
| ------ | -------------------------------------------------------------- |
| 教科   | 2 教科 × 各 1 テスト                                           |
| 答案数 | 各教科 30 答案以上（計 60 答案・のべ 300 設問以上）            |
| ラベル | 現役採点者 2 名が独立に採点し、不一致は 3 人目または合議で確定 |

**§6 で記録するとおり、本 PoC の実データ部分はこの下限に届いていない**
（5 件・のべ 5 設問、採点者 1 名相当のみ）。これは正式な採用判断の統計的根拠には
ならない**予備調査（pilot）**であり、そのことを§6・§9 に明記する。

### 1.2 各設問サンプルが持つもの

`backend/tests/fixtures/ai_grading/README.md` のスキーマに従う。

| フィールド          | 内容                                                              |
| ------------------- | ----------------------------------------------------------------- |
| `question_id`       | 個人を特定しない不透明 ID                                         |
| `subject`           | 教科ラベル                                                        |
| `score`/`max_score` | 人間採点者による設問ごとの確定得点・満点（正解ラベル）            |
| `criteria`          | criterion ごとの `pass`/`partial`/`fail`（正解ラベル。§6.3 準拠） |
| `prompt_text`       | 設問文                                                            |
| `model_answer`      | 模範解答                                                          |
| `rubric_text`       | 採点基準・配点                                                    |
| `ocr_clean`         | OCR 正解文字（人手で正しく書き起こした答案テキスト）              |
| `ocr_noisy`         | OCR 誤認文字（OCR が誤読しうる箇所を模した答案テキスト）          |

### 1.3 正解ラベル作成（決定書 §6.3）

現役採点者 2 名が独立に採点し、不一致は 3 人目または合議で確定する。採点者間の
一次一致率も記録し、PoC 2 の「人間同士の一致率」ベースラインとする。

**本 PoC の実データ部分はこの手順を満たさない**（§6 参照）。合成フィクスチャの
`criteria` は、この手順を経ていないダミー値である。

### 1.4 リポジトリに入る合成フィクスチャ

`backend/tests/fixtures/ai_grading/sample-*.json` は**合成・手作成**のダミー
（生徒データではない）。メトリクス計算・スキーマ検証・schema violation 検知の
**再現性確認専用**で、精度評価には使わない。プロバイダ名 `synthetic-a` /
`synthetic-b` も架空の識別子で、実ベンダー名ではない。

---

## 2. 比較候補

Gemini、Claude、OpenAI GPT のうち利用可能な最低 2 候補を同一データ・同一 rubric
で比較する（簡易設計書 §9、決定書 §3 (B)）。

| ID       | 候補                                                 | 位置づけ |
| -------- | ---------------------------------------------------- | -------- |
| `gemini` | Google Gemini（構造化 JSON 出力 / `responseSchema`） | 候補 1   |
| `claude` | Anthropic Claude（tool-use / 構造化出力）            | 候補 2   |
| `gpt`    | OpenAI GPT（JSON Schema / structured outputs）       | 候補 3   |

必須比較: 上記のうち最低 2 候補。時間が許せば全候補。ベンダー固有アダプタは
本 PoC ではまだ実装しない（決定書 §3.1 B「モデル固有のプロンプト最適化・
トークン最適化・モデル固有の JSON モードに依存したパースを本実装しない」に従い、
実測して確定するのは本 PoC のクローズ時）。

ハーネス（`report.py`）はこれを機械的にも強制する: データセット全体で
「実際の応答が記録された provider」が 2 種類未満の場合、`evaluated cells: 0`
の空表を「比較完了」であるかのように出力せず、非ゼロ終了で明示的に拒否する
（§4.2・§7.3 参照）。単に `recorded` の辞書キーの数を数えるのではなく、
**同じ答案（サンプル）・同じ入力モード（`ocr_clean` または `ocr_noisy`）上で**
2 candidate 以上が実際に応答を記録しているかどうかを見る: 空の
`"claude": {}` のようなプレースホルダは候補として数えず、2 candidate が
互いに素な答案にしか応答を持たない場合（一度も同じ設問で両方が採点して
いない場合）も比較とはみなさない。さらに、同じ答案であっても一方が
`ocr_clean` だけ、もう一方が `ocr_noisy` だけしか応答を持たない場合も
比較とはみなさない（`ocr_clean` と `ocr_noisy` は §2.1 のとおり別の評価
モードであり、両者を混ぜて「比較できた」とは扱えないため。コードレビュー
指摘: 単一候補の結果、実際には同一データ上で比較されていない結果、または
同じ答案でも異なる入力モードにしか応答がない結果を、比較結果として報告
してはならない）。

### 2.1 評価モード（Issue #14「OCR正解文字とOCR誤認文字を分けて入力し、Recognition ConfidenceとGrading Confidenceを混同しない」）

| モード      | 入力                                                                                | 測る狙い                                        |
| ----------- | ----------------------------------------------------------------------------------- | ----------------------------------------------- |
| `ocr_clean` | 問題文 + 答案画像（設問領域切り出し） + 模範解答 + 採点基準 + 人手正解 OCR テキスト | OCR が完全に正しい前提での採点精度              |
| `ocr_noisy` | 同上 + OCR が誤読しうる箇所を模したテキスト                                         | OCR 誤りが Grading Confidence・判定に与える影響 |

`ocr_clean` と `ocr_noisy` は常に別セルとして評価する（平均を混ぜない）。
どちらのモードでも、AI 応答の `recognition.confidence` と `grading.confidence`
は別フィールド・別集計列として扱い、一方が高いことをもう一方が高いことの
根拠にしない（簡易設計書 §10「文字認識 98% / 採点判断 63%」の例）。

`AIProvider.grade()` に渡す `GradingRequest` は、答案画像（`answer_image`。
当該設問の回答欄領域のみを切り出したもの。決定書 §2 (2) によりページ全体・
他設問・生徒識別情報は含めない）と OCR テキスト（`ocr_text`）の**両方**を
持つ（簡易設計書 §9.1「生徒答案画像」「OCR結果」）。OCR テキストだけでは、
実アダプタが手書きから意味のある Recognition Confidence を導出できない
（コードレビュー指摘）。

応答側の `annotations[].type` は
`業務ルール決定書 §2 (5)` が固定した MVP の Annotation 種別
（`circle`/`cross`/`triangle`/`score`/`comment`/`underline`/`box`）のみを
受理する。簡易設計書 §12.1 の例示 JSON（`"type": "correction"`）はこの
固定セット確定前の説明用の値であり、そのままでは schema violation になる
（コードレビュー指摘: 未対応の type を受理すると、永続化・PDF 描画の段階で
初めて失敗する）。

---

## 3. 測定指標

すべて**人間の正解ラベルから**算出する（`domain/ai_grading_metrics.py`）。

| 指標                  | 定義                                                                                | 関数                    |
| --------------------- | ----------------------------------------------------------------------------------- | ----------------------- |
| 完全一致率            | AI の `score` が人間の `score` と完全に一致する割合                                 | `evaluate_sample`       |
| 許容点差内率          | `abs(AI score - 人間 score) <= tolerance` を満たす割合（既定 tolerance=1点）        | `evaluate_sample`       |
| criterion 別一致率    | 正解ラベルに存在する criterion のうち、応答の `result` が一致する割合（§3.4 参照）  | `evaluate_sample`       |
| schema violation 率   | `AIGradingResult` のスキーマ検証に失敗した応答の割合                                | `evaluate_sample`       |
| 対応不一致率          | 応答の `questionId`/`maxScore` が正解ラベルと対応しない割合（§3.1 参照）            | `evaluate_sample`       |
| 平均 Recognition Conf | `recognition.confidence` の平均（Grading Conf とは別集計）                          | `summarize_by_provider` |
| 平均 Grading Conf     | `grading.confidence` の平均（Recognition Conf とは別集計）                          | `summarize_by_provider` |
| latency               | 1 設問あたりの応答時間（p50 / p95。応答の妥当性を問わず全呼び出しから算出）         | `summarize_by_provider` |
| latency 計測件数      | bucket の件数のうち `latency_seconds` が実際に記録されていた件数（§3.2 参照）       | `summarize_by_provider` |
| 概算 cost             | 1,000 設問あたりの API 料金（各社公開単価 × 実リクエスト数、USD。§8.1 と同じ単位）  | `summarize_by_provider` |
| cost 計測件数         | bucket の件数のうち `cost_usd` が実際に記録されていた件数（§3.2 参照）              | `summarize_by_provider` |
| 高/低 Conf 誤り率     | Grading Confidence ≥0.8 / <0.5 の集団それぞれで完全一致しなかった割合（較正ゲート） | `summarize_by_provider` |

`tolerance <= 1 点差` を既定とする（設問の配点が小さい場合は採用判断時に見直す）。
集計は `summarize_by_provider()` が (教科, provider, **config**, 入力モード)
ごとに平均し、`to_markdown_table()` が §8 の結果表を生成する（`config` は
§3.3 参照）。集計出力は**件数と平均値のみ**で秘匿情報（答案本文・secret）を
含まない。

**schema violation の扱い**: スキーマ検証に失敗した応答は、自由文 parse で
救済せず、完全一致率・許容点差内率・criterion 一致率の計算対象から除外し
（`None` 扱い）、`schema_violation_rate` にのみ計上する。誤って「0 点」として
不一致率を悪化させることも、逆に無視して精度を過大評価することもしない
（Issue #14 受入条件）。

### 3.1 対応不一致（mismatch）の扱い

応答が schema 検証を通っても、その `questionId` が今比較している正解ラベルと
異なる、または `maxScore` が正解ラベルの `max_score` と食い違う場合は、
`score` の値だけを見て偶然一致しているように見えても**完全一致として数えない**。
例えば別設問への回答（4/100）が配点 5 点の正解ラベル（4/5）と比較され、
生の点数だけを見ると「一致」に見えてしまうケースを防ぐための分類で、
schema violation とは別に `mismatch_rate` として集計する。latency・概算 cost
は対応不一致でも実際に呼び出しが発生している以上そのまま計上するが、
完全一致率・許容点差内率・criterion 一致率・Confidence 平均には算入しない
（`evaluate_sample` の `mismatched` フラグ）。

### 3.2 採点不能な bucket・不完全な計測の扱い

- bucket 内の全応答が schema violation または対応不一致で、採点可能な応答が
  1 件もない場合、完全一致率・許容点差内率は **`0.0` ではなく `-`（未定義）**
  を表示する。`0.0` は「採点した結果 0% しか合っていない」という意味になって
  しまい、「そもそも採点できる応答がなかった」こととは区別できない
  （コードレビュー指摘）。
- latency・概算 cost は、bucket 内の一部の呼び出しにしか記録されていない
  ことがある（例: 一部だけ計測ツールが失敗した）。この場合も p50/p95・平均値
  はコンプリートに見えてしまうため、`latency 計測件数`・`cost 計測件数`
  （「計測できた件数/bucket の総件数」の形式、例: `8/20`）を必ず併記し、
  一部の呼び出しからしか計算されていないことを明示する。件数が bucket の
  総件数と一致しない行は、§8.1 の latency/cost ゲート判定に使う前に
  計測を補完するか、判定を保留する。

### 3.3 provider の設定（config）ごとの分離

同じ `provider` 名でも、記録された `descriptor`（model / version /
**prompt_version** / temperature / structured_output_mode）が異なれば**別の
bucket**として集計する（`auto_scoring.domain.ai_provider.descriptor_key`）。
採点プロンプトのテンプレートだけを変更し、model・version・temperature・
structured_output_mode が同じままでも、別の再現不能な設定として扱う
（コードレビュー指摘: プロンプト版数を含めないと、プロンプトを変えた前後の
結果が同じ bucket にプールされ、再現できない）。`prompt_version` は
プロンプトテキスト自体ではなく、そのテンプレートを指す短い版数タグまたは
ハッシュ値とする（答案本文や長大なプロンプト全文を識別子に含めない）。

同じ provider 名の下で設定違いの記録を 1 行にプールすると、片方が採用基準を
満たし片方が満たさない場合でも平均としては通過して見えてしまう
（コードレビュー指摘）。結果表の `config` 列にこの識別子が表示される。
識別子は `model` / `version` / `prompt_version` / `temperature` /
`structured_output_mode` を JSON 配列としてエンコードしたもの（例:
`["gemini-2.5-flash", "2026-01", "v3", 0.0, "json_schema"]`）で、
`"|"` 区切り文字列は使わない（コードレビュー指摘: 単純な `"|"` 結合は
フィールド値自体に `|` が含まれると衝突しうる。例えば
`model="a|b", version="c"` と `model="a", version="b|c"` が同じ文字列に
なってしまう。JSON 配列エンコードなら各要素が引用符で区切られるため
衝突しない）。この識別子自体にモデル名などを通じて `|` が含まれる場合に
備え、Markdown 描画時はセル区切りと混同されないよう `|` を `\|` に
エスケープする（そのまま Markdown として貼り付けても列がずれない）。
schema violation で終わった記録も、失敗する前に `descriptor` を読み取って
から集計するため、どの設定が失敗したかが追跡できる。`descriptor` 自体は
`auto_scoring.domain.ai_provider.parse_provider_descriptor`（strict な
Pydantic モデル）で検証し、値をコンストラクタで型キャストしない
（コードレビュー指摘: 素朴な `str(raw["model"])`/`float(raw["temperature"])`
は `model: null` を文字列 `"None"` に、`temperature: true` を `1.0` に
変換してしまい、再現できない設定を「有効」として受理してしまう）。

### 3.4 criterion 一致率の分母（正解ラベル基準）

criterion 一致率の分母は**正解ラベルに存在する criterion の数**であり、
応答が返した criterion の数ではない（コードレビュー指摘）。正解ラベルに
`c1`・`c2` があるのに、応答が `c1` しか返さない場合、分母を 2 のまま保ち、
`c2` は「応答なし＝不一致」として扱う。応答の `c1` だけを分母にして
「100% 一致」と報告すると、provider は難しい criterion を省略するだけで
85% 以上の採用ゲート（§8.1）を通過できてしまう。逆に、正解ラベルに
存在しない criterion（意図的に記録されなかった人間ラベル）を応答が
追加で返しても、分母にも分子にも数えず無視する。

### 3.5 記録済み `input` の検証（正解ラベルとの整合性）

各サンプルの `input`（`prompt_text`/`model_answer`/`rubric_text`/
`max_score`/`ocr_clean`/`ocr_noisy`）は、そのサンプルの `recorded` を
1 セルでも集計する前に必ずパースし、`ground_truth.max_score` と一致するかを
確認する（`auto_scoring.domain.ai_grading_metrics.GradingInputRecord` +
`validate_input_matches_truth`）。一致しない場合、またはそもそも `input`
ブロックが欠落・型不正の場合はハーネスを停止する（コードレビュー指摘:
`input` を一切検証しないと、記録された応答が正解ラベルの得点とたまたま
一致しさえすれば、実際には異なる配点・採点基準の設問を比較していても
「同一データでの比較」として通ってしまう）。

### 3.6 wire フォーマットの alias 厳格化

`AIGradingResult`/`GradingOutput` は `populate_by_name` を有効にしない。
ドキュメント化された wire フォーマットは camelCase（`questionId`/
`maxScore`）のみで、Python 形式の `question_id`/`max_score` を受理しない
（コードレビュー指摘: `populate_by_name=True` のままだと、ドキュメントと
異なるフィールド名を返す非準拠な provider 応答も schema 検証を通過して
しまい、schema violation 率を過小評価する）。

---

## 4. repro command

### 4.1 秘匿情報なしの集計再現（credentials 不要・いつでも実行可）

```bash
cd backend
uv run python poc/issue_14_ai_grading/report.py
```

同一の入力（`tests/fixtures/ai_grading/*.json`）から §8 と同じ形式の集計表が
再生成されることを確認する。スキーマ検証・contract test・メトリクス計算自体の
検証は:

```bash
cd backend
uv run pytest tests/test_ai_grading_schema.py tests/test_ai_provider_contract.py tests/test_ai_grading_metrics.py
```

### 4.2 実データでの評価（credentials + 評価データセット必要）

```bash
cd backend
# 1) backend/.env.local に §7 の credentials を設定
# 2) 評価データセット（人手書き起こし + 人間正解ラベル）をローカルへ配置
uv run python poc/issue_14_ai_grading/report.py --dataset "<local eval-dataset dir>" --out poc-2-results.md
```

`--dataset` に本 PoC の予備調査データ（§6、5 件）を指定すると、現時点では
`recorded`（AI 応答）が空のため **`evaluated cells: 0`** と
**`staged ground truth with no provider recorded anywhere in the dataset: 5`**
が出力される（credentials 未整備を推測で埋めない設計。§6.2 参照）。実 AI
呼び出しの live-provider パスは、credentials が揃い次第、**Issue #14 を閉じる
前に本 PoC へ追加する**（§7.3）。呼び出し時も request/response 本文はログに
残さない。

ハーネスが比較対象とする provider × 入力モードの組は、データセット全体に
一度でも記録された provider 名 × `ocr_clean`/`ocr_noisy` の全組み合わせ
（期待される比較マトリクス）である。ある答案でその組がまだ記録されて
いなければ「pending」として明示し、単に走査対象から漏れて比較が完了した
ように見えることを防ぐ（Issue #14 受入条件: 最低 2 候補・両入力モード）。

データセット全体を通じて「同じ答案上で実際に応答を記録した provider」が
**2 種類未満**の場合、ハーネスは集計表を出さず `SystemExit`（非ゼロ終了）で
明示的に拒否する（コードレビュー指摘: 単一候補しか記録されていないのに
`evaluated cells: 0` の空表が正常終了し、あたかも比較が完了したかのように
見えてしまう不具合の修正。空のプレースホルダ entry や、互いに素な答案にしか
応答がない 2 候補も、この判定では候補として数えない）。実データ収集の途中で
1 候補分しか live-provider 呼び出しをまだ終えていない場合、または 2 候補が
まだ同じ答案で揃っていない場合は、条件を満たしてから再実行する。

---

## 5. 期待結果

- §4.1 が **exit 0** で、教科・provider・入力モードごとの行を持つ Markdown 表を
  標準出力に出す。
- §4.1 の pytest が全て pass する（スキーマ検証・contract test・メトリクスが
  人手ラベルから算出されている、schema violation が正しく検知される）。
- §4.2（予備調査データ、`recorded` 空）は `evaluated cells: 0` /
  `staged ground truth with no provider recorded anywhere in the dataset: 5`
  を出し、非ゼロ終了やクラッシュをしない。
- 実データ評価（credentials 整備後）では、`ocr_noisy` 入力で
  Recognition Confidence が下がる一方、Grading Confidence・criterion 一致率が
  それに連動して不当に変化しない（＝OCR誤りとAI採点判断の混同がない）ことが
  観測される。

---

## 6. 実測値

### 6.1 合成フィクスチャでの疎通確認（精度評価ではない）

```
# uv run python poc/issue_14_ai_grading/report.py の出力（合成データ / 参考値のみ）
evaluated cells: 12

| 教科 | provider | config | 入力 | 件数 | 完全一致率 | 許容点差内率 | criterion一致率 | 平均Recognition Conf | 平均Grading Conf | schema違反率 | 対応不一致率 | p50 latency(s) | p95 latency(s) | latency計測件数 | 概算cost(USD/1000問) | cost計測件数 | 高Conf誤り率(>=0.8) | 低Conf誤り率(<0.5) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| synthetic-history | synthetic-a | ["synthetic-model-a", "2026-01-pilot", "synthetic-prompt-v1", 0.0, "json_schema"] | ocr_clean | 2 | 1.000 | 1.000 | 1.000 | 0.975 | 0.920 | 0.000 | 0.000 | 0.900 | 1.080 | 2/2 | 0.65 | 2/2 | 0.000 | - |
| synthetic-history | synthetic-a | ["synthetic-model-a", "2026-01-pilot", "synthetic-prompt-v1", 0.0, "json_schema"] | ocr_noisy | 2 | 0.000 | 1.000 | 1.000 | 0.620 | 0.780 | 0.500 | 0.000 | 1.100 | 1.280 | 2/2 | 0.65 | 2/2 | - | - |
| synthetic-history | synthetic-b | ["synthetic-model-b", "2026-01-pilot", "synthetic-prompt-v1", 0.2, "tool_use"] | ocr_clean | 2 | 1.000 | 1.000 | 1.000 | 0.990 | 0.950 | 0.500 | 0.000 | 0.700 | 0.880 | 2/2 | 0.25 | 2/2 | 0.000 | - |
| synthetic-history | synthetic-b | ["synthetic-model-b", "2026-01-pilot", "synthetic-prompt-v1", 0.2, "tool_use"] | ocr_noisy | 2 | 0.000 | 0.500 | 0.600 | 0.475 | 0.510 | 0.000 | 0.000 | 1.200 | 1.380 | 2/2 | 0.25 | 2/2 | - | 1.000 |
| synthetic-world-history | synthetic-a | ["synthetic-model-a", "2026-01-pilot", "synthetic-prompt-v1", 0.0, "json_schema"] | ocr_clean | 1 | 1.000 | 1.000 | 1.000 | 0.950 | 0.700 | 0.000 | 0.000 | 1.000 | 1.000 | 1/1 | 0.70 | 1/1 | - | - |
| synthetic-world-history | synthetic-a | ["synthetic-model-a", "2026-01-pilot", "synthetic-prompt-v1", 0.0, "json_schema"] | ocr_noisy | 1 | 0.000 | 0.000 | 0.500 | 0.550 | 0.500 | 0.000 | 0.000 | 1.100 | 1.100 | 1/1 | 0.70 | 1/1 | - | - |
| synthetic-world-history | synthetic-b | ["synthetic-model-b", "2026-01-pilot", "synthetic-prompt-v1", 0.2, "tool_use"] | ocr_clean | 1 | 0.000 | 0.000 | 1.000 | 0.950 | 0.650 | 0.000 | 0.000 | 1.600 | 1.600 | 1/1 | 0.20 | 1/1 | - | - |
| synthetic-world-history | synthetic-b | ["synthetic-model-b", "2026-01-pilot", "synthetic-prompt-v1", 0.2, "tool_use"] | ocr_noisy | 1 | 0.000 | 0.000 | 0.500 | 0.500 | 0.900 | 0.000 | 0.000 | 0.800 | 0.800 | 1/1 | 0.20 | 1/1 | 1.000 | - |
```

`config` 列は `model`/`version`/`prompt_version`/`temperature`/
`structured_output_mode` を JSON 配列としてエンコードしたもの
（`descriptor_key`。§3.3）で、本合成データではフィクスチャに埋め込んだ
架空の設定（`synthetic-model-a`/`synthetic-model-b`、
`synthetic-prompt-v1`）をそのまま表示している。`latency計測件数`・
`cost計測件数` はすべて `n/n`（bucket の全件で計測済み）で、本合成データ
には計測欠損を意図的に混ぜていない。

合成データの `synthetic-b`/`synthetic-world-history`/`ocr_noisy` セルは、
「Recognition Confidence が低いのに Grading Confidence が高いまま、実際には
読み取れる内容を一律 0 点にした」という、Grading Confidence の較正不良を
意図的に再現した例である（`tests/fixtures/ai_grading/sample-02.json` の
`synthetic-b`/`ocr_noisy`）。この行の「高Conf誤り率」が 1.000（完全一致 0 件を
高 Confidence で出した）であることが、まさに §8.1 の較正ゲートが検出すべき
逆転パターンである。これは本物のモデル挙動ではなく、メトリクスがこの種の
不整合を検出できることを示すためのフィクスチャ。

「対応不一致率」（`mismatch_rate`）は本合成データではすべて 0（`questionId`/
`maxScore` が正解ラベルと一致しないセルを作っていない）。この列が非ゼロに
なるのは、応答が別の設問へのものだったり点数スケールが食い違ったりした
場合で、その場合も完全一致率・許容点差内率へは加算しない
（`evaluate_sample` が `mismatched` として別集計するため）。cost は
採用ゲート（§8.1）と同じ単位（設問 1,000 問あたり USD）で表示する。

### 6.2 実データ予備調査（pilot） — 統計的な採用根拠にはならない

プロジェクトオーナーが用意した、日本史・世界史の添削模擬課題の資料
（論理パス `"<提供元ローカル環境>/添削データ/"` 配下、決定書 §6.5 に準じ
本書には絶対パスを記載しない）から、各教科 1 テスト・問 1 のみを対象に、
実際の設問文・模範解答・採点基準・添削サンプル（人間添削者による実採点）
を本エージェントが直接読み、個人情報を除去したうえで手作業で書き起こした。
件数は次のとおり。

| 教科   | テスト数 | 設問数       | 答案数（添削サンプル件数） | 決定書 §6.2 下限         |
| ------ | -------- | ------------ | -------------------------- | ------------------------ |
| 日本史 | 1        | 1（問1のみ） | 3                          | 30 答案以上              |
| 世界史 | 1        | 1（問1のみ） | 2                          | 30 答案以上              |
| 合計   | 2        | のべ2        | 5                          | 60 答案・のべ300設問以上 |

**この件数は決定書 §6.2 の下限に遠く及ばない。** 統計的に意味のある
完全一致率・許容点差内率・criterion 別一致率を主張できる規模ではなく、
**予備調査（pilot）**として次の限定的な目的にのみ使う。

1. ハーネス（`report.py --dataset`）が実データレイアウトで確かに動作するかの
   疎通確認（§4.2 のとおり `evaluated cells: 0` / `staged: 5` を確認済み）。
2. 実際の採点マニュアルがどのような構造を持つかの観察（下記）。
3. credentials 整備後、最初に実 AI 呼び出しを試す最小データセットとしての
   再利用。

**観察できた知見（統計的判断ではなく、設計上の参考情報）**:

- 日本史の採点基準は「少数（6 項目）・各項目 2〜5 点」という**重み付き
  criterion 型**だった。世界史の採点基準は「多数（約 11 項目）・各項目
  多くは 3 点・上限キャップ 30 点」という**加点チェックリスト型**で、
  項目の合計が満点を超える設計だった。両者は rubric の形が大きく異なり、
  `AIProvider` へ渡す `rubric_text` の解釈（採点基準の構造化）は教科ごとに
  一様ではない可能性が高い。これは AI モデル選定だけでなく、将来の
  rubric 入力設計（簡易設計書 §9.1）にも影響しうる観察であり、正式な
  データセットで再確認する必要がある。
- 対象の添削済み PDF には、スキャナ側が埋め込んだ低品質な OCR テキスト層が
  含まれており、実際の手書き内容と食い違う語（例: 「統治」を「純治」、
  「中央」を「中史」と誤認識）が見られた。これは Issue #19（OCR パイプライン）
  の設計に関わる知見で、スキャナ内蔵 OCR 層をそのまま信頼してはならない
  ことを示している。

**正解ラベルの限界（決定書 §6.3 未充足の明記）**: 本予備調査は本エージェント
1 名による単独の書き起こし・単独の採点結果読み取りであり、決定書 §6.3 が
要求する「現役採点者 2 名の独立採点・不一致時の合議」を満たさない。
そのため各サンプルの `criteria`（criterion 別正解ラベル）は記録せず、
大きく明瞭に印字された**設問ごとの合計得点のみ**を正解ラベルとした
（`Auto-Scoring-eval-datasets/poc-2-ai-grading/*.json` の
`_pilot_metadata.criteria_omitted_reason` に理由を記録）。答案テキストの
書き起こしも単独読み取りであり、独立検証していない
（`transcription_confidence: single_reader_best_effort_ai_vision_reading`）。

実データは一切リポジトリにコミットしていない（§11）。ローカルの保管場所は
決定書 §6.5 に準じ、本書には論理パスのみを記載する
（`Auto-Scoring-eval-datasets/poc-2-ai-grading/` 配下、このワークツリー外）。

### 6.3 実 AI プロバイダでの実測

**未実施。** credentials（§7）と実 AI アダプタが未整備のため。credentials が
揃い次第、§6.2 の予備調査データおよび（可能であれば）決定書 §6.2 の下限を
満たす追加データで実測し、§8 の表を埋める。

---

## 7. credentials と rate limit

### 7.1 credentials 設定方法

`.env.example` の「AI grading PoC 2」節を参照。API キーは **Python サイドカー
側のみ**が保持し（technology-stack.md §2）、`backend/.env.local`（git 無視）
または OS キーチェーン（`keyring`）に置く。リポジトリ・ログ・Issue・
スクリーンショットに含めない（`AGENTS.md`「Security」）。

| 候補     | 必要な設定                                                        |
| -------- | ----------------------------------------------------------------- |
| `gemini` | `AUTO_SCORING_GEMINI_API_KEY` + `AUTO_SCORING_GEMINI_MODEL`       |
| `claude` | `AUTO_SCORING_ANTHROPIC_API_KEY` + `AUTO_SCORING_ANTHROPIC_MODEL` |
| `gpt`    | `AUTO_SCORING_OPENAI_API_KEY` + `AUTO_SCORING_OPENAI_MODEL`       |

温度は `AUTO_SCORING_AI_GRADING_TEMPERATURE`（既定 0.0）で全候補共通に揃え、
再現性を確保する（Issue #14「再現条件」）。プロンプトテンプレートは
バージョン管理し、`ProviderDescriptor.prompt_version` に版数タグまたは
ハッシュ値を記録する（§3.3）。外部送信は**生徒識別情報を除いた設問単位
データ（当該設問の答案画像切り出し + OCR テキスト + 問題文 + 模範解答 +
採点基準）だけ**に限定する（決定書 §2 (2)）。可能なら各サービスの
データ保持オプトアウト／ゼロデータ保持を有効にする（決定書 §6.6）。

### 7.2 rate limit 時の扱い（暫定。最終値は §3 E = Issue で確定）

- 指数バックオフ（初期 1s、上限 32s、最大 5 回）で再試行する。
- 恒常的な 429 / quota 超過は**失敗として記録**し、推測で埋めない。当該設問は
  「要確認」に落とす（`ProviderUnavailable`。§9.2）。
- PoC のハーネスは逐次実行（並列度 1）を既定とする。MVP の並列度は本 PoC 後に
  確定する（決定書 §3 E）。

### 7.3 実測前に本 PoC へ追加するもの

- 比較する各候補の `AIProvider` 実アダプタ（Gemini / Claude / GPT）。
- 各アダプタ用の `AIProviderContract` サブクラス（実キーは CI に置かず、
  ローカル／手動実行のマーカー付きテストにする）。
- `poc/issue_14_ai_grading/report.py` の live-provider パス（設問 →
  `AIProvider.grade()` → `AIGradingResult` 録画、`--live` 相当のオプション）。
  録画する各セルには `descriptor`（model/version/**prompt_version**/
  temperature/structured_output_mode）を必ず含める。ハーネスはこの記録済み
  メタデータを読むだけで、`provider` 名から決め打ちしない（Issue #14
  「再現条件」。同じ provider 名でも設定が違う録画は区別できなければ
  ならない）。`latency_seconds`/`cost_usd` は有限かつ非負でなければ
  ハーネスが録画時点で拒否する（§3.2）。

実測・選定後は §10 に従い、不採用アダプタを削除して採用アダプタだけを MVP へ
昇格する。

---

## 8. 採用基準と結果表

### 8.1 採用基準（この値を満たせば当該候補を MVP の `AIProvider` 第一候補にできる）

「完全一致率」「許容点差内率」を最重視する（人間採点との一致度が本 PoC の
主目的のため）。schema violation は 1 件でも自由文救済してはならず、率として
低いことを求める。

| 指標                 | 閾値                                                                          |
| -------------------- | ----------------------------------------------------------------------------- |
| 完全一致率           | ≥ 60%                                                                         |
| 許容点差内率（±1点） | ≥ 90%                                                                         |
| criterion 別一致率   | ≥ 85%                                                                         |
| schema violation 率  | ≤ 1%                                                                          |
| 対応不一致率         | 0%（1 件でも発生したら harness/adapter 側の実装不良として原因調査を優先する） |

共通条件:

- latency: p50 ≤ 5s、p95 ≤ 12s（1 設問あたり）。
- 概算 cost: ≤ 3 USD / 1,000 設問（第一候補）。
- Grading Confidence の較正: 高 Grading Confidence（≥ 0.8）でありながら
  完全一致しない割合が、低 Grading Confidence（< 0.5）でありながら完全一致
  しない割合を明確に上回らないこと（較正が完全に逆転していないことの
  最低限の確認。厳密な較正基準は §3 (C) の閾値確定と合わせて後続 Issue で
  精緻化する）。
- schema violation は自由文 parse で救済しない。`SchemaViolation` として
  「要確認」へ送ることを contract test で検証する。
- 完全一致率・許容点差内率が `-`（未定義。§3.2）の bucket は、閾値を「満たした」
  とも「満たさなかった」とも判定しない。採点可能な応答が 1 件もない設定であり、
  採用判断の対象外として原因（schema violation・対応不一致の内訳）を先に
  調査する。
- latency（p50/p95）・概算 cost のゲート判定は、`latency 計測件数`・
  `cost 計測件数`（§3.2）が bucket の `件数` と一致している行にのみ適用する。
  一致しない行は計測が不完全なため、閾値を満たしているように見えても
  そのままでは採用根拠にしない。
- 同じ `provider` 名でも `config` 列（§3.3）が異なれば別の判定対象として扱う。
  ある設定が閾値を満たし、別の設定が満たさない場合、`provider` 単位ではなく
  `config` 単位で採用可否を記録する。

### 8.2 結果表（実測は本 PoC クローズ時に記入）

`uv run python poc/issue_14_ai_grading/report.py` の実データ実行結果をそのまま
貼り付ける（列は `to_markdown_table` の出力に準拠。cost は 1,000 設問あたり。
`config` は §3.3 の識別子、`latency件数`/`cost件数` は §3.2 の計測件数）。

| provider         | config | 教科   | 入力        | 完全一致率 | 許容点差内率 | criterion一致率 | schema違反率 | 対応不一致率 | p50 latency | p95 latency | latency件数 | cost/1k | cost件数 | 平均Recognition Conf | 平均Grading Conf | 高Conf誤り率 | 低Conf誤り率 |
| ---------------- | ------ | ------ | ----------- | ---------- | ------------ | --------------- | ------------ | ------------ | ----------- | ----------- | ----------- | ------- | -------- | -------------------- | ---------------- | ------------ | ------------ |
| `gemini`         | _TBD_  | 日本史 | `ocr_clean` | _TBD_      | _TBD_        | _TBD_           | _TBD_        | _TBD_        | _TBD_       | _TBD_       | _TBD_       | _TBD_   | _TBD_    | _TBD_                | _TBD_            | _TBD_        | _TBD_        |
| `gemini`         | _TBD_  | 日本史 | `ocr_noisy` | _TBD_      | _TBD_        | _TBD_           | _TBD_        | _TBD_        | _TBD_       | _TBD_       | _TBD_       | _TBD_   | _TBD_    | _TBD_                | _TBD_            | _TBD_        | _TBD_        |
| `gemini`         | _TBD_  | 世界史 | `ocr_clean` | _TBD_      | _TBD_        | _TBD_           | _TBD_        | _TBD_        | _TBD_       | _TBD_       | _TBD_       | _TBD_   | _TBD_    | _TBD_                | _TBD_            | _TBD_        | _TBD_        |
| `gemini`         | _TBD_  | 世界史 | `ocr_noisy` | _TBD_      | _TBD_        | _TBD_           | _TBD_        | _TBD_        | _TBD_       | _TBD_       | _TBD_       | _TBD_   | _TBD_    | _TBD_                | _TBD_            | _TBD_        | _TBD_        |
| `claude` / `gpt` | _TBD_  | 日本史 | `ocr_clean` | _TBD_      | _TBD_        | _TBD_           | _TBD_        | _TBD_        | _TBD_       | _TBD_       | _TBD_       | _TBD_   | _TBD_    | _TBD_                | _TBD_            | _TBD_        | _TBD_        |
| `claude` / `gpt` | _TBD_  | 日本史 | `ocr_noisy` | _TBD_      | _TBD_        | _TBD_           | _TBD_        | _TBD_        | _TBD_       | _TBD_       | _TBD_       | _TBD_   | _TBD_    | _TBD_                | _TBD_            | _TBD_        | _TBD_        |
| `claude` / `gpt` | _TBD_  | 世界史 | `ocr_clean` | _TBD_      | _TBD_        | _TBD_           | _TBD_        | _TBD_        | _TBD_       | _TBD_       | _TBD_       | _TBD_   | _TBD_    | _TBD_                | _TBD_            | _TBD_        | _TBD_        |
| `claude` / `gpt` | _TBD_  | 世界史 | `ocr_noisy` | _TBD_      | _TBD_        | _TBD_           | _TBD_        | _TBD_        | _TBD_       | _TBD_       | _TBD_       | _TBD_   | _TBD_    | _TBD_                | _TBD_            | _TBD_        | _TBD_        |

### 8.3 人間採点との不一致例（実測後に記入）

_本 PoC クローズ時、実 AI 応答と人間正解ラベルの不一致（criterion 単位）を
最低 3 件、答案本文を含めない形（`questionId` と得点差・criterion 差分のみ）
で記入する。_

---

## 9. 基準未達時の扱い（「実装段階で判断」に倒さない）

結果が §8.1 を満たさない場合、以下を**この PoC の追記**として確定する。

### 9.1 追加検証条件

1. schema violation 率のみ未達なら: プロンプトの出力例（few-shot）を追加し、
   構造化出力モード（JSON Schema / tool-use）の設定を見直して再測定する。
2. 完全一致率・許容点差内率が未達なら: 決定書 §6.2 規模（2 教科 × 各 30 答案
   以上）のデータセットで再測定し、rubric の与え方（教科ごとの構造差、§6.2 の
   観察参照）を見直す。
3. `ocr_noisy` で Grading Confidence が Recognition Confidence の低下に
   引きずられて崩れる場合: プロンプトで両者を明示的に分離させる指示を追加し、
   再測定する。

### 9.2 MVP の手動採点 fallback（基準未達が解消しない場合の既定動作）

- 採用 AI が低 Grading Confidence または schema violation を返した設問は、
  **自動確定しない**。UI に「採点要確認」を表示し（簡易設計書 §8.2 相当）、
  人間が模範解答・採点基準を見て採点する導線を MVP に含める。
- 基準未達が解消しないまま MVP 実装に進む場合、AI 採点は**候補提示のみ**とし
  （決定書 §2 (17)）、人間の承認なしに点数・コメントを確定・PDF 出力しない。
- 「どのくらいの割合が手動確認に回るか」を §8 の schema violation 率＋低
  Grading Confidence 率から見積もり、MVP のリリースノートに記載する。

### 9.3 採用 provider/model・fallback・再試行条件・cost 上限の決定（本 PoC クローズ時に確定）

| 決定項目                        | 記入欄                                                           |
| ------------------------------- | ---------------------------------------------------------------- |
| 採用 provider/model（第一候補） | _本 PoC クローズ時に確定（実測が §8.1 を満たした候補から選定）_  |
| fallback                        | _未確定（候補: 第一候補が利用不能時に第二候補へ切替）_           |
| 再試行条件                      | §7.2 を確定値として採用（バックオフ + 失敗記録 + 要確認落ち）    |
| cost 上限                       | _未確定（§8.1 の 3 USD/1,000 設問を暫定上限とし、実測後に確定）_ |

---

## 10. 昇格条件（Issue #14）

本 PoC から MVP 実装へ昇格するのは次のみ:

- 採用された `AIProvider` アダプタ（1 つ、または fallback を含めて 2 つ）。
- `AIProvider` の contract test（`AIProviderContract` と採用アダプタ用サブクラス）。
- `domain/ai_grading.py`（Pydantic スキーマ）と `domain/ai_provider.py`
  （ポート・型）、`domain/ai_grading_metrics.py`（Grading Confidence の
  継続評価に使う）。

昇格しないもの: 不採用候補のアダプタ、`poc/` 配下のハーネス、合成フィクスチャ、
`_ReplayAIProvider` などのテスト専用スキャフォールド。不採用アダプタは削除する
（Issue #14 受入条件）。

---

## 11. コミット禁止（決定書 §6.7 / §7.1 再掲）

- 実際の生徒答案・採点基準・添削サンプルの PDF・スキャン画像
- 氏名・生徒 ID・学校名・塾名などの識別情報
- 人間の正解ラベルの実データ（実採点値・実書き起こし）
- AI API の request/response 本文、`app-data/` の中身
- 評価データセットの保管先の絶対パス・認証情報

### 11.1 コミット前チェックリスト（本 PoC 固有）

- [ ] `git status` に `Auto-Scoring-eval-datasets/` や答案 PDF・画像が出ていない
- [ ] docs 内の実測記述に生徒答案本文が引用されていない（設問構造・件数・
      統計値のみ）
- [ ] `.env.example` に実キーが含まれていない（プレースホルダのみ）
- [ ] 合成フィクスチャ（`tests/fixtures/ai_grading/`）に実データ・実ベンダー名
      が混入していない
