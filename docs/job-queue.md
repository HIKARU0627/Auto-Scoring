# 再開可能な設問DAG対応並列AI処理キュー

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
（business-rules-and-evaluation-data.md §3 (C)、閾値は未確定）は`JobProcessor`
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
必須依存パッケージは追加しない。既定値: `max_concurrency=2`
（technology-stack.md §3.4「既定2〜3」、business-rules-and-evaluation-data.md
§3 (E)「PoC後に判断」までの暫定値）、`max_attempts=3`（既存の
`Job.max_attempts`既定と一致）、指数backoff
（`initial_backoff_seconds=1.0`、`backoff_multiplier=2.0`、
`max_backoff_seconds=30.0`）。

Confidence閾値（business-rules-and-evaluation-data.md §3 (C)、PoC後に判断）は
`QueueSettings`に含めない -- 本Issoueのキューは`usable`という既に判定済みの
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

## API

`auto_scoring.api.jobs_router`（`/submissions/{submission_id}/jobs` 以下）:

- `POST /submissions/{submission_id}/jobs` -- 確定DAGに基づきQuestionごとの
  Jobを作成し、依存のないQuestionをQUEUEDでキューへ投入する
  （`can_start_submission_processing`のゲートを通らない場合は409）。既に
  同じ確定グラフバージョンのJobが存在する場合は何もしない（idempotent、上記
  複合UNIQUE制約による）。
- `GET  /submissions/{submission_id}/jobs` -- 一覧・進捗（state、attempts、
  error_code、blocked_on_question_id等）。
- `GET  /jobs/{job_id}` -- 単一Jobの詳細。
- `POST /jobs/{job_id}/retry` -- `FAILED`のJobを`QUEUED`へ戻し再投入する。
- `POST /jobs/{job_id}/cancel` -- `QUEUED`/`BLOCKED`/`FAILED`は即座に、
  `RUNNING`は実行中タスクへcancel要求を送った上で`CANCELLED`にする。
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
