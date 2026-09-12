# MVP データモデル・ローカル保存基盤

GitHub Issue #11（親: #3）の実装記録。対象は Python サイドカー側の

- domain model と SQLite スキーマ（Test / Question / Rubric / Submission /
  RecognitionResult / GradeResult / Annotation / Review / Job）
- SQLAlchemy 2 + Alembic によるスキーマ管理
- `app-data/` のファイル保存規則（atomic write・削除・復旧）

のみ。各画面と OCR/AI の具体処理は対象外（Issue #11「対象外」）。業務ルールの根拠は
[`business-rules-and-evaluation-data.md`](./business-rules-and-evaluation-data.md)
（Issue #8）、技術方針の根拠は
[`technology-stack.md`](./technology-stack.md)（§3.3 データベース、§5 リポジトリ構成）。

## 1. レイヤーとコード配置

```text
backend/src/auto_scoring/
├─ domain/
│   ├─ models.py        # Entity / 値オブジェクト / 状態機械（フレームワーク非依存）
│   └─ repositories.py  # Repository / UnitOfWork の Protocol（ポート）
├─ db/
│   ├─ base.py           # DeclarativeBase
│   ├─ orm.py            # SQLAlchemy テーブル定義（制約・index を含む）
│   ├─ engine.py         # WAL / foreign_keys 等の PRAGMA を設定するエンジン
│   └─ migrator.py       # Alembic 呼び出しのラッパー
└─ adapters/
    ├─ sqlalchemy_repositories.py  # domain.repositories の実装
    ├─ unit_of_work.py             # 1 トランザクション境界
    ├─ _mappers.py                 # domain dataclass ⇔ ORM row 変換
    ├─ local_storage.py            # app-data/ の atomic write・削除
    ├─ atomic.py                   # DB commit と ファイル書き込みをまとめる
    └─ purge.py                    # 一括削除 + 監査ログ

backend/migrations/                # Alembic migration（versions/0001, 0002, ...）
backend/alembic.ini
```

依存方向は `AGENTS.md`「Architecture」のとおり `api → domain ← adapters`。
永続化の補助経路は `adapters → db → domain` とする（`domain` は
SQLAlchemy/Alembic/FastAPI を import しない。`db` は `adapters`/`api` を import
しない。`tests/test_architecture.py` で強制）。

## 2. Entity 一覧

| Entity                       | 役割                                          | 追記のみか   |
| ---------------------------- | --------------------------------------------- | ------------ |
| `Test`                       | 登録したテスト                                | —            |
| `Question`                   | 設問。ページ・配点・各領域（0〜1 正規化座標） | —            |
| `Rubric` / `RubricCriterion` | 設問ごとの採点基準                            | —            |
| `Submission`                 | 1 生徒 = 1 PDF の答案。状態機械を持つ         | —            |
| `RecognitionResult`          | 文字認識結果（`source` = ai / human）         | **追記のみ** |
| `GradeResult`                | 採点結果（`source` = ai / human）             | **追記のみ** |
| `Annotation`                 | ○×△・点数・コメント・下線/囲み                | —            |
| `Review`                     | 人間の承認/修正/却下の履歴                    | **追記のみ** |
| `Job`                        | 非同期処理（recognition/grading/export）      | —            |
| `AnswerImage`                | 設問ごとの回答欄切り出し画像（Issue #17）     | —            |
| `Export`                     | 成功した添削済みPDF出力（Issue #23）          | **追記のみ** |

`Annotation` は永続化上 **矩形 0〜1 個**（`rect: NormalizedRect \| null`）のみ持つ。
改行をまたぐ下線・囲みの **行ごと複数矩形** は DB 列では表現しない（Issue #256）:
`anchor_text` とその attempt の `RecognitionResult.boxes` から、描画直前に
`resolve_annotation_rects`（Python）／`resolveAnnotationRects`（Electron・Flutter）で
0〜N 個の page 正規化矩形へ解決する。N>1 は UNDERLINE / BOX に限り、CROSS は N=1（先頭行）
のまま。詳細は [`pdf-export.md`](./pdf-export.md) §2.6.5。

> `AnswerImage` と `Submission` の `source_pdf_sha256` / `page_count` /
> `original_filename` / `review_reason` は Issue #17（答案取込・画像前処理）で
> マイグレーション `0005_answer_intake` により追加した。詳細は
> [`answer-intake-and-preprocessing.md`](./answer-intake-and-preprocessing.md)。
>
> `Test.status`（`draft`/`ready`、マイグレーション `0011_test_status`）は Issue #16
> で追加した登録ライフサイクルで、テストプロファイルと設問依存関係グラフ（Issue #26）
> の両方が確認済みになるまで `draft` のまま一方向に留まる。詳細は
> [`test-registration.md`](./test-registration.md)。
>
> `GradeResult` の `comment` / `provider` / `model` / `prompt_version` /
> `dependency_graph_version` / `context`（マイグレーション
> `0012_grade_result_ai_metadata`）は Issue #20（本番 AI 採点パイプライン）で
> 追加した AI 追跡用の列。人間確定行は全て `NULL`/空のまま。詳細は
> [`ai-grading-pipeline.md`](./ai-grading-pipeline.md)。
>
> `GradeResult` の `answer_image_finding`（マイグレーション
> `0017_grade_result_answer_image_finding`）は Issue #136 で追加した、採点 AI が
> 「渡された画像に何が写っていたか」を報告する列（`answer` / `blank`、報告が
> 無ければ `NULL`）。**無記入がどれくらいの頻度で来るかを、実データでの再検証を
> もう一度回さずに数えられるようにするために保存している。** `not_the_answer` は
> DB のトリガで保存できない——解答でない画像から作った点数は、点数として確定させない
> （[`ai-grading-pipeline.md`](./ai-grading-pipeline.md)）。
>
> `Review` の `version`（同時実行制御用トークン、
> `uq_reviews_submission_question_version` で一意制約）/ `regrade_job_id` /
> `undone_review_id`、および `action` の `regrade_requested` / `undone` 追加
> （マイグレーション `0013_review_history_edit`）は Issue #22（レビュー画面の
> edit/reject/regrade/approve-and-next と Undo）で追加した列。詳細は
> [`review-edit-history.md`](./review-edit-history.md)。
>
> `Export`（`job_id` に一意制約、マイグレーション `0014_exports`）は
> Issue #23（添削済みPDF出力）で追加したテーブルで、成功した出力のみを
> 記録する。失敗した試行は `Job`（kind=`export`、Issue #11 の時点で
> `JobKind` に存在していたが本Issueまで生成する経路が無かった）の
> `state=failed` にのみ残る。詳細は [`pdf-export.md`](./pdf-export.md)。
>
> `Question` の `page_2` / `answer_area_2`（マイグレーション
> `0019_two_page_question_areas`）は Issue #108 で追加した、1つの設問の解答欄が
> 2ページにまたがる答案（実測: 11教科中1教科）を表現するための列。
> 1ページ完結の既存設問は全て `NULL` のまま。詳細は §4.2。
>
> `Question` の `is_scoring_target`（マイグレーション
> `0022_scoring_target_questions`）は Issue #449 で追加した、その設問を採点するか
> を表す肯定形の真偽値。既存行は全て `true`（デフォルトはすべて）。詳細は §4.3。

「追記のみ」の 3 テーブルは `add` と参照系メソッドしか repository に生やしていない
（`domain/repositories.py`）。AI の提案値と人間の確定値は別レコードとして残り、
既存行を書き換えるコードパスが存在しない（簡易設計書 §19・§35-5）。

`元 PDF・AI 結果・人間の最終結果・操作履歴を独立して取得できる`（Issue #11 受入条件）は
次の経路で満たす。

- 元 PDF: `Submission.source_pdf_path`（`LocalFileStore`）
- AI 結果: `GradeResultRepository.latest(sub, q, GradingSource.AI)` /
  `RecognitionResultRepository.history(...)`
- 人間の最終結果: 同上 `GradingSource.HUMAN`
- 操作履歴: `ReviewRepository.history(sub, q)`

## 3. 状態機械

`domain/models.py` の `ensure_submission_transition` / `ensure_job_transition` が
許可されていない遷移を `InvalidStateTransition` で拒否する（簡易設計書 §25、
business-rules §4.4 の `blocked` 状態を含む）。

```text
Submission:
  unprocessed → ai_processing → ai_processed → needs_review → reviewed → exported
                    ↑                 ↑   ↑          ↑            ↑
                    └── error ────────┴───┼──────────┴────────────┘
                                          └──────────────┘
                    (ai_processed ⇄ reviewed も許可。Issue #112)
                    (reviewed → needs_review, exported → needs_review も許可)

Job:
  queued → running → succeeded
       ↘        ↘ blocked → queued
        ╲        ↘ failed → queued
         → cancelled (queued/running/blocked/failed から)
```

**`needs_review` は関門ではなく、取込が立てる旗である**（簡易設計書 §25.1、Issue #112）。
取込が回答欄を確定できた答案は `ai_processed` で止まり、人が全設問を確定すれば
そこから直接 `reviewed` へ動く。`needs_review` を経由するのは取込が何か問題を
見つけた答案だけで、その理由は `Submission.review_reason` に残る。
`reviewed` から戻るときも同じ判別で、**取込が置いた場所へ戻る**
（理由があれば `needs_review`、無ければ `ai_processed`）。
実装は `adapters/review_actions.py` の `_unconfirmed_state`。

`SqlAlchemySubmissionRepository.set_state` はこの状態機械を経由してから更新するので、
リポジトリ越しでも不正遷移は拒否される。DB 側にも `state` 列へ `CHECK ... IN (...)`
（`sqlalchemy.Enum(..., native_enum=False)` が生成）があり、アプリを経由しない書き込み
（手動 SQL 等）でも未知の値は拒否される。

## 4. 制約による invariant

| 不正な状態                      | 防御                                                                                |
| ------------------------------- | ----------------------------------------------------------------------------------- |
| 配点範囲外の得点                | domain: `Score.__post_init__`。DB: `CHECK (awarded BETWEEN 0 AND maximum)`          |
| 0〜1 を外れた正規化座標         | domain: `NormalizedRect.__post_init__`（rect は DB 上は JSON のため DB 制約は無し） |
| 孤児 record（親が存在しない子） | DB: FK の `ON DELETE`（§4.1）、接続ごとに `PRAGMA foreign_keys=ON`                  |
| 不正な状態遷移                  | domain の状態機械（上記§3）+ DB の `CHECK` 列                                       |
| 設問番号の重複                  | DB: `UNIQUE (test_id, number)`                                                      |
| ルーブリック行の重複順序        | domain（重複 id/position を拒否）+ DB `UNIQUE (rubric_id, position)`                |

### 4.1 `Review` が指す行の削除（Issue #149）

`reviews` は4本の参照を持ち、それぞれ1つの action について `CHECK` が必須にしている。

| 列                      | 必須になる action   | 意味                         |
| ----------------------- | ------------------- | ---------------------------- |
| `ai_grade_result_id`    | `approved`          | 承認した AI の採点行         |
| `human_grade_result_id` | `modified`          | 人が決めた点数を持つ採点行   |
| `regrade_job_id`        | `regrade_requested` | 再判定として投入した `Job`   |
| `undone_review_id`      | `undone`            | 取り消した対象の `Review` 行 |

**決定: この4本はすべて `ON DELETE CASCADE`。`SET NULL` ではない。**

`SET NULL` は、指し先が消えるときに **review 行がまだ存在したまま書き換える**。
その瞬間に同じ行の `CHECK` に当たり、削除ごと abort する。当たるかどうかを決めていたのは
SQLite がテーブルを辿る順序 = `sqlite_master` 上の並び順で、これは誰も設計していない値
（最後のマイグレーションが残した並び）でしかない。Issue #136 でその反転が実測されている:
`grade_results` を `batch_alter_table` で作り直す（SQLite で `CHECK` を足す唯一の方法）と
そのテーブルが `reviews` の後ろへ移り、8回中8回 green だったものが 6回中6回 red になった。

さらに `undone_review_id` は `reviews` 自身を指すため、**どの並び順でも救われない**。
0017 の時点で、`undone` の review を1行でも持つテストは `DELETE FROM tests` が
できなかった（`purge_test` が失敗した）。並び順の問題ではなく、既に壊れていた。

`CASCADE` は書き換えられた中間行を **そもそも作らない**。review は指し先の行についての
決定なのだから、指し先が消えれば決定も消える — これがどの並び順でも成り立つ。

**実測**（4テーブル相当の縮小スキーマ、`reviews` を先に作る / 後に作るの両順序 ×
「採点行を単体で削除」「job を単体で削除」「review を単体で削除」「`DELETE FROM tests`」）:

| 案                     | 結果          |
| ---------------------- | ------------- |
| `SET NULL`（現状）     | 8/8 red       |
| `RESTRICT`             | 8/8 red       |
| `CHECK` をトリガへ移す | 8/8 red       |
| **`CASCADE`（採用）**  | **8/8 green** |

**捨てた案と、捨てた理由:**

- **`RESTRICT`**: 参照されている採点行を消せなくなるだけでなく、`DELETE FROM tests`
  自体が両方の並び順で落ちる。SQLite の `RESTRICT` は即時判定なので、同じ文の中で
  あとから消えるはずの子行があっても待ってくれない。並び順依存を消すどころか、
  削除経路を全部塞ぐ。
- **`CHECK` をトリガへ移す**: トリガは同じ `SET NULL` の UPDATE で発火するので、
  何も変わらない（実測でも `CHECK` 版と同じ 8/8 red）。「カスケード中の中間状態だけ
  見逃す」書き方も、トリガからは「カスケード由来の UPDATE」と「人が列を空にした
  UPDATE」を区別できないため、結局 invariant を捨てることになる。
- **`approved` が AI 採点を要求するのをやめる（#118 の再検討）**: 不要だった。
  #118 が決めたのは「`modified` は AI 採点なしでもよい（AI が落ちた設問を人が引き取る）」
  であり、「`approved` は承認する対象が要る」はそのまま正しい
  （[`review-edit-history.md`](./review-edit-history.md) §3.1）。`CASCADE` はこの規則を
  弱めない — **むしろ強める**。`SET NULL` の下では `rejected` などの行が指していた
  採点行を黙って `NULL` に書き換えられていたが、`CASCADE` ではそもそも
  「指し先を失った review 行」が存在しえない。

**制約を弱めていないことの確認**（AGENTS.md「Security / Verification」）:
`CHECK` は4本とも文言のまま残っている。変えたのは FK の `ON DELETE` 動作だけで、
`Review.__post_init__`（domain）も従来どおり同じ規則を検査する。

**失われる履歴について**: `CASCADE` は「採点行を消したら、その採点行を承認/修正した
review 行も消える」を意味する。現行コードに `grade_results` / `jobs` / `reviews` を
単体で削除する経路は無く（削除は `purge.py` の test / submission 単位と
`QuestionRepository.delete_for_test` だけで、いずれも review 行ごと cascade する）、
既存の経路で失われるものは何も増えない。削除操作自体は `operation_log` に残る（§5）。

検査は `backend/tests/test_delete_cascade_order.py`（並び順に依存しない形 +
`batch_alter_table` で各テーブルを末尾へ動かした場合）と
`test_migrations.py::test_upgrade_repairs_a_review_history_that_could_not_be_deleted`
（0017 で赤 → `head` で緑を1つのテスト内で押さえる）。

### 4.2 設問の2ページ解答欄対応（Issue #108）

実機再検証 #6 で、実資料 11 教科中 1 教科において、1 つの設問の回答欄が 2 ページにまたがる
（「問N（その1）」が2ページ目、「問N（その2）」が3ページ目）答案が確認された。
従来のデータモデルでは `Question` は `page: int` と矩形 1 つしか持てず、確定時に
`CrossPageRegionError` で片方のページを削除するよう指示していたが、指示に従って削除すると
設問のないページが生じて取込時に `extra_pages` となり、答案画像が抽出されず採点ジョブも
投入されない（#215 の抑止）という問題を引き起こしていた。

**決定: `Question` に `page_2` と `answer_area_2` 列を追加し、1 つの設問エンティティで 2 ページの解答欄を保持する。**

**採用した設計と理由:**

- `Question` テーブルに `page_2` (INTEGER NULL) と `answer_area_2` (JSON NULL) を追加（マイグレーション `0019_two_page_question_areas`）。
- 既存の 1 ページ完結設問は `page_2 = NULL`, `answer_area_2 = NULL` のままであり、完全な後方互換性を維持。
- `QuestionResponse` などの既存 API スキーマを破壊せず、進行中のフロントエンド移植（`docs/frontend-migration.md`「バックエンド Issue はそのまま進めてよい。API は変わらない」）に影響を与えない。
- 答案取込・切り出しパイプライン（`submission_intake`）は、2 ページにまたがる設問について各ページから該当矩形を切り出し、垂直に結合（白パディングで幅を揃えて結合）して 1 つの `AnswerImage` を生成。これにより AI 採点（`GradingJobProcessor`）および OCR（`RecognitionJobProcessor`）は設問全体の解答を閲覧・採点できる。
- `PageCoverage` の期待ページ集合（`expected_pages`）は全設問の全ページ（`q.pages`）を参照するため、3 ページ答案が正しく完全被覆として認識され、誤った `extra_pages` 判定を防ぐ。

**捨てた案と、捨てた理由:**

- **案1: 解答領域を別テーブル（`question_answer_areas`）に完全分離する:**
  1 設問が複数ページにまたがるのは実測 11 教科中 1 教科のみである。領域を別テーブルに分離すると、全クエリ・リポジトリ・マッパー・OpenAPI スキーマへの波及が過大であり、`QuestionResponse.page` や `answer_area` の変更を強いるためフロントエンド移行と衝突する（YAGNI原則に反する）。
- **案2: 設問を小問（問N-1, 問N-2）に分割して別々の `Question` 行にする:**
  採点基準 PDF（配点表）には設問合算の配点しかなく、小問ごとの配点が不明なため機械的に配点を分割できない。また、AI 採点は設問全体の解答文脈（途中式と結論、記述の論理性）を総合してルーブリック判定を行う必要があるため、小問分割すると総合採点が不可能になる。
- **案3: 3ページ以上の任意ページ跨ぎの一般化:**
  実資料でまたがるのは「その1」「その2」の 2 ページのみであり、3 ページ以上の跨がりは実在しない。2 ページまでに制約することで、スキーマ・切り出し・インク判定を極めてシンプルかつ堅牢に保てる。3 ページ以上が登録された場合は `CrossPageRegionError` (422) で正直に拒絶し、適切な修正指示を返す。

**DB 制約 (CHECK):**

- `ck_questions_page_positive`: `page >= 1`
- `ck_questions_page_2_positive`: `page_2 IS NULL OR page_2 >= 1`
- `ck_questions_page_2_greater`: `page_2 IS NULL OR page_2 > page`（ページ番号の順序性を保証）
- `ck_questions_page_2_and_area_2_paired`: `(page_2 IS NULL AND answer_area_2 IS NULL) OR (page_2 IS NOT NULL AND answer_area_2 IS NOT NULL)`（2ページ目番号と領域の整合性を保証）

**マイグレーション運用:**

- `0019_two_page_question_areas`: `questions` テーブルに `page_2` と `answer_area_2` を追加。
- 既存データは全て `NULL` のためデータ移行・バックフィルは不要。
- 復旧: `downgrade()` で列と制約を削除（1 ページ完結のデータは無傷で維持）。

### 4.3 採点する設問の選択（Issue #449）

オーナーの依頼「採点する問題を選べるようにする。デフォルトはすべて」を受けた変更。
`Question` は 1 テストの 1 設問で、`points` / `scoring_method` と同じ寿命を持つため、
「この設問を採点するか」も同じ粒度の性質として **`Question` に真偽値列を足す**。
別テーブルにして join を増やす理由が無い（YAGNI）。値は肯定形の
`is_scoring_target`（採点する = `true`）。

- マイグレーション `0022_scoring_target_questions` は `server_default` で既存行を全て
  `true` にし、その後 default を落とす（`0011_test_status` と同じ2段階）。
  既存テストは今までどおり全設問を採点する。
- **除外は破壊的でない。** 除外した設問の行・採点結果・レビュー履歴・ジョブは消さない。
  数えない／出力しないだけであり、再び選ぶと以前の結果がそのまま見える。
  `QuestionRepository.set_scoring_targets` はこの列だけを書き換える唯一の in-place 経路で、
  `backend/tests/test_architecture.py` の「points と criteria は in-place で変えない」
  ガードの例外として理由つきで認めている。
- **分母は採点対象だけ。** `domain.review_workflow.all_questions_confirmed` /
  `count_confirmed_questions` は `question_ids` を引数で受ける純粋関数のまま変更せず、
  呼び出し側（`api.review_router` の review-progress、`adapters.review_actions` の
  `_sync_submission_review_state`、`jobs.export_processor` と `api.export_router` の
  出力ゲート）が `list_for_test(..., scoring_targets_only=True)` で対象を絞る。
  除外した設問が分母に残って「いつまでも確認済みにならない」を防ぐ。
- **採点と依存。** 除外した設問には新しい評価ジョブを作らない
  （`domain.job_scheduling.plan_submission_jobs` の `excluded_question_ids`）。
  除外した前提設問は「結果が無い前提」として扱い、依存先は前提の結果を使わずに採点する
  （OCR が読めなかった前提と同じ規則）。依存先が BLOCKED のまま残ることはない。
- **PDF。** 除外した設問には点数・コメント・添削記号を描かない。答案の紙面そのものは
  従来どおり出力する（[`pdf-export.md`](./pdf-export.md)）。
- **復旧:** `downgrade()` で列を削除する。除外は列の値だけなので、戻すと全設問が
  採点対象に戻る。採点・レビュー行はどちらの方向でも触らない。
- テスト: `backend/tests/test_migrations.py::test_0022_...`（バックフィルと
  default 撤去）、`test_e2e_intake_to_export.py::test_an_excluded_question_...`
  （採点しない・分母・PDF・依存）、`test_job_scheduling.py::test_an_excluded_prerequisite_...`。

## 5. `app-data/` のファイル保存規則

簡易設計書 §23 のレイアウトをそのまま採用する。

```text
app-data/
├─ database.sqlite            # WAL: database.sqlite-wal / -shm も同ディレクトリに生成される
├─ tests/<test-id>/{model-answer.pdf, manual.pdf, profile.json}
├─ submissions/<submission-id>/
│   ├─ source.pdf                      # 元PDF（不変）
│   ├─ pages/page-<N>.png              # 前処理済みページプレビュー（Issue #17）
│   └─ questions/<question-id>.png     # 設問ごとの回答欄切り出し画像（Issue #17）
└─ exports/<元ファイル名の stem>_corrected[_N].pdf
```

`pages/` と `questions/` 配下は Issue #17（答案取込・画像前処理）で追加した。詳細は
[`answer-intake-and-preprocessing.md`](./answer-intake-and-preprocessing.md) §6〜8。

`adapters/local_storage.py` の `LocalFileStore` が担当する。

- **Atomic write**: 書き込み先と同じディレクトリに隠しテンポラリ
  (`.<name>.<uuid>.part`) を作り、`flush` + `fsync` の後 `os.replace` で本番名へ
  差し替える。`os.replace` は Windows / POSIX いずれでもアトミック。読み手が
  中途半端なファイルを見ることはない。
- **クラッシュ復旧**: `LocalFileStore.sweep_temp()` が `*.part` の残骸を削除する。
  アプリ起動時に一度呼び出す運用とする（本 Issue ではメソッドの提供までが範囲。
  起動シーケンスへの組み込みは UI 側 Issue で行う）。
- **書き込み順序**: `adapters/atomic.py` の `transactional_operation()` は
  DB コミットが成功した後にだけファイルを書く。DB 側が失敗（例外 or commit 失敗）
  すればファイルは一切書かれない。個々のファイル書き込み自体も atomic write なので、
  複数ファイルの一部だけ書けた場合でも各ファイルは壊れていない。
  ただし SQLite とファイルシステムは同一トランザクションではないため、DB commit 後の
  ファイル書き込み失敗はDBを巻き戻せない。例外を呼び出し元へ返し、未作成ファイルを
  同じ内容で再書き込みするか、対応するDB操作を取り消す復旧が必要になる。
- **削除・復旧手順**: `adapters/purge.py` の `purge_test` / `purge_submission` が、
  監査ログ (`operation_log` テーブル) への記録 → DB 行削除（cascade）→ ファイル削除、
  の順で実行する（business-rules §2 (11)「削除操作自体は監査ログに残す」）。
  ファイル削除が失敗した場合は例外が呼び出し元へ返る。DB 行と監査ログは既にcommit済み
  なので、`LocalFileStore.delete_test()` / `delete_submission()` を再実行するか、
  `app-data/tests/<id>/` または `app-data/submissions/<id>/` を直接削除して復旧する。
  **元答案・添削済み答案・AI ログの自動削除は行わない**（business-rules §2 (11)。
  90 日で自動削除されるのは運用ログのみで、対象は別 Issue）。

## 6. マイグレーション運用（Alembic）

- `backend/alembic.ini` + `backend/migrations/`。`auto_scoring.db.migrator` が
  Python から呼び出す薄いラッパー（`upgrade` / `downgrade` / `current_revision`）。
  この2つはソースツリー直下（`backend/`）に置いた開発者向けの配置で、
  `pyproject.toml` の `force-include` で wheel には `auto_scoring/migrations` /
  `auto_scoring/alembic.ini` としても同梱する（Issue #26）。`db/migrator.py` は
  パッケージ内配置とソースツリー配置の両方を試し、存在する方を使う --
  `auto-scoring-sidecar` コンソールスクリプトはインストール済みの
  `auto_scoring` パッケージだけが存在する環境（`backend/` ソースツリーは無い）
  で起動時に `upgrade(db_url, "head")` を呼ぶため、パッケージ内蔵が無いと
  Uvicorn 起動前に落ちる（詳細: `docs/dependency-graph.md`）。
- リビジョン:
  - `0001_initial_schema` — 10 個のコアテーブル一式。
  - `0002_operation_log` — 削除操作の監査ログテーブルを追加（§5 参照）。
  - `0003_dependency_graph` / `0004_job_dependency_graph_version` — 設問依存
    関係 DAG（Issue #26）。詳細は `docs/dependency-graph.md`。
  - `0005_answer_intake` — `answer_images` テーブルと `submissions` への
    `source_pdf_sha256` / `page_count` / `original_filename` / `review_reason`
    列を追加（Issue #17）。SQLite の `CHECK` 制約追加は列追加を伴う既存テーブルの
    再作成が必要なため、Alembic のバッチモード（`recreate="always"`）を使う。
    「1 世代前 DB」（0001 で止まっている既存 DB）から `head` への適用と、
    `head → 0001 → base` の downgrade を `tests/test_migrations.py` で検証する。
  - `0006_student_label_length` / `0007_original_filename_length` —
    `submissions.student_label` / `original_filename` に長さ上限の `CHECK`
    制約を追加（Issue #17 レビュー対応）。PR #37 が main にマージされた PR #36
    （Issue #26、`0003`/`0004` を先に使用）と競合したため、Issue #17 側の
    `0003`〜`0005` を `0005`〜`0007` へ振り直した。
  - `0014_exports` — `exports` テーブルを追加（Issue #23、成功した
    添削済みPDF出力の記録。`job_id` に一意制約）。
  - `0018_review_reference_cascade` — `reviews` の4本の参照を `ON DELETE SET NULL`
    から `ON DELETE CASCADE` へ変更（Issue #149、§4.1）。データ移行は不要
    （`SET NULL` の下では孤児行が作れないため）だが、コピー後に
    `PRAGMA foreign_key_check(reviews)` で孤児が無いことを確かめてから終わる。
    復旧: 変更は `reviews` 1テーブルに閉じており、`downgrade` が同じコピーで
    `SET NULL` に戻す（並び順依存も一緒に戻る）。
  - `0019_two_page_question_areas` — `questions` テーブルに `page_2` と `answer_area_2`
    列を追加（Issue #108、§4.2）。1設問の解答欄が2ページにまたがる答案を表現する。
    データ移行は不要（既存行は `NULL` のまま）。復旧: `downgrade` で列と CHECK 制約を削除。
- スキーマを変更したら `db/orm.py` を直し、`uv run alembic revision --autogenerate`
  で新しい revision を作る。`alembic.command.check`（`test_head_schema_matches_orm_metadata`）
  が ORM とマイグレーション履歴の乖離を検出する。
- 新規 DB は `upgrade(url, "head")` で作成できる（Alembic が自動でテーブルを作る。
  アプリ側で `Base.metadata.create_all` を直接呼ぶのはテスト専用）。
- 本番相当の復旧手順: マイグレーションが失敗した場合は `app-data/database.sqlite`
  を対応する `.bak` にコピーしてから再試行する運用とする（自動バックアップの実装は
  本 Issue の対象外。UI 側の起動シーケンス Issue で決定する — **未決事項**）。

## 7. トランザクション境界

`adapters/unit_of_work.py` の `SqlAlchemyUnitOfWork` が 1 トランザクション =
1 `Session` を表す。

```python
with SqlAlchemyUnitOfWork(session_factory) as uow:
    uow.submissions.add(submission)
    uow.grades.add(grade)
    uow.commit()
```

`commit()` を呼ばずにブロックを抜けると `__exit__` が `rollback()` する
（例外の有無を問わない）。`db/engine.py` の各 SQLite 接続は
`PRAGMA journal_mode=WAL` / `foreign_keys=ON` / `busy_timeout=5000` /
`synchronous=NORMAL` を持つ。

`adapters/sqlalchemy_repositories.py` の各 `add()` は呼び出しごとに `flush()` する。
このテーブル群は `relationship()` を張っていない（domain dataclass との単純な
1 テーブル 1 row 変換にとどめるため）ので、SQLAlchemy のユニットオブワークは
マッパー間の insert 順序を保証しない。呼び出し順（親 → 子）どおりに DB へ反映する
ために、各 `add()` の直後で flush して即座に制約違反を顕在化させている。

## 8. 検証

| 受入条件・検証項目（Issue #11）                               | テスト                                                                                                                                                                                                               |
| ------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 新規 DB / 1 世代前 DB の両方に migration を適用できる         | `tests/test_migrations.py::test_fresh_database_upgrades_to_head` / `::test_one_generation_old_database_upgrades_to_head`                                                                                             |
| downgrade が機能する                                          | `::test_downgrade_walks_back_to_base`                                                                                                                                                                                |
| 不正な状態遷移を拒否する                                      | `tests/test_domain_models.py`、`tests/test_sqlalchemy_repositories.py::test_set_state_rejects_illegal_transition`                                                                                                    |
| 孤児 record を拒否する                                        | `tests/test_sqlalchemy_repositories.py::test_orphan_row_is_rejected_by_foreign_key`                                                                                                                                  |
| 配点範囲外の値を拒否する                                      | `tests/test_domain_models.py`（domain）、`tests/test_migrations.py::test_check_constraint_rejects_bad_row` と `tests/test_sqlalchemy_repositories.py::test_out_of_range_score_is_rejected_by_check_constraint`（DB） |
| Flutter が DB ファイルへ直接アクセスしない                    | 設計: DB は Python サイドカーのみが開く（`app/` に SQLite 依存を追加していない）                                                                                                                                     |
| 元 PDF・AI 結果・人間の最終結果・操作履歴を独立して取得できる | `tests/test_sqlalchemy_repositories.py::test_source_pdf_grades_reviews_are_retrievable_independently`                                                                                                                |
| 一時ディレクトリの実 SQLite で migration/integration test     | `tests/test_migrations.py`、`tests/conftest.py`（`tmp_path` 上の実ファイル DB）                                                                                                                                      |
| transaction 失敗時に DB・ファイルの中途半端な状態が残らない   | `tests/test_atomic_operation.py`（fault injection）                                                                                                                                                                  |

## 9. 未決事項

- 起動時の `sweep_temp()` 呼び出しタイミングと、DB 破損時の自動バックアップ運用は
  UI/起動シーケンスを扱う後続 Issue で決定する（§6 参照）。
- 低 Confidence 閾値によるゲーティングは本 Issue の対象外（閾値は business-rules
  §3 (C)。Issue #81 で「固定値は決めず設定値のまま、既定 0.80」に確定し、閾値判定は
  `JobProcessor` 側の設定が持つ）。`GradeResult.confidence` /
  `RecognitionResult.confidence` を保持するところまでを実装し、閾値判定ロジックは持たない。
