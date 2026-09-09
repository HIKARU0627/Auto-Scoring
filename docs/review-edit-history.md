# レビュー操作履歴（edit / reject / regrade / approve-and-next / Undo）

GitHub Issue [#22](https://github.com/HIKARU0627/Auto-Scoring/issues/22)（親
[#3](https://github.com/HIKARU0627/Auto-Scoring/issues/3)）の実装記録。対象は
添削レビュー画面（Issue #21）の action bar が実際に人間の判断を永続化し、
その全履歴を復元可能にする部分 -- `backend/src/auto_scoring/domain/
review_workflow.py` / `backend/src/auto_scoring/adapters/review_actions.py` /
`backend/src/auto_scoring/api/review_router.py` と、
`app/lib/features/pdf_review/pdf_review_page.dart` の該当箇所。

依存: #11（データモデル）・#20（AI採点パイプライン）・#21（PDFレビュー画面と
`Review`/`ReviewAction` の domain groundwork -- `APPROVED`/`MODIFIED`/
`REJECTED` と `ai_grade_result_id`/`human_grade_result_id` は #21 の時点で
既に存在した）。

## 1. データモデルの変更（migration `0013_review_history_edit`）

`reviews` テーブルに3列を追加し、`action` の許容値を2つ増やした。

| 列                 | 追加理由                                                          |
| ------------------ | ----------------------------------------------------------------- |
| `version`          | 同時実行制御のトークン（§2）                                      |
| `regrade_job_id`   | `regrade_requested` 行が投入した `Job` を指す                     |
| `undone_review_id` | `undone` 行が取り消す対象の `Review` 行を指す（物理削除はしない） |

`ReviewAction` に `REGRADE_REQUESTED`/`UNDONE` を追加。`Review.__post_init__`
（`domain/models.py`）が各 action の必須フィールドを検証し、`db/orm.py` の
`ReviewRow` が同じ検証を `CHECK` 制約として DB 側にも二重で持たせている
（AGENTS.md「invariants は…実制約で」）。

## 2. 同時実行制御（optimistic concurrency control）

**決定**: 新しい別テーブル（カーソル行）は導入せず、`reviews` 自体に
`version` 列（1始まりの、この `(submission_id, question_id)` ペア内での連番）
を持たせ、`uq_reviews_submission_question_version`
（`UNIQUE(submission_id, question_id, version)`）で保護する。

- クライアントは直前に読んだ `GET .../reviews` の配列長（何もなければ `0`）を
  `expected_version` として次の mutating request に渡す。
- `adapters.review_actions` の各関数はまず
  `domain.review_workflow.next_review_version` で
  `len(existing_reviews) == expected_version` を確認し（安価な事前チェック）、
  一致すれば `version = expected_version + 1` で新しい `Review` 行を作る。
- 事前チェックだけでは同時に2つのリクエストが同じ `expected_version` を読んで
  両方通過するレースを防げない。実際に二重作成を防いでいるのは
  `uq_reviews_submission_question_version` そのもの：片方の `commit()` が
  `IntegrityError` になり、`review_actions.py` がそれを
  `domain.review_workflow.ReviewVersionConflict` に変換して再送出する。
  `api.review_router` はこれを HTTP 409 として返す
  （Flutter 側は `SidecarErrorKind.conflict`）。
- 採点・annotation・recognitionの追加行は、確認対象の `Review` 行と
  **同じトランザクション**で `commit()` される。したがって version 衝突で
  ロールバックされれば、それらの行も一緒に取り消される -- 「重複request が
  履歴を二重作成しない」（Issue #22 受入条件）を保証する。

この設計により、`GradeResult`/`Annotation`/`RecognitionResult` 自体には一切
version を持たせていない（それらは元々 append-only で、`Review` が「どの
提案がどう確定したか」を記録する唯一の場所であるため）。

## 3. 各操作の意味

| 操作    | Review.action       | 追加で作る行                                                           | AI値が未生成でも可            |
| ------- | ------------------- | ---------------------------------------------------------------------- | ----------------------------- |
| approve | `approved`          | なし（`ai_grade_result_id` を確定として参照）                          | 不可（要AI grade）            |
| edit    | `modified`          | 人間ソースの `GradeResult`（+任意で `RecognitionResult`/`Annotation`） | 不可（要AI grade）            |
| grade   | `modified`          | 人間ソースの `GradeResult`（+任意で `RecognitionResult`/`Annotation`） | **AI grade が無い場合のみ可** |
| reject  | `rejected`          | なし                                                                   | 可                            |
| regrade | `regrade_requested` | 新規 `Job`（kind=GRADING, `dependency_graph_version=NULL`）            | 可                            |
| undo    | `undone`            | なし（`undone_review_id` で対象を指すのみ）                            | -                             |

- **edit は同じ操作で確定する**: 既存の Flutter 画面には元々「修正してから
  別途承認する」という2段階の UI がなかったため、`edit_question` は
  `ReviewAction.MODIFIED` を直接記録する（承認/却下と対等な「決定」）。
- **approve/edit は AI grade を要求する**（`NoAiGradeYetError`,
  HTTP 409）。Issue #21 の既存 UI ガード（`_canApprove`: AI grade がなければ
  承認ボタンを無効化）を踏襲した decision。AI が一度も結果を出していない
  設問は、まず regrade でやり直すか、そのまま reject する。
- **reject/regrade は AI grade を要求しない**: AI が全く処理できなかった
  設問（例: 恒久的な失敗）でも記録・再判定できる必要があるため。

### 3.1 grade（人が最初から点数を入れる） — Issue #118

**問題**: AI 採点が permanent 失敗すると `GradeResult` は作られない
（Issue #97 の意図的な決定。**誤った採点結果を残さないためであり、これは維持する**）。
ところが人の操作は上表のとおりすべて AI の行を経由していた -- approve は確定し、
edit は訂正し、どちらも `NoAiGradeYetError` で 409 になる。したがって
**AI が採点できなかった設問は人も採点できず、答案がそこで詰んでいた**。
実機検証（2026-09-09、実データ × 実 Vertex AI）で発生した。

「AI が提案し、人が確定する」は、**AI が外したときに人が引き取れて初めて成立する**。

**決定**: `edit` を緩めるのではなく、**別の経路**を足す。

- **AI grade が既に存在する場合は 409 で拒否する**（`AiGradeAlreadyExistsError`）。
  「AI が何も出していない」ことを呼び出し側が主張し、サーバが確かめる形にする。
  レビュー画面を開いてから保存が届くまでの間に再判定が着地した場合も、
  `edit`/`approve` の `expected_ai_grade_id` と同じく**衝突として表面化する** --
  人が見ていない AI の試行を黙って無視した採点を記録しない。
- **`ReviewAction.MODIFIED` を再利用する**（6つ目の action を作らない）。
  「この設問は確定済み」を読む側 -- `all_questions_confirmed` と
  それが門番をする `Submission.REVIEWED`、`domain.pdf_export` の出力ゲート、
  `resolve_effective_grade`、画面の `deriveQuestionStatus` -- は
  **すでに全員、人間 grade を伴う `modified` 行を正しく扱っている**。
  新しい値を足せば、その全員に1つずつ教え直す必要が出る。
- **`ai_grade_result_id` は `NULL`**。この列の意味は
  **「この決定が土台にした AI の試行」**であり、土台が無かったのだから
  `NULL` が正しい記録である。そして
  **`modified` かつ `ai_grade_result_id IS NULL` が「人が最初から採点した」の記録**
  になる（Issue #118 受入5）。API は既に `ReviewResponse.ai_grade_result_id`
  を返しているので、新しいフィールドは足していない。
  `human_grade_result_id` は従来どおり必須なので、確定行が
  「何を決めたのか」を持たないことは依然ありえない。
- **不変条件と DB CHECK を狭めた**（migration `0016_manual_grade_without_ai`）:
  `ck_reviews_confirmed_requires_ai_grade` は
  `action != 'approved' OR ai_grade_result_id IS NOT NULL` になった。
  approve は今までどおり AI grade を要求する（承認する対象が無いのだから当然）。
- **画面側**: AI が終了して grade を出さなかった設問に
  「AIはこの設問を採点できませんでした」（`Job.last_error` 付き）を出し、
  **「点数を入力 (G)」と「再判定 (R)」を並べて**出す。
  `last_error` は provider 名・例外クラス名・HTTP status だけで組み立てられており
  （Issue #97 レビュー4回目）、答案本文を含みえないので画面に出してよい。
- **`deriveQuestionStatus` の優先順位を1点だけ変えた**（`core/question_status.dart`）。
  従来は「キューが先、人が後」を全状態に適用していたが、
  **停止済みの Job（failed / cancelled / succeeded かつ usable=false）については、
  その Job より後に記録された人の決定が勝つ**。そうしないと、
  答案自体は `REVIEWED`（確認済み）なのに、レール・DAG・インスペクタの3箇所が
  「失敗」と言い続けることになり、Issue #84 がこの関数を1箇所に集約して
  防いだはずの食い違いがそのまま再発する。
  Job より**前**の決定は従来どおり Job が勝つ（再提出は新しい Job を作る）。

**対象外**: `edit` と同じく、この経路も Annotation の図形的な編集は扱わない
（§5）。criterion ごとの判定はダイアログで入力できるようにしたが、
これは `edit` 側には無い -- `edit` には土台となる AI の判定があり、
そのまま持ち越すのが既定だからである（`_showEditDialog` の
`carriedCriteria`）。

- **regrade は新しい `Job` を作る**が、`dependency_graph_version` は
  `NULL` のままにする（自動DAGスケジューリングの冪等キー
  `uq_jobs_submission_question_graph_version` と衝突させないため -- SQLite
  は `NULL` 同士を別物として扱うので、同じ設問への複数回の regrade もすべて
  共存できる）。`GradingJobProcessor` はこの `Job` 自身の
  `dependency_graph_version` を読まず、確認済みグラフを test から独立に
  引くため、採点自体には影響しない。

## 4. Undo（Ctrl+Z）と「有効な最新レビュー」の導出

**決定**: Redo は Issue #22 の対象外（「実施内容」が求めているのは
「直前の人間操作を取り消す」ことのみ）。Redo自体は
`business-rules-and-evaluation-data.md` §2 (16) の決定表に「将来の割り当て」
として残っているが、本Issueでは実装しない。

Undo は履歴を物理削除・変更しない。代わりに `undone` という**新しい行**を
追加し、`undone_review_id` で取り消し対象を指す。「今この設問がどういう
状態として表示されるべきか」は、生の `Review` テーブルから毎回導出する
（`domain.review_workflow.effective_latest_review`、Flutter側の等価な実装は
`pdf_review_page.dart` の `_effectiveLatestReview`）:

1. `undone` 行それぞれについて、その行自身の id と `undone_review_id` を
   「除外集合」に加える。
2. 履歴を新しい方から見て、除外集合に入っていない最初の行を返す（なければ
   `None` -- 「未着手のAI提案のまま」の状態）。

Redo がない前提では、この単純な除外集合だけで正しく動く（`undone` は必ず
「その時点での有効な最新行」を対象にする -- クライアントは
`expected_version` を渡すだけで、サーバーは自分で
`effective_latest_review` を計算して対象を決める）。

`QuestionReviewState.displayGrade`（Flutter）と
`GradeResult` の実際の表示値も、この「有効な最新レビュー」から導出するよう
変更した：

- `effectiveReview.action == 'modified'` → その `humanGradeResultId` が指す
  `GradeResult`
- `effectiveReview.action == 'approved'` → その `aiGradeResultId` が指す
  `GradeResult`
- それ以外（`rejected`/`regrade_requested`/未レビュー） → 単純に最新の
  AI `GradeResult`

これにより、edit を undo すると画面に表示される点数も実際に元へ戻る
（「単に履歴行を足すだけで、表示中の値は変わらない」という P1 相当のバグを
防ぐ -- 素朴に「タイムスタンプ最新の human GradeResult」を表示に使うと、
undo 後も取り消したはずの修正が表示され続けてしまう）。

## 5. Annotation の修正範囲（決定 / 対象外）

**決定**: `edit` はスコア・コメント・認識文字の修正はサポートするが、
Annotation（○×△・下線・囲みなどのマーク）を**図形的に**移動・追加・削除する
UI は Issue #22 の対象外とする。理由:

- Annotation は append-only で、表示側（`annotationsForDisplayedAttempt`）は
  「表示中の `GradeResult` と同じ `created_at` を持つ行」を拾う設計
  （Issue #21 P1）。`edit` が新しい human `GradeResult` を作ると、その新しい
  `created_at` に一致する annotation が無い限り、AIが付けたマークが画面から
  消えてしまう。
- これを避けるため、`edit_question`（`annotations` パラメータを渡さない
  場合）は AI 提案時点の annotation 一式を、新しい `GradeResult` と同じ
  `created_at` で**コピーして再挿入**する
  （`adapters.review_actions._carry_forward_annotations`）。人間は
  `annotations` を明示的に渡すことで、コピーではなく指定した内容で完全に
  置き換えることもできる（API レベルでは既にサポート済み）。
- グラフィカルな「このマークをドラッグして動かす/消す」UI は、既存の
  オーバーレイ実装（widget として重ねているだけ）に本格的な編集機構
  （タップ選択・削除・ドラッグ、対応する API）を追加する必要があり、
  本Issueのスコアに対して不釣り合いに大きいため見送った。後続Issueで
  「Annotationの図形編集」として扱う。

## 6. Submission の `REVIEWED` 遷移

**決定**: 「未確認設問が残る Submission は出力可能状態にならない」
（Issue #22 受入条件）を、`SubmissionState.REVIEWED` への遷移そのものを
ゲートすることで満たす。まだ出力（PDF export）機能自体は実装されていない
ため、`REVIEWED` は将来の export 機能の前提条件として振る舞う。

> **訂正（Issue #112）: 上の段落は書かれた時点の計画であって、現在のコードの
> 説明ではない。** 実際に出力を作った Issue #23 は、状態ではなく
> `domain.pdf_export.unconfirmed_question_ids` でレビュー履歴を直接見る形に
> した（`api/export_router.py`、`jobs/export_processor.py`）。
> **したがって `REVIEWED` は門ではなく鏡である** -- 出力を守っているのは出力側の
> 判定で、状態はその事実を画面へ映すためにある。`backend/tests/test_export_api.py`
> が `make_submission()` の既定（`unprocessed`）のまま通っていることが、
> 出力が `SubmissionState` から独立していることの実測である。

`adapters.review_actions._sync_submission_review_state` を、edit/reject/
regrade/approve/undo のどれが呼ばれた後でも同じトランザクション内で実行する:

- 対象 Submission の現在の state が `AI_PROCESSED`/`NEEDS_REVIEW`/`REVIEWED` の
  ときだけ動く（`_REVIEWABLE_SUBMISSION_STATES`）。
  **`AI_PROCESSED` は Issue #112 で足した。** Issue #22 の時点ではこれを
  「処理中」と読んで外していたが、実際には**取込が問題なく終わった普通の答案が
  留まる状態**であり、外している限り普通の答案ほど完了が記録されなかった。
  いまも外れているのは `UNPROCESSED`/`AI_PROCESSING`（レビューされたものが
  何も無い）、`EXPORTED`（出力済みの再オープンは後続Issueの仕事）、`ERROR`。
- そのテストの全 `Question` について
  `domain.review_workflow.all_questions_confirmed` を評価する
  （各設問の `effective_latest_review` が `approved`/`modified` かどうか）。
  **Confidence はこの判定に一切関与しない**（簡易設計書 §25.2）。
- 全問確定していれば `REVIEWED` へ。そうでなければ**取込が置いた場所へ戻す** --
  `review_reason` があれば `NEEDS_REVIEW`、無ければ `AI_PROCESSED`
  （`_unconfirmed_state`）。Undo が確定済みの設問を未確定に戻した場合もこれである。
  **取込が問題なく終わった答案を `NEEDS_REVIEW` へ送らない**のが要点で、
  あれは「人が見ないと先へ進めない」ことを表す唯一の旗
  （[design-tokens.md](./design-tokens.md) §3.1）だから、無関係な答案に立てると
  意味が薄まり、しかも二度と下りない。

### 6.1 `REVIEWED` は「隠す」ことであって「閉じる」ことではない（Issue #137）

**決定**: 答案を `REVIEWED` にすることで、その答案が**画面の作業一覧から
外れる**のはよい。しかし**サイドカーの側で到達不能になってはならない**。

Issue #112 で全問承認した答案が `REVIEWED` になり、ホーム画面の
「レビューを続ける」候補から外れるようになった（`HomeTestProgress` の
`_resumableBuckets` は `needs_review`/`ai_processed` だけを見る）。残りの作業
だけを見せるための意図した動きである。ところが #137 の実機再検証で、
**そこから先へ行けなくなっていた**: 答案がホームから消え、開き直す画面が
無く、取り込み直しは重複として弾かれ（`decide_reintake`）、PDF出力ボタンは
添削レビュー画面にしか無い。このアプリの成果物は採点済みPDFなので、
**完了操作を行うと成果物が取り出せなくなる**という事故だった。

画面の導線は `app/` 側で直す（答案キュー画面 = Issue #113、そこからの出力 =
Issue #137）。ただし導線をいくら足しても、下が塞がっていれば行き止まりに
戻る。**その下限を `backend/tests/test_finished_submission_reachability.py`
が 1 か所で押さえている**:

- `GET /tests/{id}/submissions` は `reviewed`/`exported` を落とさない。
  一覧を持つ画面にとって、ここが唯一の入口である。
- `GET /submissions/{id}` は `reviewed` の答案を返す。添削レビュー画面が
  開くときに最初に引く。
- `REVIEWED` は `_REVIEWABLE_SUBMISSION_STATES` に含まれる（§6 の一覧）ので、
  開き直して直し、また完了へ戻せる。
- `POST /submissions/{id}/export` は答案の状態を見ない（§6 の訂正のとおり、
  出力はレビュー履歴のほうを見る）。**見るようにしてはいけない** -- 完了した
  答案を「もう終わったもの」として弾く条件を足すと、成果物が二度と取り出せなく
  なる。

3 つのルータにまたがるので、どのルータのテストも単独ではこの性質を守れない。
だから 1 モジュールにまとめてある。

## 7. キーボードショートカット

`business-rules-and-evaluation-data.md` §2 (16) の決定表に統合済み。
Issue #22 で新規に決定/実装したのは `R`（再判定）と `Ctrl+Z`（Undo）。
Issue #118 で `G`（点数を入力）を追加した。
Enter/E/X/↑↓ は Issue #21 の実装をそのまま踏襲。IME変換中・テキスト入力
フォーカス中は全ショートカット無効（`_shortcutBindings` が空マップを返す）。

## 8. API

`backend/src/auto_scoring/api/review_router.py` に追加:

- `GET /submissions/{sid}/questions/{qid}/reviews` -- 履歴全件（古い順）。
  配列長が次のリクエストの `expected_version`。
- `POST .../review/edit`
- `POST .../review/grade` -- AI 採点が無い設問に人が点数を入れる（Issue #118、§3.1）。
  AI grade が存在する場合は 409。
- `POST .../review/reject`
- `POST .../review/regrade`
- `POST .../review/approve`
- `POST .../review/undo`

いずれも `expected_version` を必須で受け取り、成功時は
`ReviewActionResponse`（新しい `Review` 行 + 副産物 + 同期後の
`submission_state`）を201で返す。バージョン不一致・AI grade未生成
（`edit`/`approve`）・AI grade が既にある（`grade`）・undo対象なしは409。

## 9. 検証経路

- **file**: `backend/src/auto_scoring/domain/review_workflow.py`
  （純粋関数）、`backend/src/auto_scoring/adapters/review_actions.py`
  （オーケストレーション）、`backend/src/auto_scoring/api/review_router.py`
  （HTTP境界）、`backend/migrations/versions/0013_review_history_edit.py`
  （スキーマ）、`app/lib/features/pdf_review/pdf_review_page.dart`
  （UI/操作）。
- **environment**: `backend/tests/conftest.py` の `session_factory`/`db_url`
  fixture（実SQLite、`head` までマイグレーション済み）、
  Flutter側は `flutter_test` + 実 `pdfrx`/pdfium（`Pdfrx.cacheDirectoryPath`
  を一時ディレクトリに固定）。
- **script/discovery**: `uv run pytest`（`backend/tests/test_review_workflow.py`
  ・`test_review_api.py`・`test_domain_models.py`・`test_migrations.py`）、
  `flutter test test/pdf_review_page_test.dart`。`pnpm run test`/`pnpm run check`
  がどちらも実行する。
- **fixture**: `backend/tests/support.py`（`make_review` に `version` 既定値
  `1` を追加）、`app/test/pdf_review_page_test.dart` の `_review`/
  `_reviewAction`/`_dependencies`（edit/reject/regrade/approve/undo の
  汎用フェイクをデフォルトで配線し、個別テストは必要な callback だけ上書き
  する）。
- **assertion**: 同時実行制御（`test_duplicate_concurrent_approve_requests_do_not_double_create_history`）、
  version不一致の拒否（`test_stale_expected_version_is_rejected_with_409`）、
  AI値保持（`test_edit_creates_a_confirmed_human_grade_and_keeps_the_ai_value`）、
  Submission遷移（`test_submission_becomes_reviewed_only_once_every_question_is_confirmed`
  / `test_submission_returns_to_needs_review_once_an_undo_unconfirms_a_question`）、
  Undoの表示反映（Flutter `Ctrl+Z undoes the currently-effective review as a
new row`）。
- **exit code / CI job**: `pnpm run check`（`test:backend`/`test:app`）が
  非ゼロ終了で失敗を検知。GitHub Actions のブランチ保護必須チェックに含まれる
  （`docs/quality-gates.md` 参照）。

## 10. Codexレビュー(1回目)での修正（P1x2 / P2x3）

PR #46 の1回目コードレビューで指摘された5件。§2/§4の設計自体は変えず、
「下流の消費者」と「エラー変換」の抜けを塞いだ。

- **P1: Undo後もrecognition/gradeの"正本"が消費者側で古いまま**
  `QuestionReviewState.displayGrade`（Flutter）は元々 `effectiveReview` 経由
  で undo-aware だったが、recognition側（`latestHumanRecognition`）と、
  `GradingJobProcessor` が前提設問のcontextを組み立てる際に使っていた
  `_latest_preferring_human`（「sourceがhumanなら常に最新を採用」、undoを
  一切見ない）は undo を無視していた。
  - `domain.review_workflow` に `resolve_effective_grade`/
    `resolve_effective_recognition` を追加（`effective_latest_review` と同じ
    「reviewsから実効行を導出する」ロジックを、`GradeResult`/
    `RecognitionResult` の解決にも適用）。`GradingJobProcessor.process` は
    前提設問ごとにこれを呼ぶよう変更（`_latest_preferring_human` は削除）。
  - Flutter側は `QuestionReviewState.effectiveHumanRecognition`
    （`effectiveReview.action == 'modified'` のときだけ、その human
    `GradeResult` と同じ `createdAt` を持つ human recognition を返す）を追加
    し、`latestHumanRecognition`（undo非対応）は削除。Inspector・修正dialog
    のprefillの両方をこちらに切り替えた。
- **P1: 承認/修正がreviewerの見ていないAI試行に紐づく**
  画面ロード後、request到達前にregradeが完了すると（regrade完了はReview行を
  追加しないため `expected_version` は変化しない）、approve/editが新しい
  未確認のAI grade へ黙って確定してしまう問題。`EditReviewRequest`/
  `ApproveReviewRequest` に `expected_ai_grade_id`（省略可）を追加し、
  `adapters.review_actions._latest_ai_grade_matching` が最新AI gradeのidと
  比較、不一致なら `AiGradeChangedError` → HTTP 409
  （`_latest_ai_grade`の代わりにedit_question/approve_questionで使用）。
  `None`の場合はチェックをスキップ（後方互換; 実際のFlutterクライアントは
  常に `QuestionReviewState.latestAiGrade?.id` を渡す）。
- **P2: repository insertのflushがcommit専用のconflict handlerを迂回する**
  `SqlAlchemyReviewRepository.add()` は呼び出し直後に `session.flush()` する
  ため、同時書き込みの負け側はここで `IntegrityError` を送出しうる -- 旧
  `_commit_or_conflict` は `uow.commit()` だけを `try` していたため、この
  経路は素通りして未処理の500になっていた。`_finalize_review`
  （`uow.reviews.add` → `_sync_submission_review_state` → `uow.commit()` を
  ひとつの `try`/`except IntegrityError` で包む）に統合し、edit/reject/
  regrade/approve/undo の全関数がこれを使うよう変更。実際の並行性を検証する
  ため、`test_review_api.py` に `threading.Barrier` で両requestを事前チェック
  通過まで同期させてから競合させるテスト
  （`test_concurrent_approve_requests_racing_past_the_precheck_resolve_with_one_conflict`）
  を追加（既存の `test_duplicate_concurrent_approve_requests_do_not_double_create_history`
  は`TestClient.post`が同期実行のため、実際にはレースしていなかった）。
- **P2: domain validation失敗が client error に変換されない**
  `score_awarded > score_maximum`、未知の `criterion.outcome`、ページ外の
  annotation rect はpydanticの型検証は通過するが、`edit_question` が
  `Score`/`CriterionResult`/`NormalizedRect` を構築する際に
  `ScoreOutOfRange`/`InvalidCoordinate`（`DomainError`）または
  `ValueError`（`CriterionOutcome(...)` の不正値）を送出し、`review_router`
  はそれらを捕まえていなかった（→ 未処理の500）。`edit()` ハンドラに
  `except (DomainError, ValueError): raise HTTPException(422, ...)` を追加
  （`test_registration_router.py` の既存パターンと同じ変換規則）。
- **P2: reviewer操作中にnavigationしたまま別設問がrefreshされる**
  action中も設問navigationは有効なままのため、reviewerが設問Aを承認し、
  requestが完了する前に設問Bへ切り替えると、旧 `_performReviewAction` の
  `finally` は（その時点の）`_currentQuestion` = Bをrefreshしてしまい、Aの
  cacheはstaleなまま。`_performReviewAction`/`_refreshQuestion`/`_loadReview`
  を「操作対象の `QuestionResponse` を明示的に受け取る」形へ変更（各呼び出し
  元が action 開始前に `question`/`review` をキャプチャ）。`_approveAndNext`
  も、承認した設問がまだ選択されたままのときだけ auto-advance するよう変更。

修正差分: `backend/src/auto_scoring/domain/review_workflow.py`、
`backend/src/auto_scoring/jobs/grading_processor.py`、
`backend/src/auto_scoring/adapters/review_actions.py`、
`backend/src/auto_scoring/api/review_router.py`、
`app/lib/features/pdf_review/pdf_review_page.dart`、
`app/lib/core/app_dependencies.dart`、`app/lib/api/sidecar_api_client.dart`
（+ `pnpm run openapi:generate` で再生成した `app/packages/auto_scoring_api`）。

## 11. Codexレビュー(2回目/確認レビュー)での修正（P1x1 / P2x2）

R1修正に対する確認レビューで指摘された3件。R1で導入した `expectedAiGradeId`
自体の設計は変えず、「値をいつ確定させるか」「nullと空文字列の区別」という
2つの取り違えを塞いだ。

- **P1: edit dialogを開く前にconcurrency tokenを取得していなかった**
  `_showEditDialog` は `expectedVersion`/`expectedAiGradeId` を
  `await showDialog(...)` の**後**、つまりdialogが閉じてから `review`
  （background pollingが同じインスタンスをin-placeで更新し続けるmutableな
  `QuestionReviewState`）経由で読んでいた。dialogが開いている間にregradeが
  完了すると、dialogはprefillした古いscore/textを表示したままなのに、保存時
  には新しいAI grade ID/versionを送ってしまい、reviewerが一度も見ていない
  AI試行への古い訂正がそのまま確定してしまう。`currentGrade`/`currentText`
  を計算するのと同じタイミング（dialogを開く**前**）で
  `expectedVersion`/`expectedAiGradeId` をローカル変数へ確定させ、保存時は
  その値だけを送るよう変更。これにより、dialogが開いている間に競合が起きた
  場合は必ず409になる（一度、この2行を意図的に旧実装へ戻して新規テストが
  実際に落ちる＝有効な回帰テストであることを確認済み）。
- **P2: 送信された `score_maximum` を設問の `points` に対して検証していな
  かった** `Score.__post_init__` は `0 <= awarded <= maximum` しか見ない
  ため、5点満点の設問に対して `score_awarded=100, score_maximum=100`
  のような、内部的には整合するが設問の実際の配点と無関係な値をedit
  requestへ渡せてしまい、それがそのまま確定した人間gradeとなって下流の
  採点context（`GradeResultContextEntry`）へ流れ込む。`_load_submission_and_
question` の戻り値を `(Submission, str)`（test_idのみ）から
  `(Submission, Question)` へ変更し、`edit_question` が
  `score_maximum != question.points` を `ScoreOutOfRange` として拒否する
  （HTTP 422、R1で追加した `(DomainError, ValueError)` → 422 変換に自然に
  乗る）。`GradingJobProcessor.process` がAI responseに対して既に行っている
  `response.max_score != question.points` と同じチェックを、人間による
  edit requestにも適用する形。
- **P2: 明示的にクリアされたrecognitionが `null`（編集なし）に潰れていた**
  `recognizedText: text.isEmpty ? null : text` は、AIの誤認識文字を全部
  削除して「解答は空白」と明示的にマークする操作と、そもそも認識結果自体が
  何もない設問をスコアだけ編集する操作（textフィールドは元から空のまま）を
  区別できず、両方とも `null`（`edit_question` に「recognitionは触らない」
  と伝わる）に潰していた。前者の場合、保存は成功したと画面に表示されるのに
  human recognition行が作られないため、reviewerが消したはずのAIテキストへ
  fallbackし続けてしまう。`currentText.isEmpty && text.isEmpty ? null : text`
  へ変更（「dialogを開いた時点でも今も空」の場合だけ `null` のまま
  ＝スコアのみ編集で毎回空文字列のrecognition行が量産されるのを防ぎ、
  それ以外は空文字列を含めて実際の値をそのまま送る）。

修正差分: `backend/src/auto_scoring/adapters/review_actions.py`、
`backend/tests/test_review_api.py`、
`app/lib/features/pdf_review/pdf_review_page.dart`、
`app/test/pdf_review_page_test.dart`。

## 12. Codexレビュー(3回目/確認レビュー)での修正（P2x3、Issue #22の最終ラウンド）

3回目（P1指摘なし）で、Issue #22のレビューサイクルはこれで完了とする。

- **P2: 2回目以降のeditで、明示的にクリアされたrecognitionを保持できていな
  かった** R2で入れた `currentText.isEmpty && text.isEmpty ? null : text`
  は、「AIの誤認識文字を1回目のeditで空文字列へ明示的にクリアした後、2回目
  のeditでscoreだけ変更する」場合を見落としていた -- 2回目を開いた時点で
  `currentText` はその**保存済みの空文字列recognition**由来なので、text
  フィールドを一切触らなければ `currentText`/`text` は両方とも空になり、式が
  `null`（「recognitionは触らない」）を送ってしまう。すると2回目のeditが
  作る新しい human `GradeResult` には対応するrecognitionが無いままとなり、
  `resolve_effective_recognition`/`effectiveHumanRecognition` は
  created_atが一致するものを探せずAIの元テキストへfallbackしてしまう
  （＝無関係な2回目のeditが1回目の訂正を黙って元に戻す）。dialogを開く前に
  `currentHumanRecognition`（`review.effectiveHumanRecognition`、他の
  concurrency tokenと同じタイミングで確定）も併せて確定させ、
  `currentHumanRecognition == null && currentText.isEmpty && text.isEmpty
? null : text` へ変更 -- 「既存の有効なhuman recognitionが存在する」場合は
  そのtextが空文字列であっても常に送り直す（＝新しいhuman gradeの
  created_atに紐づけ直す）ことで、何回editを重ねても明示的な空クリアが
  維持される。
- **P2: 独立した手動recognition訂正（review履歴を経由しないもの）を保持
  できていなかった** `domain.review_workflow.resolve_effective_recognition`
  は、有効な `modified` review自身のrecognitionにマッチしない場合、
  マッチしなかった人間recognition行を一律で無視してAIへfallbackしていた。
  しかしIssue #19由来の `POST .../recognitions`（`recognitions_router.
create_manual_recognition`）はそもそも `Review` 行を一切作らずに人間
  recognitionだけを追加できるため、review履歴が全く無い設問（または
  他の無関係なeditがundoされただけの設問）でも、この手動訂正がAIテキストへ
  上書きされてしまっていた。`_undone_review_ids`（`effective_latest_review`
  と共有）を使って「undoされたeditが自分の human grade
  created_atで作ったrecognition」だけを除外リストへ入れ、それ以外の
  未マッチな人間recognition（review非依存の独立した手動訂正や、undoされて
  いない古いeditのrecognition）は除外せず、その中の最新行を採用するよう
  変更。`GradingJobProcessor` はこの関数を経由して前提設問のcontextを
  組み立てるため、依存する設問への影響も同時に直る。
- **P2: comment-onlyのeditで、未変更のrubric criteria/rationaleが消えて
  いた** dialogは元々criteria/rationaleを編集するUIを持たないため、
  `editReview` を呼ぶたびに`criteria`/`rationale`をデフォルト（空リスト/
  `None`）のまま送っていた。`edit_question`はrequestに渡された値だけで
  新しいhuman `GradeResult`を組み立てるため、コメントだけを直すつもりの
  editでも、以前判定済みだった全rubric criterionが未判定へ戻り、rationale
  も消える（`displayGrade`がその human gradeを表示に選ぶため画面にも、
  `GradeResultContextEntry`経由で下流の採点contextにも影響する）。dialogを
  開く時点の `currentGrade`（表示中のgrade）自身の `criteria`/`rationale`
  を `carriedCriteria`/`carriedRationale` としてキャプチャし、保存時は
  常にそれを送るよう変更（dialogに無いfieldは「編集できないのだから毎回
  引き継ぐ」という一貫した扱いにした）。

修正差分: `backend/src/auto_scoring/domain/review_workflow.py`、
`backend/tests/test_review_workflow.py`、
`backend/tests/test_grading_processor.py`、
`app/lib/features/pdf_review/pdf_review_page.dart`、
`app/test/pdf_review_page_test.dart`。

## 13. 対象外（後続Issue）

- Redo（Ctrl+Y / Ctrl+Shift+Z）。
- Annotation の図形的な追加・移動・削除 UI。
- 出力済み（`EXPORTED`）Submission の再オープンフロー。
- 複数レビュアー・チーム共有・自動学習（Issue #22 本文の「対象外」どおり）。
