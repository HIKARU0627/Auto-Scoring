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

| 操作    | Review.action       | 追加で作る行                                                           | AI値が未生成でも可 |
| ------- | ------------------- | ---------------------------------------------------------------------- | ------------------ |
| approve | `approved`          | なし（`ai_grade_result_id` を確定として参照）                          | 不可（要AI grade） |
| edit    | `modified`          | 人間ソースの `GradeResult`（+任意で `RecognitionResult`/`Annotation`） | 不可（要AI grade） |
| reject  | `rejected`          | なし                                                                   | 可                 |
| regrade | `regrade_requested` | 新規 `Job`（kind=GRADING, `dependency_graph_version=NULL`）            | 可                 |
| undo    | `undone`            | なし（`undone_review_id` で対象を指すのみ）                            | -                  |

- **edit は同じ操作で確定する**: 既存の Flutter 画面には元々「修正してから
  別途承認する」という2段階の UI がなかったため、`edit_question` は
  `ReviewAction.MODIFIED` を直接記録する（承認/却下と対等な「決定」）。
- **approve/edit は AI grade を要求する**（`NoAiGradeYetError`,
  HTTP 409）。Issue #21 の既存 UI ガード（`_canApprove`: AI grade がなければ
  承認ボタンを無効化）を踏襲した decision。AI が一度も結果を出していない
  設問は、まず regrade でやり直すか、そのまま reject する。
- **reject/regrade は AI grade を要求しない**: AI が全く処理できなかった
  設問（例: 恒久的な失敗）でも記録・再判定できる必要があるため。
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

`adapters.review_actions._sync_submission_review_state` を、edit/reject/
regrade/approve/undo のどれが呼ばれた後でも同じトランザクション内で実行する:

- 対象 Submission の現在の state が `NEEDS_REVIEW`/`REVIEWED` のときだけ動く
  （処理中・出力済み・エラー状態はこの Issue の対象外 -- 出力済みの再オープン
  は後続Issueの仕事）。
- そのテストの全 `Question` について
  `domain.review_workflow.all_questions_confirmed` を評価する
  （各設問の `effective_latest_review` が `approved`/`modified` かどうか）。
- 全問確定していれば `NEEDS_REVIEW → REVIEWED`、そうでなければ
  `REVIEWED → NEEDS_REVIEW`（Undo が確定済みの設問を再び未確定に戻した場合を
  含む）。`Submission.with_state`/`SubmissionRepository.set_state` が既存の
  状態機械（`_SUBMISSION_TRANSITIONS`）でこの2方向を許可済み。

## 7. キーボードショートカット

`business-rules-and-evaluation-data.md` §2 (16) の決定表に統合済み。
Issue #22 で新規に決定/実装したのは `R`（再判定）と `Ctrl+Z`（Undo）。
Enter/E/X/↑↓ は Issue #21 の実装をそのまま踏襲。IME変換中・テキスト入力
フォーカス中は全ショートカット無効（`_shortcutBindings` が空マップを返す）。

## 8. API

`backend/src/auto_scoring/api/review_router.py` に追加:

- `GET /submissions/{sid}/questions/{qid}/reviews` -- 履歴全件（古い順）。
  配列長が次のリクエストの `expected_version`。
- `POST .../review/edit`
- `POST .../review/reject`
- `POST .../review/regrade`
- `POST .../review/approve`
- `POST .../review/undo`

いずれも `expected_version` を必須で受け取り、成功時は
`ReviewActionResponse`（新しい `Review` 行 + 副産物 + 同期後の
`submission_state`）を201で返す。バージョン不一致・AI grade未生成・
undo対象なしは409。

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

## 10. 対象外（後続Issue）

- Redo（Ctrl+Y / Ctrl+Shift+Z）。
- Annotation の図形的な追加・移動・削除 UI。
- 出力済み（`EXPORTED`）Submission の再オープンフロー。
- 複数レビュアー・チーム共有・自動学習（Issue #22 本文の「対象外」どおり）。
