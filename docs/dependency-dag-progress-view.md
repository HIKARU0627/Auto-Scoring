# 設問依存DAGによるAI処理の進捗表示

GitHub Issue [#64](https://github.com/HIKARU0627/Auto-Scoring/issues/64)（親
[#3](https://github.com/HIKARU0627/Auto-Scoring/issues/3)）。答案のAI処理中に
**何が今動いていて、何が何待ちで、次に何が始まるか**を、添削レビュー画面上の
ノードグラフとして見せる。

依存: [#26](https://github.com/HIKARU0627/Auto-Scoring/issues/26)（設問依存DAG本体、
[dependency-graph.md](./dependency-graph.md)）、
[#18](https://github.com/HIKARU0627/Auto-Scoring/issues/18)（ジョブキュー、
[job-queue.md](./job-queue.md)）、
[#66](https://github.com/HIKARU0627/Auto-Scoring/issues/66)（Riverpod / go_router）、
[#67](https://github.com/HIKARU0627/Auto-Scoring/issues/67)（デザイントークン、
[design-tokens.md](./design-tokens.md)）。

## 0. 何を作っていないか

この Issue で**新しく作ったものは表示だけ**である。

| 必要なもの             | どこに既にあるか                                                                               |
| ---------------------- | ---------------------------------------------------------------------------------------------- |
| 依存グラフ             | `DependencyGraph`（Issue #26）。`GET /tests/{id}/dependency-graph`                             |
| 並列実行レイヤー       | Kahn法。backend `domain.dependency_graph._kahn_layers`、Dart側はテスト設定画面が既に使っていた |
| ジョブ状態             | `Job.state` / `Job.usable` / `Job.blocked_on_question_id`（Issue #18）                         |
| データ取得・ポーリング | 添削レビュー画面が既に `listJobs` を3秒間隔で回している                                        |

**グラフ配置アルゴリズムは書いていない。** レイヤーが「x方向の位置」を、レイヤー内の
並び順が「y方向の位置」を、それぞれそのまま決める。ノードの座標計算は
`AppLayout.dagNodeWidth` などのトークンとの掛け算だけである。

## 1. 決定事項

### 1.1 描画ライブラリを追加しない（`CustomPainter` で足りる）

ノードグラフのライブラリ（`graphview`、`flutter_flow_chart` 等）は**採用しない**。

- グラフ描画ライブラリの主な価値は**レイアウトアルゴリズム**（力学モデル、Sugiyama法
  など「どこにノードを置くか」）である。ここではその答えが Issue #26 の並列実行
  レイヤーとして既に確定しており、しかもそれは見た目の都合ではなく
  **実際の実行計画そのもの**である。ライブラリに置き直させると、画面が示す構造と
  キューが実際に走らせる順序が別々に決まることになる。
- 残る仕事は「線と矢印を引く」だけで、`CustomPainter` の範囲。
- ノードは `CustomPainter` ではなく**通常のウィジェット**（`InkWell` +
  `Semantics`）にしてある。`CustomPaint` はフォーカス機構にもスクリーンリーダーにも
  「1個の不透明な要素」に見えるため、キーボード操作とアクセシビリティラベルという
  受入条件をどちらも満たせない。線だけを描かせ、ノードはウィジェットに任せている。

再検討の条件: レイヤー内のノード数が実データで十分多くなり、交差の削減
（barycenter法など）が読みやすさに効くと分かったとき。

### 1.2 レイアウト計算と状態導出は `core` に置く

`app/lib/core/dependency_dag.dart`。`features` 側（
`app/lib/features/pdf_review/dependency_dag_panel.dart`）は描画と入力だけを持つ。
既存の `core/pdf_review_geometry.dart` と同じ分け方で、検証は
`app/test/dependency_dag_test.dart`（ウィジェットツリー無し）。

副作用として、テスト設定画面（`test_settings_page.dart`）が持っていた
`_computeLayers` は `dependencyExecutionLayers` として `core` に移った。同じ計算が
2画面に別々に存在する状態を作らないため。

### 1.3 ノードの状態は「キューが先、人間が後」

1ノードに出す状態は1つだけなので、`Job.state`（queued / running / blocked /
succeeded / failed / cancelled）と `Review.action`（approved / modified / rejected /
regrade_requested）を `DagNodeStatus` へ畳む。優先順位は**動いているジョブが常に
勝つ**。

理由: ジョブは常にレビューより**新しい試行**を表す。新しい確定グラフversionでの
再投入や再判定要求は新しい `Job` を作るが、追記専用のレビュー履歴には前回の試行への
承認が残ったままである（Issue #18）。走り直している設問に「承認済み」と出すのは、
起きていることの逆を言うことになる。

`succeeded` かつ `usable == false` は **要確認**（`AppStatusTone.attention`）にして
いる。これは「まだ誰もレビューしていない」より強い主張で、キュー自身が
「この結果では下流を解放しない」と判断した状態だからである
（[job-queue.md](./job-queue.md)）。アプリ唯一の高彩度色をここに使うのは、
**下流が全部止まっていて、人間が見るまで動かない**という、まさに人を呼んでいる状態
だからである。

### 1.4 エッジの「解放済み」は `Job.usable` で判定する

`state == 'succeeded'` では判定しない。`SUCCEEDED` でも低Confidenceなら
`usable = false` で下流を解放せず、逆に `FAILED` でも人間が
`mark_question_usable` で解放した場合は `usable = true` になる
（[job-queue.md](./job-queue.md)）。`state` で描くと、まだ正しく `BLOCKED` の
ノードの隣に「満たされた依存」が描かれる。

### 1.5 レビュー状態は「取得済みのものだけ」反映する

添削レビュー画面は選択中の設問のレビュー履歴しか取得しない
(`_ensureReviewLoaded`)。未訪問の設問のノードは**パイプラインがどこまで進んだか**を
示し、その設問を開いた時点で人間の判断が乗る。NavigationRail のアイコンが元から
持っていたのと同じ割り切りである。

全設問のレビュー履歴を毎ポーリングで取ると「設問数 × 3秒に1回」のリクエストになり、
その対価は「まだ下されていない判断」の描き分けでしかない。

### 1.6 確定済みグラフだけを描く

`POST /dependency-graph/analyze` は常に新しい DRAFT version を作り、サイドカーは
**最新version しか返さない**。登録後に再分析したテストでは、最新グラフは
「どのジョブも走ったことのないグラフ」になる。これを描くと、動いているパイプラインが
使っていない依存構造を見せることになるので、その場合は図の代わりに一行の注記を出す。

グラフが1つも無い（404）テストでは、パネルごと出さない。レビュアーの実作業
（認識文字・採点・承認）はグラフに依存しないので、ここでの404は画面のエラー状態に
してはいけない。

### 1.7 ポーリング条件を「選択中の設問」から「この答案のジョブ全部」へ広げた

従来 `_updatePolling` は選択中の設問が採点待ちかどうかだけを見ていた。この図の要点は
**自分が見ていない上流の設問が終わって、下流が解ける**ところなので、選択中の設問が
終わった瞬間に図が凍るのでは意味がない。`_anyJobInFlight`（終端状態でないジョブが
1つでもあるか）を条件に加えた。

## 2. 配置と操作

- **添削レビュー画面の最上部に全幅のバンド**として置く。図が答案全体の話であり、
  同じ範囲を持つ NavigationRail と並びが揃うため。折りたたみ可能で、たたんでも
  ヘッダに「実行中 n ・ 待機 n ・ 完了 n」が残る。
- **狭幅では縮小せずスクロールする。** ノードを縮めると設問番号と状態ラベルが
  読めなくなり、図の目的そのものが失われる。パネルの高さは
  `AppLayout.dagPanelHeight` で固定し、中を縦横にスクロールさせる。
- ノードのクリック / Enter / Space でその設問を選択する（既存の設問選択と同じ経路）。
- **キーボード**: ← → でレイヤー間、↑ ↓ でレイヤー内を移動する。添削レビュー画面は
  ↑↓ を設問移動、Enter を「承認して次へ」に割り当てているので、パネルは自分の
  `Shortcuts` をフォーカスに近い位置に置いて、パネル内にフォーカスがある間だけ
  これらを奪う。移動そのものは Flutter の方向フォーカス
  （`DirectionalFocusIntent`）に任せており、ノードの実座標をそのまま使う。

## 3. 色に依存しない表現（Issue #25 の基準）

| 情報               | 形での表現                                   | 色での補強             |
| ------------------ | -------------------------------------------- | ---------------------- |
| ノードの状態       | 状態ごとに固有のアイコン + 日本語ラベル      | `AppStatusTone`        |
| 何待ちか           | ラベルが「問1 待ち」と前提の設問番号を名指す | —                      |
| 依存が満たされたか | 未: 破線 + 開いた矢尻 / 済: 実線 + 塗り矢尻  | outlineVariant/outline |
| 依存の向き         | レイヤーが左→右、矢印も常に右向き            | —                      |
| 実行中             | 下辺の2pxの動くハイライト                    | —                      |

`app/test/dependency_dag_test.dart` が「全状態がそれぞれ固有のアイコンとラベルを
持つ」ことを検査する。

## 4. モーション（[design-tokens.md](./design-tokens.md) §5 との関係）

デザイントークンの原則は「常時動くものを作らない」である。この画面はその原則の
**唯一の明示的な例外**を持つ。

- **一度だけ動くもの**: 依存が満たされた瞬間、そのエッジを前提→後続の向きに
  250ms（`AppMotion.emphasis`）で1回だけ走らせ、`blocked` が解けたノードの枠を
  同じ時間だけ強調して戻る。これが Issue #64 の主役である。
- **動き続けるもの**: `RUNNING` のノードの下辺だけにある2px
  （`AppLayout.activityBarHeight`）の低コントラストのバー。「今まさに処理中」は
  1回告知して止められる種類の情報ではないため。**実行中のノードにしか出ず、
  ジョブが `RUNNING` を離れた瞬間に消える。**
- **動かないもの**: それ以外の全ての状態変化。`実行待ち → AI処理中` も、人間の承認も、
  `AnimatedContainer`（150ms）でその場の色が変わるだけである。1時間見る画面で
  全ての状態変化に強調を付けるのは、design-tokens.md §5 が避けている疲労そのもの。
- OSで「視差効果を減らす」（`MediaQuery.disableAnimations`）が有効なときは、
  1回の告知も実行中バーの移動も行わない。情報はアイコンとラベルに載っているので
  落ちない。

## 5. スクリーンショット（Linux開発機、実アプリ）

いずれも**合成データ**である。テスト・設問・答案PDF（リポジトリ内の PoC 3 fixture
`app/test/fixtures/a4-portrait.pdf`）・認識文字・点数まで全て作り物で、実データは
一切写っていない。

### 5.1 desktop 標準幅（1280×720）

![添削レビュー画面の依存DAGパネル（標準幅）](./dependency-dag-progress-view/desktop.png)

読み方: 問1 と 問2 と 問4 は同じ層＝並列に走りうる。問1 は人間が承認済み、問2 は
`SUCCEEDED` だが `usable = false`（低Confidence）なので**下流を解放していない**。
その結果 問3 は「問2 待ち」、問3 に依存する 問5 は「問3 待ち」で止まっている。
問1 → 問3 のエッジだけが実線＋塗り矢尻（解放済み）で、問2 → 問3 と 問3 → 問5 は
破線＋開いた矢尻（未解放）。**この画面から「今は誰も動いていない。問2 を人が見る
まで何も進まない」が読める**というのが、この機能の目的そのものである。

### 5.2 狭幅（700×720）

![添削レビュー画面の依存DAGパネル（狭幅）](./dependency-dag-progress-view/narrow.png)

NavigationRail はアイコンのみ、Inspector は PDF の下（Issue #21 の既存挙動）。
パネルはノードを縮めず、入り切らない分をスクロールに回す。

なお **`AI処理中` のノードとそのハイライト、および依存が解ける瞬間の告知は
静止画には写らない**ので、`app/test/dependency_dag_panel_test.dart` の
`only a running node moves, and it stops when the job does` /
`the moment an upstream finishes and the downstream is released is announced
once, then the diagram settles` が代わりに検査している。

## 6. 検証

- `app/test/dependency_dag_test.dart` — レイヤー分割、座標、状態導出、
  `usable` による解放判定、色に依らない表現（ユニットテスト）。
- `app/test/dependency_dag_panel_test.dart` — 描画・クリック・キーボードのみの操作・
  折りたたみ・狭幅スクロール・告知が1回で終わること・視差効果削減。
- `app/test/pdf_review_page_test.dart` の `Issue #64` グループ — 実画面での結線
  （上流完了で下流がライブに解ける、ノードから設問選択、未確定グラフ、グラフ無し）。

## 7. 未決事項

- レイヤー内の並び替えによる交差削減（§1.1）。実データの設問数を見てから。
- 未訪問の設問のレビュー状態（§1.5）。一括取得のAPIができたら見直す。
- ジョブがまだ作られていない答案（`未処理` だらけの図）の見せ方。現状は
  「これから走る計画」として同じ図をそのまま出している。
