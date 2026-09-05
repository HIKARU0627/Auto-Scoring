# 設問依存関係DAGの分析・確認基盤

GitHub Issue [#26](https://github.com/HIKARU0627/Auto-Scoring/issues/26)（親
[#3](https://github.com/HIKARU0627/Auto-Scoring/issues/3)）。1件の答案が複数
ページ・複数設問を含む場合に、採点前へ設問同士の依存関係を分析し、人間が確認し
たDAGをテスト単位で保存する。後続の処理キュー（Issue #26の対象外、将来Issue）
はこのDAGに基づいて独立設問だけを並列実行する想定。

依存: [#10](https://github.com/HIKARU0627/Auto-Scoring/issues/10)（認証付き
サイドカーAPI基盤）、[#11](https://github.com/HIKARU0627/Auto-Scoring/issues/11)
（MVPデータモデル・SQLite永続化基盤）、[#15 PoC 4](https://github.com/HIKARU0627/Auto-Scoring/issues/15)
（`Profile.from_candidates` → 人間確認 → `confirm` のdraft/confirmedパターン）。

## 決定事項

### スコープ: グラフはテスト単位

Issue本文は「graphはテストプロファイル単位で分析・確認・version管理」と書いて
いるが、これは PoC 4 (#15) の `Profile`（PDFレイアウト・座標のプロファイル）で
はなく、登録済みの `Test`（`auto_scoring.domain.models.Test`）を指す。設問
（`Question`）はすでに `test_id` を持つため、依存グラフのノード集合は「その
`test_id` に属する全 `Question.id`」とし、`DependencyGraph.test_id` で1テスト
1系列のバージョン履歴を持つ（`auto_scoring.domain.dependency_graph`）。

### draft → confirm のライフサイクル

`DependencyGraph.from_candidates` は常にDRAFTを生成し、`DependencyGraph.confirm`
だけがCONFIRMEDへ遷移できる（PoC 4の `Profile` と同じ形）。confirm時に
`unresolved`（要確認一覧）は空になる -- 人間が最終的なedge集合を明示的に確定した
時点で、曖昧な関係は「edgeとして採用」か「採用しない」のどちらかに解決済みとみな
す。

### バージョンと不変性

- `DependencyGraph.version` はテストごとに1から始まる整数。
- `POST /analyze` は呼ぶたびに必ず新しいバージョンを作る（`_next_version` は
  常に `latest.version + 1`）。以前は「latestがDRAFTなら同じバージョンへ上書き」
  していたが、これだとクライアントAがv1をレビュー中に別クライアントが
  `/analyze` を呼ぶとv1の中身が黙って書き換わり、Aが一度も見ていない内容を
  `POST /confirm {version: 1}` が確定させてしまうレースがあった（レビュー
  指摘）。分析のたびに独立した不変のバージョンを作ることで、誰かがレビュー
  中のバージョンは後続の `/analyze` から絶対に影響を受けない。
  `DependencyGraphRepository.save` 自体は引き続き `(test_id, version)` で
  upsertできる（同一バージョンへの再書き込みも技術的には可能）が、この
  upsert能力を使うのは repository 層のテストのみで、API層はもう使わない。
- CONFIRMEDになったバージョンは不変。`save` は既存のCONFIRMED行を上書きしよう
  とすると `DependencyGraphError` を送出する。確定後にグラフを変更したい場合は
  新しい（より大きい）バージョンをDRAFTから始める。
- `POST /confirm` はリクエストに `version` を必須で含み、その正確なバージョン
  だけを対象にする（`latest` を暗黙に対象にしない）。指定バージョンが存在し
  ないか既にCONFIRMEDなら404/409を返す -- 「latestを対象にする」実装だと、
  別クライアントの確定後に始まった新しいDRAFTへ、レビュー済みでない古い
  レビューが誤って適用されてしまうため。
- `POST /confirm` はさらに、指定バージョンより**新しい**CONFIRMED済みバー
  ジョンが既に存在しないかも `DependencyGraphRepository.get_latest_confirmed`
  で確認する。v2が先にconfirmされた後でv1へのconfirmが遅れて届いても、v1は
  まだDRAFTのため「既にCONFIRMED」チェックだけでは通過してしまう -- それを
  許すとgraphが2つ同時にCONFIRMED状態になり、後述のjob無効化処理がv2のjobを
  誤ってキャンセルしてv1向けに再作成してしまう（graphのlatestとjobの紐づく
  バージョンが食い違う）。より新しいCONFIRMED版が既にあれば409で拒否する。
- `POST /confirm` は確定直前にtestの現在の設問集合（`Question.list_for_test`）
  と `graph.question_ids` を比較する。`/analyze` から `/confirm` までの間に
  設問が追加・削除されていれば、そのスナップショットはもう test を正しく表
  していないため409を返し、再度 `/analyze` からやり直させる。
- バージョン採番自体は「読んでから書く」（`_next_version` が読み、`save` が
  書く）ため、2つの `/analyze` が重なると両方が同じ次バージョンを計算しう
  る。SQLiteは書き込みを直列化するため、後から書き込む側だけが
  `(test_id, version)` のUNIQUE制約違反で `IntegrityError` を受け取る。
  `analyze()` はこの `IntegrityError` を捕捉して `uow.rollback()` した上で
  次のバージョンを再計算し、最大5回まで再試行する（生の500として漏らさな
  い）。TestClient経由の実スレッド2本での再現は信頼できなかったため、テスト
  では `save()` が最初の1回だけ `IntegrityError` を送出するようモックして
  再試行経路を決定的に検証している。
- `POST /confirm` の各種チェック（status / 新しいCONFIRMED版の有無 / 設問
  集合の一致）は、その後の書き込みより前に読んだ状態に基づくため、単体では
  アトミックでない -- 2つの `/confirm` が両方チェックを通過してから両方書き
  込む、というレースが理論上あり得る（レビュー指摘）。実際の書き込みは
  `DependencyGraphRepository.try_confirm` という1本の
  `UPDATE ... WHERE status = 'draft' AND NOT EXISTS(...更に新しいCONFIRMED...)`
  で行う。この `WHERE` はSQLiteが**実行時点の実際の行**に対して評価するため
  （ORM属性を変更してflushする従来の `save()`はPKだけでUPDATEするので、
  読んだ時点の状態を条件にできず、後勝ちが黙って上書きしてしまっていた）、
  2つの `/confirm` が競合しても片方だけがマッチし、負けた方は
  `rowcount == 0` から `False` を受け取って409を返す -- 中身を一切変更しな
  い。テストでは同じ古いDRAFT読み取りから2つの `confirm()` 済みgraphを作り、
  `try_confirm` を連続で呼んで「後者は必ず負ける」ことを決定的に検証している
  （`test_dependency_graph_repository.py`）。
- `try_confirm` の `WHERE` には設問集合の一致チェックも含める（`SELECT
COUNT(*) FROM questions WHERE test_id=...` が期待件数と一致し、かつ期待
  集合に無いidの設問が存在しないこと -- 両方成り立てば有限集合として一致と
  等価）。アプリ層の事前チェック（「バージョンと不変性」節）は読み取り時点
  の状態しか見ないため、その後・`try_confirm` 実行前に別トランザクションが
  設問を追加/削除すると素通りしてしまう（レビュー指摘）。設問集合チェックを
  atomic UPDATEの `WHERE` 自体に含めることで、この窓を閉じている。テストで
  は同一トランザクション内で `try_confirm` 呼び出し直前に設問を追加して
  `False` になることを検証し（repository層）、API層でも
  `try_confirm` をモンキーパッチして「アプリ層チェック通過後・書き込み前」
  の窓を強制的に再現し409になることを確認している。
- `try_confirm` とは別に、`DependencyGraphRepository.save`（DRAFTを保存
  し直す通常のupsert経路）にも同種のTOCTOUがあった（レビュー指摘）:
  `save` は読み取り時点で行がCONFIRMEDでないことを確認するだけで、その後の
  「confirmed edgesを含む古いedge行を削除 → ORM属性を直接変更してflush」は
  無条件だった。この読み取りと書き込みの間に別トランザクションが
  `try_confirm` でこの行をCONFIRMEDへ進めると、`save`側はそれを知らずに
  確定済みedgeを削除し、PKだけのUPDATEで`status`を（confirm前に読んだ、
  DRAFTのままの）呼び出し元のgraphの値へ書き戻してしまう -- 人間が確定した
  はずのgraphが黙って未確定に戻る。修正として、`save`の実際の書き込みも
  `try_confirm`と同じ設計のcompare-and-set（`UPDATE ... WHERE id = :id AND
status = 'draft'`）にし、`rowcount != 1`（＝読み取り後に他がconfirmした）
  なら`DependencyGraphError`を送出して何も書き換えない。edge行の削除も
  このUPDATEが成功した後にのみ行うよう順序を変更した（以前はUPDATEの前に
  削除しており、CASが失敗しても確定済みedgeが既に消えているおそれがあった）。
  テストでは`update`をモンキーパッチして「`save`の読み取り後・atomic UPDATE
  実行前」の窓に別トランザクションの`try_confirm`を注入し、`save`が
  `DependencyGraphError`を送出しつつ確定済みgraphのstatus/edgesが一切
  変化しないことを検証している
  （`test_save_reports_a_conflict_when_confirmation_races_ahead_of_a_draft_overwrite`）。
- 受入条件「確定graphを変更した場合はversionを更新し、古いgraphで未完了の採点
  jobを無効化・再作成できるようにする」は実装済み: `Job` に
  `dependency_graph_version`（そのjobがどの確定バージョンに対して発行された
  か）を追加し、`JobRepository.list_incomplete_for_stale_versions(test_id,
current_version)` で「今の確定バージョンと異なるバージョンに紐づく、まだ
  QUEUED/RUNNING/BLOCKED**/FAILED**のjob」を検索できるようにした。FAILEDは
  終端状態ではない -- `_JOB_TRANSITIONS` はFAILED→QUEUEDを正当なリトライ遷移
  として許しているため、対象から外すとstale FAILED jobが後で再試行され古い
  グラフバージョンのまま実行されてしまう（レビュー指摘）。`POST /confirm` は
  グラフを保存した同じトランザクション内でこの一覧を取得し、各jobを
  `reissue_job_for_graph_version`（`auto_scoring.domain.models`）で
  CANCELLEDへ遷移させつつ、新バージョン向けの新しいQUEUED jobを作成して
  `uow.commit()` する。実際のjob生成（confirmed graphから初回のjobを作る
  スケジューラ）はこのIssueの対象外のまま（後続のジョブキューIssue）だが、
  「既存jobがある場合に無効化・再作成する」動作自体は完全にテスト済み
  （`test_dependency_graph_api.py` の「Job invalidation」節）。
- 上記のstale job再発行ループが1個ずつ `uow.jobs.save(cancelled)` を呼ぶ間、
  ワーカーが同じjobを別トランザクションでSUCCEEDED等へ進めている可能性が
  ある（レビュー指摘）。`save()` は後述の楽観的並行制御でこれを検知して
  `JobSaveConflict` を送出するので、再発行ループはそれを捕捉した場合だけ
  「そのjobについては新versionの複製jobを作らない」（`continue`）。理由:
  ワーカーが既に完了させたjobをこちらが割り込んでCANCELLEDへ上書きするのは
  誤りで、かつ完了済みjobに対して新versionの複製jobを重複作成する必要も
  無い（ワーカー側の完了処理が別途正しく進む）。テストでは
  `SqlAlchemyJobRepository.save` をモンキーパッチして常に
  `JobSaveConflict` を送出させ、confirmそのものは200で成功しつつ、対象job
  が変更されず複製QUEUED jobも作られないことを検証している
  （`test_confirm_skips_reissue_when_cancelling_a_stale_job_loses_a_race`）。
- `Job.save()` 自体も、他のリポジトリのCAS群と同じ理由でORM属性変更+flushの
  素朴なUPDATEから `UPDATE ... WHERE id = :id AND state = :current_state`
  という compare-and-set に変更した（レビュー指摘）。以前の実装はPKだけの
  `WHERE` でUPDATEしていたため、「読んでから遷移チェック→書く」の間に別の
  書き手（ワーカーの完了報告、上記の再発行ループ等）が同じ行を更新すると、
  後から書いた側が黙って上書きしてしまうレースがあった。CASが `rowcount == 0`
  を見たら、その行は自分が読んだ時点の状態から既に変わっている
  （＝他の書き手が先に勝った）とわかるので、`JobSaveConflict`（新設の
  `DomainError` サブクラス。`InvalidStateTransition` --
  「この遷移は状態機械として禁止」--とは区別され、こちらは「状態機械として
  正当な遷移だが、読み取り後に別の書き手が既にこの行を動かしていた」を表す）
  を送出する。テストは `Session.get` がSQLiteドライバの都合上その場で最新の
  コミット済み状態を返してしまう（identity mapのキャッシュに頼れない）ため、
  `ensure_job_transition` を一時的にモンキーパッチして「実際の遷移チェック
  通過直後・atomic UPDATE実行前」というピンポイントな窓に別トランザクション
  からの競合コミットを注入する方式で決定的に再現している
  （`test_job_save_raises_conflict_when_the_row_changes_between_read_and_write`）。
- 上記の初版の `Job.save()` にはさらに別の穴があった（レビュー指摘）:
  `save()` 自身が `self._session.get(JobRow, job.id)` でCASの比較対象となる
  `current_state` を都度再読み込みしていたため、2つのworkerが両方とも同じ
  QUEUEDのjobを読んで両方ともRUNNINGへ遷移させようとすると、後から実行される
  方の`save()`は「先勝ちが既にRUNNINGへ書き込んだ後の行」を再読み込みして
  `current_state = RUNNING` を得る。後勝ち呼び出し自身の遷移先も同じRUNNING
  なので `job.state is not current_state` が偽になり `ensure_job_transition`
  の呼び出し自体がスキップされ、続く `WHERE state = 'running'` は
  先勝ちが作った行にそのまま一致してしまう -- 後勝ちが一度も観測していない
  状態を「たまたま今のDB状態と一致した」というだけで書き込みに成功したこと
  になり、2つのworkerが同じjobを同時にclaimできてしまう。CASの本質は
  「呼び出し元が読んだ時点の状態」を条件にすることなので、`save()` の中で
  DBを再読み込みして条件を作るのではなく、呼び出し元に `expected_state`
  （`get()` で読んだ、`transitioned_to()` を呼ぶ前のjobの`state`）を明示的に
  引数で渡させ、それを唯一の比較対象にするよう変更した。これにより後勝ちの
  `WHERE state = 'queued'` はもう今のDB行（RUNNING）に一致せず、正しく
  `JobSaveConflict` になる。テストでは2つの別々の`uow`でそれぞれ同じ
  QUEUED状態を読み取り、片方を保存した後にもう片方を保存させて後者が確実に
  負けることを検証している
  （`test_job_save_rejects_the_second_of_two_workers_racing_to_claim_the_same_job`、
  修正前は`DID NOT RAISE JobSaveConflict`で失敗することを確認済み）。

### 追加の不変条件（レビュー指摘で強化）

- `DependencyGraph.__post_init__` は「CONFIRMEDなのに `unresolved` が空でな
  い」状態も拒否する。`confirm()` は常に `unresolved=()` にして遷移するため
  通常経路では起きないが、`from_dict`/直接構築で壊れた行を読み込んだ場合に
  `can_start_submission_processing` が誤って `True` を返さないようDBレベル
  （`ck_dependency_graphs_confirmed_has_no_unresolved`、SQLiteの
  `json_array_length`使用）でも二重に保護する。
- 同様に `__post_init__` は「CONFIRMEDなのに `confirmed_at` が無い」「DRAFT
  なのに `confirmed_at` が設定されている」という組み合わせも拒否するが、
  修復・インポート等がdomain層を経由せず直接SQLでこの不整合な行を書き込む
  可能性があり、これまではDB側に対応する制約が無かった（レビュー指摘）。
  そのような行は書き込み自体は成功してしまうのに、後続の `GET`/`list` が
  `_hydrate` → `DependencyGraph.from_dict` の呼び出しで
  `DependencyGraphError` を送出し、その行に触れるたび500になる。ORMメタ
  データ（`db/orm.py` の `DependencyGraphRow.__table_args__`）と migration
  （`0003_dependency_graph.py`）の両方に
  `ck_dependency_graphs_confirmed_at_matches_status`
  （`(status = 'confirmed') = (confirmed_at IS NOT NULL)`）というCHECK制約
  を追加し、書き込み時点でSQLiteが拒否するようにした -- 片方だけに足すと
  `test_head_schema_matches_orm_metadata`（`alembic check`）がドリフトを
  検知して落ちるため、常に両方同時に直す。テストでは`DependencyGraphRow`を
  直接構築してこの不整合な2パターン（CONFIRMED+confirmed_at=NULL、
  DRAFT+confirmed_at設定済み）を試み、両方とも`IntegrityError`になること
  をORMメタデータ側（`test_dependency_graph_repository.py`）とmigration適用
  後の生SQL側（`test_migrations.py`）の両方で検証している。
- 同様の理由で、`DependencyGraph.__post_init__`が要求する
  「`question_ids`は非空」という不変条件にもDBレベルのミラーが無かった
  （レビュー指摘）。0件の設問からなるgraphは概念として意味を持たない
  にもかかわらず、修復・インポート・直接SQLは`question_ids = '[]'`を
  書き込めてしまい、その行は`_hydrate`が`DependencyGraph.from_dict`を
  呼ぶたびに`DependencyGraphError`で失敗する。ORMメタデータとmigrationの
  両方に`ck_dependency_graphs_question_ids_non_empty`
  （`json_valid(question_ids) AND json_array_length(question_ids) > 0`）を
  追加した。`json_valid`は、`json_array_length`が非JSON文字列を受け取って
  制約チェック自体がエラーになるのを防ぐガード。
- `dependency_edges`も`confidence`の範囲チェック以外は同様に無防備だった
  （レビュー指摘）。`DependencyEdge.__post_init__`はself-loop
  （`from_question_id == to_question_id`）を`SelfLoopError`で拒否し、
  `provides`の空配列と空白のみの`rationale`を`DependencyGraphError`で
  拒否するが、これらもDBレベルのミラーが無く、修復・インポート・直接SQLが
  違反行を書き込めてしまうとそのgraphを読み込むたびにAPIが壊れる。ORMメタ
  データとmigrationの両方に`ck_dependency_edges_no_self_loop`
  （`from_question_id != to_question_id`）、
  `ck_dependency_edges_provides_non_empty`
  （`json_valid(provides) AND json_array_length(provides) > 0`）、
  `ck_dependency_edges_rationale_non_empty`
  （`length(trim(rationale)) > 0`）を追加した。テストでは`DependencyGraphRow`
  /`DependencyEdgeRow`を直接構築してこれら3種の不整合行を試み、いずれも
  `IntegrityError`になることをORMメタデータ側（`test_dependency_graph_repository.py`）
  とmigration適用後の生SQL側（`test_migrations.py`）の両方で検証している。
- `ck_dependency_edges_provides_non_empty`はJSONの形（有効なJSON配列で長さ
  > 0）しか見ておらず、要素の値までは検証していなかった（レビュー指摘）。
  > 修復・インポート・直接SQLが`provides = '["bogus"]'`のような未知の値を
  > 書き込めてしまうと、`_mappers.dependency_graph_from_rows`がそれを
  > `DependencyProvision(...)`へ変換する際に`ValueError`を送出し、その
  > graphに対する全てのGET/listが500になる。ただしSQLiteの`CHECK`制約は
  > サブクエリを一切許可しない（`json_each`のようなテーブル値関数を使った
  > `EXISTS`もサブクエリ扱いで拒否される -- `subqueries prohibited in CHECK
constraints`）ため、他の不変条件と違って`CHECK`では実装できない。代わりに
  > `BEFORE INSERT`/`BEFORE UPDATE OF provides`の2本のトリガー
  > （`trg_dependency_edges_provides_known_values_insert`/`_update`、条件は
  > `WHEN EXISTS (SELECT 1 FROM json_each(NEW.provides) WHERE value NOT IN
(...))`として`RAISE(ABORT, ...)`）で同じ検証を行う。トリガー本体でだけ
  > サブクエリ制限が掛からないため、この境界の値検証はトリガーでしか実装
  > できない。ORM側（`db/orm.py`）は`DependencyEdgeRow.__table__`の
  > `after_create`イベントに`DDL`でこの2本のトリガーを紐づけ、
  > `Base.metadata.create_all`でも生成されるようにした。値の一覧
  > （`recognized_text`/`score`/`criterion_result`）は
  > `domain.dependency_graph.DependencyProvision`と同期を保つ必要がある。
  > テストでは未知の値でのINSERT・既存の正しい行に対する未知の値への
  > UPDATEの両方が`IntegrityError`になることを、ORM経由
  > （`test_dependency_graph_repository.py`）とmigration適用後の生SQL
  > （`test_migrations.py`）の両方で検証している。
- cycle検出はKahnのアルゴリズムが行き詰まった残りノード全部ではなく、
  Tarjanの強連結成分（SCC）でサイクルに実際に参加しているノードだけを
  `CycleDetectedError.cycle_question_ids` に含める。例えば `q1<->q2` の
  サイクルに `q2 -> q3` が伸びている場合、Kahnだけでは `q3` も未配置のまま
  残るが、`q3` はサイクルの下流に過ぎないため報告対象から除く。
- ヒューリスティックanalyzerは、問題文・模範解答・採点基準のいずれも無い
  設問を「独立」と黙って判定せず、`unresolved` として報告する（分析材料が
  無いこと自体を「分析できていない」として扱う）。空白文字だけの入力
  （例: `"   "`）も同様に「テキスト無し」として扱う -- Pythonの文字列は
  空白のみでもtruthyなので、`strip()` してから空判定しないとこのケースが
  すり抜けて「独立」と誤判定されてしまう。
- `dependency_edges` の主キーは合成`id`ではなく `(graph_id,
from_question_id, to_question_id)` の複合主キー（レビュー指摘）。以前は
  `f"{graph.id}:{edge.from_question_id}:{edge.to_question_id}"` という
  区切り文字`:`連結の合成idを使っていたが、設問idそのものに`:`が含まれる
  場合（例: `from_question_id="a:b", to_question_id="c"` と
  `from_question_id="a", to_question_id="b:c"`）に異なる2本のedgeが同じ
  文字列に折り畳まれて衝突しうる。複合主キーはこの種の区切り文字衝突を
  エンコーディングの工夫ではなく構造的に排除する。テストでは実際にこの
  衝突パターンを持つ2本のedgeを保存し、両方が別々の行として残ることを
  検証している
  （`test_edge_rows_do_not_collide_when_question_ids_contain_the_separator`、
  修正前は `UNIQUE constraint failed: dependency_edges.id` で失敗すること
  を確認済み）。

### Submission処理のゲート

`can_start_submission_processing(graph, *, current_question_ids,
active_confirmed_version)` が唯一のゲート関数: `graph` が `None`（未分析・
分析失敗を含む）か、`DependencyGraphStatus.CONFIRMED` でなければ `False`。
人間未確認のDRAFTや分析失敗はここで一律にブロックされる。

CONFIRMEDというgraph自身の状態だけでは不十分（レビュー指摘）: `confirm()`
後のgraphは不変だが、testの設問集合はconfirm後も変更されうる。confirm後に
設問が追加/削除されると、graphの`status`は永遠にCONFIRMEDのままなのに
`question_ids`はもうtestを正しく表していない。そこで呼び出し側がその時点の
最新の設問集合を `current_question_ids` として渡し、`graph.question_ids`
との一致を追加条件にする -- 不一致ならCONFIRMEDでも`False`を返す。
テストでは、confirm後に設問を追加/削除した場合にそれぞれ`False`になる
ことを検証している
（`test_processing_is_blocked_when_a_question_was_added_after_confirming`、
`test_processing_is_blocked_when_a_question_was_removed_after_confirming`、
および `test_dependency_graph_api.py` の
`test_confirmed_processing_gate_goes_stale_after_a_question_is_added`）。

`status`/`question_ids` の一致だけでもまだ不十分（レビュー指摘）:
「バージョンと不変性」節の通りCONFIRMED後のバージョンは不変で、v2が
confirmされてもv1は書き換わらずCONFIRMEDのまま残る。設問が一切変わって
いなければv1の`question_ids`も最新の設問集合と一致し続けるため、`status`と
`question_ids`だけを見るゲートはv2がアクティブになった後もv1に対して
`True`を返し続けてしまう -- v2の確定で明示的に無効化されたはずのv1に対して
新しいsubmission処理を開始できてしまう。そこで呼び出し側が
`DependencyGraphRepository.get_latest_confirmed(test_id)` で読んだ最新の
アクティブなconfirmed versionを `active_confirmed_version` として渡し、
`graph.version` との一致を追加条件にする。テストでは、v1をconfirmした後に
同じ設問集合のままv2をconfirmし、v1自身の`status`/`question_ids`は変化
していないにもかかわらずゲートが`False`を返すことを検証している
（`test_processing_is_blocked_when_a_newer_version_is_the_active_confirmed_one`、
`test_dependency_graph_api.py` の
`test_processing_gate_rejects_a_superseded_confirmed_version`）。

### 候補生成: ヒューリスティック analyzer

Issue本文は「問題文、模範解答、採点マニュアル、ページ/設問構造からdependency
候補と根拠を生成する」を要求するが、`AIProvider` の具体サービス選定は
technology-stack.md §3.5のとおりPoC 2後まで未確定であり、`Question` ドメイン
モデル（#11）にも問題文（OCR/抽出前のPDFテキスト）を保存する列がまだ無い。
そのため:

- `auto_scoring.domain.dependency_analysis.DependencyAnalyzer` を
  `OCRProvider`/`AIProvider` と同じ抽象境界として定義した。
- 初期実装として
  `auto_scoring.adapters.heuristic_dependency_analyzer.ReferenceHeuristicDependencyAnalyzer`
  を用意した。これは外部AI呼び出しを行わず、各設問のテキスト中に他設問の番号
  （例:「問1」）＋依存を示唆する表現
  （「を踏まえて」「に基づいて」等）が現れるかを検出するだけの決定的な処理。
  依存の示唆はあるが対象設問番号を特定できない場合は「依存なし」と推測せず
  `unresolved` に積む。逆に、**設問番号への言及があっても依存シグナルの表現
  が無い場合もedgeにしない**（レビュー指摘）。単に互いの番号へ言及しただけの
  独立設問（例: 両方が「問1と問2を比較」のように書いている）まで参照とみな
  してedge化すると、confidence 0.5のedgeが両方向にでき、`from_candidates`
  がサイクルとして拒否して**draftすら保存されない** -- 人間が直せる下書きが
  一つも残らない。番号への言及とシグナル表現が**両方**揃った場合だけedgeに
  し、番号のみの言及はunresolvedとして人間の判断に委ねる。
- `POST /tests/{test_id}/dependency-graph/analyze` は、`Question.model_answer`
  と `Rubric` の基準説明を自動入力しつつ、問題文・採点基準のテキストを
  リクエストボディの `overrides`（`question_id` ごとの上書き）として受け取る。
  PDFからの問題文抽出パイプラインが実装され次第、そちらをデフォルト入力に
  差し替え、`overrides` は人間による上書きの位置づけに変わる想定。overrideの
  各フィールドは「未送信（`None`）ならデフォルトへfallback」「明示的な `""`
  なら文字通り空として使う（デフォルトへ戻さない）」を区別する -- `or` で
  組むと後者が前者と同じ扱いになり、呼び出し元が意図的に除外したはずの保存
  済みrubric文言が漏れてanalyzerに読まれてしまう（レビュー指摘）。
- 将来 `AIProvider` ベースの analyzer に差し替える場合も、`DependencyAnalyzer`
  を実装する新しいadapterを `build_dependency_graph_router(..., analyzer=...)`
  に渡すだけでよい。
- 設問番号は任意の非空文字列を許容するため、一方が他方の接頭辞になり得る
  （例:「問1」と「問1-1」）。`_question_number_pattern` の数字境界チェック
  （`(?<!\d)…(?!\d)`）は「問1」を「問10」の内部にマッチさせない一方で、
  「問1-1」中の「問1」は直後が数字でない`-`なので単独でもマッチしてしまう
  --「問1-1」への言及テキストが「問1」と「問1-1」の両方への参照として二重に
  検出され、両方から高確信度edgeが発行されてしまっていた（レビュー指摘）。
  `_resolve_referenced_numbers` は各番号のマッチ位置（span）を全て集め、
  ある番号のマッチが**より長い**番号のマッチに完全に包含されている場合は
  その出現を「本当の参照ではなく、より長いラベルの一部」として除外する
  （＝最長一致のみを参照として採用する）。同じ番号が他の位置で単独に出現し
  ていれば、その出現は依然として有効な参照として扱われる。テストでは
  「問1」と「問1-1」が両方存在するとき、「問1-1」への言及が「問1-1」だけを
  参照と判定すること（シグナル表現ありのedgeケース、無しのunresolvedケース
  の両方）を検証している
  （`test_overlapping_labels_resolve_to_the_longest_match`、
  `test_overlapping_labels_without_a_signal_phrase_report_only_the_longest`、
  修正前はどちらも「問1」と「問1-1」の両方が参照として検出されることを
  確認済み）。
- シグナル表現と設問番号への参照は、結合された全文中のどこかに両方存在す
  るだけでなく、**同じ入力フィールド**（`prompt_text`／`model_answer`／
  `rubric_text` のいずれか一つ）内に共起することを要求する（レビュー
  指摘）。以前は3フィールドを結合した`text`全体に対して「番号への参照が
  ある」「シグナル表現がある」をそれぞれ独立に判定していたため、例えば
  `prompt_text`に「問1と比較する」という単なる言及があり、`rubric_text`に
  無関係な「根拠に基づいて採点する」が含まれるだけで、両方のグローバル
  チェックがtrueになり、シグナルが実際には「問1」を修飾していなくても
  confidence 0.8のedgeを発行してしまっていた。相互参照の場合はこれが
  スプリアスな2-cycleを作り、`/analyze`がdraftを保存せず422を返してしまう
  （「候補生成」冒頭の設計方針と矛盾）。修正として、`analyze`は3フィールド
  を`fields`のリストとして保持し、`fields`の**各要素ごとに**
  `_resolve_referenced_numbers`とシグナル表現の有無を判定し、両方が同じ
  フィールド内で真になった番号だけを`locally_referenced`としてedge化する。
  結合済み`text`に対するグローバルな`referenced`/`matched_signal`は、
  「番号への言及はあるが同一フィールド内にシグナルが無い」場合の
  unresolved理由づけにのみ引き続き使う。テストでは、prompt/rubricを分けた
  上記の反例でedgeが作られずunresolvedになること、および番号とシグナルが
  同じフィールド内にある通常ケースでは引き続きedgeになること（他の
  フィールドに無関係なシグナルが混ざっていても）を検証している
  （`test_a_bare_mention_and_an_unrelated_signal_in_another_field_do_not_combine`、
  `test_signal_phrase_in_the_same_field_as_the_reference_still_becomes_an_edge`、
  修正前は前者が誤ってedgeを1件生成することを確認済み）。
- `locally_referenced`（同一フィールド内でシグナルと共起した参照）が非空の
  場合、それ以外の参照（`referenced`グローバルには含まれるが
  `locally_referenced`には含まれないもの）を黙って無視していた（レビュー
  指摘）。例えば`prompt_text`が「問1を踏まえて…」（edge化される）、
  `rubric_text`が「問2と比較…」（シグナル無しの裸の言及）の場合、以前は
  `locally_referenced`が非空になった時点で`elif referenced:`分岐が
  スキップされ、問2への参照は`unresolved`に一切現れずq1→currentのedgeだけ
  が生成されていた -- 問2への依存の可能性が人間のレビューに一度も上がらな
  いまま、そのgraphがconfirmできてしまう。修正として、`locally_referenced`
  でedge化した後に `referenced` との差分（`locally_referenced`に含まれない
  参照）を計算し、差分が非空なら同じ「言及はあるが依存シグナルが見つから
  ない」文言で`unresolved`に追加するようにした。テストでは、signal付き参照
  1件とsignal無し裸参照1件が別々のフィールドに混在する設問で、edgeが
  signal付きの分だけ生成されつつ、裸参照の設問番号が`unresolved`に確実に
  現れることを検証している
  （`test_a_signalled_reference_does_not_silence_a_separate_unsignalled_one`、
  修正前は`unresolved`が空のまま欠落することを確認済み）。
- edgeのrationaleスニペットは、以前は結合済み`text`全体を`number`のパター
  ンで再検索して構築していたため（`_snippet_for_number(text, number)`）、
  「問1-1」への言及がシグナル無しで前方のフィールドに、実際にシグナル付き
  の「問1」参照が後方のフィールドに、という配置だと、`_resolve_referenced_
numbers`自体はラベルを正しく区別する（round 7の最長一致ロジック）のに、
  rationale構築時の再検索は前方の「問1-1」内に埋め込まれた「問1」部分文字
  列を最初にヒットさせてしまい、生成されたedgeが実際には無関係な設問の
  文言を根拠として提示してしまっていた（レビュー指摘）。修正として、
  `_resolve_referenced_numbers`はマッチした最初の非吸収span（位置情報）も
  一緒に返すようにし、`locally_referenced`を構築するループでは
  「どのフィールドの・どのspanが」その参照を成立させたかを`local_evidence`
  （`(number, from_id) -> (field_text, span)`）に保持する。rationaleは
  `_snippet_from_span(field_text, span)`でその保持しておいた実際の一致箇所
  から直接切り出すため、もう全文再検索による取り違えは起きない。テストでは
  「問1-1」（シグナル無し・前方フィールド）と「問1」（シグナル付き・後方
  フィールド）が同時に存在する設問で、生成されたedgeのrationaleが正しく
  「問1」側フィールドの文言を含み、「問1-1」側フィールドの文言を含まない
  ことを検証している
  （`test_edge_rationale_snippet_comes_from_the_field_that_actually_justified_it`、
  修正前はrationaleが前方フィールドの無関係な文言を含むことを確認済み）。

### API・DB配線

- `auto_scoring.api.app.create_app` に `session_factory` を追加した
  （省略時は依存グラフのルートを一切マウントしない -- `/healthz` と `/score`
  のみのアプリも引き続き作れる）。
- 実運用のサイドカー起動（`auto_scoring.api.sidecar.run`）は `--app-data-dir`
  （既定 `app-data/`、simplified-design-specification.md §23）配下の
  `database.sqlite` を起動時に `alembic upgrade head` してから
  `session_factory` を渡すようにした。DBをFastAPIアプリへ接続する配線はこの
  Issueが最初で、他のエンティティ（Test/Question等）のCRUD APIはまだ無い
  ため今後追加されるルーターも同じ `session_factory` を再利用できる。
- OpenAPIスキーマ書き出し（`auto_scoring.api.openapi_schema`）はDartクライア
  ント生成のためインメモリSQLiteでルート形状だけを持つアプリを組み立てる。
- `migrations/` と `alembic.ini` は開発者の利便性のため `backend/` 直下
  （`src/auto_scoring` の外）に置いているが、wheelのビルド対象は
  `src/auto_scoring` だけなので、そのままではwheelインストール後に
  `auto-scoring-sidecar`（起動時に `upgrade(db_url, "head")` を呼ぶ）が
  マイグレーションを見つけられずUvicorn起動前に落ちてしまう（レビュー
  指摘）。`backend/pyproject.toml` の `[tool.hatch.build.targets.wheel]` に
  `force-include = { "migrations" = "auto_scoring/migrations", "alembic.ini"
= "auto_scoring/alembic.ini" }` を追加し、wheel内の `auto_scoring/` 配下
  にも同梱する。`db/migrator.py` はパッケージ内配置
  （`Path(__file__).resolve().parent.parent / "migrations"`）とソースツリー
  配置（`backend/migrations`）の両方を試し、存在する方を使う -- 開発時は
  ソースツリー版、wheelインストール後はパッケージ同梱版が使われ、両者が
  同一インストールで共存することはない。`alembic.ini` も同様に両方の場所
  を探す（見つからなければ `Config(file_=None)` でも `script_location`/
  `sqlalchemy.url` を明示設定するので動作に支障は無い）。
  実際に `uv build --wheel` でwheelを作り、`unzip`でファイル一覧を確認
  （`auto_scoring/alembic.ini`、`auto_scoring/migrations/env.py`、
  `versions/*.py` が全て含まれ `__pycache__` は含まれないこと）、さらに
  そのwheelを隔離venvへインストールして `backend/` ソースツリーが存在
  しないディレクトリから `upgrade("sqlite:///test.sqlite", "head")` を実行
  し `current_revision` がheadと一致することまで確認済み。

## 検証

- `backend/tests/test_dependency_graph.py`: validation（self-loop / 不明ID /
  cycle / 重複edge / CONFIRMED+unresolvedの拒否）、topological layer計算、
  cycle報告がサイクル本体だけに絞られること、confirmライフサイクル、
  `can_start_submission_processing` のunit test。
- `backend/tests/test_heuristic_dependency_analyzer.py`: ヒューリスティック
  analyzerのunit test（参照検出、要確認判定、テキスト無し設問の要確認化、
  「問1」が「問10」に誤マッチしないこと、シグナル表現の無い番号言及だけでは
  edgeにならないこと、互いの番号を言及し合うだけの独立設問がサイクル候補に
  ならないこと）。
- `backend/tests/test_domain_models.py`: `Job.dependency_graph_version` の
  検証、`reissue_job_for_graph_version`（cancel + 再作成）のunit test。
- `backend/tests/test_dependency_graph_repository.py`: 実SQLiteに対する
  upsert・バージョン不変性（`created_at` を含む）・`get_latest`/`list_versions`
  のintegration test。`try_confirm` が同じ古いDRAFT読み取りから作った2つの
  confirmed graphのうち一方しか勝てないこと、既にCONFIRMEDな行やより新しい
  CONFIRMED版がある場合に何も変更せず `False` を返すこと、`try_confirm` 呼び
  出し直前に設問が追加された場合に `False` を返し行を変更しないことの
  integration test。
- `backend/tests/test_sqlalchemy_repositories.py`:
  `JobRepository.list_incomplete_for_stale_versions` がテスト単位・状態・
  バージョンで正しく絞り込むこと（FAILEDも対象に含み、SUCCEEDED/CANCELLEDは
  除外すること）のintegration test。
- `backend/tests/test_migrations.py`: 新しいCHECK制約（confirmed graphの
  unresolved空検証、jobのdependency_graph_version正値検証）をDBレベルで
  拒否できることの確認。
- `backend/tests/test_dependency_graph_api.py`: 全独立・完全直列（複数ページ
  またぎ含む）・分岐/合流・cycle拒否の4fixtureをAPI経由（実SQLite）で検証、
  「AI候補の誤りを人間がconfirmで修正し、確定graphだけが
  `can_start_submission_processing` を満たす」シナリオ、レビュー中の draft を
  別クライアントの再analyzeが書き換えないこと、v2がv1より先にconfirmされた
  後の古いv1へのconfirmが拒否されること、`/analyze` と `/confirm` の間に
  設問が増えた場合にconfirmが拒否されること、`save()` の
  `IntegrityError`（バージョン採番の衝突）から正しく再試行して回復すること
  （モックで決定的に再現）、`try_confirm` がレースに負けたときAPIが409を返す
  こと（モックで決定的に再現）、アプリ層チェック通過後・`try_confirm` 実行前
  の窓で設問が追加された場合も409になること（`try_confirm` をモンキーパッチ
  してその窓を強制的に再現）、明示的な空rubric override（`""`）が保存済み
  rubric文言へfallbackせず尊重されること、**確定graphのバージョンが進んだと
  きに古いバージョンの未完了job（FAILEDを含む）がCANCELLEDへ遷移し、新バー
  ジョン向けのjobが同一トランザクションで作られること**（Issue #26 受入条件
  そのもの）。
