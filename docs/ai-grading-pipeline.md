# 本番AI採点パイプライン

GitHub Issue [#20](https://github.com/HIKARU0627/Auto-Scoring/issues/20)（親
[#3](https://github.com/HIKARU0627/Auto-Scoring/issues/3)）。問題文・設問画像・
OCR結果・模範解答・rubric・配点から構造化された採点候補を生成し、人間確認前の
提案として保存する本番パイプラインを実装する。

依存: [#26](https://github.com/HIKARU0627/Auto-Scoring/issues/26)（設問依存関係
DAG。`auto_scoring.domain.dependency_graph`）、[#16](https://github.com/HIKARU0627/Auto-Scoring/issues/16)
（テスト登録・プロファイル）、[#19](https://github.com/HIKARU0627/Auto-Scoring/issues/19)
（OCR認識パイプライン。`RecognitionJobProcessor`）、[#14 PoC 2](https://github.com/HIKARU0627/Auto-Scoring/issues/14)
（`AIProvider`契約・構造化出力スキーマ・メトリクスパイプライン。
`domain/ai_grading.py`・`domain/ai_provider.py`・`domain/ai_grading_metrics.py`）。

対象外: 人間レビュー操作（承認/修正/却下UI・API）とPDF描画は後続Issueで扱う。

## 決定事項

### AIモデル: 優先度つきフォールバック（業務ルール §3 (B)、Issue #81 で確定）

Issue #20 の実装時点では §3 (B) は未確定で、既定の`AIProvider`を
`NullAIProvider`（当時の`adapters/ai/null_provider.py`）に置いた。この既定は
Issue #97 で無くなっている（下記「アプリ本体への接続」）。
[Issue #81](https://github.com/HIKARU0627/Auto-Scoring/issues/81)で
プロジェクトオーナーが確定した内容は**単一モデルの選択ではない**:

| 優先度 | provider                             | 現状のアダプタ                                            |
| ------ | ------------------------------------ | --------------------------------------------------------- |
| 1      | Gemini API（Vertex AI + ADC）        | `adapters/ai_grading/vertex_gemini_provider.py`（#35）    |
| 2      | Codex App Server                     | `adapters/ai_grading/codex_app_server_provider.py`（#44） |
| 3      | OpenRouter（オープンウェイトモデル） | `adapters/ai_grading/openrouter_provider.py`（#44）       |
| 4      | OpenAI API                           | `adapters/ai_grading/openai_provider.py`（#35）           |

上から順に試し、失敗したら次へ落とす。本Issue（#81）はこの層をどこに置くかの設計を
記録するところまでだった。**設計どおりの実装は Issue #35 で完了している**:
合成アダプタ `adapters/ai_grading/fallback_provider.py` の `FallbackAIProvider` と、
`AUTO_SCORING_AI_GRADING_TRANSPORT` をカンマ区切りの優先度リストとして読む
`create_ai_provider()`。4 経路すべての live 疎通は
[`poc-2-ai-grading.md`](./poc-2-ai-grading.md) §7.4 に記録した。

なお ① は **Vertex AI 経由**である。Gemini の **API キーは組織ポリシーで禁止**されて
いるため、認証は Application Default Credentials（ADC）に限られる。GCP プロジェクト ID
は ADC から実行時に読むので、リポジトリには一切保存しない
（`adapters/ai_grading/_google_adc.py`）。

#### 層の置き場所: `AIProvider`ポートの内側の合成アダプタ

フォールバックは**`AIProvider`を実装する合成アダプタ**（順序つきの子アダプタ列を持ち、
`grade()`で順に試す）として`adapters/ai_grading/`に置く。`GradingJobProcessor`にも
`domain/ai_provider.py`のポート定義にも、キューにも手を入れない。理由:

- `GradingJobProcessor`側に置くと、「1回のprovider呼び出し」という前提で書かれている
  手順6〜8（`asyncio.to_thread`、DBトランザクションを保持しない、応答検証）に
  provider選択のループが混ざり、processorが採点手順とprovider運用の両方を持つことになる。
- キューのretry層に置くと、フォールバックのたびにJobの`attempt`を消費し、
  「同じproviderへのbackoff付きretry」と「別providerへの切り替え」が区別できなくなる。
  この2つは意味が違う（前者はレート制限の回復待ち、後者は回復を待たない切り替え）。
- 合成アダプタなら`AIProviderContract`（`backend/tests/test_ai_provider_contract.py`）を
  そのまま満たす1つのサブクラスとしてテストでき、`create_app(ai_provider=...)`の
  注入経路も既存のまま使える。

`create_ai_provider()`（`adapters/ai_grading/factory.py`）は
`AUTO_SCORING_AI_GRADING_TRANSPORT`を**カンマ区切りの優先度リスト**として受け取り
（既定の並びは `gemini,codex_app_server,openrouter,openai`）、**認証情報が揃っている
ものだけをチェーンに組む**（揃っていないproviderで失敗を1段消費しない。#35 で実装）。
1つも揃っていなければ空のチェーンを作らず`AIProviderConfigError`で落とす
（「設定済みに見えるのに1問も採点しない」状態を作らないため）。値が1つだけのときは
チェーンを作らずそのアダプタ自体を返すので、既存の呼び出し・`.env.local`はそのまま
動く。認証情報の持ち方は既存方針どおり`.env.example` / `backend/.env.local`で、
実キーはコミットしない（Gemini は鍵ではなく ADC）。

#### どの失敗で次へ落とすか

`GradingJobProcessor`が既に分類している例外（後述「エラー分類」）を、そのまま
フォールバックの判断にも使う。新しい例外型は追加しない。

| 失敗                                                          | 次のproviderへ落とす | 理由                                                                                                                                                                          |
| ------------------------------------------------------------- | -------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ProviderRateLimitedError`（429）                             | 落とす               | そのproviderの枠が空くのを待つより、別providerで進む方が速い                                                                                                                  |
| `ProviderServerError`（5xx）                                  | 落とす               | provider側の障害。同じ相手へのretryは同じ結果になりやすい                                                                                                                     |
| `ProviderTimeoutError`                                        | 落とす               | 同上。ただし1 provider内でのretryは行わず、1回で次へ落とす                                                                                                                    |
| `SchemaViolation`（構造化出力に従わない）                     | 落とす               | モデル固有の能力差。同じモデルへ再送しても直らないが、別モデルなら通りうる                                                                                                    |
| 認証情報不足・設定不正（`AIProviderConfigError`）             | チェーン構築時に除外 | 実行時ではなく組み立て時に落とす（上記）。Codex App Server は鍵を持たないが、`codex` 実行ファイルが無いホストでは同じく構築時に除外する（無ければ確実に失敗する段を残さない） |
| 素の`ProviderUnavailable`（実行時の401/4xx・transport error） | 落とす               | 表に無い経路。構築時には有効だった認証情報が呼び出し時に拒否される場合であり、チェーンが存在する理由そのもの                                                                  |
| 応答の対応不一致（手順7、criterion id不一致）                 | 落とさない           | ポートの外（processor）で判定するため合成アダプタからは見えない。現状どおり`PERMANENT`                                                                                        |

**上表に無い例外はチェーンを止める。** 上表はポート（`domain/ai_provider.py`）が
宣言している例外がすべてなので、それ以外はアダプタの不具合であって provider の
障害ではない。不具合を迂回すると、同じ壊れ方が毎回同じアダプタで起き続けるのに
誰も気づかないまま第2候補で動き続けることになる。落とす判断は1か所（合成アダプタの
`except`）に固定し、**任意のリモート応答を宣言済みの2例外へ変換する責任はアダプタ
境界に置く**（各アダプタの contract test にある malformed envelope のテスト）。

チェーンを全部使い切ったときは、**最後に観測した例外をそのまま送出する**。
`ProviderRateLimitedError` / `ProviderServerError` / `ProviderTimeoutError` は
既存のマッピングどおりretry対象の`ErrorCategory`になるので、全provider不調のときは
Jobがbackoffして再投入される（並列数の既定4に対するレート制限の受け皿は
business-rules-and-evaluation-data.md §3.1 E のとおり引き続き必要）。全providerが
`SchemaViolation`なら`PERMANENT`となり、人手に回る。

#### どのproviderで採点したかを残す

`GradeResult.provider` / `model` / `prompt_version`（Issue #20で追加済み、
`domain/models.py`）が既にこの記録である。合成アダプタは**成功した子アダプタの
`ProviderDescriptor`をそのまま返す**（合成アダプタ自身の名前で上書きしない） --
再現性と、後からの一致率比較（provider別集計、`domain/ai_grading_metrics.py`）が
provider単位で成立するのはこの1点にかかっている。スキーマ変更は不要。

#### アプリ本体への接続（Issue #97 で完了）

Issue #20 は本番**パイプライン**（境界・schema検証・永続化・分類・Confidence運用・
前提設問contextの受け渡し）を実装し、`create_app()`の`job_processor`既定値を
`RecognitionJobProcessor`（Issue #19）から`GradingJobProcessor`（後述、
`RecognitionJobProcessor`を内部で合成する）へ置き換えた。ただし、その
`GradingJobProcessor`が呼ぶ`ai_provider`の既定値は`NullAIProvider`のままで、
`create_ai_provider()`（Issue #35 で完成）には**呼び出し側が存在しなかった**。
Issue #80 で取込のあと採点ジョブが起票されるようになっても、そのジョブは
何もしなかった。Issue #97 がこれを繋いだ。

**どこで環境を読むか: `create_app()` ではなく composition root（`api/sidecar.py`
の `run()`）。** `create_app()` の中で`os.environ`を読むと、アプリを組み立てる
テスト全部が「そのマシンにたまたま入っている設定」を引き継ぐ -- `gcloud` ログイン
のある開発機と無い CI runner で結果が変わる。これは Issue #35 で実際に CI を
落とした失敗そのものであり、`docs/quality-gates.md`「ホストを見る判定はテストへ
注入する」が禁じている形である。`run()` が
`api.app.build_ai_provider(os.environ)` を呼び、結果を
`create_app(ai_provider=...)` へ渡す。実環境は1つしか無い場所で1回読む。

**認証情報が1つも無いホスト: 起動する。ただし黙らない。**
`create_ai_provider()`は`AIProviderConfigError`で落ちるが、`build_ai_provider()`
はそれを**状態**へ変換する -- 採点以外（取込・レビュー・PDF出力）はプロバイダを
必要としないのに、鍵が無いという理由でその3つまで失うのは、採点できないことより
はるかに悪い失敗であるため。

| 決めたこと                                       | そうした理由                                                                                                                                                                                                               |
| ------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `NullAIProvider`を`UnconfiguredAIProvider`へ置換 | `NullAIProvider`は score 0・confidence 0.0 の`GradeResult`を**永続化する**。レビュー画面では「実プロバイダが答案を読んで0点を付けた」と見分けがつかない。これがこの Issue の消したかった「AIが採点したが空だった」そのもの |
| `grade()`で`ProviderUnavailable`を送出           | `GradingJobProcessor`が既に`PERMANENT`へ分類する。設問のJobはFAILEDで終わり、retryもされず（retryしても鍵は増えない）、`GradeResult`行は1つも書かれない                                                                    |
| 理由はJobではなくアプリ全体で1回言う             | 理由はどの設問でも同じ1文であり、`Job.last_error`にはprovider例外文言を入れない規約（AGENTS.md「Security」）がある。`GET /grading/availability`が`{available, reason}`を返し、アプリはそれを**全画面の上の帯**として出す   |
| 帯は消せない／`reason`をそのまま出す             | 閉じられる帯は「消したまま採点されない」状態を作れてしまう。`reason`は英語だが、設定変数名とホスト前提条件だけを含み（値は含まない）、実際に直せる人が読む唯一の手がかり                                                   |
| 応答が無いときは帯を**出さない**                 | 「サイドカーが応えなかった」と「採点が使えない」は別の事実。前者を後者と断定すると、一度の通信失敗が設定不備の告知になる（`app/lib/core/widgets/grading_unavailable_banner.dart`）                                         |

`reason`に**設定値**を入れないことは2重に担保する: `create_ai_provider()`の
`AIProviderConfigError`は変数**名**しか含まない（規約は`factory.py`のモジュール
docstring）、それ以外の想定外例外は**例外型名だけ**を残して本文を捨てる
（`_google_adc`が google-auth のメッセージに対して既に採っている規律と同じ）。

**この規約は後から必要になったものである（レビュー1回目 P2）。** `factory.py`の
メッセージ群は「ログにしか出ない」前提で書かれており、
`AUTO_SCORING_AI_GRADING_TEMPERATURE`の読めなかった値・未知の transport 名・
`AUTO_SCORING_CODEX_EXECUTABLE`の設定値をそのまま含んでいた。本Issueが
**公開経路を新設した**ことで、設定先を間違えて鍵を貼った操作者に、その鍵が画面と
ログから読み返される状態になっていた。3か所とも値を落とし、規約を
`factory.py`側（値を書く側）へ置いた。`backend/tests/test_grading_availability.py`
は、`create_ai_provider()`が読む**全変数**に順に偽の鍵を入れ、`reason`にも
HTTP応答本文にも出ないことを確認する（既知の悪いメッセージの一覧ではなく変数の
一覧にしてあるのは、将来また値を書き始めたメッセージを捕まえるため）。

**同じ事故がもう1つの経路でも起きた（レビュー2回目 P2）。** Vertex アダプタは
`AUTO_SCORING_VERTEX_PROJECT` / `AUTO_SCORING_GEMINI_MODEL` をリクエスト URL へ
組み込み、httpx がそれを INFO でログに出す。サイドカーは root を INFO にして回転
ファイルログへ書くので、404 応答だけで設定値が永続ログに残っていた。**この経路は
本Issueが作った**（実providerに繋いだからこそ URL が組み立てられる）。

経路を数え上げるのをやめ、**外へ出る場所にゲートを置いた**:
`api/secret_redaction.py` が「設定値とは何か」を1か所で定義し
（`AUTO_SCORING_` 名前空間の、12文字以上の値と資格情報系の変数。`v1`・`0.0`・
`global` のような短い構造的な値は伏せない -- 伏せるとログが読めなくなる）、
テキストがプロセスを出る2か所がこれを適用する: `install_log_redaction`
（このプロセスがログを設定する唯一の場所。uvicorn は `log_config=None` で起動する
ので uvicorn のロガーも root のハンドラを通る）と `build_ai_provider`
（reason を作る唯一の場所）。詳細と教訓は `docs/quality-gates.md`
「新しい公開経路を作ったら、そこへ流れ込むものを全部見直す」。

実キーでの疎通・schema 検証は Issue #35 で 4 経路すべて実施済み
（[`poc-2-ai-grading.md`](./poc-2-ai-grading.md) §7.4。合成フィクスチャのみを送信）。

**OCR 側（`NullOCRProvider`）は依然未接続である。** Document AI のアダプタが
無いため（本Issueの対象外、業務ルール §3 (A)）、`GradingJobProcessor`が採点へ
渡すOCRテキストは空のままで、実際に設問が採点されるにはそのアダプタが要る。

### `GradingJobProcessor`: `RecognitionJobProcessor`を合成し、採点半分を追加する

`docs/job-queue.md`が決定した「1 Question = 1 Job（`JobKind.GRADING`）、
Job内部でOCR→採点をどう分けるかはJobProcessor実装側の自由」という設計を受け、
`auto_scoring.jobs.grading_processor.GradingJobProcessor`は
`RecognitionJobProcessor`（Issue #19、変更なし）を内部に持ち、その`process()`を
呼んだ後にAI採点を行う:

1. まず`RecognitionJobProcessor.process(job)`を呼ぶ。`FAILED`ならそのまま
   返し、採点は一切試みない。
2. `SUCCEEDED`でも、`RecognitionResult`が実際に永続化されているか
   （`recognition_result_id(job)`で参照）を確認する。無ければ
   （回答欄検出失敗で切り出し画像自体が信頼できず、providerを一切呼ばずに
   `usable=False`を返した場合）、採点する文字が無いため即座に同じ結果を返す。
3. 同じ`job.id`に対する`GradeResult`が既に存在すれば（クラッシュ後の再処理、
   `RecognitionJobProcessor`と同じ理由）providerを再度呼ばず、既存行から
   `usable`を再計算して返す。
4. `Question.model_answer`が未登録、または`Rubric`が無い（`criteria`が空）
   場合は、`RecognitionJobProcessor`の「回答欄画像が無い」場合と同じ扱いで
   `FAILED`(`PERMANENT`)にする -- 採点材料が無い設問をAIに推測させない
   （AGENTS.md「Verification」: 「読めない文字や判断不能を推測で補完しない」）。
   人間がmodel answer/rubricを登録するまで自動リトライしても無意味なため
   `PERMANENT`とする。
5. 確定済み`DependencyGraph`（Issue #26）から前提設問のcontextを組み立てる
   （後述）。
6. `AIProvider.grade()`を呼ぶ（`asyncio.to_thread`でイベントループをブロック
   しない。ネットワーク呼び出し中はDBトランザクションを保持しない --
   `jobs/queue.py`・`RecognitionJobProcessor`と同じ規約）。rubric_textには
   各criterionの登録済み`id`と設問の`scoring_method`（加算/減点）を含める
   （後述「provider requestで全rubric意味論を保持する」、コードレビュー
   指摘）。
7. 応答の`question_id`/`max_score`が要求したものと一致しない場合、または
   応答の`criteria[].id`の集合が登録済みrubricのcriterion id集合と完全一致
   しない場合（未知のidを含む、または既知のidを省略している）は
   `FAILED`(`PERMANENT`)にする -- PoC 2のメトリクスハーネス
   （`ai_grading_metrics.evaluate_sample`）が「対応不一致」として実装している
   分類を、本番パイプラインでも同じ理由で採用・拡張する: 別設問への応答や、
   rubricへ確実にマッピングできない応答をこの設問の採点として保存しない
   （コードレビュー指摘: schema上は妥当でもcriterion idが登録済みrubricと
   食い違う応答を、そのまま高confidenceで永続化・usableにしていた）。
8. 成功応答は`GradeResult`（`source=ai`、常に）として永続化し、応答に含まれる
   `annotations[]`も`Annotation`（`source=ai`）として保存する
   （`target`を`anchor_text`へ、座標は一切持たない -- 簡易設計書 §12.1）。
   graderの認識結果（`response.recognition_text`/`recognition_confidence`）も
   別の`RecognitionResult`（後述）として保存する。
9. `Job.usable`は「OCR pipeline自身のRecognition Confidence、AI grader自身の
   Recognition Confidence、Grading Confidenceの**3つすべて**が閾値以上」
   （後述、Issue #20受入条件）。

### エラー分類: timeout / rate limit / 5xx / スキーマ不正 / 対応不一致

`domain/ai_provider.py`の`ProviderUnavailable`に`ProviderTimeoutError`・
`ProviderRateLimitedError`・`ProviderServerError`の3サブクラスを追加した
（`domain/ocr.py`の`OCRProviderError`サブクラス群と同じパターン -- PoC 2時点の
`ProviderUnavailable`は無分類の単一例外だったが、Issue #20は「timeout、429/5xx
を分類しqueueのretry規則へ接続する」ことを求めるため、この粒度が必要）。
`GradingJobProcessor`は以下へ分類する（`ErrorCategory`、Issue #18で確定済みの
4値を再利用 -- 新しい値は追加しない）:

| 例外                          | `ErrorCategory` | retry対象 |
| ----------------------------- | --------------- | --------- |
| `ProviderTimeoutError`        | `TIMEOUT`       | される    |
| `ProviderRateLimitedError`    | `RATE_LIMITED`  | される    |
| `ProviderServerError`         | `SERVER_ERROR`  | される    |
| `SchemaViolation`             | `PERMANENT`     | されない  |
| 応答の対応不一致（上記手順7） | `PERMANENT`     | されない  |
| その他の`ProviderUnavailable` | `PERMANENT`     | されない  |

「範囲外score」はこの表に現れない -- `ai_grading.GradingOutput`のPydantic
バリデーション（`score <= max_score`、両方とも`>= 0`）が構造化出力のパース時点
（provider adapter内部）で`SchemaViolation`として弾くため、`GradingJobProcessor`
が改めて数値レンジをチェックする必要が無い。`error_message`にはprovider例外の
生メッセージを含めない（request/response本文（答案本文を含み得る）を含み得る
ため、AGENTS.md「Security」）。

### provider requestで全rubric意味論を保持する

`GradingRequest.rubric_text`は当初、各criterionの`description`と
`max_points`のみを結合した文字列だった。登録済みcriterion `id`（応答の
`criteria[].id`をrubricへマッピングし直すために必須）と、設問の
`scoring_method`（`ScoringMethod.ADDITIVE`/`SUBTRACTIVE`。加算式と減点式を
providerが区別するために必須）のどちらも欠けていた -- 実providerが接続
された場合、outcomeをrubricへ確実にマッピングできず、減点式採点を加算式と
取り違えるおそれがあった（コードレビュー指摘）。

修正: `jobs.grading_processor._rubric_text_for`が「採点方式:
加算方式/減点方式」の1行と、`- id=<criterion id>: <description>(配点<max_points>点)`
という行をcriterionごとに生成する。この`id`が、次節の応答検証で使う
「登録済みrubricのcriterion id集合」と一致することを要求する。

### Confidence閾値: 3つの確信度すべてが閾値以上のときだけusable

Issue #20受入条件「Recognition ConfidenceとGrading Confidenceのどちらかが
閾値未満ならneeds_reviewにする」を実装する。`Job.usable`は次の**3つすべて**が
閾値以上のときだけ`True`になる（コードレビュー指摘: 当初の実装はrecognition
confidenceを`RecognitionSettings`の閾値ではなく`GradingSettings`の閾値と
比較しており、2つの設定値が異なる場合に誤って`usable`と判定しうる不具合が
あった）:

1. OCR pipeline自身のRecognition Confidence
   （`recognition_outcome.usable`、`RecognitionJobProcessor`が自身の
   `RecognitionSettings.confidence_threshold`で既に判定済みの値をそのまま
   再利用する -- `GradingJobProcessor`が独自に`RecognitionResult.confidence`
   を読み直して別の閾値と比較することはしない）。
2. AI grader自身のRecognition Confidence（`response.recognition_confidence`。
   後述のとおりOCRテキストを訂正した場合の、grader自身の読み取りに対する
   確信度）。`RecognitionJobProcessor.confidence_threshold`
   （新設の公開プロパティ、`RecognitionSettings`と単一の情報源を共有する）
   と比較する -- `GradingSettings`の閾値と比較しない。
3. Grading Confidence（`response.grading_confidence`、
   `GradingSettings.confidence_threshold`と比較）。

回答欄画像が丸ごと信頼できない場合（`AnswerImageStatus.NEEDS_REVIEW`）は、
`RecognitionJobProcessor`の既存の振る舞いどおり文字認識自体を試みず、採点する
文字が無いため`GradingJobProcessor`も採点を一切試みない。それ以外は
Recognition Confidenceが低くても採点そのものは試みる -- 2つ目・3つ目の数値が
実際に存在して初めて比較が意味を持つため。

閾値は`auto_scoring.jobs.grading_settings.GradingSettings`
（`RecognitionSettings`と同じ素の`dataclass`）が持つ。Recognition Confidenceと
Grading Confidenceを混同しない（簡易設計書 §10）という方針に合わせ、
`RecognitionSettings.confidence_threshold`とは別の設定値として独立させた
（同じ値を共有する保証はない -- 将来どちらかだけ調整できるようにするため）。
`0.80`は業務ルール決定書 §3 (C)の**既定値**である。Issue #81 で「固定値は決めず、
設定値のまま運用しながら都度調整する」ことが確定し、既定 0.80 は据え置かれた。
閾値がいくつであれ**閾値に基づく自動確定（人間レビューのスキップ）は実装しない**
（§3.1 C）-- `Job.usable`が制御するのは「この設問を人間が見なくてよいか」ではなく
「後続の依存設問へ進んでよいか」である。

### AI graderが訂正した認識結果を保持する

`AIProviderContract`（PoC 2）は、マルチモーダルなproviderが与えられたOCR
テキストを訂正して返すことを明示的に許容する
（`test_grade_preserves_the_recognized_text`）。当初の実装はこれを
`GradingRequest`構築後に一切参照せず、`response.recognition_text`/
`response.recognition_confidence`を破棄していた -- レビュー担当者はAIが
実際に採点した文字列を確認できず、graderが低いRecognition Confidenceを
報告している場合でも（元のOCR結果が高Confidenceであれば）`usable`になり
得た（コードレビュー指摘）。

修正: 採点成功時に、graderの読み取り結果を2つ目の`RecognitionResult`
（`source=ai`、id `grading-recognition:<job.id>`。OCR pipeline自身の結果
`recognition:<job.id>`とは別行）として永続化し、その`confidence`を上記の
usable判定へ組み込む。簡易設計書 §16.5の「AI認識文字」がレビューUI上
2つの独立した項目（OCR結果とAI採点結果）になり得ることに対応する。

前提設問context（後述）の`recognized_text`は、履歴の中で最も新しいAI行
（`_latest_preferring_human`。人間確定行があればそちらを優先）を採用するため、
前提設問が採点済みであればgraderが訂正した読み取りが渡る -- 実際に採点で
使われた文字列の方が、採点前の生OCR結果より前提として正確なため。

### `prompt_text`のプレースホルダ（未解決事項の記録）

`GradingRequest.prompt_text`（設問文）は非空白文字列必須だが（PoC 2時点の
`__post_init__`不変条件）、MVPの`Question`ドメインモデル（Issue #11）は
問題文抽出パイプラインをまだ持たない -- `docs/dependency-graph.md`の
`QuestionInfo.prompt_text`が同じ理由で空文字既定値になっているのと同じ未解決
事項である（「PDFからの問題文抽出パイプラインが実装され次第、そちらを既定入力
に差し替え」）。

本Issueはこれを解決しない（別Issueのスコープ）。代わりに、設問文を捏造せず、
`prompt_text`を「設問「{number}」の解答を、模範解答と採点基準に基づいて採点
してください。」という設問番号のみを含む正直な指示文に留める
（`jobs.grading_processor._prompt_text_for`）。実際の採点材料
（`model_answer`・`rubric_text`）は省略せずそのままproviderへ渡る。将来、
問題文抽出/入力の仕組み（Issue #26の`overrides`と同種の仕組み、または新しい
永続フィールド）が実装されたら、その値に差し替える。

### 前提設問context: 業務ルール §4.3 が許可する情報だけを渡す

業務ルール決定書 §4.3は依存元設問から依存先設問の採点へ引き継いでよい情報を
次に限定する: 確定した（人間承認済み、または高Confidenceの）OCRテキスト、
criterion結果と最終得点。禁止する情報: 依存元の答案画像そのもの、依存元のAI
コメント文・自由文の判定根拠、生徒識別情報、確定DAGに無い設問の情報。

`auto_scoring.domain.grading_context`（新規、純粋domain関数のみ）が
`DependencyGraph`（Issue #26）のedgeと、呼び出し側が解決済みの前提結果
（`PrerequisiteSource`）から、`ai_provider.PrerequisiteAnswer`のタプルを
組み立てる。`PrerequisiteAnswer`は`recognized_text`/`score`+`max_score`/
`criteria`（`domain.models.CriterionResult`、rationaleを持たない --
§4.3が除外する「自由文の判定根拠」を構造的に持ち込めない）のみを持ち、
画像・コメント・生徒識別情報のフィールドは存在しない。`graph.edges`に
無い設問はそもそも走査対象にならないため、確定DAGに無い設問の情報が
混入することは構造的に無い。

`provides`が要求するデータを呼び出し側の`sources`が持たない場合は
`MissingPrerequisiteContextError`を送出し、値を捏造しない
（AGENTS.md「Verification」）。DAGスケジューリング（Issue #18/#26）が
前提未usableな依存先Questionの`Job`を`BLOCKED`のまま留めるため
（`domain.job_scheduling.evaluate_readiness`）、この例外は通常経路では
発生しない -- `GradingJobProcessor`はこれを`FAILED`(`PERMANENT`)として扱う。

**未対応の項目（記録）**: §4.3は「条件分岐型のとき、分岐の結果として選択された
依存先の採点基準・模範解答の枝」と「依存元設問の模範解答（テストプロファイル
由来）」も渡してよいとするが、Issue #26が確定した
`DependencyProvision`（`recognized_text`/`score`/`criterion_result`のみ）には
対応する値が無い。本Issueは「#26のedge定義に従う」よう指示されているため、
`DependencyProvision`の拡張（新しい値の追加とDBトリガーの更新、
`migrations/versions/0003_dependency_graph.py`の`_KNOWN_DEPENDENCY_PROVISIONS_SQL`
参照）は本Issueのスコープ外とし、将来Issue #26の後続作業として記録するに
留める。

前提未完了（依存元Questionの`Job`が`usable`に達していない）の間は、依存先
Questionの`Job`自体が`BLOCKED`のまま`JobQueueService`のワーカーに一度も
ディスパッチされないため、`AIProvider.grade()`は呼ばれない -- Issue #20
追加受入条件「前提未完了では依存QuestionのAIProviderが呼ばれない」は
Issue #18/#26が既に実装したDAGスケジューリングでそのまま満たされる
（`backend/tests/test_grading_processor.py`の
`test_dependent_question_job_is_blocked_until_prerequisite_is_usable`で確認）。

### GradeResultのAI追跡情報とcontextの記録

`GradeResult`（`domain/models.py`）に以下を追加した
（`migrations/versions/0012_grade_result_ai_metadata.py`）:

- `comment`: AIの総評コメント（簡易設計書 §16.5「コメント」）。
- `provider`/`model`/`prompt_version`: AI再現性の3つ組（Issue #20受入条件
  「provider/model/prompt versionが追跡でき」）。3つ together か、3つとも
  `NULL`かのどちらかのみ許容する -- 人間確定行はこの3つを持たない。
- `dependency_graph_version`: 採点時点で有効だった確定`DependencyGraph`の
  バージョン（`JobRow.dependency_graph_version`と同じ理由、Issue #26）。
- `context`: どの前提`RecognitionResult`/`GradeResult`行を実際に読んで
  この採点を行ったか（`question_id`/`recognition_result_id`/
  `grade_result_id`のJSON配列）。

Issue #20追加受入条件「使用したgraph versionと前提result versionをGradeResult
へ記録し、前提が更新された場合は古い下流結果を再利用しない」は、
`GradeResult`（`RecognitionResult`と同じく追記のみ）の性質と`Job.SUCCEEDED`が
終端状態であること（`domain.models._JOB_TRANSITIONS`）から成立する: 前提が
人間レビュー等で更新された後の再採点は、必ず**新しいJob**（新しい`job.id`）を
必要とし、その新しいJobの`GradingJobProcessor.process()`は前提の**最新**の
結果を読んで新しい`GradeResult`行（新しい`id`、異なる`context`/
`dependency_graph_version`を持ちうる）を作る -- 古い行は書き換えられず、
2つの行は`context`を見比べれば区別できる。「前提が更新された後に自動で
再採点する」トリガー機構自体（人間レビューAPIからの`Job`再発行）は、本Issueが
対象外とする人間レビュー操作の一部であり、後続Issueで扱う。

### セキュリティ

- providerへ送る`GradingRequest`は当該設問1問分の情報のみ（プロンプト文・
  設問1問分の答案画像・OCRテキスト・模範解答・rubric・配点・前提設問context）
  で構成し、生徒識別情報（`student_label`等）やテスト全体・他設問の答案は
  一切含めない（業務ルール §2 (2)、§4.3）。
- 前提設問contextは§4.3が許可する範囲に構造的に限定される（前節）。
- APIキー・画像バイト列・答案本文・provider生応答はログに出さない
  （`error_message`はカテゴリ名のみを含む固定文言、`RecognitionJobProcessor`
  と同じパターン）。

## 検証

- `backend/tests/test_ai_provider_contract.py`: `ProviderTimeoutError`等の
  新しい例外階層、`PrerequisiteAnswer`のバリデーション（provides要求データの
  必須化、空白ocr_textの許容）、`UnconfiguredAIProvider`のcontract相当テスト。
- `backend/tests/test_grading_context.py`: `build_prerequisite_context`/
  `build_context_entries`のunit test（各provisionの受け渡し、確定DAGに無い
  設問が混入しないこと、不足時に捏造せず例外を送出すること）。
- `backend/tests/test_grading_processor.py`: `GradingJobProcessor`を
  スクリプト可能なfake `OCRProvider`/`AIProvider`＋実SQLite＋実
  `LocalFileStore`で検証 -- 正常系（GradeResult/Annotation永続化・
  再現性メタデータ）、schema不正、対応不一致、timeout/rate limit/5xx分類、
  低Recognition/低Grading Confidenceそれぞれのneeds_review化、model
  answer/rubric未登録時の`PERMANENT`失敗、クラッシュ後の再処理で二重に
  providerを呼ばないこと、前提設問contextの実際の組み立てと`GradeResult.
context`への記録、依存先Jobが前提未完了の間`BLOCKED`のままであること。
- `backend/tests/test_domain_models.py`: `GradeResult`の新フィールド
  （comment長さ上限、AI再現性3つ組の全部/無しのみ許容、
  `dependency_graph_version`の正値制約、`GradeResultContextEntry`の
  重複question_id拒否）のunit test。
- `backend/tests/test_migrations.py`（既存ファイルの一部）:
  `0012_grade_result_ai_metadata`のhead revision反映確認。
- `backend/tests/test_grading_availability.py`（Issue #97）: `build_ai_provider`
  の2つの失敗経路（設定不足・想定外例外）と、そのどちらでも資格情報の値が
  `reason`へ出ないこと、`GET /grading/availability`の応答と認証要求。ホストの
  `codex`/ADC の有無は両方とも注入する。
- `backend/tests/test_sidecar.py`（Issue #97）: 認証情報の無いホストでも
  `run()`が起動し、環境を読む場所が composition root であること。
- 実AIサービスを呼ぶテストはこのリポジトリに1つも無い。Issue #20 時点では
  同梱アダプタが`NullAIProvider`だけだったためで、実アダプタが揃った今も
  同じである -- 各アダプタの contract test は`httpx.MockTransport`と偽の
  資格情報で書き、live 疎通は`docs/poc-2-ai-grading.md`の probe command で
  手元から行う（結果は §7.4）。
