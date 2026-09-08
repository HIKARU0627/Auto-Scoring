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
                    ↑                 ↑              ↑            ↑
                    └── error ────────┴──────────────┴────────────┘
                    (reviewed → needs_review, exported → needs_review も許可)

Job:
  queued → running → succeeded
       ↘        ↘ blocked → queued
        ╲        ↘ failed → queued
         → cancelled (queued/running/blocked/failed から)
```

`SqlAlchemySubmissionRepository.set_state` はこの状態機械を経由してから更新するので、
リポジトリ越しでも不正遷移は拒否される。DB 側にも `state` 列へ `CHECK ... IN (...)`
（`sqlalchemy.Enum(..., native_enum=False)` が生成）があり、アプリを経由しない書き込み
（手動 SQL 等）でも未知の値は拒否される。

## 4. 制約による invariant

| 不正な状態                      | 防御                                                                                |
| ------------------------------- | ----------------------------------------------------------------------------------- |
| 配点範囲外の得点                | domain: `Score.__post_init__`。DB: `CHECK (awarded BETWEEN 0 AND maximum)`          |
| 0〜1 を外れた正規化座標         | domain: `NormalizedRect.__post_init__`（rect は DB 上は JSON のため DB 制約は無し） |
| 孤児 record（親が存在しない子） | DB: 全 FK に `ON DELETE CASCADE`、接続ごとに `PRAGMA foreign_keys=ON`               |
| 不正な状態遷移                  | domain の状態機械（上記§3）+ DB の `CHECK` 列                                       |
| 設問番号の重複                  | DB: `UNIQUE (test_id, number)`                                                      |
| ルーブリック行の重複順序        | domain（重複 id/position を拒否）+ DB `UNIQUE (rubric_id, position)`                |

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
