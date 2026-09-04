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
- 同じバージョンがDRAFTの間は、再分析・人間の修正で **上書き**できる
  （`DependencyGraphRepository.save` が `(test_id, version)` でupsertする）。
- CONFIRMEDになったバージョンは不変。`save` は既存のCONFIRMED行を上書きしよう
  とすると `DependencyGraphError` を送出する。確定後にグラフを変更したい場合は
  新しい（より大きい）バージョンをDRAFTから始める。
- 受入条件「確定graphを変更した場合はversionを更新し、古いgraphで未完了の採点
  jobを無効化・再作成できるようにする」のうち、**実装した範囲**: バージョン履歴
  は `list_versions` で全件保持・参照でき、各バージョンは不変なので「どのバー
  ジョンで生成されたjobか」を後から判別する土台になる。**未実装（次のスコープ）**:
  `Job`（`auto_scoring.domain.models.Job`）はまだどの依存グラフ・バージョンから
  生成されたかを保持しておらず、`JobRepository` もテスト単位の検索を持たない
  ため、「古いバージョンに紐づくjobを自動的に無効化・再作成する」処理は未実装。
  これはジョブキュー実装Issue（simplified-design-specification.md §29）で
  `Job` にグラフバージョンの参照を追加してから対応する。

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
  差し替え、`overrides` は人間による上書きの位置づけに変わる想定。
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
  cycle / 重複edge）、topological layer計算、confirmライフサイクル、
  `can_start_submission_processing` のunit test。
- `backend/tests/test_heuristic_dependency_analyzer.py`: ヒューリスティック
  analyzerのunit test（参照検出、要確認判定）。
- `backend/tests/test_dependency_graph_repository.py`: 実SQLiteに対する
  upsert・バージョン不変性・`get_latest`/`list_versions` のintegration test。
- `backend/tests/test_dependency_graph_api.py`: 全独立・完全直列（複数ページ
  またぎ含む）・分岐/合流・cycle拒否の4fixtureをAPI経由（実SQLite）で検証、
  および「AI候補の誤りを人間がconfirmで修正し、確定graphだけが
  `can_start_submission_processing` を満たす」シナリオ。
