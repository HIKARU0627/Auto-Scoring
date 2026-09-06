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

### AIモデル選定（業務ルール §3 (B)）は未確定のまま — `NullAIProvider`をdefaultにする

PoC 2（`docs/poc-2-ai-grading.md`）は`AIProvider`契約・構造化出力スキーマ
（`domain/ai_grading.py`）・メトリクス集計基盤（`domain/ai_grading_metrics.py`）を
実装したが、credentials が揃わず実ベンダー（Gemini/Claude/GPT）の採用・実測は
行われなかった（同docs §0.1参照。§9相当の「採用AI」欄は依然未確定）。業務ルール
決定書 §3.1「B（AIモデル）確定まで」は実装を`AIProvider`の抽象とPoCの記録のみに
限定するとしている。

本Issueはこの制約の中で本番**パイプライン**（境界・schema検証・永続化・分類・
Confidence運用・前提設問contextの受け渡し）を実装する。`create_app()`の
`job_processor`既定値を`RecognitionJobProcessor`（Issue #19）から
`GradingJobProcessor`（後述、`RecognitionJobProcessor`を内部で合成する）へ
置き換えるが、その`GradingJobProcessor`自体が呼ぶ`AIProvider`の既定実装は
`auto_scoring.adapters.ai.null_provider.NullAIProvider`とする。
`NullOCRProvider`（Issue #19）と同じ理由（正直に「未設定」を報告する）で、
`NullAIProvider`は常にConfidence 0.0・score 0・空の認識文字列を返し、
ネットワークに一切アクセスしない。結果として、実アダプタが
`create_app(ai_provider=...)`で注入されるまで、すべての設問が自動的に
needs_review（`Job.usable=False`）に倒れる。

実AIアダプタ（Gemini/Claude/GPT）の追加は、プロジェクトオーナーが業務ルール
§3 (B)を確定した後の別Issueで行う。`AIProvider`のcontract test
（`backend/tests/test_ai_provider_contract.py`の`AIProviderContract`）へ
新しいサブクラスを追加するだけで済むよう、`domain/ai_provider.py`のポート定義は
変更していない（例外の分類粒度を上げた点を除く。後述）。

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
   `jobs/queue.py`・`RecognitionJobProcessor`と同じ規約）。
7. 応答の`question_id`/`max_score`が要求したものと一致しない場合は
   `FAILED`(`PERMANENT`)にする -- PoC 2のメトリクスハーネス
   （`ai_grading_metrics.evaluate_sample`）が「対応不一致」として実装している
   分類を、本番パイプラインでも同じ理由で採用する: 別設問への応答をこの設問の
   採点として保存しない。
8. 成功応答は`GradeResult`（`source=ai`、常に）として永続化し、応答に含まれる
   `annotations[]`も`Annotation`（`source=ai`）として保存する
   （`target`を`anchor_text`へ、座標は一切持たない -- 簡易設計書 §12.1）。
9. `Job.usable`は「Recognition ConfidenceとGrading Confidenceの**両方**が
   閾値以上」（後述、Issue #20受入条件）。

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

### Confidence閾値: RecognitionとGradingの両方が閾値以上のときだけusable

Issue #20受入条件「Recognition ConfidenceとGrading Confidenceのどちらかが
閾値未満ならneeds_reviewにする」を文字どおり実装する: `Job.usable`は
Recognition ConfidenceとGrading Confidenceの両方が閾値以上のときだけ
`True`になる。

Recognition Confidenceが低い（が0ではない、つまり回答欄画像自体は信頼できる）
場合でも、採点そのものは試みる -- Grading Confidenceという2つ目の数値が
実際に存在して初めて「どちらか」の比較が意味を持つため。回答欄画像が丸ごと
信頼できない場合（`AnswerImageStatus.NEEDS_REVIEW`）は、`RecognitionJobProcessor`
の既存の振る舞いどおり文字認識自体を試みず、採点する文字が無いため
`GradingJobProcessor`も採点を一切試みない。

閾値は`auto_scoring.jobs.grading_settings.GradingSettings`
（`RecognitionSettings`と同じ素の`dataclass`）が持つ。Recognition Confidenceと
Grading Confidenceを混同しない（簡易設計書 §10）という方針に合わせ、
`RecognitionSettings.confidence_threshold`とは別の設定値として独立させた
（同じ値を共有する保証はない -- 将来どちらかだけ調整できるようにするため）。
`0.80`は業務ルール決定書 §3 (C)自身が名指す暫定値であり、本Issueが確定させた
値ではない。

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
  必須化、空白ocr_textの許容）、`NullAIProvider`のcontract相当テスト。
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
- 実AIサービスを使うテストはこのIssueには存在しない（`NullAIProvider`が
  唯一の同梱アダプタで、ネットワークに一切アクセスしないため）。実アダプタを
  追加する後続Issueが、そのアダプタ専用のlive probe commandを
  `docs/poc-2-ai-grading.md`の方針に従って追加する。
