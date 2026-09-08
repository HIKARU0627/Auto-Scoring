# 再開可能な設問DAG対応並列AI処理キュー

> **Issue #101 で画面が変わった。** 「答案取込画面」は 資料取込画面 (`/intake`) に
> 統合された。**起票の規則そのものは変えていない** -- 取込1件につき1回、
> `createSubmission` が `ai_processed` を返したときだけ呼ぶ。呼ぶ場所が
> `app/lib/features/intake/intake_page.dart` に移っただけである。
> 起票の失敗は取込の失敗として扱わず、取込結果の行に理由を併記する
> （新規登録直後のテストは確定DAGを持たないため、これは異常ではなく通常の状態）。
> 詳細は [`intake-and-settings.md`](./intake-and-settings.md)。

GitHub Issue [#18](https://github.com/HIKARU0627/Auto-Scoring/issues/18)（親
[#3](https://github.com/HIKARU0627/Auto-Scoring/issues/3)）。複数答案の
OCR/AI処理を制限付きで並列実行し、アプリ再起動や一時障害後も安全に再開できるよ
うにする。Submission内では[#26](https://github.com/HIKARU0627/Auto-Scoring/issues/26)
の確定DAGに従って設問単位で依存順を守る。

依存: [#26](https://github.com/HIKARU0627/Auto-Scoring/issues/26)（設問依存関
係DAG。`auto_scoring.domain.dependency_graph`、`Job.dependency_graph_version`、
`reissue_job_for_graph_version`）、[#10](https://github.com/HIKARU0627/Auto-Scoring/issues/10)
（認証付きサイドカーAPI）、[#11](https://github.com/HIKARU0627/Auto-Scoring/issues/11)
（`Job`ドメインモデル・SQLite永続化基盤）。

対象外: OCR/AIのprovider固有処理（実際にどのモデル・サービスを呼ぶか、答案画像
の切り出し・送信）は後続Issueで扱う。本Issueは「並列度・再開性・DAG順序を守る
キュー機構」に限定し、実処理は `JobProcessor` という差し替え可能な境界の向こう
側に置く。

## 決定事項

### `JobProcessor`: 実処理を境界の外に置く

`auto_scoring.domain.job_execution.JobProcessor`（`OCRProvider`/`AIProvider`と
同じ位置づけのProtocol）を導入した。キューは「`process(job)` を呼び、
`ProcessingResult`（成功/失敗、成功時は`usable`、失敗時は`error_category`と
メッセージ）を受け取る」以外、実処理の中身を一切知らない。実際にOCR/AIを呼び
RecognitionResult/GradeResultを永続化する具象実装は後続Issueで追加し、この
Protocolを実装するだけでよい。テストは`tests/fakes.py`の`FakeJobProcessor`
（結果をスクリプト可能）を注入する。

Issue #19が`auto_scoring.jobs.recognition_processor.RecognitionJobProcessor`
としてOCR認識半分を実装し、`create_app`の既定`job_processor`を
`NullJobProcessor`からこれへ置き換えた（`docs/ocr-recognition-pipeline.md`）。

Issue #20が採点（`AIProvider`）半分を実装した
（`auto_scoring.jobs.grading_processor.GradingJobProcessor`、
`docs/ai-grading-pipeline.md`）。`GradingJobProcessor`は
`RecognitionJobProcessor`を内部で合成し（OCR半分はIssue #19のまま変更なし）、
その後にAI採点を行う -- `create_app`の既定`job_processor`は現在この
`GradingJobProcessor`である。

### Submission内DAGスケジューリングの単位: 1 Question = 1 Job（`JobKind.GRADING`）

Issue #26の確定DAGはQuestion単位の依存を表す。本Issueもこれに合わせ、
Submission処理を開始する際に**確定DAGのQuestionごとに1つのJobを作成**する
（`JobKind.GRADING`を流用 -- OCR文字認識とAI採点を1設問分まとめて1つの処理単位
として扱う。個々のJobの内部でOCR→採点をどう分けるかは`JobProcessor`実装側の
自由で、キュー機構には見えない）。新しい`JobKind`は追加しない。

### 依存の解放は「usable」を明示的に永続化して判定する

Issueの受入条件は「前提Questionがusableな結果を返した時だけ後続Questionを解放
する。低Confidence・失敗・cancelの場合は後続を…ロックし外部providerを呼ばな
い」。これは「Jobが成功した」だけでは判定できない -- 成功しても低Confidenceな
ら後続を解放してはならない、という3値（未完了 / usable / usableでない）が要る。
`Job`に`usable: bool | None`を追加した（`SUCCEEDED`遷移時にのみ設定。
`FAILED`/`CANCELLED`は常にusableでない扱い）。実際のConfidence判定基準
（business-rules-and-evaluation-data.md §3 (C)。閾値は設定値で、既定0.80）は`JobProcessor`
の実装側の責務とし、本Issueのキューは`ProcessingResult.usable`という既に判定
済みのbool値を受け取るだけに留める。

### `BLOCKED`を「待機中」と「前提がusableでないためロック中」の両方に使う

Issue本文は後続Questionを「locked_by_dependency」にすると書いているが、
`JobState`に新しい値は追加しない。理由:

- 依存先Questionから見た挙動は「前提がまだ処理中で待っている」場合と「前提が
  失敗/低Confidence/cancelで確定的にusableでないため待っている」場合とで、
  機構としては同じ（外部providerを呼ばずBLOCKEDのまま留まり、前提がusableに
  なった時にだけ自動でQUEUEDへ戻る）。状態機械を分けても振る舞いは増えない。
- 既存の`Job.state`docstringは既に「`BLOCKED` = waiting on a dependency
  (§4.4)」と定義しており、`JobState`は`db/orm.py`のCHECK制約・
  `_JOB_TRANSITIONS`の両方に列挙されているため、値を増やすには migration と
  ORM 制約の両方の変更が要る。振る舞いが変わらないなら追加しない
  （AGENTS.md「既存資産で満たせない場合のみ追加」）。

区別が必要なのは人間向けの表示だけなので、`Job.blocked_on_question_id`（既存
フィールド、未解決の前提のうち辞書順で最初の1件）と`Job.last_error`
（例:「waiting on q1」または「locked: q1 is not usable (low confidence)」）で
表現する。`blocked_on_question_id`は複数前提がある合流点でも単一のIDしか持て
ないが、これは「代表して1件を表示する」ためのフィールドであり、実際の解放判定
（全前提がusableか）は`domain.job_scheduling.evaluate_readiness`が
`DependencyGraph`のedgeから毎回計算し直すため、フィールドの一意性はこの判定の
正しさに影響しない。

### 二重処理防止（idempotency）: 新しいキー列ではなく複合UNIQUE制約

Issueは「idempotency keyで二重処理を防ぐ」ことを求めるが、新しい不透明な文字列
列を追加する代わりに、`jobs`テーブルへ
`UNIQUE(submission_id, question_id, dependency_graph_version)`の複合制約を追加
した。SubmissionのDAG処理で作るJobは常にこの3つを持つ（`question_id`と
`dependency_graph_version`は必ず設定される）ため、この複合キーが実質的な
idempotency keyとして機能する -- 同じ確定グラフバージョンに対して同じ
Submission・同じQuestionのJobを二重に作ろうとすると`IntegrityError`になり、
呼び出し側（`JobQueueService.submit_submission`）はそれを「既に作成済み」として
無視する。クラッシュ後の再起動で`submit_submission`が再度呼ばれても、既存のJob
行と衝突するだけで新しい行は作られない。

同じ理由で、SQLiteのUNIQUE制約はNULLを複数許容するため、`question_id`または
`dependency_graph_version`がNULLの非DAG Job（将来のRECOGNITION単体/EXPORT用
途）にはこの制約は効かない。それらは本Issueの対象外であり、必要になった時点で
別の制約を追加する。

### retry対象の分類: `ErrorCategory`

`Job.error_code`（新規列、`ErrorCategory`の値）を追加し、`last_error`
（自由文言、答案本文・secretを含めない）とは別に、`timeout` /
`rate_limited` / `server_error` / `permanent` の4値で永続化する。retryするのは
`timeout`・`rate_limited`・`server_error`のみ（Issue受入条件どおり）。実際に
どのHTTPステータス・例外をどのカテゴリに落とすかはOCR/AI呼び出しを行う
`JobProcessor`実装（後続Issue）の責務で、本Issueのキューは既に分類済みの
`ErrorCategory`を受け取るだけ。cancelは「エラー」ではないため`ErrorCategory`
に含めない（`error_code`は`NULL`のまま、`last_error`に理由を残す）。

### クラッシュ回復: `RUNNING`を`QUEUED`または`FAILED`へ

起動時、`RUNNING`のまま残っているJob（プロセスがkillされ、worker側の
finally/exceptハンドラすら走れなかった場合）を規則どおり回収する:

- `attempts < max_attempts` なら`QUEUED`へ戻す（今回のRUNNING遷移で既に1回分
  カウント済みなので、`attempts`は増やさない）。
- `attempts >= max_attempts` なら`FAILED`（`error_code=permanent`、
  「startup recovery: exhausted retries after an interrupted run」）にし、
  自動retryループへ入れない。人間が`retry`APIで明示的に再試行できる。

このため`_JOB_TRANSITIONS[JobState.RUNNING]`に`JobState.QUEUED`を追加した
（通常の処理コードパスではこの遷移を使わず、起動時回収専用の
`domain.job_scheduling.recover_running_job`だけが使う）。

### 並列度・retry設定: 新しい設定フレームワークを追加しない

technology-stack.md §3 は「設定管理: pydantic-settings」と書いているが、既存の
`create_app(..., max_concurrent_uploads: int = 2, ...)`は`pydantic-settings`を
経由せず、素のキーワード引数として並列度を渡している。本Issueもこの既存の慣習
に合わせ、`auto_scoring.jobs.settings.QueueSettings`を素の`dataclass`にし、
`create_app(..., queue_settings: QueueSettings | None = None)`として渡す。新しい
必須依存パッケージは追加しない。既定値: `max_concurrency=4`
（technology-stack.md §3.4、business-rules-and-evaluation-data.md §3 (E)。
Issue #18 時点の暫定値2から、[Issue #81](https://github.com/HIKARU0627/Auto-Scoring/issues/81)
でオーナーが確定した4へ変更した。設定値であることは変わらず、採用providerの
レート制限は未実測なので、下記のbackoff・キュー再投入は引き続き必須。
**既定4での飽和動作は未検証**である -- `test_e2e_dag_parallelism` /
`test_e2e_acceptance` は明示的に2を渡しており、同時実行可能なジョブが4つある
シナリオを持たない。上限を超えないことと2並列で実際に重なることは検証済みだが、
worker 4本が同時に飛ぶ状態は誰も通していない。必要なら別Issueで足す）、
`max_attempts=3`（既存の
`Job.max_attempts`既定と一致）、指数backoff
（`initial_backoff_seconds=1.0`、`backoff_multiplier=2.0`、
`max_backoff_seconds=30.0`）。

Confidence閾値（business-rules-and-evaluation-data.md §3 (C)。固定値を置かず
設定値のまま運用調整すると確定、既定0.80）は`QueueSettings`に含めない -- 本Issoueのキューは`usable`という既に判定済みの
値を受け取るだけで、閾値そのものを参照するコードを持たないため、ここに置くと
使われない設定値になる。閾値は`JobProcessor`の具象実装（後続Issue）が持つ設定
に属する。

### 依存が解放された後の自動requeue、および人間による再開

- Jobが`SUCCEEDED`（usable）になった直後、同じSubmission内でこの設問に直接
  依存するQuestionの`BLOCKED`なJobを再評価し、前提が全てusableになっていれば
  `QUEUED`へ戻し再度キューへ積む（同一トランザクション内）。
- 前提が失敗/低Confidenceで一度ロックされた後、人間が前提を修正して`usable`
  にした場合の再開経路として、`JobQueueService.mark_question_usable` /
  `POST /submissions/{submission_id}/questions/{question_id}/resume`を用意し
  た。実際のレビューUI・レビューAPI（人間の承認操作）は後続Issueの対象だが、
  「前提がusableになったら後続を自動requeueする」という受入条件そのものは、
  このエンドポイントを通じてテスト可能な形で実装済み。将来のレビューAPIは、
  人間が承認した時点でこのメソッドを呼ぶだけでよい。

### 並列度の共有: SubmissionをまたいでもDAG内でも同じSemaphore

`JobQueueService`はプロセス内に1つの`asyncio.Semaphore(max_concurrency)`だけを
持つ。どのSubmissionのどのQuestionのJobであっても、実行中に必ずこの1つの
Semaphoreを取得する。これにより「異なるSubmission間の並列実行」と「Submission
内でDAGが許す範囲の並列実行」が同じ上限で制御される（Issue受入条件）。

### #26のconfirm再発行ジョブもこのキューに直接渡す

`dependency_graph_router.confirm`（#26）は確定グラフのバージョンが進んだ時、
古いバージョンの未完了Jobを`CANCELLED`にし新バージョン向けの`QUEUED`な複製Job
を直接DBへ`add`する。この複製Jobはプロセス内の`asyncio.Queue`を経由しないた
め、`JobQueueService`が気づかないまま放置され、次回プロセス再起動時の
`start()`の全QUEUEDスイープまで実行されない。これを避けるため
`build_dependency_graph_router(..., on_job_reissued=...)`という差し込み口を
追加し、`create_app`が`queue_service.enqueue`をそこへ渡す。既定は`None`（何も
しない）なので、この引数を渡さない既存の呼び出し・テストの挙動は変わらない。

### 起票のタイミング: アプリが取込直後に自動、失敗したものは明示操作で再試行（Issue #80）

`POST /submissions/{submission_id}/jobs` は上記のとおり最初から存在するが、
**Flutterアプリはこれを一度も呼んでいなかった**（`sidecar_api_client.dart` に
ラッパが無く、`app/lib/` に呼び出し箇所ゼロ）。取込エンドポイントもジョブを
起票しないので、**アプリ経由では採点が一度も始まらなかった**（Issue #80）。
どこで起票するかは決まっていなかったので、ここに決めてから実装した。

**候補と、採らなかった理由。**

1. **取込エンドポイント側で自動起票する** — 採らない。
   - `POST /tests/{test_id}/submissions` は画像前処理と回答欄抽出を同期で行う
     長い要求で、`UNPROCESSED -> AI_PROCESSING -> AI_PROCESSED` はそこまでを
     指す（`adapters/submission_intake.py`）。ここへ採点の起票を混ぜると、
     確定DAGゲート（`can_start_submission_processing`）で弾かれたときに
     「取込は成功したが採点は始まらなかった」を1つの応答で表せない。取込ごと
     失敗させれば取り込めた答案を捨てることになり、握り潰せばクライアントは
     起票されなかったことを知る手段が無い。
   - 「Jobは明示的な `POST .../jobs` でしか作られない」は #18 で決めた不変条件で、
     `app/lib/core/question_status.dart` の `pending`（「まだジョブが無い」）、
     `pdf_review_page.dart` の `_latestJobFor`、`core/dependency_dag.dart` の
     `waiting` がその前提で書かれている。暗黙起票にすると、この3箇所が同じ
     語で別のことを言い始める。
2. **明示操作だけにする** — 採らない。受入条件「人手でDBを触ることなく
   QUEUEDになる」は満たすが、答案を取り込むたびに人間が押すボタンが増える。
   取込に成功した答案の採点を、そこで始めない理由が無い。
3. **両方（自動 + 明示的な再試行）** — **これを採る。**

**決定。**

- **答案取込画面**: `createSubmission` が成功した直後に、その答案IDで
  `POST /submissions/{submission_id}/jobs` を呼ぶ。取込1件につき1回。
  これが常用経路で、人間の操作は増えない。
- **添削レビュー画面**: その答案のJobが0件のとき「AI採点を開始」を出す。
  自動起票が失敗した答案と、**この変更より前に取り込まれた答案**の唯一の
  復帰口である（後者はアプリからは二度と起票されないまま残る）。
- 起票はidempotent（同じ確定グラフバージョンのJobがあれば何も作らない）
  なので、二重に押しても、自動と手動が重なっても、Jobは増えない。
- 起票は取込とは別の操作として扱う。**起票に失敗しても取込は成功のまま**
  であり、答案を一覧から消したり取込エラーとして見せたりしない。答案は
  サーバに存在する。

**自動起票は `ai_processed` の答案だけに限る。** 取込の結果が `needs_review`
（ページ数が合わない、回答欄が未定義の設問がある）や `error` になった答案は、
自動では起票しない。`docs/answer-intake-and-preprocessing.md` §3 の
「前提設問を含むページが欠落した状態では AI 採点を開始しない」を、起票側で
守るのがここになったためである。一方、**添削レビュー画面の「AI採点を開始」は
状態で塞がない** -- あれは答案と要確認の理由を見た人間が明示的に押すもので、
business-rules §4.4 が認めている「人間が前提を承認して続行する」に当たる。
回答欄が信頼できない設問については、パイプライン側が既に
`AnswerImageStatus.NEEDS_REVIEW` の画像へproviderを呼ばず
`SUCCEEDED(usable=False)` を返す（`docs/ocr-recognition-pipeline.md`）ので、
起票しても誤った画像が外部へ出ることはない。

**エラーの扱い。**

- **409 はアプリ側で区別しない。** この応答には2種類ある
  （確定DAGが無い/古い = `SubmissionNotReadyError`、同時起票の競合 =
  `SubmissionJobCreationConflictError`）が、`detail` は英語の内部メッセージで、
  文字列の中身で分岐するのは壊れやすいうえ、画面の出しかたも変わらない。
  どちらも「答案は取り込めているが採点は始まっていない」「時間をおくか、
  テスト設定で依存関係を確定し直せば通りうる」という同じ扱いで足りる。
  画面は日本語で両方の可能性を書き、再試行ボタンを出す
  （サイドカーの英語メッセージはそのまま出さない）。
- **404**（答案が存在しない）は再試行しても変わらないので、**どちらの画面も
  再試行の導線を出さない** -- 答案取込画面はバナーの再試行ボタンを、添削レビュー
  画面は「AI採点を開始」ボタンそのものを消す。取込直後にこれが返るのは想定外の
  状態なので、握り潰さずそのまま見せる。
- **文言と再試行可否は `app/lib/core/grading_kickoff.dart` の
  `GradingKickoffFailure` が1つの値として持つ。** 最初の実装ではこれが2つの
  関数に分かれていて、添削レビュー画面が文言だけを使い再試行可否を握り潰した
  結果、404 の「答案が見つかりません」の真上から同じ要求を何度でも押せた
  （review round 1, P2-2）。片方だけを取り出せない形にしてあれば、2つの画面が
  別々の振る舞いへ分かれようがない -- `QuestionStatus` が語・形・強調度を
  1組で持つのと同じ理由である。
- 通信不能・タイムアウトは 409 と同じく再試行可能として扱う。

**確定DAGが無いときに何が起きるか。** 答案取込画面が出す答案は
`GET /tests`（`TestStatus.READY` のテストだけ）から選ぶので、取込できた時点で
確定グラフは一度は存在している。それでも 409 になるのは、テストが `ready` に
なった後に設問が増減した、または新しいグラフバージョンをanalyzeしたまま
confirmしていない場合である（`can_start_submission_processing` の3条件）。
つまり **409 は「テスト設定でグラフを確定し直せ」という指示**であり、画面の
文言もそう書く。添削レビュー画面では、最新グラフがdraftのときに出る
「最新の依存関係グラフが未確定のため、処理の進み方は表示できません。」の
注意書きと並ぶことがあるが、注意書きが出ない場合（グラフは確定済みだが設問が
増減した場合）もあるので、**起票ボタンはグラフの状態で塞がない**。

**バックエンドは変更していない。** 必要なエンドポイント・ゲート・
idempotencyは #18 の時点で揃っており、欠けていたのは呼び出し側だけである。
OpenAPIスキーマも生成クライアントも変わらない
（`createSubmissionJobsSubmissionsSubmissionIdJobsPost` は生成済みだった）。

## API

`auto_scoring.api.jobs_router`（`/submissions/{submission_id}/jobs` 以下）:

- `POST /submissions/{submission_id}/jobs` -- 確定DAGに基づきQuestionごとの
  Jobを作成し、依存のないQuestionをQUEUEDでキューへ投入する
  （`can_start_submission_processing`のゲートを通らない場合は409）。既に
  同じ確定グラフバージョンのJobが存在する場合は何もしない（idempotent、上記
  複合UNIQUE制約による）。**呼ぶのはアプリ側で、タイミングは上記
  「起票のタイミング」で確定した**（取込成功の直後に自動、失敗したものは
  添削レビュー画面から明示的に再試行）。
- `GET  /submissions/{submission_id}/jobs` -- 一覧・進捗（state、attempts、
  error_code、blocked_on_question_id等）。
- `GET  /jobs/{job_id}` -- 単一Jobの詳細。
- `POST /jobs/{job_id}/retry` -- `FAILED`のJobを`QUEUED`へ戻し再投入する。
- `POST /jobs/{job_id}/cancel` -- `QUEUED`/`BLOCKED`/`FAILED`は即座に
  `CANCELLED`にして200を返す。`RUNNING`は実行中タスクへcancel要求を
  送るだけで、実際の`CANCELLED`書き込みはそのworker task自身が数瞬後に
  行うため、202とcancel前のスナップショット（`state: "running"`）を
  返す（review round 6, P2）。
- `POST /submissions/{submission_id}/questions/{question_id}/resume` -- 上記
  「人間による再開」の暫定エンドポイント。

## 検証

- `backend/tests/test_retry_policy.py`: `ErrorCategory`の分類、指数backoffの
  決定的な計算（fakeを使わず純粋関数）。
- `backend/tests/test_job_scheduling.py`: `evaluate_readiness`の分岐・合流・
  独立・複数ページDAGでの決定的なunit test（DBなし）。
- `backend/tests/test_job_queue.py`: `FakeClock`/`FakeJobProcessor`を注入した
  `JobQueueService`のasync test -- 並列数の上限、429/timeoutでのretryと
  backoff、最大retry回数超過後のFAILED終端、cancel（QUEUED/RUNNING両方）、
  crashからの再起動回復（RUNNINGのまま残ったJobをQUEUEDへ戻し、重複せず1回
  だけ完了させる）、A→BとCが独立なDAGでB がAより前に開始しないこと、分岐/
  合流DAGでの解放順。
- `backend/tests/test_jobs_api.py`: 上記APIをTestClient経由で検証（実SQLite）。
- 起票を呼ぶ側（Issue #80）は Flutter 側にある。`app/test/grading_kickoff_test.dart`
  （409を2種類に分けず、404は再試行を勧めない文言）、
  `app/test/answer_intake_page_test.dart` の `Issue #80: 取込直後のAI採点起票`
  （`ai_processed` だけ自動起票する・要確認は起票しない・409のあと取込は成功の
  まま残り「AI採点を開始」で再試行できる・404には再試行を出さない）、
  `app/test/pdf_review_page_test.dart` の
  `Issue #80: ジョブが無い答案からAI採点を開始する`（0件のときだけボタンを出す・
  押すとジョブができて図が動く・409は画面のエラーにしない・404のあとはボタンを
  出さない・ジョブ一覧を読めていないときは「まだ開始されていません」と言わない）。
- 実外部API（実際のOCR/AIサービス）を使うテストはこのIssueには存在しない
  （`JobProcessor`の具象実装が無いため）。将来`JobProcessor`の実装Issueが
  実プロバイダ向けテストを追加する際は、AGENTS.md/`docs/quality-gates.md`の
  方針どおり`pnpm run check`から分離し、必要な環境変数とコマンドをそちらの
  ドキュメントに明記すること。

## レビュー第1round（Codex）で修正した点

- **再発行されたJobを新グラフに対して再計画してからenqueueする**
  （P1）: `dependency_graph_router.confirm`が呼ぶ`reissue_job_for_graph_version`
  は常に置き換えをQUEUEDとして作る -- 新バージョンの依存構造を一切見ない。
  v2が新しいedge（例: 既存の独立設問同士にA→Bを追加）を持ち、A・B両方が
  v1で未完了だった場合、Bの置き換えをそのままenqueueするとAがusableになる
  前にBがprocessorへ到達し、DAGゲートを回避してしまう。`confirm`は
  Submissionごとに、置き換え候補全体（そのSubmissionの完了済みJob + 全ての
  兄弟置き換え）から`question_statuses`/`evaluate_readiness`で再判定し、
  readyでないものはQUEUEDではなくBLOCKED（`blocked_on_question_id`付き）
  として保存する。`on_job_reissued`もQUEUEDになったものだけを呼ぶ。
- **queue操作をevent loopスレッドへ委譲する**（P1）: FastAPIは同期`def`の
  route handlerをworker threadで実行するが、`JobQueueService`の
  `asyncio.Queue`/`asyncio.Task`はlifespanのevent loopが所有する。
  `asyncio.Queue.put_nowait`と`Task.cancel`はどちらも呼び出し元スレッドを
  問わないわけではない。`JobQueueService.enqueue`と`cancel_job`のtask
  cancel要求は`loop.call_soon_threadsafe`経由にし、`start()`で
  `asyncio.get_running_loop()`を保持しておく。route handler自体は同期の
  ままにし（既存の他routeとの一貫性、DBアクセスをevent loop上でブロック
  させない）、asyncioへ触れる箇所だけをthread-safeにする設計を選んだ。
- **重複したdispatchシグナルでもactive taskの追跡を失わない**（P2）:
  起動時の「recoveredしたJob」と「QUEUEDの全件sweep」が同じjob_idを二重に
  enqueueしうる（他にも冪等な`submit_submission`の二重呼び出し等）。当初は
  `_job_tasks`を`job_id -> 単一Task`ではなく`job_id -> set[Task]`にし、doneコ
  ールバックは自分自身をsetから取り除くだけにする、という対処にしたが、この
  方式はレビュー第2roundでdispatcher自体をworker poolへ置き換えたことで、
  「CASに勝ったworkerだけが登録する」という、そもそも重複登録が起こらない
  設計に置き換わった。詳細は下の第2round節を参照。
- **`submit_submission`の並行idempotency競合を処理する**（P2）: 2つの
  リクエストが同じSubmissionに対して同時に呼ばれると、両方とも「既存Jobな
  し」を観測して`insert`を試みうる。`JobRepository.add`は即座にflushする
  ため、負けた側は複合UNIQUE制約から`IntegrityError`を受け取る。
  `submit_submission`はこれを捕捉し、新しい`SqlAlchemyUnitOfWork`から読み
  直して最大5回まで再試行する（`dependency_graph_router.analyze`のバージョ
  ン割当と同じパターン）。尽きた場合は`SubmissionJobCreationConflictError`
  （API層で409）。
- **retry可否は永続化されたJob自身の`max_attempts`で判定する**（P2）:
  以前は`self._settings.retry_policy`（サービス現在の設定）を使っていたが、
  設定変更後の再起動や再発行/レガシーJobでは、Jobが実際に持つ
  `max_attempts`と食い違いうる。`_retry_policy_for(job)`でJob自身の
  `max_attempts`を使い、backoffのタイミング（initial/multiplier/max）だけ
  サービス設定から取る。
- **backoff sleep中はSemaphoreを解放する**（P2）: 以前は`_finalize_result`が
  `_run_one`の`async with self._semaphore:`の内側でsleepしていたため、
  既に`FAILED`として永続化された（実行中ではない）Jobがbackoffの間ずっと
  並列度枠を1つ占有し続けていた。`_finalize_result`はDB書き込みとretry
  遅延の計算だけを行う同期関数にし、実際の`await self._clock.sleep(...)`
  と再enqueueは`_run_one`がSemaphoreを抜けた後に行う（第2roundでSemaphore
  自体をworker poolへ置き換えた後も、この「backoffはworkerを専有しない」と
  いう性質はそのまま`_schedule_retry`が引き継いでいる。下の第2round節参照）。
- **`mark_question_usable`はアクティブなgraph versionのJobを対象にする**
  （P2）: `list_for_submission`は作成日時の古い順に並ぶため、単に最初の
  `SUCCEEDED`一致を使うと、グラフバージョンが進んだ後でも古い（既に
  supersedeされた）バージョンのJobを誤って復活させてしまう。まず
  `get_latest_confirmed`でそのテストのアクティブなconfirmed graphを解決し、
  `dependency_graph_version`がそのバージョンと一致するJobだけを対象にする。

## レビュー第2round（Codex）で修正した点

- **起動時にretry可能なFAILED jobを回収する**（P1）: 第1roundで「backoff
  sleep中はSemaphoreを解放する」ようにした結果、backoffのsleepは
  `_run_one`とは別の（worker poolを専有しない）task
  （`_schedule_retry`/`_sleep_then_requeue`）で行うようになった。この
  timerはプロセスが強制終了されると一緒に消える。Jobは既にその時点で
  `FAILED`としてattempts/error_code込みで永続化されているが、backoffが
  明けても誰も再enqueueしないため、再起動しない限り恒久的に取り残されて
  いた。`start()`は`RUNNING`の回収・`QUEUED`のsweepに加えて、
  `error_code`が`is_retryable`かつ`attempts < max_attempts`な`FAILED` Job
  を`QUEUED`へ戻すsweepも行う（backoffをもう一度待たせず即座に再試行 --
  プロセス再起動自体が既に十分な間隔になっているとみなす）。
- **stale RUNNING jobのJob再発行時に実タスクもキャンセルする**（P1）:
  `dependency_graph_router.confirm`のreissue処理は、staleなJobが`RUNNING`
  だった場合もDB行を`CANCELLED`へ書き換えるだけで、実際にprocessorを呼んで
  いる非同期taskには何も伝えていなかった。`JobQueueService`へ新しい公開
  メソッド`cancel_running_task(job_id)`を追加し（DBへは一切書き込まず、
  その`job_id`を現在処理しているworker taskへcancel要求を送るだけ）、
  `build_dependency_graph_router`に`on_stale_running_job_cancelled`フックを
  追加して`create_app`から`queue_service.cancel_running_task`を配線した。
  confirmの側は自分の書き込みが終わった**後**にこれを呼ぶ -- DB上のstate
  遷移は依然としてconfirm自身のtransactionが所有し、`cancel_running_task`
  は「実行中のtaskへ知らせる」役目だけを持つ。
- **worker poolへの設計変更**（この2つのP1と、下のP2 x2をまとめて解決する
  ための土台）: 以前は「dispatcherがqueueから1件取り出すたびに新しい
  `asyncio.Task`を作り、`asyncio.Semaphore`でprocessor呼び出しだけを絞る」
  方式だった。これだと巨大なbacklog（起動時の一括回収や大量submitなど）が
  あると、実際に並列実行できる数を超えて大量のtaskがその場で作られてしま
  い、メモリと`shutdown`（全taskをgatherする）の所要時間がbacklogの大きさ
  に比例してしまう（P2「dispatcher taskをworker並行度で制限する」）。
  `max_concurrency`個の長生きするworker coroutine（`_worker_loop`）が
  `asyncio.Queue`を消費し続ける固定poolに置き換えた。worker数自体が並列度
  の上限になるため、`asyncio.Semaphore`は不要になった。
  - **タスク追跡はCASに勝ったworkerだけが行う**（P2「task-registryへの
    アクセスをevent loop上に保つ」も合わせて解決）: `_run_one`は
    `QUEUED -> RUNNING`のcompare-and-setに**成功した**workerだけが
    `self._running[job_id] = 自分のtask`を登録する（登録は常にevent loop
    上で、他のworkerとの競合なしに行われる）。重複したdispatchシグナルで
    生まれた「負けた」呼び出しは登録を一切行わずno-opで終わるため、
    `job_id -> 単一Task`のdictのままで安全（第1roundの`set[Task]`は不要に
    なった）。`cancel_running_task`は「lookupしてcancelする」処理全体を
    `loop.call_soon_threadsafe`で1つの関数としてevent loopへ丸ごと委譲する
    ため、worker threadがdictを直接読むことは無くなり、「イテレーション中
    にdictが変化してRuntimeError」という懸念自体が構造的に起こらない
    （そもそも複数taskを保持するcollectionを反復する場面が無い）。
  - **backoffは専用の軽量taskに切り出す**: workerが自分自身をbackoffの
    sleepで塞ぐと、そのworkerがpoolから実質的に1枠減ってしまい、第1round
    で直した「backoffはpermitを専有しない」という性質が別の形で壊れる。
    `_schedule_retry`は`self._pending_retries`という別集合に切り出した
    task（`_sleep_then_requeue`）でsleep+再enqueueを行い、workerはすぐに
    次のqueue itemを処理できる。この`_pending_retries`はbacklogの大きさで
    はなく直近の失敗率に比例するため、dispatcher taskと同種の問題にはなら
    ない（`shutdown`はこれらを待たずcancelするだけ -- 上記の起動時FAILED
    sweepが後始末を保証する）。
- **cancelのcompare-and-set失敗を処理する**（P2）: `cancel_job`が読んだ後、
  workerや別のbackoff再enqueueが同じ行を書き換えると`JobSaveConflict`が
  発生し、以前は捕捉されず素の500になっていた。`cancel_job`を（他の
  compare-and-setリトライと同じ）有限回のretryループにし、`JobSaveConflict`
  を捕捉したら最新状態を読み直して判定をやり直す。それでも勝てなければ
  新設の`JobCancelConflictError`（API層で409）。
- **retry設定を構築時に検証する**（P2）: `QueueSettings`が持つbackoff関連の
  値（`initial_backoff_seconds`が負、`backoff_multiplier`が1未満、
  `max_backoff_seconds`が`initial_backoff_seconds`未満など）は、以前は
  `QueueSettings()`の構築自体は素通りし、最初にJobが失敗して
  `_retry_policy_for`が`RetryPolicy`を組み立てる時点で初めて例外になって
  いた -- その時点では既にRUNNING行がcommit済みで、再起動するまでそのJob
  が詰まってしまう。`QueueSettings.__post_init__`が`RetryPolicy`を実際に
  構築してみることで検証を再利用し（値を重複定義しない）、構築時点で早期に
  失敗するようにした。
- **前提Questionの全ての「使用不能」終端結果を再開できるようにする**
  （P1）: `mark_question_usable`は`SUCCEEDED`のJobしか対象にしていなかった
  ため、(a) 前提QuestionがFAILEDのまま人間が修正した場合と、(b) confirmの
  reissueは「未完了」だったJobしか作り直さないため、既に終端状態
  （SUCCEEDED/FAILED）だった古いバージョンのJobがアクティブバージョンに
  一切存在しない場合、の両方で404になり後続Questionが永久にBLOCKEDのまま
  残っていた。まず`Job.usable`を`SUCCEEDED`だけでなく`FAILED`でも設定
  できるようにドメインモデル・DB制約（`ck_jobs_usable_matches_state`、
  migration 0009）・`JobRepository.mark_usable`・
  `domain.job_scheduling.question_statuses`を拡張した（FAILEDのJobは
  `state`をFAILEDのまま保ちつつ`usable`だけを持てる -- 実際に失敗した
  という記録に嘘をつかない）。その上で`mark_question_usable`の対象選択を
  「アクティブバージョンのSUCCEEDED/FAILED」→（無ければ）「任意バージョン
  の中で最新のSUCCEEDED/FAILED」の順で解決するようにした。

## レビュー第3round（Codex）で修正した点

- **resumeをretry遷移に対して直列化する**（P1）: `mark_question_usable`が
  対象Jobを読んでから`JobRepository.mark_usable`で書き込むまでの間に、
  別の`retry_job`呼び出しが同じ行を`FAILED -> QUEUED`へ書き換えると、
  以前の`mark_usable`は`state`を条件にせず`usable`列だけを無条件に書いて
  いたため、両方の書き込みがcommitされ得た -- resumeは「まだ
  FAILEDだと思っている」古いJobの上で後続Questionを解放してしまうが、
  実際にはそのJobは既に再試行が始まっており、結果はまだ分からない。
  `JobRepository.mark_usable`のシグネチャに`expected_state`を追加し、
  `UPDATE ... WHERE id=? AND state=?`のcompare-and-setにした。
  `mark_question_usable`は他のcompare-and-setリトライと同じ形（有限回
  リトライ、負けたら`_MAX_RESUME_ATTEMPTS`回で`JobResumeConflictError`
  を送出）に変えた。CASが負けた場合、次のリトライで対象を読み直すと
  当該Jobは既に終端状態(SUCCEEDED/FAILED)ではなくなっているため、通常は
  `JobNotFoundError`になる（前提が今まさに再処理中であることの自然な
  帰結であり、人間には再度状況を見て判断してもらう）。
- **各backoffタイマーを発生元の失敗に紐付ける**（P1）: `_schedule_retry`
  が起動するsleep+再enqueueのtaskは、以前は起き抜けに「今も`FAILED`か」
  だけを確認していた。手動`retry_job`がbackoff中のJobを先に再enqueueし、
  その新しいattemptがそのタイマーの目覚めより前に再び失敗すると、
  タイマーは「新しい失敗も`FAILED`だから」と誤って再enqueueしてしまい、
  新しいattempt自身の（正しいタイミングの）backoffを飛ばすか、既にretry
  上限に達していた新しい失敗を不正に復活させ得た。`_schedule_retry`/
  `_sleep_then_requeue`/`_requeue_after_backoff`に
  `expected_attempts`（タイマーが発生した瞬間の`current.attempts`）を
  持たせ、起きた時点の`current.attempts`と一致しなければno-opにした。
- **finalization競合を吸収しworkerを殺さない**（P1）: `_finalize_result`
  が`RUNNING`行を読んでからcompare-and-setで書き込むまでの間に、
  `dependency_graph_router.confirm`のreissue処理が同じ行を`CANCELLED`へ
  書き換えると、以前は`uow.jobs.save(...)`が送出する`JobSaveConflict`を
  誰も捕捉しておらず、`_finalize_result` → `_run_one` →
  `_worker_loop`まで例外が伝播して、固定poolからそのworker taskが
  恒久的に失われていた（`max_concurrency=1`ならqueue全体が次の再起動まで
  完全に停止する）。SUCCEEDED/FAILED両方の書き込みを
  `try/except JobSaveConflict: return None`で包み、staleな
  finalizationを「既に他の書き込みがこのJobの運命を決めている」as-is
  no-opとして扱うようにした。
- **stale job claim成功後にreadinessを再計算する**（P1）:
  `dependency_graph_router.confirm`のreissueは、以前は最初の一覧取得
  （`list_incomplete_for_stale_versions`）で作った暫定snapshotをそのまま
  使って後続Questionのreadinessを判定していた。その一覧取得と各Jobの
  cancellation compare-and-setの間に、stale前提が実際に（本物のworkerで）
  完了すると、そのJobの置き換えはCASの前提が崩れてskipされるが、readiness
  計算は依然として「その置き換えは存在する（＝PENDING）」という幻の
  snapshotを見てしまい、既に完了した本物の行を見落としたまま後続を
  `BLOCKED`で永続化し得た -- そのアクティブversionの前提はもう二度と
  完了イベントを起こさないので、その後続は永久に解放されない。`confirm`
  を2パスに分割した: 1パス目は全てのcancellation CASを試みて
  `accepted_replacements`（実際に成功した置き換え）を集め、2パス目は
  `uow.jobs.list_for_submission`で最新のJob一覧を読み直し、その実際の
  状態から`question_statuses`を計算した上で、成功した置き換えについてのみ
  readinessを評価する。
- **自動回復時に承認済みの失敗を保持する**（P1）: `start()`起動時の
  retry可能FAILED job sweepと、`_requeue_after_backoff`のbackoff明け
  チェックは、どちらも「retry可能で`attempts < max_attempts`ならFAILEDを
  requeueする」という条件だけを見ていた。人間が`mark_question_usable`
  で既に`usable=True`（承認済み）とマークしたFAILED jobもこの条件を
  満たしてしまい、後続Questionが既に解放されているにもかかわらず、
  自動回復がそれを再enqueueしてしまうと`transitioned_to`が
  `usable`をリセットし、その承認が黙って失われる。両方の経路に
  `job.usable is not None`（＝人間が既に判断済み）を除外条件として
  追加した -- 承認済みの失敗を自動retryの対象から外す。
- **retry CASの競合を500ではなく処理する**（P2）: `retry_job`が読んだ後、
  2つの手動retryリクエストが重なる、またはbackoffによる自動requeueが
  先に同じ行を書き換えると`JobSaveConflict`が発生し、以前は捕捉されず
  素の500になっていた。`cancel_job`と同じ形（有限回のcompare-and-set
  リトライ、負けたら新設の`JobRetryConflictError`でAPI層は409）にした。
- **永続化されたbacklogを排出する前にworkerを停止する**（P2）:
  `shutdown`が積む`_STOP`センチネルはFIFO queueの**末尾**に置かれるため、
  以前はqueued idがまだ多数残っている状態でshutdownを呼ぶと、workerは
  自分の`_STOP`に辿り着くまで（遅いprovider呼び出しを含む）残りの
  backlog全部を律儀に処理してから止まっていた -- 大きな永続的backlogが
  あるとアプリの終了/再起動が無期限に遅延し得る。`shutdown`が`_STOP`を
  積む**前**に立てる`_closing`フラグを追加し、`_worker_loop`は
  dequeueした直後に`_closing`を確認して、`_STOP`以外のitemであっても
  即座にreturnするようにした。処理されなかった分はDB上QUEUEDのまま
  残り、次回`start()`のsweepが拾う。
- **ダウングレード前にfailed usable行を正規化する**（P2、migration
  0009）: `/resume`がFAILED jobに`usable=True`を保存した後にmigration
  0009をダウングレードすると、batch modeの「recreate」は既存行を
  そのまま新しいテーブルへコピーするため、その行は
  「`usable`は`SUCCEEDED`のみ許可」という古い制約に違反し、
  `IntegrityError`でダウングレードが中断していた。`downgrade()`の
  batch再構成の前に
  `UPDATE jobs SET usable = NULL WHERE state = 'failed' AND usable IS NOT NULL`
  を実行して正規化するようにした（古いスキーマにはそもそも表現できない
  情報なので、これは新しいデータの捏造ではなく正規化であり、明示的な
  ダウングレード操作でしか走らない）。

## レビュー第4round（Codex）で修正した点

- **アクティブversionのjobが存在しない場合のみfallbackする**（P2）:
  `mark_question_usable`の「アクティブバージョンに行が無ければ他バージョン
  の最新終端jobにfallbackする」ロジック（round 2, P1）は、`at_active_version`
  を`state in terminal_states`で絞り込んでから空かどうかを見ていたため、
  アクティブバージョンに行自体はあるがまだ終端状態でない（QUEUED/RUNNING/
  BLOCKED）場合も「無い」と誤判定し、古いバージョンのstaleな終端jobを
  fallbackで選んで承認してしまい得た。retryが`/resume`と競合した直後や、
  current-versionのjobが作成された直後にこれが起こると、アクティブな
  jobが保留のままなのに古い結果を承認したことになり、後続が誤って解放
  され得る。「アクティブバージョンに行が**一件も無い**」ケースと「ある
  が終端でない」ケースを`active_version_jobs`（状態を問わない）と
  `at_active_version`（終端のみ）の2つに分けて判定し、後者の場合は
  fallbackせず`JobResumeConflictError`（409、既存の「再度読み直して
  retry」挙動と同じ）を返すようにした。
- **承認済みの失敗した前提のretryを拒否する**（P2）: `/resume`が
  FAILEDの前提を`usable=True`とマークし後続を解放した後も、`retry_job`
  は`state is FAILED`しか見ていなかったためそのretryを許可してしまい
  得た。`transitioned_to`はFAILED→QUEUEDの遷移で`usable`を無条件に
  クリアするが、既に解放された後続を再びBLOCKEDへ戻す仕組みは無いため、
  `A -> B`のgraphでAの置き換え結果が定まらないままBが走り得た。
  `retry_job`は`job.usable is not None`（＝人間が既に承認/判断済み）
  なら新設の`JobRetryRejectedError`（409）で拒否するようにした -- 本当に
  このattemptをやり直したいなら、まず解放済みの後続をcancelしてからにする。
- **shutdown時にin-memory queueをリセットする**（P2）: 同じserviceを
  （あるいはFastAPI app lifespanが再度）`start()`すると、直前の
  `shutdown`が未消費のまま残したjob idや`_STOP`センチネルが
  `self._queue`に居座り続けていた。次の`start()`が spawn する新しい
  workerは、まずそのstaleな`_STOP`を先に引いてしまい、`_closing`が
  既に`False`に戻っていても`item is _STOP`の判定で即座に終了して
  しまう -- その結果、次の`start()`自身がDBのsweepで再投入したはずの
  backlogが処理されないまま永久に取り残され得た（2回目のlifespanが別の
  event loopを使う場合も同様に安全でない）。`shutdown`が worker の
  gatherを終えた直後に`self._queue = asyncio.Queue()`で作り直し、
  `self._loop = None`でloop所有権もクリアするようにした -- 破棄される
  job idはどれも既にDB上QUEUEDのまま残っているので、次の`start()`自身の
  sweepが必ず拾い直す。

## レビュー第5round（Codex）で修正した点

- **無効化CASが失敗した場合はstale jobを再読み込みする**（P1）:
  `dependency_graph_router.confirm`のreissue処理は、以前は各stale job
  のcancellation compare-and-setが失敗した場合、常に「本当に完了/
  キャンセルされた」とみなしてそのjobをskipしていた。しかし失敗する
  理由は他にもある: 初回一覧取得とこの書き込みの間にworkerがQUEUEDを
  RUNNINGとしてclaimした、あるいはbackoffによる自動requeueがFAILEDを
  QUEUEDへ戻した、といった「まだ未完了の別状態へ移っただけ」という
  ケースも同じ例外を送出する。それを一律skipすると、そのjobは新しく
  確定されたgraphが追加した依存関係を回避したまま、supersededな古い
  graph versionの下で走り続けてしまい得る
  （docs/dependency-graph.md「stale-job無効化要件」違反）。各stale job
  の無効化を有限回リトライするループに変更した: CASが失敗したら
  `uow.jobs.get`で対象を再読み込みし、その状態がまだ
  `QUEUED`/`RUNNING`/`BLOCKED`/`FAILED`（=`list_incomplete_for_stale_versions`
  が対象とする「未完了」の集合）のいずれかであれば、その新しい状態を
  前提に無効化をやり直す。再読み込みの結果が`SUCCEEDED`/`CANCELLED`
  （本当に終端に達した）または行自体が消えていた場合にのみskipする。
  リトライが尽きた場合は409を返し、confirm全体をロールバックして
  クライアントに再試行を促す。
- **resumeとretryを両方の順序で排他的にする**（P1）: `mark_usable`の
  compare-and-setは`state`しか見ないため、`retry_job`が「FAILED/
  usable未設定」の行を読んだ後、その書き込みの前に`/resume`が
  `usable=True`をcommitして後続を解放しても、`retry_job`側の
  `save(... expected_state=FAILED)`は`state`列だけを条件にしているため
  依然としてマッチし、後続が実行を継続しているにもかかわらず
  `usable`をクリアしてしまい得た（round 4のP2で追加した「読んだ時点で
  `usable is not None`なら拒否する」チェックは、retry自身の読み取り
  **後**に承認がcommitされるこの窓を防げない）。`JobRepository.save`に
  `require_usable_unset: bool = False`を追加し、真の場合はCASの
  `WHERE`へ`usable IS NULL`も加えるようにした。`retry_job`は自分の
  `save`呼び出しにこれを渡す -- `/resume`がこの窓でcommitに勝てば
  `retry_job`側のCASが負けて`JobSaveConflict`となり、読み直した結果
  `usable is not None`を検知して`JobRetryRejectedError`で正しく拒否
  できる。
- **承認済みの失敗した前提のキャンセルを拒否する**（P2）: `usable=True`
  のFAILED jobは、後続が既にqueued/runningかもしれない人間承認済みの
  前提を表す。`cancel_job`はこの条件を見ておらず、
  `transitioned_to(CANCELLED)`が後続を再ブロックしないまま`usable`を
  クリアしてしまうため、後続はキャンセル済みとして記録された前提に
  対して処理を継続してしまい得た。`retry_job`と同じ形で
  `job.state is FAILED and job.usable is not None`なら新設の
  `JobCancelRejectedError`（409）で拒否するようにした。書き込み自体にも
  `require_usable_unset=True`を渡し、`retry_job`と同じ理由でresumeとの
  レースを閉じている。
- **起動時回復をまたいでretry backoffを保持する**（P2）: `start()`の
  retry可能FAILED job sweepは、以前はbackoffが尽きているかどうかに
  関わらず即座にQUEUEDへ書き換えていた。長いrate-limit backoff
  （例: 429で初期値が数十秒〜数分）の途中でプロセスが再起動すると、
  この処理がその指数backoffを完全に無視してproviderへ即座に再度アクセス
  してしまい得た。`job.updated_at`（FAILEDへ遷移した瞬間に更新される）
  と現在時刻から経過時間を求め、`RetryPolicy.delay_seconds(job.attempts)`
  が返すそのattemptの本来のbackoffから差し引いた「残り時間」だけを待つ
  ようにした -- 残りが0以下ならこれまで通り即座にQUEUEDへ、残りがあれば
  行はFAILEDのまま`_schedule_retry`（既存のbackoffタイマー機構、
  `_pending_retries`に追跡される）へその残り時間だけを渡す。

## レビュー第6round（Codex）で修正した点

- **承認の書き込みをABA状態サイクルから保護する**（P1）:
  `mark_usable`のcompare-and-setは`state`しか見ていなかったが、FAILEDは
  行き止まりではない（retryで`FAILED -> QUEUED -> RUNNING -> FAILED`と
  一周できる）。`/resume`がFAILEDのattemptを読み取ってから書き込むまでの
  間に、並行するretryがこの一周を完了させると、`state`述語は（同じ
  `FAILED`のまま）再び一致してしまい、古いattemptに対する人間の承認が、
  実際には全く別の・未レビューの新しいattemptへ適用されてしまい得た。
  `JobRepository.mark_usable`に`expected_attempts`を追加し、CASの
  `WHERE`へ`attempts == expected_attempts`も加えた。`attempts`は
  `RUNNING`への遷移でしか変化しないため、`FAILED`へ戻るどんな一周を
  経てもattemptsは必ず変わっており、`_requeue_after_backoff`が既に
  stale backoffタイマーの判別に使っているのと同じ性質を、ここでも
  ABAサイクル検知に転用した形になる。CASが負ければ通常のcompare-and-set
  失敗と同じくfresh readからやり直され、その時点の実際のattemptに対して
  改めて判断される。
- **graph再発行をまたいで承認済みの失敗を保持する**（P1）:
  `mark_usable`でFAILED jobをusableとマークしても、
  `list_incomplete_for_stale_versions`は状態が`FAILED`である限り依然
  として「未完了」として選択してしまっていた。その後confirmが新しい
  graphを確定すると、この承認済みjobをキャンセル・再発行し
  （`reissue_job_for_graph_version`の置き換えは常に`usable`をリセット
  する）、既に解放済みの後続はもはや存在しない承認に対して処理を継続
  または完了したままになり得た -- `retry_job`/`cancel_job`が既に明示的
  に拒否しているのと同じ不整合（round 4/5）。`usable`が非nullのFAILED
  行を「スケジューリング上の終端」（`question_statuses`が既にそう扱って
  いる状態と同じ）として扱うことにし、2箇所を修正した:
  `list_incomplete_for_stale_versions`のSQLで`FAILED AND usable IS NULL`
  の場合のみ対象にする、および`dependency_graph_router.confirm`の
  無効化リトライループ自体にも`require_usable_unset=True`を渡し
  `_still_needs_invalidation`ヘルパーがFAILED+usable設定済みを終端扱い
  するようにする -- 前者が主な防御線、後者は初回一覧取得とcancellation
  CASの間の極めて狭い窓（その間に承認が着地するケース）を閉じる二重の
  防御線になっている。
- **running jobに対してキャンセル後の状態を返す**（P2）:
  `POST /jobs/{job_id}/cancel`は、対象がRUNNINGの場合`cancel_job`が
  実行中taskへcancel要求を送るだけで、実際の`RUNNING -> CANCELLED`
  書き込みはそのworker task自身（`_finalize_cancelled`）が数瞬後に
  非同期で行う。以前はこの場合もHTTP 200とcancel前のスナップショット
  （`state: "running"`）を返しており、docs/job-queue.md（本ドキュメント）
  が説明する挙動と裏腹に「何も起きていない」ように見えてしまっていた。
  RUNNINGブランチの場合のみレスポンスを202（Accepted）に変更した --
  bodyは引き続き同じ`JobResponse`（cancel前のスナップショット）だが、
  ステータスコード自体が「受理されたが、まだ適用されていない」ことを
  示す。

## レビュー第7round（Codex）で修正した点

- **インフラエラーでqueue workerが死なないようにする**（P1）: `_run_one`
  はprocessor呼び出し中の例外（processorのバグ、`asyncio.CancelledError`）
  とcompare-and-set競合（`JobSaveConflict`）は既に吸収していたが、それ
  以外の予期しない例外（例: claimやfinalization中のSQLiteのbusy timeout
  による一時的な`OperationalError`）は`_worker_loop`の`await
self._run_one(...)`から素通りしてしまっていた。固定worker poolには
  死んだworker taskを置き換える仕組みが無いため、`max_concurrency=1`
  では再起動までqueue全体が完全に停止し得た。`_worker_loop`側に
  `try/except Exception`のbackstopを追加し、ログを残してそのjobは
  諦め次のqueue itemの処理を続けるようにした -- claim済みのまま
  取り残されたjobがあっても、`start()`のRUNNING sweepが次回起動時に
  拾う（プロセスが実際にkillされた場合と同じ回復経路）。
- **job1つにつき1つのtaskを生成する代わりにretry待機を制限する**（P2）:
  以前は retry可能な失敗のたびに`_sleep_then_requeue`という専用task
  （`_pending_retries`という`set[Task]`で追跡）を1つ作っていた。これは
  `start()`が読み込んだ「まだ期限が来ていない」全てのFAILED行（round 5,
  P2で追加した機能）も含むため、providerの障害でbacklogが大きく失敗が
  速い場合、固定worker数にもかかわらずO(backlog)個のasyncio taskが
  蓄積し得、queueのbounded-task設計（モジュールdocstring冒頭で謳って
  いる性質）を無効化しメモリを枯渇させ得た。`(due_at, seq, job_id,
expected_attempts)`のmin-heap（`_retry_heap`）と、それを1件ずつ
  due順に処理する単一のscheduler task（`_retry_scheduler_task`、
  `_retry_scheduler_loop`）に置き換えた。heapが空の間は`_retry_added`
  （`asyncio.Event`）で待機し、非空の間は先頭要素の残り時間だけ
  `self._clock.sleep(...)`する（`FakeClock`はこれまで通り実時間を
  消費しない）。sleep中に、より早く期限が来る新しいentryが追加されても
  割り込みはしない -- 現在処理中のentryのsleepが終わるまで少し待たされる
  だけで、「保留中のretryが何件あってもtaskは常に1つだけ」という性質と
  引き換えの、許容できる程度の追加の不正確さで済む。テストの
  `test_a_stale_backoff_timer_does_not_requeue_a_newer_failed_attempt`
  も、複数timerが同時にsleepするのではなく、単一schedulerが順番に
  処理する前提に合わせて書き直した。
- **ランタイムの202レスポンスをOpenAPIで宣言する**（P2）:
  round 6で`cancel_job`のRUNNING分岐がレスポンスを202へ変更するように
  したが、FastAPIのルートデコレータは`response_model`由来のデフォルト
  200（と422）しか宣言していなかったため、生成されたOpenAPI
  ドキュメントは実際に返り得る202を広告していなかった。契約から生成
  されたクライアントやバリデータは、受理済みだが保留中のcancel結果を
  モデル化できず、実際のレスポンスを未文書化として扱い得た。
  `@router.post(..., responses={202: {"model": JobResponse, ...}})`で
  `JobResponse`を伴う明示的な202レスポンスを宣言し、
  `pnpm run openapi:export`/`openapi:generate`でOpenAPIスキーマと
  Dartクライアントを再生成した。

## レビュー第8round（Codex）で修正した点

- **自動requeueをusable未設定の場合のみに限定する**（P1）:
  `_requeue_after_backoff`と`start()`の起動時retry sweepは、どちらも
  読み取り時点の`job.usable is not None`チェックだけに頼っていた。
  `/resume`がこのチェックの後・実際のsaveの前に`usable=True`を
  commitすると、`mark_usable`は`state`を変更しないため両方の操作は
  依然として`state=FAILED`に一致してしまい、このsaveがその承認を
  `usable=None`で上書きしてjobを再enqueueしてしまい得た -- resumeの
  トランザクションが既に後続を解放している可能性があるにもかかわらず。
  `retry_job`/`cancel_job`が既に使っている`require_usable_unset=True`
  （round 5, P1）を、この2箇所のsaveにも追加した。
- **一時的なworker失敗後にjobを再enqueueする**（P1）:
  round 7で追加した`_worker_loop`の`try/except`は、workerが死ぬことは
  防いだが、`_run_one`がclaim（QUEUED→RUNNINGのCAS）より前に例外を
  送出した場合、そのjobの行はQUEUEDのまま残るのに、in-memory queueから
  はこのworkerが既にIDを取り出してしまっているため、ログを出して
  続行するだけでは誰もそのjobを再度dispatchしない -- アプリ全体が
  再起動するまで未処理のまま残り得た。例外を吸収した直後に
  `self.enqueue(job_id)`でdispatchシグナルを復元するようにした。
  claimが実際には成功していた場合（RUNNINGへ遷移済み）でも、この
  再enqueueは無害（次の`_run_one`呼び出しが単に「もうQUEUEDではない」
  と気づいて即座にno-opするだけ）。
- **1回のrequeueエラー後もretry schedulerを生かし続ける**（P1）:
  `_retry_scheduler_loop`が`_requeue_after_backoff`を無防備に呼んで
  いたため、その呼び出しが一度でも例外を送出すると（例:
  SQLiteがbusy timeoutを超える）、唯一のscheduler taskそのものが
  終了してしまい、以降のretryは`_retry_heap`に溜まり続けるだけで
  再起動まで誰も消費しなくなり得た。`_requeue_after_backoff`の呼び出しを
  entryごとに`try/except`で囲み、失敗したentryは
  `_SCHEDULER_ERROR_RETRY_DELAY_SECONDS`（1秒、常に0より大きい値 --
  event loopを一度も`await`で明け渡さずにスピンし続けることを防ぐため）
  後に`_schedule_retry`で再スケジュールしつつ、loop自体は次のentryの
  処理へ進み続けるようにした。
- **event loopを変更する際にretry eventを再作成する**（P2）:
  `_retry_added`（`asyncio.Event`）は、最初に`await`されたevent loopに
  束縛される。lifecycleドキュメントが明示的に許可している通り、この
  serviceが別のevent loopの下でshutdown・startされ得るが（`_loop`や
  `_queue`が同じ理由でリセットされているのと同様）、`clear()`は
  この束縛を解除しない。そのため、heapが空の状態で再起動した
  schedulerがこの同じEventを待とうとすると`RuntimeError: ... is bound
to a different event loop`を送出し得た。`shutdown()`で`clear()`する
  代わりに新しい`asyncio.Event()`へ置き換えるようにした（`_queue`を
  作り直しているのと同じ扱い）。

## レビュー第9round（Codex）で修正した点

- **job saveのCASにattempt番号を含める**（P1）:
  `FAILED`は終端状態ではなく、`FAILED -> QUEUED -> RUNNING -> FAILED`と
  何度でも循環し得る（`attempts`は`RUNNING`を経由する遷移でのみ増える）。
  そのため呼び出し元がattempt Nの時点でFAILEDのjobを読み取った後、
  別のretryがこの更新の前にABAサイクルを完了しattempt N+1でFAILEDに
  戻った場合、`state`（と`usable`）述語だけのCASは依然として一致して
  しまい、staleな値がより新しいattemptの結果を上書きし得た。
  `mark_usable`が round 6 で導入した`expected_attempts`パターンを
  汎用の`JobRepository.save()`自体に拡張し、`retry_job`・`cancel_job`・
  `_requeue_after_backoff`・起動時のFAILED sweep・
  `dependency_graph_router.confirm`の古いjob無効化、それぞれの呼び出しに
  `expected_attempts=job.attempts`（読み取り時点の値）を渡すようにした。
- **排他的なdata-root lockで複数sidecarの共存を防ぐ**（P1）:
  `auto_scoring.api.sidecar`の`--app-data-dir`は`cwd()/app-data`が
  既定値で、2つのsidecarプロセスが同じdata rootを指すことを妨げる
  仕組みがなかった。その場合、後から起動した方の`start()`が実行する
  クラッシュ回復sweepは、先に起動して今も生きているプロセスの
  RUNNING jobを「クラッシュの残骸」と区別できず再enqueueしてしまい、
  providerへの二重呼び出しや、先のプロセスの本来の finalize が
  CASに負けて実際には完了した結果を静かに握り潰す事態が起こり得た。
  `auto_scoring.adapters.data_root_lock.acquire_data_root_lock`を追加し、
  data root配下の`.lock`ファイルに対してOSレベルの排他ロック
  （POSIX: `fcntl.flock`、Windows: `msvcrt.locking`）を取得するように
  した。ロックはファイルの中身ではなくOSが管理するため、プロセスが
  クラッシュしてもファイルディスクリプタが閉じた時点で自動的に
  解放され、stale lockの掃除は不要。`create_app()`の`_lifespan`に
  組み込み、`session_factory`を自前で用意している場合
  （＝実運用のdata root）にのみ`service.start()`の前で取得し、
  `service.shutdown()`の後で解放するようにした。テストが供給する
  `session_factory`を使う場合はロックを取得しない
  （同じdata rootに対して複数の`create_app()`インスタンスを作るが
  lifespanは同時に走らせない既存テストと衝突しないため）。
- **冪等なsubmissionのdispatchを重複排除する**（P2）:
  既存のjobがQUEUEDのままの間に同じsubmissionへ`submit_submission`
  （`POST /submissions/{id}/jobs`）が繰り返されるたびに、同じjob IDが
  in-memory queueへ再度積まれていた。queueにはpending IDの重複排除が
  なく、クライアントの繰り返しretryやpollingが無制限にqueueへ
  同じIDを溜め込み得た（`_run_one`のclaim CAS自体は無害にno-opする
  が、その前に走るDB lookupが無関係なsubmissionの新規jobを同じFIFO
  queueの中で遅延させ得る）。`_plan_and_create_jobs`が既存jobを見つけた
  ときの再enqueue分岐を削除し、新しく作成したjobだけをenqueueする
  ようにした。既存jobが何らかの理由でin-process dispatchシグナルを
  失った場合の回復は、`start()`自身のQUEUED sweep（round 8, P1）が
  引き続き担う。

## レビュー第10round（Codex）で修正した点

- **data-rootの初期化全体をロックで保護する**（P1）:
  round 9で追加したdata-root lockは`create_app()`の`_lifespan`
  （ASGI startup）の時点でしか取得されておらず、その時点までに
  `create_app()`本体は既にmigration・`store.sweep_temp()`・
  `repair_incomplete_submissions`を実行済みだった。しかも
  `auto_scoring.api.sidecar.run()`はsocketのbindとhandshakeファイルの
  書き込みを`create_app()`の呼び出しより前に済ませてしまうため、
  稼働中のdata rootを指す2番目のsidecarは、拒否されるより先に
  1番目のプロセスがまだ書き込み中の`*.part`ファイルを削除したり、
  進行中のintakeをerroneousとマークしたりし得た。ロック取得を
  `create_app()`本体の先頭（`owns_session_factory`が真の場合、
  migration実行より前）へ移動し、そこから`sweep_temp`・
  `repair_incomplete_submissions`までを`try`で包んで、途中で例外が
  発生した場合もロックを解放してから再送出するようにした
  （同一プロセス内での再試行や、別のdata rootに対する後続の
  `create_app()`呼び出しがロックを取り戻せなくなることを防ぐ）。
  `_lifespan`は取得済みのハンドルを`service.shutdown()`後に解放する
  だけになった。副作用として、`data_root`を指定せず一時ディレクトリ
  （`scratch`）を使う`create_app()`呼び出しも「lifespanを一度も
  動かさない」まま常にロックを取得するようになったため、
  `atexit`登録の`_cleanup_scratch`（DBエンジンをdisposeしてから
  ディレクトリを削除する既存の仕組み）にもロックハンドルのcloseを
  追加した（Windowsでは開いたままの`.lock`ファイルが
  `shutil.rmtree`を`PermissionError`で失敗させるため、DBエンジンと
  同じ理由で必要）。
- **RUNNINGクレーム後の失敗からjobを回復する**（P1）:
  `_run_one`が`QUEUED -> RUNNING`のCASをcommitした後（例:
  `_finalize_result`が結果を永続化する際の一時的なDBエラー）に
  例外を送出すると、`_worker_loop`の既存のbackstopが行う
  「job IDを無条件でre-enqueue」では回復できなかった --
  `_run_one`自身の早期returnガードが、QUEUED以外の状態のjobを
  即座にno-opしてしまうため、行はプロセス再起動まで
  RUNNINGのままstrandedし続けた。`_run_one`のclaim成功後の処理を
  `_run_claimed`として切り出し、`_run_one`がこれを`try`で包んで、
  例外発生時は新設の`_recover_stuck_running`を呼ぶようにした。
  `_recover_stuck_running`は`start()`の起動時sweepと全く同じ
  `recover_running_job`（retryが残っていればQUEUED、尽きていれば
  FAILEDへ遷移）を使い、その場でDBへ反映し、QUEUEDに戻った場合は
  `enqueue`で再ディスパッチする。`_worker_loop`自身のbackstopは、
  claimがcommitされる前（行はまだQUEUEDのまま）の失敗だけを担当する
  役割に整理した。

## Linux環境で`test_retry_scheduler_survives_a_requeue_after_backoff_error`が

決定的に失敗していた原因（Issue #50）

Issue [#47](https://github.com/HIKARU0627/Auto-Scoring/issues/47)（Orca
リモート開発環境構築）の検証中、Windows専用CI（`.github/workflows/ci.yml`）
以外で初めてbackendテストスイートをUbuntu上で実行したところ、
`tests/test_job_queue.py::test_retry_scheduler_survives_a_requeue_after_backoff_error`
が個別実行・全体実行のいずれでも高確率で（フレーキーではなく実行のたびに
ほぼ再現して）`AssertionError: timed out waiting for condition`で失敗した
（Ubuntu 24.04.4、Python 3.12.3、`uv run pytest`）。

### 誤っていた最初の仮説: 実時間マージン不足

最初の調査では「`_wait_until`（実時間`time.monotonic()`でポーリングする
テストヘルパー）の既定`timeout=5.0`秒がWindows CIでしか検証されておらず、
別環境では不足していただけ」と判断し、`timeout`を`20.0`秒へ引き上げる
修正を行った。しかしUbuntu環境（SSH経由）で実際に検証したところ、
`timeout=20.0`秒でも**ほぼ毎回正確に約20.1秒で**同じ箇所（
`await _wait_until(lambda: _state(service, job_a) is JobState.SUCCEEDED)`）
でタイムアウトすることが判明し、これは「多少遅いだけ」ではなく決定的な
ハングであると分かった。timeoutをどれだけ伸ばしても解決しないため、
この最初の対応は誤りだった（`_wait_until`の`timeout`は`5.0`秒へ戻した）。

### 真の原因: テストとFakeClock駆動のretry stormの間のレース条件

`_retry_scheduler_loop`/`_requeue_after_backoff`/`_schedule_retry`に一時的な
デバッグログを仕込みSSH経由のUbuntu環境で実行を追跡したところ、以下が
判明した:

- `FakeClock.sleep`（`backend/tests/fakes.py`）は仮想時刻を即座に進める
  だけで実時間をほとんど消費しない（`await asyncio.sleep(0)`による
  cooperative schedulingの1回のyieldのみ）。そのため`queue.py`側の
  retry/backoffロジック（`_retry_scheduler_loop`、`_schedule_retry`、
  `_requeue_after_backoff`を含む、round 8, P1のエラー吸収経路も含む）は
  正しく実装されており、それ自体にはバグは無い。
- 問題はテスト側の設計にあった。このテストは
  `processor = FakeJobProcessor(default=FAILED/TIMEOUT)`で開始し、
  `_wait_until(job_a/job_b is FAILED)`を2回待ってから
  `processor.set_default(SUCCEEDED)`を呼び、その後`SUCCEEDED`を待つ、
  という手順で「job_aのrequeueエラーが吸収された後もjob_aが最終的に
  成功する」ことを検証しようとしていた。しかし`service.start()`後の
  最初の`await`（最初の`_wait_until`呼び出し）に到達するまでの間に、
  workerタスクとretry schedulerタスクは実時間をほとんど消費せずに
  何ラウンドでも実行を進められる（`FakeClock`のおかげでbackoffが実質
  瞬時のため）。そのため、`processor.set_default(SUCCEEDED)`がテストに
  よって呼ばれる前に、job_a・job_bの両方が`max_attempts=5`回の試行を
  （scriptedでないデフォルトのFAILED/TIMEOUT結果のまま）使い切り、
  リトライ不能な最終FAILED（`attempts=5, should_retry=False`）に到達
  してしまうことがある。一度この状態になると`_requeue_after_backoff`の
  ガード（`current.attempts >= job.max_attempts`相当の判定は
  `_finalize_result`の`should_retry`計算で行われ、以降は
  `start()`の起動時sweep条件`attempts < max_attempts`にも一致しなくなる）
  により二度と自動requeueされないため、後続の
  `_wait_until(... SUCCEEDED)`は原理的に条件を満たすことがなく、
  `timeout`の値に関わらず必ずタイムアウトする。
- 実際にUbuntu環境へデバッグログ（`[DBG t=...]`形式、時刻付き）を
  仕込んで観測したところ、job_a・job_b双方が`t=0.06`秒未満の実時間で
  `attempts=5, should_retry=False`に到達しており（`processor.set_default`
  が呼ばれるより前）、この仮説が実測で裏付けられた。
- このレースの勝敗は「`service.start()`が起動したworker/retry scheduler
  タスクが、テストコルーチンに制御を返す前にどれだけ多くのラウンドを
  実行できるか」という実行速度の問題であり、実時間マージンをいくら
  広げても解決しない。Windows側でこれまで再現しなかったのは、単に
  イベントループの実際のスケジューリング速度・粒度の違いにより、この
  レースがWindowsでは（比較的）テスト側に有利に働いていたためと考えられる
  （`uvloop`は`uvicorn[standard]`のUnix限定transitive dependencyとして
  インストールされるだけで、テストのevent loop policyには一切関与しない
  ことは確認済み -- 「Linux側だけ`uvloop`を使っているため」という仮説は
  誤り）。

### 対応

対症療法（`_wait_until`のtimeout調整）ではなく、テスト設計そのものの
レース条件を除去した。`processor.set_default(...)`を実行タイミングに
依存する形でテスト内から呼ぶのをやめ、`FakeJobProcessor.script(...)`で
job_a・job_bそれぞれの1回目の呼び出し結果を`FAILED/TIMEOUT`に固定し、
`processor`の既定値を最初から`SUCCEEDED`にした。これにより両ジョブの
運命（1回目失敗→2回目成功）は`service.start()`が呼ばれる前に完全に
決定しており、workerタスク・retry schedulerタスクが実際にどれだけ速く
（あるいは遅く）実行されるかに一切依存しなくなった。あわせて、
値そのものが本質的に不要になった中間の`_wait_until(job_a/job_b is FAILED)`
待機も削除した（scriptingにより発生タイミングが保証されなくなった
transientなFAILED状態を実時間ポーリングで捕捉しようとすると、今度は
「速すぎて捕まえ損ねる」形の別のレースを生みかねないため）。
`_wait_until`の既定`timeout`は元の`5.0`秒に戻した。

Ubuntu環境（SSH経由）で該当テストを25回連続実行し全て成功（各実行
0.1秒未満）、`tests/test_job_queue.py`全体を5回連続実行し全て成功
（各回49件、約2.6秒）、backend全体テストスイート（968件）も成功する
ことを確認した。

`tests/test_jobs_api.py`/`tests/test_recognitions_api.py`にも同じ
パターンの`_wait_until_job_state`ヘルパー（実時間5秒ポーリング）が
別途存在するが、これらは`TestClient`経由で実サーバーlifespanを使い
`SystemClock`（実時間）で駆動されるテストであり、`FakeClock`を使う
このテストとは性質が異なる（実際に業務ロジック側の遅延も実時間で発生
するため、テスト側が制御を取り戻せないまま先へ進んでしまうレースは
起こりにくい）。本Issueの対象外として変更していない。
