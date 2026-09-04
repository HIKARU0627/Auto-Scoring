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
- 受入条件「確定graphを変更した場合はversionを更新し、古いgraphで未完了の採点
  jobを無効化・再作成できるようにする」は実装済み: `Job` に
  `dependency_graph_version`（そのjobがどの確定バージョンに対して発行された
  か）を追加し、`JobRepository.list_incomplete_for_stale_versions(test_id,
current_version)` で「今の確定バージョンと異なるバージョンに紐づく、まだ
  QUEUED/RUNNING/BLOCKEDのjob」を検索できるようにした。`POST /confirm` は
  グラフを保存した同じトランザクション内でこの一覧を取得し、各jobを
  `reissue_job_for_graph_version`（`auto_scoring.domain.models`）で
  CANCELLEDへ遷移させつつ、新バージョン向けの新しいQUEUED jobを作成して
  `uow.commit()` する。実際のjob生成（confirmed graphから初回のjobを作る
  スケジューラ）はこのIssueの対象外のまま（後続のジョブキューIssue）だが、
  「既存jobがある場合に無効化・再作成する」動作自体は完全にテスト済み
  （`test_dependency_graph_api.py` の「Job invalidation」節）。

### 追加の不変条件（レビュー指摘で強化）

- `DependencyGraph.__post_init__` は「CONFIRMEDなのに `unresolved` が空でな
  い」状態も拒否する。`confirm()` は常に `unresolved=()` にして遷移するため
  通常経路では起きないが、`from_dict`/直接構築で壊れた行を読み込んだ場合に
  `can_start_submission_processing` が誤って `True` を返さないようDBレベル
  （`ck_dependency_graphs_confirmed_has_no_unresolved`、SQLiteの
  `json_array_length`使用）でも二重に保護する。
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

### Submission処理のゲート

`can_start_submission_processing(graph)` が唯一のゲート関数: `graph` が
`None`（未分析・分析失敗を含む）か、`DependencyGraphStatus.CONFIRMED` でなけ
れば `False`。人間未確認のDRAFTや分析失敗はここで一律にブロックされる。

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
  `unresolved` に積む。
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

## 検証

- `backend/tests/test_dependency_graph.py`: validation（self-loop / 不明ID /
  cycle / 重複edge / CONFIRMED+unresolvedの拒否）、topological layer計算、
  cycle報告がサイクル本体だけに絞られること、confirmライフサイクル、
  `can_start_submission_processing` のunit test。
- `backend/tests/test_heuristic_dependency_analyzer.py`: ヒューリスティック
  analyzerのunit test（参照検出、要確認判定、テキスト無し設問の要確認化、
  「問1」が「問10」に誤マッチしないこと）。
- `backend/tests/test_domain_models.py`: `Job.dependency_graph_version` の
  検証、`reissue_job_for_graph_version`（cancel + 再作成）のunit test。
- `backend/tests/test_dependency_graph_repository.py`: 実SQLiteに対する
  upsert・バージョン不変性（`created_at` を含む）・`get_latest`/`list_versions`
  のintegration test。`try_confirm` が同じ古いDRAFT読み取りから作った2つの
  confirmed graphのうち一方しか勝てないこと、既にCONFIRMEDな行やより新しい
  CONFIRMED版がある場合に何も変更せず `False` を返すことのintegration test。
- `backend/tests/test_sqlalchemy_repositories.py`:
  `JobRepository.list_incomplete_for_stale_versions` がテスト単位・状態・
  バージョンで正しく絞り込むことのintegration test。
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
  こと（モックで決定的に再現）、明示的な空rubric override（`""`）が保存済み
  rubric文言へfallbackせず尊重されること、**確定graphのバージョンが進んだと
  きに古いバージョンの未完了jobがCANCELLEDへ遷移し、新バージョン向けのjobが
  同一トランザクションで作られること**（Issue #26 受入条件そのもの）。
