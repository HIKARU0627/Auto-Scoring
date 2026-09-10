# フロントエンド不変条件 — 移植先が守るべき約束の正本

GitHub Issue [#204](https://github.com/HIKARU0627/Auto-Scoring/issues/204) / [#216](https://github.com/HIKARU0627/Auto-Scoring/issues/216)（親 [#201](https://github.com/HIKARU0627/Auto-Scoring/issues/201) Flutter → Electron 移行）。

**この文書の目的:** 実装が書き直されても失われてはいけない約束を、外に出す。
要約ではなく、**移植先（Electron）のテストが再現すべき約束の正本**である。

正本は 2 つの区画からなる。

| 区画                                                  | 根拠                                                 | ID      |    件数 | 出どころ                                                      |
| ----------------------------------------------------- | ---------------------------------------------------- | ------- | ------: | ------------------------------------------------------------- |
| §1〜§13                                               | `app/test` が固定している振る舞い                    | `INV-*` | **170** | [#204](https://github.com/HIKARU0627/Auto-Scoring/issues/204) |
| [§14](#14-テストが無いまま実装だけが持っている保証ug) | `app/lib` の実装だけが持っている保証（テストが無い） | `UG-*`  |  **15** | [#216](https://github.com/HIKARU0627/Auto-Scoring/issues/216) |

`app/test` に無い保証は §1〜§13 の読み方では定義上こぼれる。§14 はそれを `app/lib` の側から掃いた結果で、
**移行の完了条件を満たしたまま黙って消えうるもの**を数えてある。

## 0. §1〜§13（`app/test` 由来）の棚卸しの範囲と件数

| 指標                   |         値 | 備考                                                                                                                                                                                                                                                         |
| ---------------------- | ---------: | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 読んだテストファイル   |     **52** | `app/test/**/*_test.dart` 全件                                                                                                                                                                                                                               |
| 読んだテスト行数       | **23,868** | 同上（Issue #201 に記載されていた 19,294 行・41 ファイルは移行検討を始めた時点の値で、`frontend-migration.md` 旧版もこれを転記していた。本ワークツリーはその後テストが増えており、`frontend-migration.md` §1.2 も本 PR で 23,868 行・52 ファイルへ更新した） |
| 読んだ `test()`        |    **346** |                                                                                                                                                                                                                                                              |
| 読んだ `testWidgets()` |    **387** |                                                                                                                                                                                                                                                              |
| **読んだテスト合計**   |    **733** | `test()` + `testWidgets()`                                                                                                                                                                                                                                   |
| **抽出した不変条件**   |    **170** | 下表の INV-201-01〜10 および INV-001〜INV-205（欠番あり）。1 テストが複数不変条件を固定する場合は分割して数える                                                                                                                                              |

各不変条件は次の 4 列を持つ。

| 列               | 内容                                                    |
| ---------------- | ------------------------------------------------------- |
| **不変条件**     | 実装が変わっても残すべき約束                            |
| **出どころ**     | 関連 Issue または仕様節（テストに書かれているもののみ） |
| **根拠のテスト** | `app/test/xxx_test.dart:行`                             |
| **壊れると**     | 違反時に利用者・運用で起きること                        |

Issue #201 の「守るべき不変条件」10 項目は **INV-201-01〜10** として先頭にまとめ、詳細は各ドメインの INV にも展開する。

---

## 1. Issue #201 の 10 項目（司令塔リスト）

| ID         | 不変条件                                                                 | 出どころ     | 根拠のテスト                                                                                                    | 壊れると                                                                      |
| ---------- | ------------------------------------------------------------------------ | ------------ | --------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| INV-201-01 | 見ていない判断材料で確定・承認できない                                   | #85 / #145   | `pdf_review_page_test.dart:4657`, `submission_confirm_page_test.dart:201`, `material_read_ranges_test.dart:112` | スクロールせずに承認・確定でき、#85 で直した「見ないで承認」が再発            |
| INV-201-02 | 確信度（Confidence）から完了・確定を導かない                             | §25.2 / #136 | `submission_confirmation_test.dart:191`                                                                         | 高確信の誤 0 点が一括確定され、実測 14 件中 7 件の誤りが通る                  |
| INV-201-03 | 失敗が要約から漏れない。パネルを畳んでも残る。下流の「待ち」と区別できる | #86          | `dependency_dag_panel_test.dart:502`, `dependency_dag_test.dart:506`                                            | 失敗と要確認が同じ「待ち」に見え、上流の対応が永久に先送りされる              |
| INV-201-04 | 無効な操作には、無効条件そのものから導いた理由が必ず出る                 | #88          | `action_requirements_test.dart:38`, `disabled_action_reason_test.dart:45`                                       | 灰色ボタンが黙り、何をすれば有効になるか分からない（#111/#138 再発の温床）    |
| INV-201-05 | 画面を足したら「ホームへ戻れる」検査の対象か除外（理由付き）に必ず載る   | #88 / #197   | `home_escape_test.dart:114`                                                                                     | 新画面に出口が無く、スタック空で開かれたとき行き止まりになる                  |
| INV-201-06 | 失敗文言は「何が起きたか」と「次に何ができるか」を両方持つ               | #86          | `dag_failure_guidance_test.dart:103`                                                                            | 講師が次の操作を選べず、provider 名や HTTP を画面に出す誘惑が残る             |
| INV-201-07 | 廃止した文言が二度と現れない                                             | #111 / #138  | `home_page_test.dart:229`, `intake_page_test.dart:522`                                                          | 存在しない資料（模範解答 PDF 等）を探させる、または「まだありません」で先送り |
| INV-201-08 | 別ボタンにフォーカスした Enter が確定を実行しない                        | #145         | `submission_confirm_page_test.dart:343`                                                                         | 後回しボタンにフォーカスした Enter で答案が確定する                           |
| INV-201-09 | 無効ボタンのコントラストは目視でなく計算で WCAG を満たす                 | #88          | `app_theme_contrast_test.dart:148`                                                                              | ダークテーマで無効ボタンがカードと同化し、ボタンであることも読めない          |
| INV-201-10 | 回答欄の未検出・未割当・読み順食い違いを原因別に見せる                   | #164 / #171  | `answer_area_editor_test.dart:608`, `answer_area_editor_test.dart:773`                                          | 「検出失敗」と「紙に無い」を混同し、採点基準を探す無駄時間が発生              |

---

## 2. アーキテクチャと依存方向

| ID      | 不変条件                                                                | 出どころ        | 根拠のテスト                            | 壊れると                                                          |
| ------- | ----------------------------------------------------------------------- | --------------- | --------------------------------------- | ----------------------------------------------------------------- |
| INV-001 | `api` 層は `core` / `features` を import しない                         | AGENTS.md       | `architecture_test.dart:29`             | 生成クライアントが UI に依存し、OpenAPI 再生成で循環参照          |
| INV-002 | `core` 層は `features` を import しない                                 | AGENTS.md       | `architecture_test.dart:36`             | 画面追加で core が肥大化し、ビジネスルールが画面ごとに複製される  |
| INV-003 | 添削レビュー画面は `setState` 直呼び禁止。`_setStateIfMounted` 経由のみ | #66 / #64 / #80 | `mounted_after_await_lint_test.dart:24` | 読み込み中に画面を離れると未処理 `StateError`                     |
| INV-004 | 無効操作の判定と文言は `core/action_requirements.dart` の単一ソース     | #88             | `action_requirements_test.dart:5`       | 画面ごとに理由が発明され、条件変更で文言だけ古くなる（#111/#138） |
| INV-005 | 答案確定可否は `core/submission_confirmation.dart` に置く               | #145            | `submission_confirmation_test.dart:8`   | 確定ルールが UI に散らばり、到達判定と確信度の混入を検知できない  |
| INV-006 | 設問ステータスは `core/question_status.dart` で一元決定                 | #118 / #156     | `question_status_test.dart:77`          | レール・DAG・Inspector で同一設問が別状態に見える                 |
| INV-007 | レビューキュー順序は `core/review_queue.dart` で決定                    | #113            | `review_queue_test.dart:39`             | ホーム「次の 1 件」とキュー先頭が一致しない                       |

---

## 3. ナビゲーションとルーティング

| ID      | 不変条件                                                                           | 出どころ | 根拠のテスト                          | 壊れると                                                 |
| ------- | ---------------------------------------------------------------------------------- | -------- | ------------------------------------- | -------------------------------------------------------- |
| INV-010 | `features/` 内で `go_router` の `.go()` / `.goNamed()` を使わない                  | #160     | `navigation_stack_lint_test.dart:29`  | スタック破棄で戻る・Escape が効かない行き止まり画面      |
| INV-011 | 画面間移動は `push` / `replace` / `pop` のみ                                       | #160     | `navigation_stack_lint_test.dart:5`   | 入口によって同じ画面が行き止まりになったりならなかったり |
| INV-012 | `AppRoutes` の各 location が対応 Widget を開く                                     | —        | `app_router_test.dart:41`             | ルート表と builder の drift → 実行時 route not found     |
| INV-013 | パラメータ付き URL（`testId`, `submissionId`, `questionId`）が正しく decode される | #145     | `app_router_test.dart:50`             | 「問 4 を直す」リンクが問 1 を開く                       |
| INV-014 | 添削レビューは開く設問を URL で指定できる                                          | #145     | `app_router_test.dart:50`             | キューから特定設問へ直接遷移できない                     |
| INV-015 | スタック空で開いた covered ルートすべてに `BackOrHomeButton` がある                | #88      | `home_escape_test.dart:137`           | 戻る矢印が出ない画面から脱出不能                         |
| INV-016 | 狭幅 700×720 でも出口ボタンが押せる                                                | #88      | `home_escape_test.dart:158`           | 狭窓で AppBar actions から出口が消える                   |
| INV-017 | Tab→Enter のみでホームへ戻れる                                                     | #88      | `home_escape_test.dart:175`           | キーボードのみ利用者が脱出不能                           |
| INV-018 | ホーム自身には出口を出さない                                                       | —        | `home_escape_test.dart:206`           | 無意味な「ホームへ戻る」が増える                         |
| INV-019 | push で積んだ画面では出口は 1 枚戻る（ホーム直行ではない）                         | —        | `home_escape_test.dart:215`           | 画面を 1 枚めくるたびにホームへ飛ばされる                |
| INV-020 | 新ルート追加時、covered か skipped（理由付き）のどちらかに必ず登録                 | #88      | `home_escape_test.dart:114`           | 新画面の home escape 検査漏れ                            |
| INV-021 | 答案キュー行タップは答案確定画面を開く（設問ごと承認ではない）                     | #145     | `submission_queue_page_test.dart:198` | 40 答案 × 5 設問の 200 回承認に戻る                      |

**意図的除外（follow-up #192）:** `submissionQueue` / `pdfReview` は `home_escape_test.dart:39` で除外。技術的障害は無い。

---

## 4. サイドカー起動・ライフサイクル

| ID      | 不変条件                                                | 出どころ  | 根拠のテスト                                   | 壊れると                                |
| ------- | ------------------------------------------------------- | --------- | ---------------------------------------------- | --------------------------------------- |
| INV-030 | 起動中はスプラッシュ→ healthy 後にホーム表示            | #24       | `startup_gate_test.dart:36`                    | サイドカー未準備で UI が操作可能になる  |
| INV-031 | ウィンドウ閉じる前に sidecar を kill                    | #24       | `startup_gate_test.dart:59`                    | 孤児プロセス・ロック残留                |
| INV-032 | 起動失敗時「再起動」でアプリ再起動なしに復旧            | #24       | `startup_gate_test.dart:75`                    | 障害から回復不能                        |
| INV-033 | push 済み画面の上でもクラッシュ overlay＋再起動が見える | #24 / #68 | `startup_gate_test.dart:103`                   | 深い画面でだけ API 失敗し説明なし       |
| INV-034 | 二重起動は「すでに起動しています」                      | #24       | `startup_gate_test.dart:145`                   | クラッシュ風の誤表示                    |
| INV-035 | 実行ファイル欠落→再インストール案内                     | —         | `startup_gate_test.dart:158`                   | ログだけで利用者が困る                  |
| INV-036 | エラー画面に bearer token を描画しない                  | Security  | `startup_gate_test.dart:168`                   | 秘密情報漏えい                          |
| INV-037 | handshake 未完成はリトライ、即失敗しない                | —         | `sidecar_supervisor_test.dart:78`              | 起動レースで誤タイムアウト              |
| INV-038 | ready 後 handshake ファイル削除                         | —         | `sidecar_supervisor_test.dart:117`             | トークンがディスクに残る                |
| INV-039 | 即 exit はタイムアウト待たず failed                     | —         | `sidecar_supervisor_test.dart:172`             | 60 秒待ちの UX                          |
| INV-040 | exit code 3 = alreadyRunning                            | —         | `sidecar_supervisor_test.dart:328`             | 二重起動判定のプロトコル破綻            |
| INV-041 | shutdown は kill 後 crash 報告しない                    | —         | `sidecar_supervisor_test.dart:310`             | 正常終了がクラッシュ扱い                |
| INV-042 | Windows: バンドル優先、venv fallback                    | —         | `sidecar_paths_test.dart:19`                   | 本番インストールで sidecar 見つからない |
| INV-043 | POSIX: `.exe` なし、`bin/` venv                         | —         | `sidecar_paths_test.dart:44`                   | Linux CI/dev で起動不能                 |
| INV-044 | 統合: 動的 port、token で保護 API 成功                  | #24       | `sidecar_supervisor_integration_test.dart:70`  | 固定 port 衝突                          |
| INV-045 | 統合: shutdown 後プロセス/port/lock 解放                | #24 / #57 | `sidecar_supervisor_integration_test.dart:106` | 再起動・二重起動不可                    |
| INV-046 | 統合: 外部 sidecar を survivor と誤認しない             | #57       | `sidecar_supervisor_integration_test.dart:173` | flaky な false positive                 |
| INV-047 | `sidecarStillServing`: 空 `[]` の 200 は alive          | #57       | `sidecar_probe_test.dart:27`                   | shutdown 検査の flaky                   |
| INV-048 | ホームに `backend: ok` 等デバッグ表示なし               | #68       | `home_page_test.dart:58`                       | サイドカー状態の二重表示                |

---

## 5. PDF レビュー・座標・オーバーレイ

| ID      | 不変条件                                                      | 出どころ     | 根拠のテスト                         | 壊れると                   |
| ------- | ------------------------------------------------------------- | ------------ | ------------------------------------ | -------------------------- |
| INV-050 | 正規化座標→ピクセル変換（A4 縦・90°回転）                     | #12          | `pdf_review_geometry_test.dart:44`   | オーバーレイと PDF ずれ    |
| INV-051 | ズーム 2× で overlay も 2× スケール                           | #21          | `pdf_review_geometry_test.dart:62`   | 拡大時マーク位置ずれ       |
| INV-052 | explicit rect はそのまま使用                                  | —            | `pdf_review_geometry_test.dart:128`  | 既知位置の記号が消える     |
| INV-053 | anchor_text → OCR box 解決（§12.3）                           | —            | `pdf_review_geometry_test.dart:153`  | 下線・×が単語に付かない    |
| INV-054 | crop 座標→page 座標変換（answer_area 経由）                   | —            | `pdf_review_geometry_test.dart:178`  | 回答欄切り出し後の注釈ずれ |
| INV-055 | degenerate answer_area は full page 扱い                      | —            | `pdf_review_geometry_test.dart:242`  | 注釈 rect が 0 に潰れる    |
| INV-056 | OCR 改行付き anchor もマッチ                                  | #141         | `pdf_review_geometry_test.dart:270`  | Document AI 改行で記号消失 |
| INV-057 | 複数 token は union rect                                      | —            | `pdf_review_geometry_test.dart:295`  | 複合語への 1 マーク不可    |
| INV-058 | 最短 run が選ばれる                                           | —            | `pdf_review_geometry_test.dart:353`  | 広すぎるハイライト         |
| INV-059 | 長すぎる run は拒否（null）                                   | —            | `pdf_review_geometry_test.dart:397`  | 全文に誤マーク             |
| INV-060 | 非連続 box は拒否                                             | —            | `pdf_review_geometry_test.dart:421`  | 別解答を 1 anchor に結合   |
| INV-061 | anchor 未一致時 score_area に fallback しない                 | #141 / §12.4 | `pdf_review_geometry_test.dart:465`  | 誤位置に ×/○               |
| INV-062 | ウィジェット: 正規化 (0.5,0.5) が pdfrx 実 render size で配置 | #12          | `pdf_review_page_test.dart:790`      | 本番 overlay ずれ          |
| INV-063 | 90° PDF でも同じ alignment                                    | #12          | `pdf_review_page_test.dart:839`      | 回転答案で記号ずれ         |
| INV-064 | ターゲット無し annotation → 設問コメント欄                    | #141         | `pdf_review_page_test.dart:769`      | コメント消失               |
| INV-065 | 判断材料未読範囲 merge が NaN を出さない                      | #85          | `material_read_ranges_test.dart:6`   | 毎フレーム rebuild ループ  |
| INV-066 | 行 covered = 0→1 全域到達で承認可能                           | #85          | `material_read_ranges_test.dart:112` | 上半分だけ見て承認できる   |
| INV-067 | 判断材料が画面外のあいだ承認・Enter 不可。却下は可            | #85          | `pdf_review_page_test.dart:4657`     | 見ないで承認（INV-201-01） |
| INV-068 | 高確信度に緑チェックを付けない（低のみ）                      | #156         | `pdf_review_page_test.dart:658`      | 確信度=正しさの誤信号      |
| INV-069 | blank answer 申告は本文に伴う                                 | #136 / #156  | `pdf_review_page_test.dart:712`      | 0 点理由不明               |
| INV-070 | レール・DAG・Inspector で同一語・アイコン                     | #84          | `pdf_review_page_test.dart:3962`     | 同一設問が別状態に見える   |
| INV-071 | Issue #22: edit/reject/regrade/approve/undo 一連が通る        | #22          | `pdf_review_page_test.dart:2103`     | 編集履歴・並行性バグ       |

### 5.1 移行後の座標の作り方（Issue #207 / PoC 6 案 B）

上の INV-050〜INV-063 は、**Flutter が pdfrx で PDF を描いていた前提**の上に立っている。
移行後はその前提が無くなる。renderer は PDF を描かず、サイドカーが pypdfium2 で描いた
ページ画像を表示する。引き取り先の規則は次の 3 つ。

| ID     | 移行後の不変条件                                                                        | 出どころ | 根拠のテスト                                                          | 壊れると                                      |
| ------ | --------------------------------------------------------------------------------------- | -------- | --------------------------------------------------------------------- | --------------------------------------------- |
| MIG-01 | 正規化座標は**受け取った画像の画素寸法だけ**で割って作る（`click_px ÷ image_width_px`） | #207     | `backend/tests/test_page_image_api.py`（画素寸法 = 表示ページ×scale） | 案 B が消した二重解釈が renderer 側で復活する |
| MIG-02 | `/pages` の `displayed_*` を座標計算に使わない。枠取り・ページ送り・回転の把握に限る    | #207     | 同上 + OpenAPI description（4 本）                                    | 幾何と画像の丸めが割れ、ズームごとにずれる    |
| MIG-03 | renderer は**生の PDF バイト列を受け取らない**。app-data の所有はサイドカーのまま       | #207     | `test_page_image_api.py` / `sidecar-api.md` §7.5                      | 描画経路が 2 つに戻り、座標バグも 2 組に戻る  |

契約の全体は [`sidecar-api.md`](./sidecar-api.md) §7。画面ごとの現れ方は
[`pdf-review-overlay.md`](./pdf-review-overlay.md) §3.1 と
[`answer-area-detection.md`](./answer-area-detection.md) §2。

**実答案 PDF での座標往復は未測定**（PoC 6 の残存リスク）。最高責任者の実機検証 Issue #6 の
結果が出るまで、回答欄エディタと添削レビューのオーバーレイには着手しない（#202 の決定）。

---

## 6. デザイントークン・アクセシビリティ

| ID      | 不変条件                                                                   | 出どころ  | 根拠のテスト                         | 壊れると                                        |
| ------- | -------------------------------------------------------------------------- | --------- | ------------------------------------ | ----------------------------------------------- |
| INV-080 | `lib/features/` に padding/gap/radius/elevation/icon/layout/色リテラル禁止 | #67       | `design_tokens_lint_test.dart:40`    | 画面ごとに寸法がバラバラ                        |
| INV-081 | 主要 7 画面が light/dark 両テーマで surface ramp から背景                  | #67       | `design_tokens_screens_test.dart:73` | ダークで独自背景・ThemeExtension 欠落クラッシュ |
| INV-082 | Noto Sans JP variable（fvar、≥17000 glyphs）                               | #67       | `app_typography_test.dart:46`        | 稀な漢字が □、OCR 照合不能                      |
| INV-083 | 数字は等幅（点数更新で横ジャンプしない）                                   | #67       | `app_typography_test.dart:85`        | 点数編集時 UI が揺れる                          |
| INV-084 | fontWeight が variable axis を駆動                                         | #67       | `app_typography_test.dart:104`       | 太字/見出しが平坦化                             |
| INV-085 | 全 text role が bundled family + height                                    | #67       | `app_typography_test.dart:123`       | 日本語行間崩れ                                  |
| INV-086 | 認識文字 role は body より大・letterSpacing>0                              | #67       | `app_typography_test.dart:144`       | 手書き照合 UI の意味消失                        |
| INV-087 | 全 surface 段で onSurface/onSurfaceVariant ≥4.5:1                          | #67 / #25 | `app_theme_contrast_test.dart:49`    | WCAG AA 未達                                    |
| INV-088 | Material on/role ペア ≥4.5:1                                               | #67       | `app_theme_contrast_test.dart:77`    | ボタン・チップ不可読                            |
| INV-089 | status 色（attention/success/error）≥4.5:1 on surface                      | #67 / #25 | `app_theme_contrast_test.dart:111`   | 状態が色だけでは判別不可                        |
| INV-090 | disabled ボタン: outline ≥3:1、label ≥4.5:1                                | #88 / #67 | `app_theme_contrast_test.dart:148`   | INV-201-09 再発                                 |
| INV-091 | Material 既定 disabled outline は AA 未達（上書き理由の実測）              | #88       | `app_theme_contrast_test.dart:190`   | 上書き削除で再発                                |
| INV-092 | filled/outlined/text 全 ButtonTheme が disabled 色を返す                   | #67       | `app_theme_contrast_test.dart:207`   | 定義だけあって適用されない                      |
| INV-093 | annotationMark は両テーマ同一・白紙 PDF 上 ≥4.5:1                          | —         | `app_theme_contrast_test.dart:262`   | 答案用紙上の ○×△不可読                          |
| INV-094 | dark onSurface contrast 7–13（白黒最大回避）                               | #67       | `app_theme_contrast_test.dart:277`   | 長時間閲覧の halation                           |
| INV-095 | AppStatusColors / AppTextRoles extension 必須                              | #67       | `app_theme_contrast_test.dart:291`   | `context.statusColors!` クラッシュ              |
| INV-096 | AppErrorBanner: 再試行・busy 時 disable・1 回 fade-in で settle            | #67       | `app_error_banner_test.dart:20`      | エラー UI が永遠アニメーション                  |
| INV-097 | QuestionStatus: 各状態に固有 label+icon（色だけにしない）                  | #25       | `question_status_test.dart:285`      | 色覚多様性で状態判別不能                        |

---

## 7. 無効操作の理由（action_requirements）

| ID      | 不変条件                                          | 出どころ       | 根拠のテスト                           | 壊れると                        |
| ------- | ------------------------------------------------- | -------------- | -------------------------------------- | ------------------------------- |
| INV-100 | 無効操作には理由 id が 1 件以上、有効時 0 件      | #88            | `action_requirements_test.dart:38`     | INV-201-04 再発                 |
| INV-101 | 理由文は「。」終わり・Exception/HTTP/数字なし     | #88 / Security | `action_requirements_test.dart:20`     | 診断文が講師に見える            |
| INV-102 | busy は単独でも理由になる                         | #88            | `action_requirements_test.dart:54`     | 処理中に理由なし無効            |
| INV-103 | intake: template 未選択→`intake-template`         | #88            | `action_requirements_test.dart:38`     | フォルダ選択不可理由なし        |
| INV-104 | 条件充足で理由消去＋高さ 0（余白残さない）        | #88            | `disabled_action_reason_test.dart:71`  | 理由欄の空白                    |
| INV-105 | 理由は Tooltip ではなく visible Text              | #88            | `disabled_action_reason_test.dart:59`  | ホバー必須→キーボード利用者排除 |
| INV-106 | 狭幅 700×720 で理由が画面内                       | #88            | `disabled_action_reason_test.dart:96`  | 理由が clip                     |
| INV-107 | API キー: 未設定→verify 無効+理由                 | #88 / #96      | `action_requirements_test.dart:320`    | 設定画面で操作不能理由不明      |
| INV-108 | helperText と disabled reason の二重表示禁止      | #88            | `disabled_action_reason_test.dart:210` | 文言の片方だけ古くなる          |
| INV-109 | Tab 順: 理由 Text は focus 取らず隣ボタン到達可能 | #88            | `disabled_action_reason_test.dart:215` | 理由追加で Tab 順破壊           |
| INV-110 | profile confirm 理由 ⊇ save 理由（部分集合）      | #88            | `action_requirements_test.dart:175`    | 1 理由欄で save だけ塞がる      |

---

## 8. 取込・登録フロー

| ID      | 不変条件                                               | 出どころ   | 根拠のテスト                       | 壊れると                       |
| ------- | ------------------------------------------------------ | ---------- | ---------------------------------- | ------------------------------ |
| INV-120 | 未確認 AI 提案がある間 import 不可                     | #101       | `intake_review_test.dart:70`       | 未レビュー AI 分類で本番取込   |
| INV-121 | 規則マッチファイルは AI 確認不要                       | #101       | `intake_review_test.dart:150`      | 40 答案すべて手確認            |
| INV-122 | 既存テスト追記時は gradingCriteria 不要                | #101       | `intake_review_test.dart:170`      | 2 週目以降ブロック             |
| INV-123 | 新規テストは criteria 必須                             | #101       | `intake_review_test.dart:186`      | 基準なしテスト登録             |
| INV-124 | 規則のみなら AI 分類 API 0 回                          | #101       | `intake_page_test.dart:231`        | 不要コスト・レイテンシ         |
| INV-125 | 取込前に件数・概算費用表示                             | #101       | `intake_page_test.dart:264`        | 同意なし API 送信              |
| INV-126 | 単価未設定時は費用を数字で言わない                     | —          | `intake_page_test.dart:284`        | 誤った 0 円表示                |
| INV-127 | 完了画面は「採点できる」と言わない                     | #80        | `intake_page_test.dart:456`        | 配点未設定なのに採点可能と誤解 |
| INV-128 | 模範解答 PDF 要求文言なし                              | #95 / #101 | `home_page_test.dart:229`          | INV-201-07                     |
| INV-129 | 「採点マニュアル PDF」旧呼び名なし                     | #138       | `home_page_test.dart:234`          | INV-201-07（別画面での再発）   |
| INV-130 | 「画面はまだありません」文言なし                       | #111       | `intake_page_test.dart:522`        | INV-201-07                     |
| INV-131 | 27 件目失敗でも前 26 答案残存                          | —          | `intake_page_test.dart:563`        | 部分成功のロールバック         |
| INV-132 | 取込後 AI 採点起票経路を維持                           | #80        | `intake_page_test.dart:707`        | 答案が unprocessed のまま      |
| INV-133 | 起票失敗でも取込成功扱い+理由                          | #80        | `intake_page_test.dart:761`        | 取込成功なのに採点不能が隠れる |
| INV-134 | material role は wire name（`annotation_resource` 等） | #139       | `sidecar_api_client_test.dart:208` | 422 unknown role               |
| INV-135 | PDF upload は `application/pdf` content-type           | —          | `sidecar_api_client_test.dart:178` | 400 で取込前失敗               |

---

## 9. レビュー・答案キュー・確定

| ID      | 不変条件                                               | 出どころ    | 根拠のテスト                            | 壊れると                         |
| ------- | ------------------------------------------------------ | ----------- | --------------------------------------- | -------------------------------- |
| INV-140 | キュー順: needs_review 優先、同状態は取込古い順        | #113        | `review_queue_test.dart:39`             | ホーム「次の 1 件」と不一致      |
| INV-141 | 済み答案も一覧から消さない                             | #113        | `review_queue_test.dart:58`             | 残り把握不能                     |
| INV-142 | `positionOf` は 1 始まり、未知は 0                     | #113        | `review_queue_test.dart:75`             | 「1 枚目」表示混乱               |
| INV-143 | `nextAfter` は reviewed スキップ、末尾→前の未了        | #113        | `review_queue_test.dart:91`             | 後回し答案を拾えない             |
| INV-144 | 設問進捗: partial/manual grading 表示                  | #112 / #118 | `review_queue_test.dart:138`            | 3/5 と未着手が同じ見た目         |
| INV-145 | `isFullyConfirmed`: 全問確定なら state≠reviewed でも可 | #112 / #137 | `review_queue_test.dart:190`            | legacy `ai_processed` が出力不可 |
| INV-146 | 進捗不明時は export 可と言わない                       | #137        | `review_queue_test.dart:228`            | 押せるが必ず 409                 |
| INV-147 | ホーム: `ai_processed` は確認済みに数えない            | #112        | `home_dashboard_test.dart:88`           | 進捗バーが嘘                     |
| INV-148 | 続きは needs_review 最古優先                           | #68         | `home_dashboard_test.dart:122`          | 新しい要確認を飛ばす             |
| INV-149 | 答案キュー入口はホーム「確認済み N/M」タップのみ       | #113        | `home_page_test.dart:165`               | キューに到達不能                 |
| INV-150 | 溢れテストの要確認も fetch/表示                        | #151        | `home_dashboard_test.dart:213`          | 11 教科中 2 教科が invisible     |
| INV-151 | 設問並び: 自然順 number、page 優先                     | #145        | `question_order_test.dart:22`           | レールと確定画面の設問不一致     |
| INV-152 | usable=false + waiting → needsCheck; 待ち無し → graded | #156        | `question_status_test.dart:112`         | 11/12 設問が誤って要確認         |
| INV-153 | 人間採点後は stopped job より review 優先              | #118        | `question_status_test.dart:184`         | 手入力後も「失敗」表示           |
| INV-154 | 未到達設問があれば確定不可、番号明示                   | #85 / #145  | `submission_confirmation_test.dart:201` | INV-201-01                       |
| INV-155 | 全到達後 1 操作で N 問 approve                         | #145        | `submission_confirm_page_test.dart:267` | 200 回操作に戻る                 |
| INV-156 | 部分失敗: 確定済み数・残り・failedNumber 表示          | #145        | `submission_confirmation_test.dart:132` | 2 問確定を隠す                   |
| INV-157 | AI 採点不可設問→humanScoreRequired で確定不可          | #118        | `submission_confirmation_test.dart:72`  | 承認不能設問を確定               |
| INV-158 | `review_reason` wire format パース                     | #122        | `submission_review_reason_test.dart:12` | 警告が誤設問/消失                |
| INV-159 | 未知 reason は推測せず空                               | #122        | `submission_queue_page_test.dart:117`   | 当てずっぽう警告                 |

---

## 10. DAG 失敗表示・採点障害

| ID      | 不変条件                                                         | 出どころ       | 根拠のテスト                              | 壊れると                 |
| ------- | ---------------------------------------------------------------- | -------------- | ----------------------------------------- | ------------------------ |
| INV-160 | 要確認と失敗でヘッダー要約文字列が異なる                         | #86            | `dependency_dag_panel_test.dart:503`      | INV-201-03               |
| INV-161 | パネル畳んでも失敗件数・次の一手・遷移ボタンが残る               | #86            | `dependency_dag_panel_test.dart:517`      | INV-201-03               |
| INV-162 | 下流「待ち」文言が上流理由（確認待ち vs 失敗で停止）で変わる     | #86            | `dependency_dag_panel_test.dart:551`      | INV-201-03               |
| INV-163 | `dagFailureGuidance`: 分類ごとに次の操作が変わる                 | #86            | `dag_failure_guidance_test.dart:22`       | 一律「待て」で操作不能   |
| INV-164 | 返す文言に last_error の断片（provider 名・URL・HTTP）が入らない | #86 / Security | `dag_failure_guidance_test.dart:72`       | 診断文漏えい             |
| INV-165 | 各分類で cause と nextStep が非空。nextStep は操作名指し         | #86            | `dag_failure_guidance_test.dart:103`      | INV-201-06               |
| INV-166 | crop_not_the_answer → 回答欄修正を促す（再判定を勧めない）       | #136           | `dag_failure_guidance_test.dart:55`       | 同じ誤画像で再判定ループ |
| INV-167 | GradingKickoffFailure: 409 は両可能性、404 は非 retry            | #80            | `grading_kickoff_test.dart:10`            | 誤った再試行 UX          |
| INV-168 | grading unavailable banner: unavailable のみ表示                 | #97            | `grading_unavailable_banner_test.dart:40` | 一時障害を設定不備と誤認 |

---

## 11. 回答欄エディタ（未検出・未割当・読み順）

| ID      | 不変条件                                                  | 出どころ | 根拠のテスト                       | 壊れると                     |
| ------- | --------------------------------------------------------- | -------- | ---------------------------------- | ---------------------------- |
| INV-170 | 未検出と未割当（absent）を別グループ表示                  | #164     | `answer_area_editor_test.dart:608` | INV-201-10                   |
| INV-171 | 該当グループのみ表示（片方だけのとき他方は出さない）      | #164     | `answer_area_editor_test.dart:625` | 空グループで混乱             |
| INV-172 | 全クリア表示は両グループ空のときのみ                      | #164     | `answer_area_editor_test.dart:640` | 未割当が残るのに「全部検出」 |
| INV-173 | absent グループは「見つけられなかった」表現（断定しない） | #167     | `answer_area_editor_test.dart:654` | 採点基準を探す無駄時間       |
| INV-174 | 画面に実測比率・件数・% を出さない                        | #164     | `answer_area_editor_test.dart:684` | 古い統計が残り誤解           |
| INV-175 | 出口アクションは該当チップの直上                          | #164     | `answer_area_editor_test.dart:706` | 「枠を引く」が脚注化         |
| INV-176 | absent のみのとき描画ターゲットは absent 設問             | #164     | `answer_area_editor_test.dart:730` | 出口が 1 クリック長い        |
| INV-177 | 読み順と設問番号が一致するとき警告なし                    | #171     | `answer_area_editor_test.dart:795` | 不要な警告                   |
| INV-178 | 読み順食い違い時は警告表示                                | #171     | `answer_area_editor_test.dart:773` | INV-201-10                   |

---

## 12. PDF 出力ダイアログ

| ID      | 不変条件                                      | 出どころ    | 根拠のテスト                          | 壊れると                     |
| ------- | --------------------------------------------- | ----------- | ------------------------------------- | ---------------------------- |
| INV-180 | 単体: progress→success + path                 | —           | `export_dialog_test.dart:70`          | 完了フィードバックなし       |
| INV-181 | `reuse_existing` は即 success                 | —           | `export_dialog_test.dart:100`         | 不要ポーリング               |
| INV-182 | 409 `unconfirmed_questions`→設問 id 一覧      | —           | `export_dialog_test.dart:119`         | 何を確定すべきか不明         |
| INV-183 | 409 `no_room_for_score`≠未確認文言            | #150        | `export_dialog_test.dart:141`         | 確定済みなのに「未確認」と嘘 |
| INV-184 | 未知 conflict code→sidecar message をそのまま | #150        | `export_dialog_test.dart:171`         | 誤った修復指示               |
| INV-185 | failed→retry で requeue                       | —           | `export_dialog_test.dart:195`         | 失敗から回復不能             |
| INV-186 | ポーリング transient failure は progress 維持 | —           | `export_dialog_test.dart:235`         | 一瞬断で failed 扱い         |
| INV-187 | cancelled job retry→新規 requestExport        | —           | `export_dialog_test.dart:272`         | キャンセル済みを再試行       |
| INV-188 | 一括: 全問確定のみ対象、除外は理由付き        | #142 / #137 | `bulk_export_test.dart:163`           | 押せるが必ず断られる         |
| INV-189 | 1 件 refused でも残り続行、失敗一覧           | #142        | `bulk_export_test.dart:252`           | 1 件で全停止                 |
| INV-190 | キュー行から export（レビュー画面経由不要）   | #137        | `submission_queue_page_test.dart:285` | 2 画面めくり必須             |

---

## 13. API クライアント

| ID      | 不変条件                                                         | 出どころ | 根拠のテスト                       | 壊れると           |
| ------- | ---------------------------------------------------------------- | -------- | ---------------------------------- | ------------------ |
| INV-200 | `/healthz` は bogus token でも OK                                | —        | `sidecar_api_client_test.dart:130` | health 設計誤解    |
| INV-201 | 正 token で protected API 成功                                   | —        | `sidecar_api_client_test.dart:140` | セッション確立失敗 |
| INV-202 | 誤 token→401 unauthorized                                        | —        | `sidecar_api_client_test.dart:153` | 認可バイパス       |
| INV-203 | 非 loopback URL→ArgumentError（URL/token を message に含めない） | Security | `sidecar_api_client_test.dart:307` | 資格情報漏えい     |
| INV-204 | unknown transport error→接続詳細なし                             | Security | `sidecar_api_client_test.dart:325` | 内部 URL 漏えい    |
| INV-205 | 409→`conflictCode` + `conflictQuestionIds` 保持                  | #150     | `sidecar_api_client_test.dart:357` | refusal 種別喪失   |

---

## 14. テストが無いまま実装だけが持っている保証（UG）

GitHub Issue [#216](https://github.com/HIKARU0627/Auto-Scoring/issues/216)。§1〜§13 は `app/test` を読んで書いた。
**`app/test` に無い保証は、その読み方では定義上こぼれる。** この区画は `app/lib` の側から掃いた結果である。

移行の完了条件は「`app/test` が固定している不変条件が新スタックのテストで固定されていること」（#201）。
実装だけが持っていてテストが無い保証は、この条件を満たしたまま黙って消える。PoC 7（[#203](https://github.com/HIKARU0627/Auto-Scoring/issues/203)、
[`poc-7-sidecar-lifecycle.md`](./poc-7-sidecar-lifecycle.md) §4）が Job Object を偶然踏んだので分かった。
**この区画は「偶然見つかる」を「数えてある」に変えるためにある。**

`INV-*` は `app/test` が根拠、`UG-*` は **`app/lib` の実装そのものが根拠**（Untested Guarantee）。
既存 170 件（INV-201-01〜10 / INV-001〜INV-205）の中身と番号はこの区画では一切変えていない。

### 14.1 掃き方と件数（再現手順）

| 指標                            |     値 | 備考                                                                     |
| ------------------------------- | -----: | ------------------------------------------------------------------------ |
| **掃いた `app/lib` ファイル数** | **63** | `app/lib/**/*.dart` 全件。`app/lib` に `.dart` 以外のファイルは無い      |
| 掃いた行数                      | 24,780 | 同上                                                                     |
| **候補として検討した数**        | **31** | 下の 6 本の grep のヒットを「保証の主張」単位に畳んだ数（§14.2 + §14.3） |
| **保証として認定した数**        | **15** | §14.2 の UG-01〜UG-15                                                    |
| 検討したが認定しなかった数      |     16 | §14.3。理由を1件ずつ書いてある                                           |

**候補の出し方**（`app/lib` を対象に、この 6 本を実行して重複を畳んだ）。
**測った時点:** `origin/main` = `7e45b20`（`app/lib` / `app/test` は本 PR で1行も変えていない。
本 PR の変更は `docs/` の 2 ファイルだけ）。ヒット数は GNU grep 3.11 と ugrep 7.8.4 の両方で同じ値を得ている:

```bash
cd app  # 以下すべて lib/ を対象にする

# G1 FFI                     -> 15 hits / 1 file
grep -rn "dart:ffi\|DynamicLibrary\|lookupFunction\|package:ffi\|Pointer<\|calloc\|malloc" lib
# G2 プラットフォーム分岐    -> 6 hits / 4 files
grep -rn "Platform\.\(isWindows\|isLinux\|isMacOS\|operatingSystem\|environment\|pathSeparator\|resolvedExecutable\)" lib
# G3 条件付き import / *_io  -> 0 hits / ファイル名は 1 件（core/sidecar_platform_io.dart）
grep -rn "if (dart.library" lib; find lib -name '*_io.dart' -o -name '*_web.dart' -o -name '*_stub*.dart'
# G4 OS リソース             -> 8 hits / 2 files
grep -rn "Process\.\|\.kill(\|RandomAccessFile\|\.lock(\|ServerSocket\|Socket\.\|HttpServer\|systemTemp\|createTemp(" lib
# G5 パス・フォント・ダイアログ -> 20 hits / 11 files
grep -rni "separator\|fontFamily\|FontLoader\|package:path\|FilePicker" lib
# G6 Windows を名指ししている箇所（コメント・文言込み）-> 49 hits / 8 files
grep -rn "Windows\|Win32\|kernel32\|\.exe\|%TEMP%\|LOCALAPPDATA\|taskkill" lib
# 参考: dart:io を import するファイルは 5 件だけ
grep -rl "import 'dart:io'" lib
```

**認定の判定**（候補1件ごとに次の 3 つをやった。3 つ目が要点で、`app/test` に名前が出てくるだけでは「固定されている」とは数えない）:

1. `app/test` を識別子で grep する（例: `grep -rn "ChildProcessGroup\|JobObject" app/test` → **0 件**）。
2. その実装がテストで**実際に走るか**、provider override やフェイクで**差し替えられて走らないか**を読む。
   （例: `folder_scan.dart` の `_scanDirectory` は `scanFolderProvider` が全テストで差し替えられるため一度も走らない）
3. その性質を実装から**取り除いたらテストが赤くなるか**を読む。ならないなら固定されていない。
   （例: `sidecar_supervisor_test.dart:239` は `expect(platform.elapsed, greaterThanOrEqualTo(sidecarStartupTimeout))` と
   定数を参照しているだけなので、60 秒を 5 秒に変えても赤くならない → UG-08）

**「他に無い」の範囲**: 上の 6 本の grep が拾わない保証は、この掃きでは見つからない。
純粋な Dart のビジネスルールで、かつ OS にもプラットフォーム分岐にも触れない保証は G1〜G6 に掛からない。
それらは §1〜§13（`app/test` 由来）が受け持つ。**この区画が主張する「無い」は、
「上の 6 本の grep が `app/lib` から拾った 31 件のうち、認定に至ったのは 15 件だけだった」という意味であって、
`app/lib` に他の保証が存在しないという意味ではない。**

### 14.2 認定した保証 15 件

「分類」は**テスト不能**（`flutter test` の届く範囲では固定できない）と**書き忘れ**（書けるのに書かれていない）を区別する。
書き忘れは移行先でも同じ理由で落ちるとは限らない ―― 移行先ではテストを書けるので、扱いが違う。

| ID    | 保証                                                                         | 根拠の実装                                                               | 分類         | 壊れると                                                              |
| ----- | ---------------------------------------------------------------------------- | ------------------------------------------------------------------------ | ------------ | --------------------------------------------------------------------- |
| UG-01 | アプリを強制終了してもサイドカーが道連れで終わる（Job Object kill-on-close） | `core/child_process_group.dart:39,167,199`                               | テスト不能   | 孤児が `app-data/.lock` を握り、次回起動が「すでに起動しています」    |
| UG-02 | kill-on-close を設定できなかった Job は持たない（保証が有るふりをしない）    | `core/child_process_group.dart:184`                                      | テスト不能   | 子を登録するが道連れにしない Job ができ、UG-01 が成立したように見える |
| UG-03 | Job ハンドルはプロセスの生涯閉じない（`dispose()` でも閉じない）             | `core/child_process_group.dart:159`, `core/sidecar_platform_io.dart:124` | テスト不能   | 後片付けのつもりの `close` が、動作中のサイドカーをその場で殺す       |
| UG-04 | 子プロセスは spawn の直後に Job へ登録する（孤児化の窓を最小にする）         | `core/sidecar_platform_io.dart:91`                                       | テスト不能   | 起動直後にアプリが落ちた場合だけ孤児が残る、再現しない不具合          |
| UG-05 | リリースビルドは起動ルートとテーマを環境変数から取らない                     | `main.dart:69`                                                           | テスト不能   | 出荷物の初期画面と配色を環境変数で外から変えられる                    |
| UG-06 | アプリは `app-data` の場所を決めない（`--app-data-dir` を渡さない）          | `main.dart:87`, `core/sidecar_supervisor.dart:162`                       | 書き忘れ     | 同じインストールに保存先が2つでき、過去の答案が消えたように見える     |
| UG-07 | 子プロセスの stdout/stderr を常にドレインする                                | `core/sidecar_platform_io.dart:140`                                      | 書き忘れ     | パイプが埋まってサイドカーが一括採点の途中で無言のまま止まる          |
| UG-08 | 起動タイムアウトは 60 秒 ―― Defender の初回スキャンを待てる長さ              | `core/sidecar_supervisor.dart:30`                                        | テスト不能   | 初回起動だけタイムアウトし、インストール直後に必ず失敗する            |
| UG-09 | 一括出力は既存ファイルを絶対に上書きしない（`_2`, `_3` へ逃がす）            | `core/bulk_export_writer.dart:34`                                        | 書き忘れ     | 講師が受け取り済みの添削 PDF を黙って消す（業務ルール §2 (15) 違反）  |
| UG-10 | フォルダ走査は隠しファイルと OS メタデータを除き、5,000 件で打ち切る         | `core/folder_scan.dart:63,70,95,99`                                      | 書き忘れ     | ホーム全体を選ばれた時に全ファイルをハッシュし、画面が返ってこない    |
| UG-11 | 走査が返す `relativePath` は常に `/` 区切り（Windows の `\` を潰す）         | `core/folder_scan.dart:104`                                              | テスト不能   | Windows でだけグルーピングと突き合わせが崩れる                        |
| UG-12 | 走査はファイル内容を外に出さない（ダイジェストだけ、しかもストリーム読み）   | `core/folder_scan.dart:108`                                              | 書き忘れ     | 実答案の中身がプラン要求に載る／数百 MB を一度に載せて落ちる          |
| UG-13 | 長いファイル名がファイル選択ボタンを画面外へ押し出さない                     | `core/widgets/app_file_picker_row.dart:52`                               | 書き忘れ     | Windows の長い名前を選んだ後、選び直すボタンに手が届かない            |
| UG-14 | 失敗画面が指すログの場所が、サイドカーが実際に書く場所と一致している         | `features/startup/startup_gate.dart:122`                                 | 併記（下記） | 「ここを見ろ」と言われた場所に何も無く、調査がそこで止まる            |
| UG-15 | 待たせるときは、待つ理由（初回マイグレーションと Defender スキャン）を出す   | `features/startup/startup_gate.dart:87`                                  | 書き忘れ     | 数十秒の初回起動が「ハングした」に見え、強制終了される（→ UG-01）     |

#### 認定した各件 ―― なぜテストが無いのか / 移行先で何をすれば守れるのか

**UG-01 強制終了時のサイドカー自動回収（第1号）**
`dart:ffi` から `kernel32.dll` の `CreateJobObjectW` / `SetInformationJobObject` /
`OpenProcess` / `AssignProcessToJobObject` を呼び、`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` を立てた
Job にサイドカーを入れている。アプリがどう死んでも OS がハンドルを閉じ、カーネルが子を回収する。

- **なぜテストが無いのか: テスト不能。** 検証には「アプリを `taskkill /F` して、子が消えたことを見る」という
  Windows 実機の操作が要る。`flutter test` は Linux でも走るうえ、テストプロセス自身を殺す形の検査は書けない。
  `app/test` 全体で `ChildProcessGroup` / `JobObject` への参照は 0 件（実測、`grep -rn` ）。
- **移行先で何をすれば守れるのか:** 素の Node.js `child_process` にこの機構は無い（PoC 7 §4 の表 1 行目）。
  Electron 側では次のどちらかを実装したうえで、**Windows 実機で「強制終了 → 再起動が成功する」を確認する**。
  (a) `node-addon-api` / FFI で `AssignProcessToJobObject` を呼ぶ、
  (b) Python サイドカーに親プロセス監視（stdin の EOF 検知、または親 PID の待機）を足して自律終了させる。
  (b) が PoC 7 §5.4 の推奨で、担当は backend 側（本 Issue のスコープ外）。
  どちらを採っても、**確認は自動テストではなく Windows 実機の手順**になる ―― だから
  [`frontend-migration.md`](./frontend-migration.md) の cut-over 条件に必須条件として入れた。

**UG-02 kill-on-close を設定できなかった Job は持たない**
`SetInformationJobObject` が失敗したら Job ハンドルを閉じて `null` を返す。子を登録しない。

- **なぜテストが無いのか: テスト不能。** `SetInformationJobObject` を失敗させるには Win32 の呼び出しを
  差し替える必要があり、`WindowsJobObject` は `kernel32.dll` を直に開く（コンストラクタ以外に注入口が無い）。
- **移行先で何をすれば守れるのか:** 「Job の作成に失敗したら Job 無しで続ける」を明示的に書く。
  **Job を作ったが limit を設定できなかった状態のまま子を登録してはいけない** ―― UG-01 が成立していないのに
  成立して見える状態が一番危ない。移行先では Job 作成を1つの関数に閉じ込め、
  戻り値を `JobHandle | null` にして「半端な Job」を型で表現できなくする。

**UG-03 Job ハンドルを生存中に閉じない**
ハンドルを閉じることこそが子を殺す操作なので、閉じてよいのはプロセス終了時の暗黙の close だけ。
`SidecarPlatformIo.dispose()` が probe クライアントは閉じるのに Job は閉じないのは、この理由による。

- **なぜテストが無いのか: テスト不能。** 「閉じていないこと」の否定形で、しかも観測は Windows 実機でしかできない。
  なお否定形のアサーションは、起こす側が消えても赤くならない（`app/test` 側にも同種の注意がある）。
- **移行先で何をすれば守れるのか:** Job ハンドルをライフサイクル管理（`dispose` / `close` / `unref` の連鎖）の
  対象に**入れない**。テストで守るなら「`dispose()` を呼んだ後もサイドカーが生きている」を
  Playwright (Electron) の実プロセス試験として書ける ―― これは移行先では**テスト可能になる**。

**UG-04 spawn の直後に Job へ登録する**
`Process.start` の戻り直後に `adopt(pid)` を呼ぶ。Windows の完全な答えは `CREATE_SUSPENDED` →
登録 → `resume` だが `dart:io` はそれを出さないので、残る窓は数マイクロ秒。

- **なぜテストが無いのか: テスト不能。** 窓の大きさは競合状態であり、`flutter test` で再現も観測もできない。
- **移行先で何をすれば守れるのか:** `spawn` と登録を**同じ関数の中で隣り合わせに置く**（間に `await` を入れない）。
  ネイティブアドオンを採るなら、Node の `child_process` にも `CREATE_SUSPENDED` 相当は無いので窓は残る。
  窓を消したいなら (b) の親プロセス監視のほうが強い ―― サイドカー自身が親の死を見るので、
  登録が間に合ったかどうかに依存しない。

**UG-05 リリースビルドは起動ルートとテーマを環境変数から取らない**
`AUTO_SCORING_INITIAL_ROUTE` / `AUTO_SCORING_THEME` は `kDebugMode` でコンパイル時に閉じてある。
スクリーンショット撮影スクリプト（`scripts/screenshot-linux-app.sh`）だけのための口である。

- **なぜテストが無いのか: テスト不能。** `flutter test` は常に debug で走るので `kDebugMode` は常に `true`。
  「リリースでは読まない」側の分岐をテストから踏む方法が無い。実装のコメント自身が
  「リリースビルドから分岐が*除去される*ことは測っていない。保証しているのは*通らない*ことだけ」と断っている。
- **移行先で何をすれば守れるのか:** 同じ口を `app.isPackaged`（Electron）1箇所で閉じ、
  **packaged ビルドを Playwright (Electron) で起動して環境変数が効かないことを確認する**。
  移行先では**テスト可能になる**（Playwright は packaged アプリを起動できる）ので、テストを書くこと。

**UG-06 アプリは `app-data` の場所を決めない**
`buildSidecarSupervisor()` は `appDataDirectory` を渡さない。保存先の定義はサイドカー側
（`auto_scoring.api.sidecar.default_app_data_dir`）1箇所だけ、というのがこの保証。

- **なぜテストが無いのか: 書き忘れ。** supervisor の側（引数を渡さなければ `--app-data-dir` を付けない）は
  `sidecar_supervisor_test.dart:58` が固定している。固定されていないのは**本番の合成ルート**のほうで、
  `buildSidecarSupervisor` は `app/test` から一度も呼ばれていない（実測: 参照 0 件）。
- **移行先で何をすれば守れるのか:** Electron では `app.getPath('userData')` が手元にあるので、
  **それを渡したくなる**のがこの保証の落とし穴。渡さない。テストは
  「本番の起動引数に `--app-data-dir` が含まれない」を main プロセスの単体テストで固定できる ―― 書くこと。

**UG-07 子プロセスの stdout/stderr を常にドレインする**
読まれないパイプが埋まると、子は次の書き込みでブロックする。uvicorn のアクセスログなら数百リクエストで到達する。
症状は「一括採点の途中でサイドカーが無言のまま止まる」。

- **なぜテストが無いのか: 書き忘れ。** 実プロセスを使えば書ける（`sidecar_supervisor_integration_test.dart` は
  すでに実サイドカーを起動している）。パイプを埋めるだけの出力を出す子を起動して、
  一定時間後も応答することを見ればよい。単に書かれていない。
- **移行先で何をすれば守れるのか:** `child.stdout` / `child.stderr` に必ず consumer を付ける
  （`'data'` ハンドラ、またはログファイルへの pipe）。`stdio: 'ignore'` にしてしまうと保証は
  「たまたま」満たされるが、後でログを取りたくなって `'pipe'` に戻した瞬間に壊れる。
  **テストを書くこと** ―― 移行先でも同じ理由（実プロセスが要る）で面倒だが、不可能ではない。

**UG-08 起動タイムアウト 60 秒**
初回起動は遅い。全 Alembic マイグレーションが走り、Windows Defender が未署名の実行ファイル木を初回スキャンする。
`app/test/sidecar_api_client_test.dart` のコメントが、GitHub ホストの Windows ランナーで
1分近い起動を記録したと書いている。

- **なぜテストが無いのか: テスト不能（値の側）。** タイムアウトの*振る舞い*は
  `sidecar_supervisor_test.dart:239` がフェイク時計で固定しているが、そこは
  `expect(platform.elapsed, greaterThanOrEqualTo(sidecarStartupTimeout))` と**定数を参照している**だけなので、
  60 秒を 5 秒に変えてもテストは赤くならない。値そのものの妥当性は Windows 実機の初回起動でしか測れない。
- **移行先で何をすれば守れるのか:** タイムアウト値と**その根拠**（Defender 初回スキャン＋初回マイグレーション）を
  1箇所に定数＋コメントで置き、cut-over 前に **Windows 実機の初回起動を1回測る**。
  「起動が遅いから縮めよう」は初回起動を必ず壊す変更になる。

**UG-09 一括出力は既存ファイルを上書きしない**
`_freePath` が既存名を避けて `_2`, `_3` と番号を足す。上書きは、講師が既に受け取った添削 PDF を黙って消すこと。
業務ルール §2 (15)「過去の出力を上書きしない」に真っ向から反する。

- **なぜテストが無いのか: 書き忘れ。** `dart:io` と一時ディレクトリだけで書ける純粋な関数で、
  ネイティブ依存もプラットフォーム分岐も無い。`core/bulk_export_writer.dart` は
  **`app/test` のどのファイルからも import されていない**（実測: 参照 0 件）。
  `bulk_export_test.dart` が固定しているのは畳み方のほうで、書き出しは `bulk_export_dialog.dart` が
  `writeFile` を差し替えられるようにしてあるため、実装は一度も走らない。
- **移行先で何をすれば守れるのか:** 同じ「番号を足して逃がす」を移植し、
  **Vitest で一時ディレクトリを使って固定する**（同名を3回書いて `x.pdf`, `x_2.pdf`, `x_3.pdf` になること）。
  移行先ではテストが書けるので、必ず書くこと。なお `existsSync` → `writeAsBytes` は TOCTOU を含むが、
  1人の利用者が1つのウィンドウから出力する前提なので、現状は実害として扱っていない
  （移行先で `wx` フラグの排他作成にできるなら、そのほうが強い）。

**UG-10 隠しファイル・OS メタデータの除外と 5,000 件の上限**
`.` 始まり、`.DS_Store` / `thumbs.db` / `desktop.ini` を除く。5,000 件を超えたら
`FolderTooLargeException` で打ち切る（実際の1バッチは約70件）。上限が無いと、
うっかりホームディレクトリを選ばれた瞬間に全ファイルをハッシュし始める。

- **なぜテストが無いのか: 書き忘れ。** 一時ディレクトリを作れば書ける。
  `_scanDirectory` は `scanFolderProvider` 経由でしか使われず、`app/test` は**全箇所でこれを差し替える**
  （`intake_page_test.dart:152,1027,2009,2090`）ので、実装は一度も走らない。
  `FolderTooLargeException` / `maxScannedFiles` への参照は `app/test` に 0 件。
- **移行先で何をすれば守れるのか:** 除外セットと上限を移植し、**Vitest で一時ディレクトリに実ファイルを置いて固定する**。
  `desktop.ini` / `thumbs.db` は Windows がフォルダを開くだけで作るので、除外を落とすと
  「頼んでいない資料が確認画面に出る」が Windows でだけ起きる。

**UG-11 `relativePath` は常に `/` 区切り**
`p.relative(...).replaceAll(r'\', '/')`。Windows の `p.relative` は `\` を返すが、
この値はサイドカーへ渡ってグルーピングと突き合わせのキーになる。

- **なぜテストが無いのか: テスト不能（今の実装の形では）。** `folder_scan.dart` は
  `package:path` をグローバルコンテキストで使うので、Linux の `flutter test` からは
  `\` を返す `p.relative` を再現できない。`p.Context(style: Style.windows)` を注入する形に
  実装を変えれば書けるが、**本 Issue は `app/lib` を1行も変えない**ので、その変更はしていない。
- **移行先で何をすれば守れるのか:** パス正規化を `path.win32` / `path.posix` を**明示的に選べる関数**に切り出し、
  Windows スタイルの入力を渡す Vitest を書く（Linux の CI でも走る）。
  移行先では**テスト可能になる** ―― 切り出しさえすれば、実機は要らない。

**UG-12 走査はファイル内容を外に出さない**
バイト列はダイジェストを取るためだけに読み、捨てる。しかも `entity.openRead()` のストリームに
`sha256.bind` で流すので、答案 PDF を丸ごとメモリに載せない。サイドカーへ送るのは一覧だけ。

- **なぜテストが無いのか: 書き忘れ。** UG-10 と同じ理由（実装が一度も走らない）。
  ダイジェストが既知の値と一致すること、要求本文にバイト列が載らないことは、どちらも書ける。
- **移行先で何をすれば守れるのか:** ハッシュ計算をストリーム（`createReadStream` → `crypto.createHash`）で行い、
  **要求に載せるのは一覧だけ**という境界を1つの関数に閉じる。
  `readFileSync` で済ませたくなるが、それは (1) 数百 MB のバッチで落ちる (2)
  内容がメモリと（下手をすると）ログに載る、の2つを同時に招く。Vitest で「送信本文に内容が含まれない」を固定すること。
  実データを fixture に持ち込まないこと（[`frontend-migration.md`](./frontend-migration.md) §6）。

**UG-13 長いファイル名がボタンを押し出さない**
ファイル名の `Text` に `overflow: TextOverflow.ellipsis` が付いている。実装のコメントが
「長い Windows ファイル名がボタンを画面外へ押し出してはならない」と理由を書いている。

- **なぜテストが無いのか: 書き忘れ。** ウィジェットテストで書ける
  （狭い surface に長い名前を渡して overflow が出ないことを見る）。
  `AppFilePickerRow` は **`app/test` のどこからも参照されていない**（実測: 参照 0 件）。
  `app/test` 全体で `TextOverflow` / `ellipsis` へのアサーションも 0 件。
- **移行先で何をすれば守れるのか:** CSS の `text-overflow: ellipsis` + `min-width: 0`（flex 子は既定で縮まないので
  これが要る）。React Testing Library では省略の見た目は測れないので、
  **Playwright で狭い幅にしてボタンが可視・クリック可能であることを固定する**のが確実。
  §3 の INV-016（狭幅 700×720 でも出口ボタンが押せる）と同じ検査の仲間として扱うとよい。

**UG-14 失敗画面が指すログの場所**
`ログ: %LOCALAPPDATA%\Auto-Scoring\app-data\logs\sidecar.log` が
`startup_gate.dart` にリテラルで埋まっている。エラー画面は例外文もパスも token も出さない代わりに、
この1行だけを出して「詳しくはここ」と言う。

- **なぜテストが無いのか: 2つに分かれる。**
  - **文言が出ること: 書き忘れ。** `startup_gate_test.dart` は `executableMissing` の詳細行
    （`インストーラーから再インストールしてください。`）は固定しているが、
    それ以外の3つの失敗が取る `ログ:` の枝は固定していない（`app/test` に `ログ:` / `LOCALAPPDATA` の参照 0 件）。
  - **その場所が実際にログのある場所と一致すること: テスト不能。** 一致の相手はバックエンドの
    `default_app_data_dir` であり、`flutter test` からは見えない。UG-06 とは表裏（アプリは場所を決めないのに、
    場所を文字列として知っている）。
- **移行先で何をすれば守れるのか:** リテラルをやめ、**サイドカーに実際のログパスを言わせる**
  （handshake か `/healthz` の応答に載せる、あるいは既存の起動ログから読む）。
  そうすれば「一致」はテストではなく構造で保証される。それができないうちは、
  文言が出ることだけでも Vitest で固定し、**cut-over 前に Windows 実機で実在を1回確認する**。

**UG-15 待たせる理由を出す**
スプラッシュに `初回起動には時間がかかることがあります。` を出す。UG-08 の 60 秒を、利用者の側から見た形にしたもの。
実装のコメントいわく「これが『まだ動いている』と『固まった』の違いになる」。

- **なぜテストが無いのか: 書き忘れ。** `startup_gate_test.dart:43` は
  `バックエンドを起動しています…` は固定しているが、この一行は固定していない（参照 0 件）。ウィジェットテストで書ける。
- **移行先で何をすれば守れるのか:** 同じ文言をスプラッシュに置き、**Vitest / RTL で固定する**。
  これを落とすと、初回起動の数十秒（UG-08）が「ハングした」に見え、利用者はタスクマネージャーから
  強制終了する ―― つまり **UG-01 を踏む経路を、こちらの手で増やすことになる。**

### 14.3 候補として検討し、認定しなかった 16 件

| #   | 候補                                                                      | 根拠の実装                            | 認定しなかった理由                                                                                                              |
| --- | ------------------------------------------------------------------------- | ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| 1   | `OpenProcess` の権限は `PROCESS_TERMINATE\|PROCESS_SET_QUOTA` だけ        | `core/child_process_group.dart:62`    | 監査上の作法であって利用者に見える保証ではない。狭すぎれば `adopt` がその場で失敗し UG-01 の確認で露見する                      |
| 2   | Job は無名（第2インスタンスが名前で開いて参加できない）                   | `core/child_process_group.dart:163`   | Node/Electron 側は Job 名を付ける API をそもそも通らない。UG-01 の再現手順（強制終了→再起動）で同時に守られる                   |
| 3   | `JOBOBJECT_EXTENDED_LIMIT_INFORMATION` の 144 バイト ABI と offset 16     | `core/child_process_group.dart:92`    | 誤れば UG-01 が成立しないので、UG-01 の Windows 実機確認が同じ1回で覆う。独立した保証として数えると二重計上になる               |
| 4   | `WindowsJobObject` は全プラットフォームでコンパイル・解析される           | `core/child_process_group.dart:125`   | `flutter analyze` と `flutter test` がすでに固定している（Linux でも型検査は通る）。テストが無い保証ではない                    |
| 5   | 非 Windows では no-op（POSIX プロセスグループを作らない）                 | `core/child_process_group.dart:45`    | 意図的な非実装であり保証ではない。配布対象は Windows のみ（`technology-stack.md` §7-1）                                         |
| 6   | handshake は `%TEMP%` 配下に作り、読み取り後にディレクトリごと消す        | `core/sidecar_platform_io.dart:47,71` | `sidecar_supervisor_integration_test.dart:91` が実プロセスで固定している（`_handshakeDirectories()`）。INV-038 / INV-045 の範囲 |
| 7   | `Process.kill()` は Windows で `TerminateProcess`（graceful path が無い） | `core/sidecar_supervisor.dart:344`    | 安全性の根拠（WAL・アトミック書き込み・起動時修復）は backend 側にあり、本 Issue のスコープ外。解放の観測は INV-045             |
| 8   | サイドカー実行ファイルの探索順（bundle → venv、`.exe` / `Scripts`）       | `core/sidecar_paths.dart:42`          | INV-042 / INV-043 が固定済み。環境値を全部引数で受ける設計なので Linux から Windows 配置を検査できている                        |
| 9   | `_parentDirectory` は `/` と `\` の両方を区切りとして受ける               | `core/sidecar_paths.dart:91`          | 純粋な文字列処理で、`sidecar_paths_test.dart` の Windows / POSIX 両グループが実質的に覆っている                                 |
| 10  | ネイティブ PDF ピッカーの拡張子フィルタ（`allowedExtensions: ['pdf']`）   | `core/pdf_file_picker.dart:19`        | 破れても後段（サイドカー）が拒否し、利用者にはエラーとして見える。黙って失われる保証ではない                                    |
| 11  | ネイティブフォルダピッカー（`getDirectoryPath()`）                        | `core/folder_scan.dart:85`            | プラットフォームチャネルの薄い委譲。保証の中身は UG-10 / UG-11 / UG-12 側にある                                                 |
| 12  | Noto Sans JP をバンドルし、`fontWeight` が可変軸に乗る                    | `core/design/app_typography.dart:27`  | `app_typography_test.dart` が**実フォントファイルを測って**固定している。テストが無い保証ではない                               |
| 13  | pdfrx / pdfium のネイティブライブラリ解決とキャッシュ先                   | （`app/lib` に該当実装が無い）        | パッケージ側の責務で、`app/lib` は初期化コードを1行も持たない。表示方式は PoC 6（#202）の決定に従う                             |
| 14  | loopback 以外の URL を拒否し、エラーに URL / token を載せない             | `api/sidecar_api_client.dart`         | INV-203 / INV-204 が固定済み                                                                                                    |
| 15  | `didRequestAppExit` でウィンドウを閉じる前に `shutdown()`                 | `main.dart:189`                       | INV-031 が固定済み。**強制終了の側**（テスト不能な異常系）だけを UG-01 として切り出した                                         |
| 16  | 二重起動は exit code 3 →「すでに起動しています」画面                      | `core/sidecar_supervisor.dart:36`     | INV-034 / INV-040 が固定済み。PoC 7 §4 でも Electron で完全再現可能と実測されている                                             |

### 14.4 この区画の使い方

1. **`UG-*` も引き取りの対象である。** 画面・機構を移植する PR は、関係する `INV-*` と同じように
   `UG-*` を PR 本文に列挙し、何で守るか（テストか、Windows 実機の手順か）を書く。
2. **分類が「書き忘れ」の 7 件（UG-06 / 07 / 09 / 10 / 12 / 13 / 15）と UG-14 の文言部分は、移行先ではテストを書く。**
   Flutter で書かれなかった理由は「面倒だった」以上のものではなく、移行先に同じ穴を持ち込む理由にはならない。
3. **分類が「テスト不能」の 7 件（UG-01〜05 / 08 / 11）と UG-14 の一致部分のうち、
   UG-03 / UG-05 / UG-11 は移行先では*テスト可能になる*。** 残り（UG-01 / 02 / 04 / 08 と UG-14 の一致部分）は
   Windows 実機の確認に落ちる ―― だから [`frontend-migration.md`](./frontend-migration.md) の
   cut-over 条件に「強制終了しても次回の起動が失敗しないこと」を必須条件として入れた。
4. **この一覧も網羅の終点ではない。** §14.1 の「無い」は、6 本の grep が `app/lib` から拾った 31 件についての話である。
   `app/lib` に手を入れるとき、あるいは移行先で新しい OS 境界（ファイルロック、ハンドル、ネイティブアドオン）に
   触れるときは、同じ 6 本を回して同 PR で本書を更新する。

---

## 15. Electron 移行時の使い方

1. **新画面・新コンポーネントを足す前に** §1 の INV-201 と §3 の INV-020 を確認する。
2. **画面移植 PR** は、その画面に関係する INV を Vitest/Playwright で再固定する。INV ID を PR 説明に書く。
   本一覧は各 PR が INV 番号で参照する正本であり、170 件を画面ごとの PR で積み上げて覆う運用の詳細は
   [`frontend-migration.md`](./frontend-migration.md) §3「不変条件の引き取りを PR で積み上げる」。
3. **`UG-*` も同じように引き取る。** §14 の 15 件は、テストが無いぶん INV より落ちやすい。
   引き取り方（テストで守るのか、Windows 実機の手順で守るのか）は §14.4。
4. **PoC 6（#202）完了後**、§5 の座標系 INV は選択した PDF 表示方式でも同じ許容誤差（0.004）で再検証する。
5. 本一覧は **網羅の終点ではない**。`app/test` にテストが増えたら同 PR で本書も更新する。
   `app/lib` の OS 境界（FFI・プラットフォーム分岐・ファイルロック・ハンドル・パス）に触れたときは §14.1 の grep を回す。

関連: [`frontend-migration.md`](./frontend-migration.md)、[`design-tokens.md`](./design-tokens.md)、[`mvp-acceptance.md`](./mvp-acceptance.md) §1（フロント検証の対応表）。

---

## 16. 不変条件 185 件の画面・基盤割り当て表（Phase 3 準備）

GitHub Issue [#229](https://github.com/HIKARU0627/Auto-Scoring/issues/229)（親 [#201](https://github.com/HIKARU0627/Auto-Scoring/issues/201)）。
Phase 3（画面ごとの移植）に入る前に、本不変条件文書が定義する全 **185 件（INV 170 件 + UG 15 件）** を画面・共通基盤・引き取り済みに網羅的に割り当てた正本である。

### 16.1 本表の使われ方

1. **Phase 3 の各 Issue 起票時:** 担当画面の行を本表から抜き出し、Issue の受入条件に列挙する。起票者が毎回 185 件を精査し直す負担を解消する。
2. **画面移植 PR の作成時:** [`frontend-migration.md`](./frontend-migration.md) §3 の運用規約に従い、その画面が引き取った `INV-*` / `UG-*` 番号を PR 本文に明記し、対応する新スタックのテスト（Vitest / Playwright）や実機確認手順を示す。引き取らない項目があれば理由を付記する。
3. **表は網羅の終点ではない:** 移植の実装途中で「この INV は別の画面で引き取るべき」「画面固有ではなく共通基盤の責務だった」と判明した場合は、その画面の PR の中で本表を直接修正・同期する。

### 16.2 画面単位と `app/lib/features/` 実構造の突き合わせと修正理由

`docs/frontend-migration.md` §3 が挙げた Phase 3 の単位（取込、テスト設定（配点・回答欄エディタ）、答案キュー、添削レビュー、答案確定、設定、出力）と、現行 Flutter 実装（`app/lib/features/` および `app/lib/core/`）の実構造を突き合わせ、以下のとおり整理・修正した。

| 移行単位（Phase 3）                    | Flutter 実装の配置                                                                                                             | 突き合わせ結果と修正・整理の理由                                                                                                                                                                                                                                                                                                                                         |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **取込**                               | `features/intake/` (`intake_page.dart`)                                                                                        | **完全一致**。フォルダ選択、ファイル照合、概算費用、取込実行、採点起票を含む取込フロー全体を担当。                                                                                                                                                                                                                                                                       |
| **テスト設定（配点・回答欄エディタ）** | `features/test_registration/` (`test_settings_page.dart`, `answer_area_editor.dart`, `test_list_page.dart`)                    | **実構造に対応して細分化**。Flutter では 1 ディレクトリに同居しているが、不変条件の性質から (a) **テスト設定**（配点・設問登録・プロファイル確定 INV-110）と (b) **回答欄エディタ**（未検出・未割当・読み順の幾何キャンバス INV-170〜178, INV-201-10 の 10 件）の 2 責務が存在する。Issue 起票の粒度に合わせて追跡できるよう、表内では sub-unit として明示的に区別する。 |
| **答案キュー**                         | `features/review_queue/` (`submission_queue_page.dart`)                                                                        | **完全一致**。キューソート順、進行中答案の保持、進捗表示、キューからの確定画面遷移を担当。                                                                                                                                                                                                                                                                               |
| **添削レビュー**                       | `features/pdf_review/` (`pdf_review_page.dart`, `dependency_dag_panel.dart`, `confidence_badge.dart`, `answer_crop_view.dart`) | **分割（答案確定を分離）**。Flutter では `submission_confirm_page.dart` も同ディレクトリ内にあるが、添削レビュー（5,688 行）は PDF 幾何・描画・注釈・未読トラッキング・DAG 障害表示など極めて巨大なため、答案確定と分離した。                                                                                                                                            |
| **答案確定**                           | `features/pdf_review/submission_confirm_page.dart`                                                                             | **独立画面として分離**。添削レビューと同居していたが、未到達設問の確定不可（INV-201-01, INV-154）や一括確定・後回しフォーカス（INV-201-08, INV-155）を担う終端フローモーダルであり、PR をレビュー可能なサイズに保つため独立単位とした。                                                                                                                                  |
| **設定**                               | `features/settings/` (`settings_page.dart`, `api_key_tab.dart`)                                                                | **完全一致**。API キー設定・疎通確認を担当。                                                                                                                                                                                                                                                                                                                             |
| **出力**                               | `core/widgets/export_dialog.dart`, `bulk_export_dialog.dart`, `core/bulk_export.dart`, `core/bulk_export_writer.dart`          | **画面単位として格上げ**。Flutter ではキューとレビューの両方から呼ばれるため `core/` に置かれていたが、進捗・排他・リトライ・上書き防止（UG-09）を含む 12 件の不変条件を持つ完結した機能であり、Phase 3 の画面単位として扱うのが自然。                                                                                                                                   |
| **ホーム（補足）**                     | `features/home/` (`home_page.dart`, `home_dashboard.dart`)                                                                     | **Phase 2-4 にて先行移植**。Phase 3 ではなく Phase 2 の土台（ホーム画面 1 枚 + そのテスト）として計画されている。ホーム固有の不変条件（INV-048, INV-128, INV-129, INV-147〜150, INV-018）はホーム画面が引き取る。                                                                                                                                                        |
| **起動ゲート（補足）**                 | `features/startup/` (`startup_gate.dart`)                                                                                      | **共通基盤へ配置**。`features/` にあるが業務画面ではなく、サイドカープロセスの起動・監視・スプラッシュ・クラッシュオーバーレイであるため、「共通基盤: サイドカーライフサイクル・起動ゲート」として整理。                                                                                                                                                                 |

### 16.3 Phase 2 引き取り済み状況の突き合わせ（PR #220 / PR #225）

GitHub App API 経由（`./scripts/invoke-github-app-api.ps1`）で Phase 2 の先行 PR 本文・コメントを直接取得し、不変条件の引き取り実績を突き合わせた。

- **PR #220（Issue #217: desktop 骨格とテスト土台）:**
  - PR 本文およびコメントに `INV-*` / `UG-*` 番号の列挙は **0 件**。
  - `desktop/test/architecture.test.ts` により依存方向の土台は作られたが、不変条件の明示的な引き取り宣言は行われていない。
- **PR #225（Issue #222: デザイントークン CSS 変数 + Tailwind）:**
  - PR 本文「## 引き取った不変条件」に **7 件**が明記されている:
    1. `INV-201-09`: 無効ボタンのコントラストは計算で WCAG を満たす（`desktop/test/theme-contrast.test.ts`）
    2. `INV-090`: disabled ボタン: outline ≥3:1、label ≥4.5:1（同上）
    3. `INV-087`: 全 surface 段で onSurface/onSurfaceVariant ≥4.5:1（同上）
    4. `INV-088`: Material on/role ペア ≥4.5:1（同上）
    5. `INV-089`: status 色（attention/success/error）≥4.5:1 on surface（同上）
    6. `INV-093`: annotationMark は両テーマ同一・白紙 PDF 上 ≥4.5:1（同上）
    7. `INV-094`: dark onSurface contrast 7–13（白黒最大回避）（同上）
  - PR 本文「### 今回引き取らないもの（理由）」に列挙された項目（INV-080, INV-081, INV-082〜086, INV-091〜092, INV-095〜097）は未引き取りであることを確認し、本割り当て表において共通基盤等へ配分した。

### 16.4 集計と内訳（件数検証: 185 件 = INV 170 件 + UG 15 件）

185 件すべてに厳密な割り当て先と理由が存在する。内訳は以下のとおり。

#### 大区分別の内訳

| 大区分                                      | `INV-*` 件数 | `UG-*` 件数 | 合計件数 | 概要                                                            |
| ------------------------------------------- | -----------: | ----------: | -------: | --------------------------------------------------------------- |
| **画面（Phase 3 および Phase 2-4 ホーム）** |      **100** |       **4** |  **104** | 各業務画面の Issue/PR が引き取る不変条件                        |
| **共通基盤**                                |       **63** |      **11** |   **74** | ライフサイクル、ルーター、APIクライアント、共通コンポーネント等 |
| **引き取り済み（Phase 2-2 / PR #225）**     |        **7** |       **0** |    **7** | PR #225 にて新スタックのテストで固定済み                        |
| **合計**                                    |      **170** |      **15** |  **185** | **全 185 件と厳密に一致**                                       |

#### 画面別の内訳（計 104 件）

| 画面（引き取り Issue）           | `INV-*` | `UG-*` |   合計 | 主な対象・範囲                                                          |
| -------------------------------- | ------: | -----: | -----: | ----------------------------------------------------------------------- |
| **添削レビュー**                 |      35 |      0 | **35** | PDF描画・座標・注釈・確信度・未読トラッキング・DAG障害案内              |
| **取込**                         |      16 |      3 | **19** | 取込フロー・費用概算・アップロード規約・フォルダ走査安全性（UG-10〜12） |
| **出力**                         |      11 |      1 | **12** | 単体/一括出力ダイアログ・進捗・排他・既存ファイル上書き防止（UG-09）    |
| **答案キュー**                   |      11 |      0 | **11** | キュー順序・進捗表示・要確認理由・確定画面遷移                          |
| **回答欄エディタ**（テスト設定） |      10 |      0 | **10** | 未検出/未割当/読み順食い違いの表示・描画（INV-201-10, INV-170〜178）    |
| **ホーム**（Phase 2-4）          |       8 |      0 |  **8** | ホームダッシュボード進捗・次の答案遷移・旧文言排除・デバッグ非表示      |
| **答案確定**                     |       7 |      0 |  **7** | 未到達設問確定不可（INV-201-01, INV-154）・一括承認・誤確定防止         |
| **設定**                         |       1 |      0 |  **1** | API キー未設定時の検証ボタン無効化理由（INV-107）                       |
| **テスト設定**（テスト設定）     |       1 |      0 |  **1** | プロファイル保存・確定ボタンの無効理由包含関係（INV-110）               |

#### 共通基盤別の内訳（計 74 件）

| 共通基盤分類                             | `INV-*` | `UG-*` |   合計 | 画面に属さない理由の要約                                               |
| ---------------------------------------- | ------: | -----: | -----: | ---------------------------------------------------------------------- |
| **サイドカーライフサイクル・起動ゲート** |      18 |      9 | **27** | プロセス起動・監視・Job Object 自動回収・スプラッシュ待機案内          |
| **ナビゲーション・ルーティング**         |      10 |      1 | **11** | ルーター規約・パラメータデコード・全画面脱出検査・起動環境変数遮断     |
| **共通 UI コンポーネント**               |      10 |      1 | **11** | DisabledActionReason、AppErrorBanner、設問状態バッジ、ファイル選択行等 |
| **デザイントークン・アクセシビリティ**   |       8 |      0 |  **8** | トークン直接記述禁止 Lint、Noto Sans JP フォント同梱、テーマ型安全等   |
| **API クライアント**                     |       6 |      0 |  **6** | loopback 制限、セッション認証、エラー詳細保持等の通信基盤              |
| **操作要件・無効理由エンジン**           |       5 |      0 |  **5** | action_requirements 単一情報源ロジック・文言規約                       |
| **ドメインロジック・設問状態**           |       3 |      0 |  **3** | question_status による複数画面横断の設問状態一元判定                   |
| **アーキテクチャ・依存方向**             |       2 |      0 |  **2** | レイヤー間依存方向強制テスト（INV-001, INV-002）                       |
| **全体検証・文言検査**                   |       1 |      0 |  **1** | 廃止文言の全体回帰防止検査（INV-201-07）                               |

### 16.5 不変条件 185 件の画面・基盤割り当て一覧表

| ID         | 区分         | 引き取る画面 / 担当先                                                  | 不変条件 / 保証の概要                                                              | 割り当ての理由 / 画面に属さない理由 / 引き取りの根拠                                                                                                                     |
| ---------- | ------------ | ---------------------------------------------------------------------- | ---------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| INV-201-01 | 画面         | 添削レビュー（主）/ 答案確定（副）                                     | 見ていない判断材料で確定・承認できない                                             | 判断材料のスクロール・未読トラッキング（material_read_ranges）および設問承認制御は添削レビュー画面が主担当（答案確定の未到達確定不可 INV-154 と連動）                    |
| INV-201-02 | 画面         | 答案確定                                                               | 確信度（Confidence）から完了・確定を導かない                                       | 確信度にかかわらず全問の到達・確認を必須とする判定ロジック（core/submission_confirmation.dart）であり答案確定フローが引き取る                                            |
| INV-201-03 | 画面         | 添削レビュー                                                           | 失敗が要約から漏れない。パネルを畳んでも残る。下流の「待ち」と区別できる           | 添削レビュー画面内の常駐コンポーネント DependencyDagPanel における要約・折りたたみ表示の維持                                                                             |
| INV-201-04 | 共通基盤     | 共通基盤: 操作要件・無効理由エンジン                                   | 無効な操作には、無効条件そのものから導いた理由が必ず出る                           | 全画面横断の無効操作理由の単一情報源化エンジン（core/action_requirements.dart）および表示コンポーネントの契約                                                            |
| INV-201-05 | 共通基盤     | 共通基盤: ナビゲーション・ルーティング                                 | 画面を足したら「ホームへ戻れる」検査の対象か除外（理由付き）に必ず載る             | 全画面を対象にホーム脱出手段（BackOrHomeButton）の存在を強制するメタテスト（静的/結合検査）                                                                              |
| INV-201-06 | 画面         | 添削レビュー                                                           | 失敗文言は「何が起きたか」と「次に何ができるか」を両方持つ                         | 添削レビュー画面の DAG パネルに表示する失敗ガイダンス（原因＋次の操作の明示）                                                                                            |
| INV-201-07 | 共通基盤     | 共通基盤: 全体検証・文言検査（関連: ホーム、取込）                     | 廃止した文言が二度と現れない                                                       | 「模範解答 PDF」「画面はまだありません」などの旧仕様文言がアプリ全体に再発しないことを保証する横断検査                                                                   |
| INV-201-08 | 画面         | 答案確定                                                               | 別ボタンにフォーカスした Enter が確定を実行しない                                  | 答案確定画面におけるフォーカス別ボタン（後回し等）の Enter 誤確定防止                                                                                                    |
| INV-201-09 | 引き取り済み | 引き取り済み (Phase 2-2 / PR #225)                                     | 無効ボタンのコントラストは目視でなく計算で WCAG を満たす                           | PR #225（Issue #222 デザイントークン）にて CSS 変数 + Vitest (`desktop/test/theme-contrast.test.ts`: disabled outline/label コントラスト検査) で引き取り済み             |
| INV-201-10 | 画面         | 回答欄エディタ（Phase 3 テスト設定）                                   | 回答欄の未検出・未割当・読み順食い違いを原因別に見せる                             | 回答欄エディタ（answer_area_editor.dart）における未検出・未割当（absent）・読み順食い違いの原因別グループ表示                                                            |
| INV-001    | 共通基盤     | 共通基盤: アーキテクチャ・依存方向                                     | `api` 層は `core` / `features` を import しない                                    | レイヤー間依存方向（api→core←features, desktop: main/preload/renderer）を強制する静的テスト（特定画面に属さない）                                                        |
| INV-002    | 共通基盤     | 共通基盤: アーキテクチャ・依存方向                                     | `core` 層は `features` を import しない                                            | レイヤー間依存方向（api→core←features, desktop: main/preload/renderer）を強制する静的テスト（特定画面に属さない）                                                        |
| INV-003    | 画面         | 添削レビュー                                                           | 添削レビュー画面は `setState` 直呼び禁止。`_setStateIfMounted` 経由のみ            | 添削レビュー画面の非同期処理中アンマウント時の StateError 防止規約                                                                                                       |
| INV-004    | 共通基盤     | 共通基盤: 操作要件・無効理由エンジン                                   | 無効操作の判定と文言は `core/action_requirements.dart` の単一ソース                | 全画面の操作可否判定と理由文言を一元管理する中核モジュール（core/action_requirements.dart）                                                                              |
| INV-005    | 画面         | 答案確定                                                               | 答案確定可否は `core/submission_confirmation.dart` に置く                          | 答案確定可否の単一判定ロジック（core/submission_confirmation.dart）であり答案確定画面が直接引き取る                                                                      |
| INV-006    | 共通基盤     | 共通基盤: ドメインロジック・設問状態（関連: 添削レビュー、答案キュー） | 設問ステータスは `core/question_status.dart` で一元決定                            | レール・DAG・Inspector・キューで同一設問の状態を一元決定する横断ドメインロジック                                                                                         |
| INV-007    | 画面         | 答案キュー（関連: ホーム）                                             | レビューキュー順序は `core/review_queue.dart` で決定                               | レビューキューのソート順序・進行位置を決定するロジック（答案キュー画面が主担当）                                                                                         |
| INV-010    | 共通基盤     | 共通基盤: ナビゲーション・ルーティング                                 | `features/` 内で `go_router` の `.go()` / `.goNamed()` を使わない                  | 全画面を統括するルーター・画面遷移規約・スタック制御・パラメータデコード基盤                                                                                             |
| INV-011    | 共通基盤     | 共通基盤: ナビゲーション・ルーティング                                 | 画面間移動は `push` / `replace` / `pop` のみ                                       | 全画面を統括するルーター・画面遷移規約・スタック制御・パラメータデコード基盤                                                                                             |
| INV-012    | 共通基盤     | 共通基盤: ナビゲーション・ルーティング                                 | `AppRoutes` の各 location が対応 Widget を開く                                     | 全画面を統括するルーター・画面遷移規約・スタック制御・パラメータデコード基盤                                                                                             |
| INV-013    | 共通基盤     | 共通基盤: ナビゲーション・ルーティング                                 | パラメータ付き URL（`testId`, `submissionId`, `questionId`）が正しく decode される | 全画面を統括するルーター・画面遷移規約・スタック制御・パラメータデコード基盤                                                                                             |
| INV-014    | 画面         | 添削レビュー                                                           | 添削レビューは開く設問を URL で指定できる                                          | 添削レビュー画面への設問指定ディープリンク遷移機能                                                                                                                       |
| INV-015    | 共通基盤     | 共通基盤: ナビゲーション・ルーティング                                 | スタック空で開いた covered ルートすべてに `BackOrHomeButton` がある                | 全画面を対象とするホーム脱出手段（BackOrHomeButton）の存在・最小幅表示・キーボード操作性                                                                                 |
| INV-016    | 共通基盤     | 共通基盤: ナビゲーション・ルーティング                                 | 狭幅 700×720 でも出口ボタンが押せる                                                | 全画面を対象とするホーム脱出手段（BackOrHomeButton）の存在・最小幅表示・キーボード操作性                                                                                 |
| INV-017    | 共通基盤     | 共通基盤: ナビゲーション・ルーティング                                 | Tab→Enter のみでホームへ戻れる                                                     | 全画面を対象とするホーム脱出手段（BackOrHomeButton）の存在・最小幅表示・キーボード操作性                                                                                 |
| INV-018    | 画面         | ホーム（Phase 2-4）                                                    | ホーム自身には出口を出さない                                                       | ホーム画面自身には出口ボタン（戻る/ホーム）を表示しない画面固有仕様                                                                                                      |
| INV-019    | 共通基盤     | 共通基盤: ナビゲーション・ルーティング                                 | push で積んだ画面では出口は 1 枚戻る（ホーム直行ではない）                         | 全画面を統括するルーター・画面遷移規約・スタック制御・パラメータデコード基盤                                                                                             |
| INV-020    | 共通基盤     | 共通基盤: ナビゲーション・ルーティング                                 | 新ルート追加時、covered か skipped（理由付き）のどちらかに必ず登録                 | 全画面を統括するルーター・画面遷移規約・スタック制御・パラメータデコード基盤                                                                                             |
| INV-021    | 画面         | 答案キュー                                                             | 答案キュー行タップは答案確定画面を開く（設問ごと承認ではない）                     | 答案キュー行タップ時に答案確定画面を開く遷移制御（設問ごと承認画面ではない）                                                                                             |
| INV-030    | 共通基盤     | 共通基盤: サイドカーライフサイクル・起動ゲート                         | 起動中はスプラッシュ→ healthy 後にホーム表示                                       | サイドカープロセスの起動・監視・handshake・二重起動防止・パス解決・クラッシュオーバーレイ等の共通基盤                                                                    |
| INV-031    | 共通基盤     | 共通基盤: サイドカーライフサイクル・起動ゲート                         | ウィンドウ閉じる前に sidecar を kill                                               | サイドカープロセスの起動・監視・handshake・二重起動防止・パス解決・クラッシュオーバーレイ等の共通基盤                                                                    |
| INV-032    | 共通基盤     | 共通基盤: サイドカーライフサイクル・起動ゲート                         | 起動失敗時「再起動」でアプリ再起動なしに復旧                                       | サイドカープロセスの起動・監視・handshake・二重起動防止・パス解決・クラッシュオーバーレイ等の共通基盤                                                                    |
| INV-033    | 共通基盤     | 共通基盤: サイドカーライフサイクル・起動ゲート                         | push 済み画面の上でもクラッシュ overlay＋再起動が見える                            | サイドカープロセスの起動・監視・handshake・二重起動防止・パス解決・クラッシュオーバーレイ等の共通基盤                                                                    |
| INV-034    | 共通基盤     | 共通基盤: サイドカーライフサイクル・起動ゲート                         | 二重起動は「すでに起動しています」                                                 | サイドカープロセスの起動・監視・handshake・二重起動防止・パス解決・クラッシュオーバーレイ等の共通基盤                                                                    |
| INV-035    | 共通基盤     | 共通基盤: サイドカーライフサイクル・起動ゲート                         | 実行ファイル欠落→再インストール案内                                                | サイドカープロセスの起動・監視・handshake・二重起動防止・パス解決・クラッシュオーバーレイ等の共通基盤                                                                    |
| INV-036    | 共通基盤     | 共通基盤: サイドカーライフサイクル・起動ゲート                         | エラー画面に bearer token を描画しない                                             | サイドカープロセスの起動・監視・handshake・二重起動防止・パス解決・クラッシュオーバーレイ等の共通基盤                                                                    |
| INV-037    | 共通基盤     | 共通基盤: サイドカーライフサイクル・起動ゲート                         | handshake 未完成はリトライ、即失敗しない                                           | サイドカープロセスの起動・監視・handshake・二重起動防止・パス解決・クラッシュオーバーレイ等の共通基盤                                                                    |
| INV-038    | 共通基盤     | 共通基盤: サイドカーライフサイクル・起動ゲート                         | ready 後 handshake ファイル削除                                                    | サイドカープロセスの起動・監視・handshake・二重起動防止・パス解決・クラッシュオーバーレイ等の共通基盤                                                                    |
| INV-039    | 共通基盤     | 共通基盤: サイドカーライフサイクル・起動ゲート                         | 即 exit はタイムアウト待たず failed                                                | サイドカープロセスの起動・監視・handshake・二重起動防止・パス解決・クラッシュオーバーレイ等の共通基盤                                                                    |
| INV-040    | 共通基盤     | 共通基盤: サイドカーライフサイクル・起動ゲート                         | exit code 3 = alreadyRunning                                                       | サイドカープロセスの起動・監視・handshake・二重起動防止・パス解決・クラッシュオーバーレイ等の共通基盤                                                                    |
| INV-041    | 共通基盤     | 共通基盤: サイドカーライフサイクル・起動ゲート                         | shutdown は kill 後 crash 報告しない                                               | サイドカープロセスの起動・監視・handshake・二重起動防止・パス解決・クラッシュオーバーレイ等の共通基盤                                                                    |
| INV-042    | 共通基盤     | 共通基盤: サイドカーライフサイクル・起動ゲート                         | Windows: バンドル優先、venv fallback                                               | サイドカープロセスの起動・監視・handshake・二重起動防止・パス解決・クラッシュオーバーレイ等の共通基盤                                                                    |
| INV-043    | 共通基盤     | 共通基盤: サイドカーライフサイクル・起動ゲート                         | POSIX: `.exe` なし、`bin/` venv                                                    | サイドカープロセスの起動・監視・handshake・二重起動防止・パス解決・クラッシュオーバーレイ等の共通基盤                                                                    |
| INV-044    | 共通基盤     | 共通基盤: サイドカーライフサイクル・起動ゲート                         | 統合: 動的 port、token で保護 API 成功                                             | サイドカープロセスの起動・監視・handshake・二重起動防止・パス解決・クラッシュオーバーレイ等の共通基盤                                                                    |
| INV-045    | 共通基盤     | 共通基盤: サイドカーライフサイクル・起動ゲート                         | 統合: shutdown 後プロセス/port/lock 解放                                           | サイドカープロセスの起動・監視・handshake・二重起動防止・パス解決・クラッシュオーバーレイ等の共通基盤                                                                    |
| INV-046    | 共通基盤     | 共通基盤: サイドカーライフサイクル・起動ゲート                         | 統合: 外部 sidecar を survivor と誤認しない                                        | サイドカープロセスの起動・監視・handshake・二重起動防止・パス解決・クラッシュオーバーレイ等の共通基盤                                                                    |
| INV-047    | 共通基盤     | 共通基盤: サイドカーライフサイクル・起動ゲート                         | `sidecarStillServing`: 空 `[]` の 200 は alive                                     | サイドカープロセスの起動・監視・handshake・二重起動防止・パス解決・クラッシュオーバーレイ等の共通基盤                                                                    |
| INV-048    | 画面         | ホーム（Phase 2-4）                                                    | ホームに `backend: ok` 等デバッグ表示なし                                          | ホーム画面上にサイドカーのデバッグ表示を出さない画面固有仕様                                                                                                             |
| INV-050    | 画面         | 添削レビュー                                                           | 正規化座標→ピクセル変換（A4 縦・90°回転）                                          | PDF 描画・座標変換・注釈配置・OCRアンカー解決・未読トラッキング・確信度表示・設問編集 undo 等、添削レビュー画面の中核機能                                                |
| INV-051    | 画面         | 添削レビュー                                                           | ズーム 2× で overlay も 2× スケール                                                | PDF 描画・座標変換・注釈配置・OCRアンカー解決・未読トラッキング・確信度表示・設問編集 undo 等、添削レビュー画面の中核機能                                                |
| INV-052    | 画面         | 添削レビュー                                                           | explicit rect はそのまま使用                                                       | PDF 描画・座標変換・注釈配置・OCRアンカー解決・未読トラッキング・確信度表示・設問編集 undo 等、添削レビュー画面の中核機能                                                |
| INV-053    | 画面         | 添削レビュー                                                           | anchor_text → OCR box 解決（§12.3）                                                | PDF 描画・座標変換・注釈配置・OCRアンカー解決・未読トラッキング・確信度表示・設問編集 undo 等、添削レビュー画面の中核機能                                                |
| INV-054    | 画面         | 添削レビュー                                                           | crop 座標→page 座標変換（answer_area 経由）                                        | PDF 描画・座標変換・注釈配置・OCRアンカー解決・未読トラッキング・確信度表示・設問編集 undo 等、添削レビュー画面の中核機能                                                |
| INV-055    | 画面         | 添削レビュー                                                           | degenerate answer_area は full page 扱い                                           | PDF 描画・座標変換・注釈配置・OCRアンカー解決・未読トラッキング・確信度表示・設問編集 undo 等、添削レビュー画面の中核機能                                                |
| INV-056    | 画面         | 添削レビュー                                                           | OCR 改行付き anchor もマッチ                                                       | PDF 描画・座標変換・注釈配置・OCRアンカー解決・未読トラッキング・確信度表示・設問編集 undo 等、添削レビュー画面の中核機能                                                |
| INV-057    | 画面         | 添削レビュー                                                           | 複数 token は union rect                                                           | PDF 描画・座標変換・注釈配置・OCRアンカー解決・未読トラッキング・確信度表示・設問編集 undo 等、添削レビュー画面の中核機能                                                |
| INV-058    | 画面         | 添削レビュー                                                           | 最短 run が選ばれる                                                                | PDF 描画・座標変換・注釈配置・OCRアンカー解決・未読トラッキング・確信度表示・設問編集 undo 等、添削レビュー画面の中核機能                                                |
| INV-059    | 画面         | 添削レビュー                                                           | 長すぎる run は拒否（null）                                                        | PDF 描画・座標変換・注釈配置・OCRアンカー解決・未読トラッキング・確信度表示・設問編集 undo 等、添削レビュー画面の中核機能                                                |
| INV-060    | 画面         | 添削レビュー                                                           | 非連続 box は拒否                                                                  | PDF 描画・座標変換・注釈配置・OCRアンカー解決・未読トラッキング・確信度表示・設問編集 undo 等、添削レビュー画面の中核機能                                                |
| INV-061    | 画面         | 添削レビュー                                                           | anchor 未一致時 score_area に fallback しない                                      | PDF 描画・座標変換・注釈配置・OCRアンカー解決・未読トラッキング・確信度表示・設問編集 undo 等、添削レビュー画面の中核機能                                                |
| INV-062    | 画面         | 添削レビュー                                                           | ウィジェット: 正規化 (0.5,0.5) が pdfrx 実 render size で配置                      | PDF 描画・座標変換・注釈配置・OCRアンカー解決・未読トラッキング・確信度表示・設問編集 undo 等、添削レビュー画面の中核機能                                                |
| INV-063    | 画面         | 添削レビュー                                                           | 90° PDF でも同じ alignment                                                         | PDF 描画・座標変換・注釈配置・OCRアンカー解決・未読トラッキング・確信度表示・設問編集 undo 等、添削レビュー画面の中核機能                                                |
| INV-064    | 画面         | 添削レビュー                                                           | ターゲット無し annotation → 設問コメント欄                                         | PDF 描画・座標変換・注釈配置・OCRアンカー解決・未読トラッキング・確信度表示・設問編集 undo 等、添削レビュー画面の中核機能                                                |
| INV-065    | 画面         | 添削レビュー                                                           | 判断材料未読範囲 merge が NaN を出さない                                           | PDF 描画・座標変換・注釈配置・OCRアンカー解決・未読トラッキング・確信度表示・設問編集 undo 等、添削レビュー画面の中核機能                                                |
| INV-066    | 画面         | 添削レビュー                                                           | 行 covered = 0→1 全域到達で承認可能                                                | PDF 描画・座標変換・注釈配置・OCRアンカー解決・未読トラッキング・確信度表示・設問編集 undo 等、添削レビュー画面の中核機能                                                |
| INV-067    | 画面         | 添削レビュー                                                           | 判断材料が画面外のあいだ承認・Enter 不可。却下は可                                 | PDF 描画・座標変換・注釈配置・OCRアンカー解決・未読トラッキング・確信度表示・設問編集 undo 等、添削レビュー画面の中核機能                                                |
| INV-068    | 画面         | 添削レビュー                                                           | 高確信度に緑チェックを付けない（低のみ）                                           | PDF 描画・座標変換・注釈配置・OCRアンカー解決・未読トラッキング・確信度表示・設問編集 undo 等、添削レビュー画面の中核機能                                                |
| INV-069    | 画面         | 添削レビュー                                                           | blank answer 申告は本文に伴う                                                      | PDF 描画・座標変換・注釈配置・OCRアンカー解決・未読トラッキング・確信度表示・設問編集 undo 等、添削レビュー画面の中核機能                                                |
| INV-070    | 画面         | 添削レビュー                                                           | レール・DAG・Inspector で同一語・アイコン                                          | PDF 描画・座標変換・注釈配置・OCRアンカー解決・未読トラッキング・確信度表示・設問編集 undo 等、添削レビュー画面の中核機能                                                |
| INV-071    | 画面         | 添削レビュー                                                           | Issue #22: edit/reject/regrade/approve/undo 一連が通る                             | PDF 描画・座標変換・注釈配置・OCRアンカー解決・未読トラッキング・確信度表示・設問編集 undo 等、添削レビュー画面の中核機能                                                |
| INV-080    | 共通基盤     | 共通基盤: デザイントークン・アクセシビリティ                           | `lib/features/` に padding/gap/radius/elevation/icon/layout/色リテラル禁止         | 全画面のスタイル指定でトークン直接書き込みを禁止する静的 Lint 検査（PR #225 で画面移植時に追加と明記）                                                                   |
| INV-081    | 共通基盤     | 共通基盤: デザイントークン・アクセシビリティ                           | 主要 7 画面が light/dark 両テーマで surface ramp から背景                          | 全主要画面がテーマの surface ramp から背景色を取得することを検証する統合テスト（PR #225 保留）                                                                           |
| INV-082    | 共通基盤     | 共通基盤: デザイントークン・アクセシビリティ                           | Noto Sans JP variable（fvar、≥17000 glyphs）                                       | 全画面共通の Noto Sans JP フォント同梱・等幅数字・バリアブルフォント設定（PR #225 保留）                                                                                 |
| INV-083    | 共通基盤     | 共通基盤: デザイントークン・アクセシビリティ                           | 数字は等幅（点数更新で横ジャンプしない）                                           | 全画面共通の Noto Sans JP フォント同梱・等幅数字・バリアブルフォント設定（PR #225 保留）                                                                                 |
| INV-084    | 共通基盤     | 共通基盤: デザイントークン・アクセシビリティ                           | fontWeight が variable axis を駆動                                                 | 全画面共通の Noto Sans JP フォント同梱・等幅数字・バリアブルフォント設定（PR #225 保留）                                                                                 |
| INV-085    | 共通基盤     | 共通基盤: デザイントークン・アクセシビリティ                           | 全 text role が bundled family + height                                            | 全画面共通の Noto Sans JP フォント同梱・等幅数字・バリアブルフォント設定（PR #225 保留）                                                                                 |
| INV-086    | 共通基盤     | 共通基盤: デザイントークン・アクセシビリティ                           | 認識文字 role は body より大・letterSpacing>0                                      | 全画面共通の Noto Sans JP フォント同梱・等幅数字・バリアブルフォント設定（PR #225 保留）                                                                                 |
| INV-087    | 引き取り済み | 引き取り済み (Phase 2-2 / PR #225)                                     | 全 surface 段で onSurface/onSurfaceVariant ≥4.5:1                                  | PR #225（Issue #222 デザイントークン）にて Vitest (`desktop/test/theme-contrast.test.ts`: surface ramp onSurface/onSurfaceVariant ≥4.5:1) で引き取り済み                 |
| INV-088    | 引き取り済み | 引き取り済み (Phase 2-2 / PR #225)                                     | Material on/role ペア ≥4.5:1                                                       | PR #225（Issue #222 デザイントークン）にて Vitest (`desktop/test/theme-contrast.test.ts`: Material on/role ペア ≥4.5:1) で引き取り済み                                   |
| INV-089    | 引き取り済み | 引き取り済み (Phase 2-2 / PR #225)                                     | status 色（attention/success/error）≥4.5:1 on surface                              | PR #225（Issue #222 デザイントークン）にて Vitest (`desktop/test/theme-contrast.test.ts`: status 色 ≥4.5:1 on surface) で引き取り済み                                    |
| INV-090    | 引き取り済み | 引き取り済み (Phase 2-2 / PR #225)                                     | disabled ボタン: outline ≥3:1、label ≥4.5:1                                        | PR #225（Issue #222 デザイントークン）にて Vitest (`desktop/test/theme-contrast.test.ts`: disabled outline ≥3:1, label ≥4.5:1) で引き取り済み                            |
| INV-091    | 共通基盤     | 共通基盤: 共通UIコンポーネント                                         | Material 既定 disabled outline は AA 未達（上書き理由の実測）                      | 全画面共通ボタンコンポーネントの disabled スタイル・コントラスト保証（PR #225 保留）                                                                                     |
| INV-092    | 共通基盤     | 共通基盤: 共通UIコンポーネント                                         | filled/outlined/text 全 ButtonTheme が disabled 色を返す                           | 全画面共通ボタンコンポーネントの disabled スタイル・コントラスト保証（PR #225 保留）                                                                                     |
| INV-093    | 引き取り済み | 引き取り済み (Phase 2-2 / PR #225)                                     | annotationMark は両テーマ同一・白紙 PDF 上 ≥4.5:1                                  | PR #225（Issue #222 デザイントークン）にて Vitest (`desktop/test/theme-contrast.test.ts`: annotationMark 白紙 PDF 上 ≥4.5:1) で引き取り済み                              |
| INV-094    | 引き取り済み | 引き取り済み (Phase 2-2 / PR #225)                                     | dark onSurface contrast 7–13（白黒最大回避）                                       | PR #225（Issue #222 デザイントークン）にて Vitest (`desktop/test/theme-contrast.test.ts`: dark onSurface contrast 7-13) で引き取り済み                                   |
| INV-095    | 共通基盤     | 共通基盤: デザイントークン・アクセシビリティ                           | AppStatusColors / AppTextRoles extension 必須                                      | 状態色・テキストスタイルの型安全基盤（React ThemeContext / TypeScript 型定義）（PR #225 保留）                                                                           |
| INV-096    | 共通基盤     | 共通基盤: 共通UIコンポーネント                                         | AppErrorBanner: 再試行・busy 時 disable・1 回 fade-in で settle                    | 全画面で共通利用される AppErrorBanner コンポーネントの振る舞い（再試行・busy時 disable）                                                                                 |
| INV-097    | 共通基盤     | 共通基盤: 共通UIコンポーネント（関連: 添削レビュー、答案キュー）       | QuestionStatus: 各状態に固有 label+icon（色だけにしない）                          | 全画面で共通利用される設問状態バッジ（QuestionStatus）のアイコン・テキスト併記（アクセシビリティ）                                                                       |
| INV-100    | 共通基盤     | 共通基盤: 操作要件・無効理由エンジン                                   | 無効操作には理由 id が 1 件以上、有効時 0 件                                       | 全画面共通の操作要件判定エンジン（core/action_requirements.dart）の基本契約                                                                                              |
| INV-101    | 共通基盤     | 共通基盤: 操作要件・無効理由エンジン                                   | 理由文は「。」終わり・Exception/HTTP/数字なし                                      | 全画面共通の操作要件判定エンジン（core/action_requirements.dart）の基本契約                                                                                              |
| INV-102    | 共通基盤     | 共通基盤: 操作要件・無効理由エンジン                                   | busy は単独でも理由になる                                                          | 全画面共通の操作要件判定エンジン（core/action_requirements.dart）の基本契約                                                                                              |
| INV-103    | 画面         | 取込                                                                   | intake: template 未選択→`intake-template`                                          | 取込画面におけるテンプレート未選択時の取込ボタン無効化理由 ID                                                                                                            |
| INV-104    | 共通基盤     | 共通基盤: 共通UIコンポーネント                                         | 条件充足で理由消去＋高さ 0（余白残さない）                                         | 全画面共通の無効理由表示コンポーネント（DisabledActionReason）の表示・余白・アクセシビリティ仕様                                                                         |
| INV-105    | 共通基盤     | 共通基盤: 共通UIコンポーネント                                         | 理由は Tooltip ではなく visible Text                                               | 全画面共通の無効理由表示コンポーネント（DisabledActionReason）の表示・余白・アクセシビリティ仕様                                                                         |
| INV-106    | 共通基盤     | 共通基盤: 共通UIコンポーネント                                         | 狭幅 700×720 で理由が画面内                                                        | 全画面共通の無効理由表示コンポーネント（DisabledActionReason）の表示・余白・アクセシビリティ仕様                                                                         |
| INV-107    | 画面         | 設定                                                                   | API キー: 未設定→verify 無効+理由                                                  | 設定画面（API キー設定タブ）における検証ボタン無効化理由                                                                                                                 |
| INV-108    | 共通基盤     | 共通基盤: 共通UIコンポーネント                                         | helperText と disabled reason の二重表示禁止                                       | 全画面共通の無効理由表示コンポーネント（DisabledActionReason）の表示・余白・アクセシビリティ仕様                                                                         |
| INV-109    | 共通基盤     | 共通基盤: 共通UIコンポーネント                                         | Tab 順: 理由 Text は focus 取らず隣ボタン到達可能                                  | 全画面共通の無効理由表示コンポーネント（DisabledActionReason）の表示・余白・アクセシビリティ仕様                                                                         |
| INV-110    | 画面         | テスト設定（Phase 3 テスト設定）                                       | profile confirm 理由 ⊇ save 理由（部分集合）                                       | テストプロファイル設定画面（test_settings_page.dart）における保存・確定ボタンの無効理由包含関係                                                                          |
| INV-120    | 画面         | 取込                                                                   | 未確認 AI 提案がある間 import 不可                                                 | 取込画面（intake_page.dart / intake_review）のファイル照合・費用概算・取込実行・採点起票フロー                                                                           |
| INV-121    | 画面         | 取込                                                                   | 規則マッチファイルは AI 確認不要                                                   | 取込画面（intake_page.dart / intake_review）のファイル照合・費用概算・取込実行・採点起票フロー                                                                           |
| INV-122    | 画面         | 取込                                                                   | 既存テスト追記時は gradingCriteria 不要                                            | 取込画面（intake_page.dart / intake_review）のファイル照合・費用概算・取込実行・採点起票フロー                                                                           |
| INV-123    | 画面         | 取込                                                                   | 新規テストは criteria 必須                                                         | 取込画面（intake_page.dart / intake_review）のファイル照合・費用概算・取込実行・採点起票フロー                                                                           |
| INV-124    | 画面         | 取込                                                                   | 規則のみなら AI 分類 API 0 回                                                      | 取込画面（intake_page.dart / intake_review）のファイル照合・費用概算・取込実行・採点起票フロー                                                                           |
| INV-125    | 画面         | 取込                                                                   | 取込前に件数・概算費用表示                                                         | 取込画面（intake_page.dart / intake_review）のファイル照合・費用概算・取込実行・採点起票フロー                                                                           |
| INV-126    | 画面         | 取込                                                                   | 単価未設定時は費用を数字で言わない                                                 | 取込画面（intake_page.dart / intake_review）のファイル照合・費用概算・取込実行・採点起票フロー                                                                           |
| INV-127    | 画面         | 取込                                                                   | 完了画面は「採点できる」と言わない                                                 | 取込画面（intake_page.dart / intake_review）のファイル照合・費用概算・取込実行・採点起票フロー                                                                           |
| INV-128    | 画面         | ホーム（Phase 2-4）                                                    | 模範解答 PDF 要求文言なし                                                          | ホーム画面上の旧文言（模範解答PDF、採点マニュアルPDF）排除の検査                                                                                                         |
| INV-129    | 画面         | ホーム（Phase 2-4）                                                    | 「採点マニュアル PDF」旧呼び名なし                                                 | ホーム画面上の旧文言（模範解答PDF、採点マニュアルPDF）排除の検査                                                                                                         |
| INV-130    | 画面         | 取込                                                                   | 「画面はまだありません」文言なし                                                   | 取込画面（intake_page.dart / intake_review）のファイル照合・費用概算・取込実行・採点起票フロー                                                                           |
| INV-131    | 画面         | 取込                                                                   | 27 件目失敗でも前 26 答案残存                                                      | 取込画面（intake_page.dart / intake_review）のファイル照合・費用概算・取込実行・採点起票フロー                                                                           |
| INV-132    | 画面         | 取込                                                                   | 取込後 AI 採点起票経路を維持                                                       | 取込画面（intake_page.dart / intake_review）のファイル照合・費用概算・取込実行・採点起票フロー                                                                           |
| INV-133    | 画面         | 取込                                                                   | 起票失敗でも取込成功扱い+理由                                                      | 取込画面（intake_page.dart / intake_review）のファイル照合・費用概算・取込実行・採点起票フロー                                                                           |
| INV-134    | 画面         | 取込（副: 共通基盤: API クライアント）                                 | material role は wire name（`annotation_resource` 等）                             | 取込画面の資料アップロード API 通信規約（material role, content-type）                                                                                                   |
| INV-135    | 画面         | 取込（副: 共通基盤: API クライアント）                                 | PDF upload は `application/pdf` content-type                                       | 取込画面の資料アップロード API 通信規約（material role, content-type）                                                                                                   |
| INV-140    | 画面         | 答案キュー                                                             | キュー順: needs_review 優先、同状態は取込古い順                                    | 答案キュー画面（submission_queue_page.dart / review_queue.dart）のソート・進捗表示・要確認理由                                                                           |
| INV-141    | 画面         | 答案キュー                                                             | 済み答案も一覧から消さない                                                         | 答案キュー画面（submission_queue_page.dart / review_queue.dart）のソート・進捗表示・要確認理由                                                                           |
| INV-142    | 画面         | 答案キュー                                                             | `positionOf` は 1 始まり、未知は 0                                                 | 答案キュー画面（submission_queue_page.dart / review_queue.dart）のソート・進捗表示・要確認理由                                                                           |
| INV-143    | 画面         | 答案キュー                                                             | `nextAfter` は reviewed スキップ、末尾→前の未了                                    | 答案キュー画面（submission_queue_page.dart / review_queue.dart）のソート・進捗表示・要確認理由                                                                           |
| INV-144    | 画面         | 答案キュー                                                             | 設問進捗: partial/manual grading 表示                                              | 答案キュー画面（submission_queue_page.dart / review_queue.dart）のソート・進捗表示・要確認理由                                                                           |
| INV-145    | 画面         | 答案キュー                                                             | `isFullyConfirmed`: 全問確定なら state≠reviewed でも可                             | 答案キュー画面（submission_queue_page.dart / review_queue.dart）のソート・進捗表示・要確認理由                                                                           |
| INV-146    | 画面         | 答案キュー                                                             | 進捗不明時は export 可と言わない                                                   | 答案キュー画面（submission_queue_page.dart / review_queue.dart）のソート・進捗表示・要確認理由                                                                           |
| INV-147    | 画面         | ホーム（Phase 2-4）                                                    | ホーム: `ai_processed` は確認済みに数えない                                        | ホーム画面ダッシュボードの進捗数・次の答案遷移・キュー入口・全テストカード取得                                                                                           |
| INV-148    | 画面         | ホーム（Phase 2-4）                                                    | 続きは needs_review 最古優先                                                       | ホーム画面ダッシュボードの進捗数・次の答案遷移・キュー入口・全テストカード取得                                                                                           |
| INV-149    | 画面         | ホーム（Phase 2-4）                                                    | 答案キュー入口はホーム「確認済み N/M」タップのみ                                   | ホーム画面ダッシュボードの進捗数・次の答案遷移・キュー入口・全テストカード取得                                                                                           |
| INV-150    | 画面         | ホーム（Phase 2-4）                                                    | 溢れテストの要確認も fetch/表示                                                    | ホーム画面ダッシュボードの進捗数・次の答案遷移・キュー入口・全テストカード取得                                                                                           |
| INV-151    | 画面         | 添削レビュー（副: 答案確定）                                           | 設問並び: 自然順 number、page 優先                                                 | 添削レビュー画面レールおよび答案確定画面における設問並び順（自然順 number, page優先）                                                                                    |
| INV-152    | 共通基盤     | 共通基盤: ドメインロジック・設問状態（関連: 添削レビュー）             | usable=false + waiting → needsCheck; 待ち無し → graded                             | core/question_status.dart における設問状態（needsCheck, graded等）の優先度決定ドメインロジック                                                                           |
| INV-153    | 共通基盤     | 共通基盤: ドメインロジック・設問状態（関連: 添削レビュー）             | 人間採点後は stopped job より review 優先                                          | core/question_status.dart における設問状態（needsCheck, graded等）の優先度決定ドメインロジック                                                                           |
| INV-154    | 画面         | 答案確定                                                               | 未到達設問があれば確定不可、番号明示                                               | 答案確定画面（submission_confirm_page.dart / submission_confirmation.dart）の確定判定・一括承認・部分失敗表示                                                            |
| INV-155    | 画面         | 答案確定                                                               | 全到達後 1 操作で N 問 approve                                                     | 答案確定画面（submission_confirm_page.dart / submission_confirmation.dart）の確定判定・一括承認・部分失敗表示                                                            |
| INV-156    | 画面         | 答案確定                                                               | 部分失敗: 確定済み数・残り・failedNumber 表示                                      | 答案確定画面（submission_confirm_page.dart / submission_confirmation.dart）の確定判定・一括承認・部分失敗表示                                                            |
| INV-157    | 画面         | 答案確定                                                               | AI 採点不可設問→humanScoreRequired で確定不可                                      | 答案確定画面（submission_confirm_page.dart / submission_confirmation.dart）の確定判定・一括承認・部分失敗表示                                                            |
| INV-158    | 画面         | 答案キュー                                                             | `review_reason` wire format パース                                                 | 答案キュー画面（submission_queue_page.dart / review_queue.dart）のソート・進捗表示・要確認理由                                                                           |
| INV-159    | 画面         | 答案キュー                                                             | 未知 reason は推測せず空                                                           | 答案キュー画面（submission_queue_page.dart / review_queue.dart）のソート・進捗表示・要確認理由                                                                           |
| INV-160    | 画面         | 添削レビュー                                                           | 要確認と失敗でヘッダー要約文字列が異なる                                           | 添削レビュー画面内の DependencyDagPanel におけるヘッダー要約・折りたたみ保持・次の一手ガイダンス                                                                         |
| INV-161    | 画面         | 添削レビュー                                                           | パネル畳んでも失敗件数・次の一手・遷移ボタンが残る                                 | 添削レビュー画面内の DependencyDagPanel におけるヘッダー要約・折りたたみ保持・次の一手ガイダンス                                                                         |
| INV-162    | 画面         | 添削レビュー                                                           | 下流「待ち」文言が上流理由（確認待ち vs 失敗で停止）で変わる                       | 添削レビュー画面内の DependencyDagPanel におけるヘッダー要約・折りたたみ保持・次の一手ガイダンス                                                                         |
| INV-163    | 画面         | 添削レビュー                                                           | `dagFailureGuidance`: 分類ごとに次の操作が変わる                                   | 添削レビュー画面内の DependencyDagPanel におけるヘッダー要約・折りたたみ保持・次の一手ガイダンス                                                                         |
| INV-164    | 画面         | 添削レビュー                                                           | 返す文言に last_error の断片（provider 名・URL・HTTP）が入らない                   | 添削レビュー画面内の DependencyDagPanel におけるヘッダー要約・折りたたみ保持・次の一手ガイダンス                                                                         |
| INV-165    | 画面         | 添削レビュー                                                           | 各分類で cause と nextStep が非空。nextStep は操作名指し                           | 添削レビュー画面内の DependencyDagPanel におけるヘッダー要約・折りたたみ保持・次の一手ガイダンス                                                                         |
| INV-166    | 画面         | 添削レビュー                                                           | crop_not_the_answer → 回答欄修正を促す（再判定を勧めない）                         | 添削レビュー画面内の DependencyDagPanel におけるヘッダー要約・折りたたみ保持・次の一手ガイダンス                                                                         |
| INV-167    | 画面         | 取込                                                                   | GradingKickoffFailure: 409 は両可能性、404 は非 retry                              | 取込後の AI 採点キックオフ例外分類（grading_kickoff.dart）                                                                                                               |
| INV-168    | 共通基盤     | 共通基盤: 共通UIコンポーネント（アプリシェル）                         | grading unavailable banner: unavailable のみ表示                                   | main.dart のルーター最上位に常駐する採点不可バナー（GradingUnavailableBanner）の表示制御                                                                                 |
| INV-170    | 画面         | 回答欄エディタ（Phase 3 テスト設定）                                   | 未検出と未割当（absent）を別グループ表示                                           | 回答欄エディタ（answer_area_editor.dart）の未検出・未割当・読み順食い違い表示・描画アクション                                                                            |
| INV-171    | 画面         | 回答欄エディタ（Phase 3 テスト設定）                                   | 該当グループのみ表示（片方だけのとき他方は出さない）                               | 回答欄エディタ（answer_area_editor.dart）の未検出・未割当・読み順食い違い表示・描画アクション                                                                            |
| INV-172    | 画面         | 回答欄エディタ（Phase 3 テスト設定）                                   | 全クリア表示は両グループ空のときのみ                                               | 回答欄エディタ（answer_area_editor.dart）の未検出・未割当・読み順食い違い表示・描画アクション                                                                            |
| INV-173    | 画面         | 回答欄エディタ（Phase 3 テスト設定）                                   | absent グループは「見つけられなかった」表現（断定しない）                          | 回答欄エディタ（answer_area_editor.dart）の未検出・未割当・読み順食い違い表示・描画アクション                                                                            |
| INV-174    | 画面         | 回答欄エディタ（Phase 3 テスト設定）                                   | 画面に実測比率・件数・% を出さない                                                 | 回答欄エディタ（answer_area_editor.dart）の未検出・未割当・読み順食い違い表示・描画アクション                                                                            |
| INV-175    | 画面         | 回答欄エディタ（Phase 3 テスト設定）                                   | 出口アクションは該当チップの直上                                                   | 回答欄エディタ（answer_area_editor.dart）の未検出・未割当・読み順食い違い表示・描画アクション                                                                            |
| INV-176    | 画面         | 回答欄エディタ（Phase 3 テスト設定）                                   | absent のみのとき描画ターゲットは absent 設問                                      | 回答欄エディタ（answer_area_editor.dart）の未検出・未割当・読み順食い違い表示・描画アクション                                                                            |
| INV-177    | 画面         | 回答欄エディタ（Phase 3 テスト設定）                                   | 読み順と設問番号が一致するとき警告なし                                             | 回答欄エディタ（answer_area_editor.dart）の未検出・未割当・読み順食い違い表示・描画アクション                                                                            |
| INV-178    | 画面         | 回答欄エディタ（Phase 3 テスト設定）                                   | 読み順食い違い時は警告表示                                                         | 回答欄エディタ（answer_area_editor.dart）の未検出・未割当・読み順食い違い表示・描画アクション                                                                            |
| INV-180    | 画面         | 出力                                                                   | 単体: progress→success + path                                                      | 単体・一括 PDF 出力ダイアログ（export_dialog.dart / bulk_export.dart）の進捗・排他・リトライ・エラー処理                                                                 |
| INV-181    | 画面         | 出力                                                                   | `reuse_existing` は即 success                                                      | 単体・一括 PDF 出力ダイアログ（export_dialog.dart / bulk_export.dart）の進捗・排他・リトライ・エラー処理                                                                 |
| INV-182    | 画面         | 出力                                                                   | 409 `unconfirmed_questions`→設問 id 一覧                                           | 単体・一括 PDF 出力ダイアログ（export_dialog.dart / bulk_export.dart）の進捗・排他・リトライ・エラー処理                                                                 |
| INV-183    | 画面         | 出力                                                                   | 409 `no_room_for_score`≠未確認文言                                                 | 単体・一括 PDF 出力ダイアログ（export_dialog.dart / bulk_export.dart）の進捗・排他・リトライ・エラー処理                                                                 |
| INV-184    | 画面         | 出力                                                                   | 未知 conflict code→sidecar message をそのまま                                      | 単体・一括 PDF 出力ダイアログ（export_dialog.dart / bulk_export.dart）の進捗・排他・リトライ・エラー処理                                                                 |
| INV-185    | 画面         | 出力                                                                   | failed→retry で requeue                                                            | 単体・一括 PDF 出力ダイアログ（export_dialog.dart / bulk_export.dart）の進捗・排他・リトライ・エラー処理                                                                 |
| INV-186    | 画面         | 出力                                                                   | ポーリング transient failure は progress 維持                                      | 単体・一括 PDF 出力ダイアログ（export_dialog.dart / bulk_export.dart）の進捗・排他・リトライ・エラー処理                                                                 |
| INV-187    | 画面         | 出力                                                                   | cancelled job retry→新規 requestExport                                             | 単体・一括 PDF 出力ダイアログ（export_dialog.dart / bulk_export.dart）の進捗・排他・リトライ・エラー処理                                                                 |
| INV-188    | 画面         | 出力                                                                   | 一括: 全問確定のみ対象、除外は理由付き                                             | 単体・一括 PDF 出力ダイアログ（export_dialog.dart / bulk_export.dart）の進捗・排他・リトライ・エラー処理                                                                 |
| INV-189    | 画面         | 出力                                                                   | 1 件 refused でも残り続行、失敗一覧                                                | 単体・一括 PDF 出力ダイアログ（export_dialog.dart / bulk_export.dart）の進捗・排他・リトライ・エラー処理                                                                 |
| INV-190    | 画面         | 出力                                                                   | キュー行から export（レビュー画面経由不要）                                        | 単体・一括 PDF 出力ダイアログ（export_dialog.dart / bulk_export.dart）の進捗・排他・リトライ・エラー処理                                                                 |
| INV-200    | 共通基盤     | 共通基盤: API クライアント                                             | `/healthz` は bogus token でも OK                                                  | サイドカー API クライアント（sidecar_api_client）の認証・loopback制限・409詳細保持                                                                                       |
| INV-201    | 共通基盤     | 共通基盤: API クライアント                                             | 正 token で protected API 成功                                                     | サイドカー API クライアント（sidecar_api_client）の認証・loopback制限・409詳細保持                                                                                       |
| INV-202    | 共通基盤     | 共通基盤: API クライアント                                             | 誤 token→401 unauthorized                                                          | サイドカー API クライアント（sidecar_api_client）の認証・loopback制限・409詳細保持                                                                                       |
| INV-203    | 共通基盤     | 共通基盤: API クライアント                                             | 非 loopback URL→ArgumentError（URL/token を message に含めない）                   | サイドカー API クライアント（sidecar_api_client）の認証・loopback制限・409詳細保持                                                                                       |
| INV-204    | 共通基盤     | 共通基盤: API クライアント                                             | unknown transport error→接続詳細なし                                               | サイドカー API クライアント（sidecar_api_client）の認証・loopback制限・409詳細保持                                                                                       |
| INV-205    | 共通基盤     | 共通基盤: API クライアント                                             | 409→`conflictCode` + `conflictQuestionIds` 保持                                    | サイドカー API クライアント（sidecar_api_client）の認証・loopback制限・409詳細保持                                                                                       |
| UG-01      | 共通基盤     | 共通基盤: サイドカーライフサイクル・起動ゲート                         | アプリを強制終了してもサイドカーが道連れで終わる（Job Object kill-on-close）       | サイドカーのプロセス管理・Job Object・ライフサイクル・起動引数・スプラッシュ案内に関する保証（`core/child_process_group.dart:39,167,199`）                               |
| UG-02      | 共通基盤     | 共通基盤: サイドカーライフサイクル・起動ゲート                         | kill-on-close を設定できなかった Job は持たない（保証が有るふりをしない）          | サイドカーのプロセス管理・Job Object・ライフサイクル・起動引数・スプラッシュ案内に関する保証（`core/child_process_group.dart:184`）                                      |
| UG-03      | 共通基盤     | 共通基盤: サイドカーライフサイクル・起動ゲート                         | Job ハンドルはプロセスの生涯閉じない（`dispose()` でも閉じない）                   | サイドカーのプロセス管理・Job Object・ライフサイクル・起動引数・スプラッシュ案内に関する保証（`core/child_process_group.dart:159`, `core/sidecar_platform_io.dart:124`） |
| UG-04      | 共通基盤     | 共通基盤: サイドカーライフサイクル・起動ゲート                         | 子プロセスは spawn の直後に Job へ登録する（孤児化の窓を最小にする）               | サイドカーのプロセス管理・Job Object・ライフサイクル・起動引数・スプラッシュ案内に関する保証（`core/sidecar_platform_io.dart:91`）                                       |
| UG-05      | 共通基盤     | 共通基盤: ナビゲーション・ルーティング                                 | リリースビルドは起動ルートとテーマを環境変数から取らない                           | リリースビルドにおける起動ルート・テーマ環境変数の無効化保証（main.dart:69）                                                                                             |
| UG-06      | 共通基盤     | 共通基盤: サイドカーライフサイクル・起動ゲート                         | アプリは `app-data` の場所を決めない（`--app-data-dir` を渡さない）                | サイドカーのプロセス管理・Job Object・ライフサイクル・起動引数・スプラッシュ案内に関する保証（`main.dart:87`, `core/sidecar_supervisor.dart:162`）                       |
| UG-07      | 共通基盤     | 共通基盤: サイドカーライフサイクル・起動ゲート                         | 子プロセスの stdout/stderr を常にドレインする                                      | サイドカーのプロセス管理・Job Object・ライフサイクル・起動引数・スプラッシュ案内に関する保証（`core/sidecar_platform_io.dart:140`）                                      |
| UG-08      | 共通基盤     | 共通基盤: サイドカーライフサイクル・起動ゲート                         | 起動タイムアウトは 60 秒 ―― Defender の初回スキャンを待てる長さ                    | サイドカーのプロセス管理・Job Object・ライフサイクル・起動引数・スプラッシュ案内に関する保証（`core/sidecar_supervisor.dart:30`）                                        |
| UG-09      | 画面         | 出力                                                                   | 一括出力は既存ファイルを絶対に上書きしない（`_2`, `_3` へ逃がす）                  | 一括出力時の既存ファイル上書き防止（連番退避）保証（core/bulk_export_writer.dart:34）                                                                                    |
| UG-10      | 画面         | 取込（副: 共通基盤: フォルダ走査）                                     | フォルダ走査は隠しファイルと OS メタデータを除き、5,000 件で打ち切る               | 取込画面で使われるフォルダ走査機能（core/folder_scan.dart）の件数上限・パス正規化・ハッシュ保護保証（`core/folder_scan.dart:63,70,95,99`）                               |
| UG-11      | 画面         | 取込（副: 共通基盤: フォルダ走査）                                     | 走査が返す `relativePath` は常に `/` 区切り（Windows の `\` を潰す）               | 取込画面で使われるフォルダ走査機能（core/folder_scan.dart）の件数上限・パス正規化・ハッシュ保護保証（`core/folder_scan.dart:104`）                                       |
| UG-12      | 画面         | 取込（副: 共通基盤: フォルダ走査）                                     | 走査はファイル内容を外に出さない（ダイジェストだけ、しかもストリーム読み）         | 取込画面で使われるフォルダ走査機能（core/folder_scan.dart）の件数上限・パス正規化・ハッシュ保護保証（`core/folder_scan.dart:108`）                                       |
| UG-13      | 共通基盤     | 共通基盤: 共通UIコンポーネント（関連: 取込、設定）                     | 長いファイル名がファイル選択ボタンを画面外へ押し出さない                           | ファイル選択行（AppFilePickerRow）の長いファイル名省略表示保証（core/widgets/app_file_picker_row.dart:52）                                                               |
| UG-14      | 共通基盤     | 共通基盤: サイドカーライフサイクル・起動ゲート                         | 失敗画面が指すログの場所が、サイドカーが実際に書く場所と一致している               | サイドカーのプロセス管理・Job Object・ライフサイクル・起動引数・スプラッシュ案内に関する保証（`features/startup/startup_gate.dart:122`）                                 |
| UG-15      | 共通基盤     | 共通基盤: サイドカーライフサイクル・起動ゲート                         | 待たせるときは、待つ理由（初回マイグレーションと Defender スキャン）を出す         | サイドカーのプロセス管理・Job Object・ライフサイクル・起動引数・スプラッシュ案内に関する保証（`features/startup/startup_gate.dart:87`）                                  |

---

## 17. 移行 PR 引き取り実績と不変条件 185 件の照合（Issue #246）

GitHub Issue [#246](https://github.com/HIKARU0627/Auto-Scoring/issues/246)（親 [#201](https://github.com/HIKARU0627/Auto-Scoring/issues/201)）。

最高責任者が定めたフロントエンド cut-over の第 1 条件:

> - **185 件の不変条件を、画面ごとの引き取りが覆っていること**（割当表で照合）

を満たすため、`origin/main` にマージ済みの移行 PR 9 本の引き取り実績を GitHub App API 経由で取得し、§16 の割当表 185 件（`INV-*` 170 件 + `UG-*` 15 件）と照合した。

### 17.1 対象 PR の引き取り状況と根拠

各 PR 本文は `gh` CLI を使わず、`./scripts/invoke-github-app-api.ps1` 経由で GitHub REST API から直接取得した（`AGENTS.md` の GitHub App authentication 規則準拠）。推測による穴埋めは行わず、PR 本文およびコメントに実際に記載された番号のみを根拠とした。

| PR       | 画面・領域                           | 引き取り宣言件数 | 引き取った不変条件 ID                                                                                                 | 備考                                                                                                              |
| -------- | ------------------------------------ | ---------------: | --------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| **#220** | `desktop/` 骨格                      |            **0** | なし                                                                                                                  | PR 本文・コメントに `INV-*` / `UG-*` 番号の列挙なし（骨格とテスト土台のみ）                                       |
| **#225** | デザイントークン                     |            **7** | `INV-201-09`, `INV-087`, `INV-088`, `INV-089`, `INV-090`, `INV-093`, `INV-094`                                        | CSS 変数 + Vitest（`desktop/test/theme-contrast.test.ts`）で固定                                                  |
| **#231** | TS 生成クライアント                  |            **0** | なし                                                                                                                  | openapi-typescript + openapi-fetch 生成基盤。クライアント不変条件（INV-200〜205）は未請求                         |
| **#235** | ホーム + シェル + ルート表メタテスト |            **9** | `INV-018`, `INV-048`, `INV-128`, `INV-129`, `INV-147`, `INV-148`, `INV-149`, `INV-150`, `INV-201-05`                  | ホーム画面 8 件に加え、共通基盤のルート脱出メタテスト `INV-201-05` を引き取り                                     |
| **#237** | サイドカー lifecycle（main）         |           **21** | `INV-030`〜`INV-032`, `INV-034`〜`INV-047`, `UG-01`, `UG-06`〜`UG-08`                                                 | main プロセス監視。Job Object 代替親監視 `--parent-pid` 採用。保留 6 件（UG-02〜04, INV-033, UG-14, UG-15）を明記 |
| **#238** | 回答欄エディタ                       |           **10** | `INV-201-10`, `INV-170`〜`INV-178`                                                                                    | 回答欄エディタ本体 10 件。プロファイル保存・確定ボタン無効理由 `INV-110` はスコープ外として未請求                 |
| **#240** | 取込                                 |           **19** | `INV-103`, `INV-120`〜`INV-127`, `INV-130`〜`INV-135`, `INV-167`, `UG-10`〜`UG-12`                                    | 取込画面 19 件。主担当外の `INV-201-07`, `UG-13` は二重計上防止として主引き取りから明示除外                       |
| **#243** | 答案キュー                           |           **11** | `INV-007`, `INV-021`, `INV-140`〜`INV-146`, `INV-158`, `INV-159`                                                      | 答案キュー画面に割り当てられた 11 件全件を引き取り                                                                |
| **#244** | 添削レビュー                         |           **35** | `INV-201-01`, `INV-201-03`, `INV-201-06`, `INV-003`, `INV-014`, `INV-050`〜`INV-071`, `INV-151`, `INV-160`〜`INV-166` | 添削レビュー画面に割り当てられた 35 件全件を引き取り                                                              |
| **合計** | (9 PR)                               |          **112** | (ユニーク 112 件)                                                                                                     | 重複引き取りなし                                                                                                  |

### 17.2 集計サマリと二重計上の検出

185 件に対する引き取り状態の 3 つの数は以下のとおりである。

| 状態区分         |    件数 |   割合 | 概要                                                                              |
| ---------------- | ------: | -----: | --------------------------------------------------------------------------------- |
| **引き取り済み** | **112** |  60.5% | マージ済み PR #225, #235, #237, #238, #240, #243, #244 により新スタックで固定済み |
| **未引き取り**   |  **73** |  39.5% | 未移植画面（答案確定・設定・出力・テスト設定残余）および未引き取り共通基盤        |
| **二重計上**     |   **0** |   0.0% | 複数の PR が主担当として重複して引き取った不変条件は 0 件                         |
| **合計**         | **185** | 100.0% | **§16 割当表の全 185 件（INV 170 + UG 15）と厳密に一致**                          |

#### 二重計上・主担当と関連の区別

- **主担当としての重複引き取りは 0 件:** 同一の不変条件番号を複数の PR が主担当として二重にカウントしている箇所は存在しない。
- **PR #240 における二重計上防止の明示:**
  - `INV-201-07`（廃止文言の全体回帰防止）: 取込完了画面の文言テスト（INV-130 と同一）で検査されているが、主担当は「共通基盤: 全体検証・文言検査（関連: ホーム、取込）」であるため、PR #240 本文にて「主担当外だが本 PR で触れたもの（二重計上防止）」として主引き取りから明示的に除外されている。
  - `UG-13`（ファイル選択ボタン押し出し防止）: `FilePickerRow` の長いファイル名省略テストが含まれるが、主担当は「共通基盤: 共通 UI コンポーネント（関連: 取込、設定）」であるため、同様に二重計上防止として主引き取りから明示的に除外されている。
- **PR #235 による共通基盤の先行引き取り:**
  - `INV-201-05`（ホーム脱出検査）: 割当表 §16.5 では「共通基盤: ナビゲーション・ルーティング」に配分されていたが、PR #235 がホーム画面およびシェル実装時にルート表メタテスト（`every declared route is covered`）として引き取りを完了した。
- **副担当を持つ不変条件の引き取り:**
  - `INV-201-01`（未読材料での確定不可）: 添削レビュー（主）/ 答案確定（副）。PR #244 が主担当として引き取り済み（答案確定画面の未到達確定不可 `INV-154` と連動）。
  - `INV-151`（設問並び順）: 添削レビュー（主）/ 答案確定（副）。PR #244 が引き取り済み。

### 17.3 未引き取り 73 件の内訳と未移植画面との差分分析

「未移植の 3 画面（答案確定 7 件 + 設定 1 件 + 出力 12 件 = 計 20 件）」と「未引き取り 73 件」の間には **53 件の差**が存在する。どこで何が落ちているかを精査した結果、以下の構造が判明した。

```text
未引き取り全 73 件
├─ 画面側の残余: 21 件
│   ├─ 答案確定画面: 7 件（INV-201-02, INV-201-08, INV-005, INV-154〜INV-157）
│   ├─ 設定画面: 1 件（INV-107）
│   ├─ 出力機能: 12 件（INV-180〜INV-190, UG-09）
│   └─ テスト設定画面（プロファイル確定）: 1 件（INV-110） ★ PR #238 スコープ外の積み残し
└─ 共通基盤側の残余: 52 件
    ├─ ナビゲーション・ルーティング: 10 件（INV-010〜013, INV-015〜017, INV-019, INV-020, UG-05）
    ├─ 共通 UI コンポーネント: 10 件（INV-091, INV-092, INV-096, INV-097, INV-104〜106, INV-108, INV-109, INV-168）
    ├─ デザイントークン・アクセシビリティ: 8 件（INV-080〜086, INV-095）
    ├─ サイドカーライフサイクル・起動ゲート: 6 件（INV-033, UG-02〜04, UG-14, UG-15）
    ├─ API クライアント: 6 件（INV-200〜205）
    ├─ 操作要件・無効理由エンジン: 5 件（INV-201-04, INV-004, INV-100〜102）
    ├─ ドメインロジック・設問状態: 3 件（INV-006, INV-152, INV-153）
    ├─ アーキテクチャ・依存方向: 2 件（INV-001, INV-002）
    ├─ 全体検証・文言検査: 1 件（INV-201-07）
    └─ 共通 UI コンポーネント（ファイル選択）: 1 件（UG-13）
```

#### 差分が生じる 2 つの要因

1. **画面側での積み残し（1 件: `INV-110`）:**
   - 割当表 §16.4 では、テスト設定の領域に「回答欄エディタ 10 件」と「テスト設定（テストプロファイル保存・確定無効理由）1 件（`INV-110`）」が割り当てられていた。
   - PR #238 は回答欄エディタ本体と 10 件を引き取ったが、PR 本文「レビュアーへの補足: プロファイル保存・確定 UI は本 Issue のスコープ外」と明記し、`INV-110` を引き取らなかった。このため、未移植画面は 3 画面ではなく「3 画面 + テスト設定プロファイル（計 21 件）」となる。
2. **共通基盤側の未引き取り（52 件）:**
   - 割当表 §16.4 の共通基盤 74 件のうち、PR #237（21 件）と PR #235（1 件: `INV-201-05`）が引き取った 22 件を除く **52 件**が依然として未引き取りである。
   - 画面移植（Phase 3）は各画面のローカルな振る舞いを引き取るが、アプリ全体のルーター規約（`INV-010`〜`013` 等）、共通ボタン・エラーバナー等の共通 UI（`INV-091`〜`109`）、API クライアント通信規約（`INV-200`〜`205`）、無効理由エンジン（`INV-100`〜`102`）などの横断的不変条件は画面移植のスコープから自然と外れるためである。

**結論:** cut-over 条件である「185 件の不変条件を覆うこと」を満たすには、残る未移植 3 画面（答案確定・設定・出力）とテスト設定プロファイルの移植だけでは不足であり、**共通基盤の未引き取り 52 件を固定する独立した Issue / テスト整備が必要**である。

### 17.4 不変条件 185 件の完全照合一覧表

§16.5 の割当表 185 件（`INV-201-01`〜`INV-201-10`、`INV-001`〜`INV-205`、`UG-01`〜`UG-15`）すべてについて、移行 PR（#220, #225, #231, #235, #237, #238, #240, #243, #244）の引き取り実績と突き合わせた完全照合表を以下に示す。

- **引き取り済み:** 計 **112 件**（新スタックのテストで固定済み）
- **未引き取り:** 計 **73 件**（未移植画面 21 件 + 未引き取り共通基盤 52 件）
- **二重計上:** **0 件**（主担当としての重複引き取りなし）
- **合計件数:** **185 件（112 + 73 = 185、完全一致）**

| ID         | 区分         | 割当担当先                                                             | 状態             | 引き取り元 PR / 残存理由                                                        | 不変条件 / 保証の概要                                                              |
| ---------- | ------------ | ---------------------------------------------------------------------- | ---------------- | ------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| INV-201-01 | 画面         | 添削レビュー（主）/ 答案確定（副）                                     | **引き取り済み** | PR #244                                                                         | 見ていない判断材料で確定・承認できない                                             |
| INV-201-02 | 画面         | 答案確定                                                               | 未引き取り       | 未移植 (答案確定)                                                               | 確信度（Confidence）から完了・確定を導かない                                       |
| INV-201-03 | 画面         | 添削レビュー                                                           | **引き取り済み** | PR #244                                                                         | 失敗が要約から漏れない。パネルを畳んでも残る。下流の「待ち」と区別できる           |
| INV-201-04 | 共通基盤     | 共通基盤: 操作要件・無効理由エンジン                                   | 未引き取り       | 未移植 (共通基盤: 操作要件・無効理由エンジン)                                   | 無効な操作には、無効条件そのものから導いた理由が必ず出る                           |
| INV-201-05 | 共通基盤     | 共通基盤: ナビゲーション・ルーティング                                 | **引き取り済み** | PR #235                                                                         | 画面を足したら「ホームへ戻れる」検査の対象か除外（理由付き）に必ず載る             |
| INV-201-06 | 画面         | 添削レビュー                                                           | **引き取り済み** | PR #244                                                                         | 失敗文言は「何が起きたか」と「次に何ができるか」を両方持つ                         |
| INV-201-07 | 共通基盤     | 共通基盤: 全体検証・文言検査（関連: ホーム、取込）                     | 未引き取り       | 未移植 (共通基盤: 全体検証・文言検査（関連: ホーム、取込）)                     | 廃止した文言が二度と現れない                                                       |
| INV-201-08 | 画面         | 答案確定                                                               | 未引き取り       | 未移植 (答案確定)                                                               | 別ボタンにフォーカスした Enter が確定を実行しない                                  |
| INV-201-09 | 引き取り済み | 引き取り済み (Phase 2-2 / PR #225)                                     | **引き取り済み** | PR #225                                                                         | 無効ボタンのコントラストは目視でなく計算で WCAG を満たす                           |
| INV-201-10 | 画面         | 回答欄エディタ（Phase 3 テスト設定）                                   | **引き取り済み** | PR #238                                                                         | 回答欄の未検出・未割当・読み順食い違いを原因別に見せる                             |
| INV-001    | 共通基盤     | 共通基盤: アーキテクチャ・依存方向                                     | 未引き取り       | 未移植 (共通基盤: アーキテクチャ・依存方向)                                     | `api` 層は `core` / `features` を import しない                                    |
| INV-002    | 共通基盤     | 共通基盤: アーキテクチャ・依存方向                                     | 未引き取り       | 未移植 (共通基盤: アーキテクチャ・依存方向)                                     | `core` 層は `features` を import しない                                            |
| INV-003    | 画面         | 添削レビュー                                                           | **引き取り済み** | PR #244                                                                         | 添削レビュー画面は `setState` 直呼び禁止。`_setStateIfMounted` 経由のみ            |
| INV-004    | 共通基盤     | 共通基盤: 操作要件・無効理由エンジン                                   | 未引き取り       | 未移植 (共通基盤: 操作要件・無効理由エンジン)                                   | 無効操作の判定と文言は `core/action_requirements.dart` の単一ソース                |
| INV-005    | 画面         | 答案確定                                                               | 未引き取り       | 未移植 (答案確定)                                                               | 答案確定可否は `core/submission_confirmation.dart` に置く                          |
| INV-006    | 共通基盤     | 共通基盤: ドメインロジック・設問状態（関連: 添削レビュー、答案キュー） | 未引き取り       | 未移植 (共通基盤: ドメインロジック・設問状態（関連: 添削レビュー、答案キュー）) | 設問ステータスは `core/question_status.dart` で一元決定                            |
| INV-007    | 画面         | 答案キュー（関連: ホーム）                                             | **引き取り済み** | PR #243                                                                         | レビューキュー順序は `core/review_queue.dart` で決定                               |
| INV-010    | 共通基盤     | 共通基盤: ナビゲーション・ルーティング                                 | 未引き取り       | 未移植 (共通基盤: ナビゲーション・ルーティング)                                 | `features/` 内で `go_router` の `.go()` / `.goNamed()` を使わない                  |
| INV-011    | 共通基盤     | 共通基盤: ナビゲーション・ルーティング                                 | 未引き取り       | 未移植 (共通基盤: ナビゲーション・ルーティング)                                 | 画面間移動は `push` / `replace` / `pop` のみ                                       |
| INV-012    | 共通基盤     | 共通基盤: ナビゲーション・ルーティング                                 | 未引き取り       | 未移植 (共通基盤: ナビゲーション・ルーティング)                                 | `AppRoutes` の各 location が対応 Widget を開く                                     |
| INV-013    | 共通基盤     | 共通基盤: ナビゲーション・ルーティング                                 | 未引き取り       | 未移植 (共通基盤: ナビゲーション・ルーティング)                                 | パラメータ付き URL（`testId`, `submissionId`, `questionId`）が正しく decode される |
| INV-014    | 画面         | 添削レビュー                                                           | **引き取り済み** | PR #244                                                                         | 添削レビューは開く設問を URL で指定できる                                          |
| INV-015    | 共通基盤     | 共通基盤: ナビゲーション・ルーティング                                 | 未引き取り       | 未移植 (共通基盤: ナビゲーション・ルーティング)                                 | スタック空で開いた covered ルートすべてに `BackOrHomeButton` がある                |
| INV-016    | 共通基盤     | 共通基盤: ナビゲーション・ルーティング                                 | 未引き取り       | 未移植 (共通基盤: ナビゲーション・ルーティング)                                 | 狭幅 700×720 でも出口ボタンが押せる                                                |
| INV-017    | 共通基盤     | 共通基盤: ナビゲーション・ルーティング                                 | 未引き取り       | 未移植 (共通基盤: ナビゲーション・ルーティング)                                 | Tab→Enter のみでホームへ戻れる                                                     |
| INV-018    | 画面         | ホーム（Phase 2-4）                                                    | **引き取り済み** | PR #235                                                                         | ホーム自身には出口を出さない                                                       |
| INV-019    | 共通基盤     | 共通基盤: ナビゲーション・ルーティング                                 | 未引き取り       | 未移植 (共通基盤: ナビゲーション・ルーティング)                                 | push で積んだ画面では出口は 1 枚戻る（ホーム直行ではない）                         |
| INV-020    | 共通基盤     | 共通基盤: ナビゲーション・ルーティング                                 | 未引き取り       | 未移植 (共通基盤: ナビゲーション・ルーティング)                                 | 新ルート追加時、covered か skipped（理由付き）のどちらかに必ず登録                 |
| INV-021    | 画面         | 答案キュー                                                             | **引き取り済み** | PR #243                                                                         | 答案キュー行タップは答案確定画面を開く（設問ごと承認ではない）                     |
| INV-030    | 共通基盤     | 共通基盤: サイドカーライフサイクル・起動ゲート                         | **引き取り済み** | PR #237                                                                         | 起動中はスプラッシュ→ healthy 後にホーム表示                                       |
| INV-031    | 共通基盤     | 共通基盤: サイドカーライフサイクル・起動ゲート                         | **引き取り済み** | PR #237                                                                         | ウィンドウ閉じる前に sidecar を kill                                               |
| INV-032    | 共通基盤     | 共通基盤: サイドカーライフサイクル・起動ゲート                         | **引き取り済み** | PR #237                                                                         | 起動失敗時「再起動」でアプリ再起動なしに復旧                                       |
| INV-033    | 共通基盤     | 共通基盤: サイドカーライフサイクル・起動ゲート                         | 未引き取り       | 未移植 (共通基盤: サイドカーライフサイクル・起動ゲート)                         | push 済み画面の上でもクラッシュ overlay＋再起動が見える                            |
| INV-034    | 共通基盤     | 共通基盤: サイドカーライフサイクル・起動ゲート                         | **引き取り済み** | PR #237                                                                         | 二重起動は「すでに起動しています」                                                 |
| INV-035    | 共通基盤     | 共通基盤: サイドカーライフサイクル・起動ゲート                         | **引き取り済み** | PR #237                                                                         | 実行ファイル欠落→再インストール案内                                                |
| INV-036    | 共通基盤     | 共通基盤: サイドカーライフサイクル・起動ゲート                         | **引き取り済み** | PR #237                                                                         | エラー画面に bearer token を描画しない                                             |
| INV-037    | 共通基盤     | 共通基盤: サイドカーライフサイクル・起動ゲート                         | **引き取り済み** | PR #237                                                                         | handshake 未完成はリトライ、即失敗しない                                           |
| INV-038    | 共通基盤     | 共通基盤: サイドカーライフサイクル・起動ゲート                         | **引き取り済み** | PR #237                                                                         | ready 後 handshake ファイル削除                                                    |
| INV-039    | 共通基盤     | 共通基盤: サイドカーライフサイクル・起動ゲート                         | **引き取り済み** | PR #237                                                                         | 即 exit はタイムアウト待たず failed                                                |
| INV-040    | 共通基盤     | 共通基盤: サイドカーライフサイクル・起動ゲート                         | **引き取り済み** | PR #237                                                                         | exit code 3 = alreadyRunning                                                       |
| INV-041    | 共通基盤     | 共通基盤: サイドカーライフサイクル・起動ゲート                         | **引き取り済み** | PR #237                                                                         | shutdown は kill 後 crash 報告しない                                               |
| INV-042    | 共通基盤     | 共通基盤: サイドカーライフサイクル・起動ゲート                         | **引き取り済み** | PR #237                                                                         | Windows: バンドル優先、venv fallback                                               |
| INV-043    | 共通基盤     | 共通基盤: サイドカーライフサイクル・起動ゲート                         | **引き取り済み** | PR #237                                                                         | POSIX: `.exe` なし、`bin/` venv                                                    |
| INV-044    | 共通基盤     | 共通基盤: サイドカーライフサイクル・起動ゲート                         | **引き取り済み** | PR #237                                                                         | 統合: 動的 port、token で保護 API 成功                                             |
| INV-045    | 共通基盤     | 共通基盤: サイドカーライフサイクル・起動ゲート                         | **引き取り済み** | PR #237                                                                         | 統合: shutdown 後プロセス/port/lock 解放                                           |
| INV-046    | 共通基盤     | 共通基盤: サイドカーライフサイクル・起動ゲート                         | **引き取り済み** | PR #237                                                                         | 統合: 外部 sidecar を survivor と誤認しない                                        |
| INV-047    | 共通基盤     | 共通基盤: サイドカーライフサイクル・起動ゲート                         | **引き取り済み** | PR #237                                                                         | `sidecarStillServing`: 空 `[]` の 200 は alive                                     |
| INV-048    | 画面         | ホーム（Phase 2-4）                                                    | **引き取り済み** | PR #235                                                                         | ホームに `backend: ok` 等デバッグ表示なし                                          |
| INV-050    | 画面         | 添削レビュー                                                           | **引き取り済み** | PR #244                                                                         | 正規化座標→ピクセル変換（A4 縦・90°回転）                                          |
| INV-051    | 画面         | 添削レビュー                                                           | **引き取り済み** | PR #244                                                                         | ズーム 2× で overlay も 2× スケール                                                |
| INV-052    | 画面         | 添削レビュー                                                           | **引き取り済み** | PR #244                                                                         | explicit rect はそのまま使用                                                       |
| INV-053    | 画面         | 添削レビュー                                                           | **引き取り済み** | PR #244                                                                         | anchor_text → OCR box 解決（§12.3）                                                |
| INV-054    | 画面         | 添削レビュー                                                           | **引き取り済み** | PR #244                                                                         | crop 座標→page 座標変換（answer_area 経由）                                        |
| INV-055    | 画面         | 添削レビュー                                                           | **引き取り済み** | PR #244                                                                         | degenerate answer_area は full page 扱い                                           |
| INV-056    | 画面         | 添削レビュー                                                           | **引き取り済み** | PR #244                                                                         | OCR 改行付き anchor もマッチ                                                       |
| INV-057    | 画面         | 添削レビュー                                                           | **引き取り済み** | PR #244                                                                         | 複数 token は union rect                                                           |
| INV-058    | 画面         | 添削レビュー                                                           | **引き取り済み** | PR #244                                                                         | 最短 run が選ばれる                                                                |
| INV-059    | 画面         | 添削レビュー                                                           | **引き取り済み** | PR #244                                                                         | 長すぎる run は拒否（null）                                                        |
| INV-060    | 画面         | 添削レビュー                                                           | **引き取り済み** | PR #244                                                                         | 非連続 box は拒否                                                                  |
| INV-061    | 画面         | 添削レビュー                                                           | **引き取り済み** | PR #244                                                                         | anchor 未一致時 score_area に fallback しない                                      |
| INV-062    | 画面         | 添削レビュー                                                           | **引き取り済み** | PR #244                                                                         | ウィジェット: 正規化 (0.5,0.5) が pdfrx 実 render size で配置                      |
| INV-063    | 画面         | 添削レビュー                                                           | **引き取り済み** | PR #244                                                                         | 90° PDF でも同じ alignment                                                         |
| INV-064    | 画面         | 添削レビュー                                                           | **引き取り済み** | PR #244                                                                         | ターゲット無し annotation → 設問コメント欄                                         |
| INV-065    | 画面         | 添削レビュー                                                           | **引き取り済み** | PR #244                                                                         | 判断材料未読範囲 merge が NaN を出さない                                           |
| INV-066    | 画面         | 添削レビュー                                                           | **引き取り済み** | PR #244                                                                         | 行 covered = 0→1 全域到達で承認可能                                                |
| INV-067    | 画面         | 添削レビュー                                                           | **引き取り済み** | PR #244                                                                         | 判断材料が画面外のあいだ承認・Enter 不可。却下は可                                 |
| INV-068    | 画面         | 添削レビュー                                                           | **引き取り済み** | PR #244                                                                         | 高確信度に緑チェックを付けない（低のみ）                                           |
| INV-069    | 画面         | 添削レビュー                                                           | **引き取り済み** | PR #244                                                                         | blank answer 申告は本文に伴う                                                      |
| INV-070    | 画面         | 添削レビュー                                                           | **引き取り済み** | PR #244                                                                         | レール・DAG・Inspector で同一語・アイコン                                          |
| INV-071    | 画面         | 添削レビュー                                                           | **引き取り済み** | PR #244                                                                         | Issue #22: edit/reject/regrade/approve/undo 一連が通る                             |
| INV-080    | 共通基盤     | 共通基盤: デザイントークン・アクセシビリティ                           | 未引き取り       | 未移植 (共通基盤: デザイントークン・アクセシビリティ)                           | `lib/features/` に padding/gap/radius/elevation/icon/layout/色リテラル禁止         |
| INV-081    | 共通基盤     | 共通基盤: デザイントークン・アクセシビリティ                           | 未引き取り       | 未移植 (共通基盤: デザイントークン・アクセシビリティ)                           | 主要 7 画面が light/dark 両テーマで surface ramp から背景                          |
| INV-082    | 共通基盤     | 共通基盤: デザイントークン・アクセシビリティ                           | 未引き取り       | 未移植 (共通基盤: デザイントークン・アクセシビリティ)                           | Noto Sans JP variable（fvar、≥17000 glyphs）                                       |
| INV-083    | 共通基盤     | 共通基盤: デザイントークン・アクセシビリティ                           | 未引き取り       | 未移植 (共通基盤: デザイントークン・アクセシビリティ)                           | 数字は等幅（点数更新で横ジャンプしない）                                           |
| INV-084    | 共通基盤     | 共通基盤: デザイントークン・アクセシビリティ                           | 未引き取り       | 未移植 (共通基盤: デザイントークン・アクセシビリティ)                           | fontWeight が variable axis を駆動                                                 |
| INV-085    | 共通基盤     | 共通基盤: デザイントークン・アクセシビリティ                           | 未引き取り       | 未移植 (共通基盤: デザイントークン・アクセシビリティ)                           | 全 text role が bundled family + height                                            |
| INV-086    | 共通基盤     | 共通基盤: デザイントークン・アクセシビリティ                           | 未引き取り       | 未移植 (共通基盤: デザイントークン・アクセシビリティ)                           | 認識文字 role は body より大・letterSpacing>0                                      |
| INV-087    | 引き取り済み | 引き取り済み (Phase 2-2 / PR #225)                                     | **引き取り済み** | PR #225                                                                         | 全 surface 段で onSurface/onSurfaceVariant ≥4.5:1                                  |
| INV-088    | 引き取り済み | 引き取り済み (Phase 2-2 / PR #225)                                     | **引き取り済み** | PR #225                                                                         | Material on/role ペア ≥4.5:1                                                       |
| INV-089    | 引き取り済み | 引き取り済み (Phase 2-2 / PR #225)                                     | **引き取り済み** | PR #225                                                                         | status 色（attention/success/error）≥4.5:1 on surface                              |
| INV-090    | 引き取り済み | 引き取り済み (Phase 2-2 / PR #225)                                     | **引き取り済み** | PR #225                                                                         | disabled ボタン: outline ≥3:1、label ≥4.5:1                                        |
| INV-091    | 共通基盤     | 共通基盤: 共通UIコンポーネント                                         | 未引き取り       | 未移植 (共通基盤: 共通UIコンポーネント)                                         | Material 既定 disabled outline は AA 未達（上書き理由の実測）                      |
| INV-092    | 共通基盤     | 共通基盤: 共通UIコンポーネント                                         | 未引き取り       | 未移植 (共通基盤: 共通UIコンポーネント)                                         | filled/outlined/text 全 ButtonTheme が disabled 色を返す                           |
| INV-093    | 引き取り済み | 引き取り済み (Phase 2-2 / PR #225)                                     | **引き取り済み** | PR #225                                                                         | annotationMark は両テーマ同一・白紙 PDF 上 ≥4.5:1                                  |
| INV-094    | 引き取り済み | 引き取り済み (Phase 2-2 / PR #225)                                     | **引き取り済み** | PR #225                                                                         | dark onSurface contrast 7–13（白黒最大回避）                                       |
| INV-095    | 共通基盤     | 共通基盤: デザイントークン・アクセシビリティ                           | 未引き取り       | 未移植 (共通基盤: デザイントークン・アクセシビリティ)                           | AppStatusColors / AppTextRoles extension 必須                                      |
| INV-096    | 共通基盤     | 共通基盤: 共通UIコンポーネント                                         | 未引き取り       | 未移植 (共通基盤: 共通UIコンポーネント)                                         | AppErrorBanner: 再試行・busy 時 disable・1 回 fade-in で settle                    |
| INV-097    | 共通基盤     | 共通基盤: 共通UIコンポーネント（関連: 添削レビュー、答案キュー）       | 未引き取り       | 未移植 (共通基盤: 共通UIコンポーネント（関連: 添削レビュー、答案キュー）)       | QuestionStatus: 各状態に固有 label+icon（色だけにしない）                          |
| INV-100    | 共通基盤     | 共通基盤: 操作要件・無効理由エンジン                                   | 未引き取り       | 未移植 (共通基盤: 操作要件・無効理由エンジン)                                   | 無効操作には理由 id が 1 件以上、有効時 0 件                                       |
| INV-101    | 共通基盤     | 共通基盤: 操作要件・無効理由エンジン                                   | 未引き取り       | 未移植 (共通基盤: 操作要件・無効理由エンジン)                                   | 理由文は「。」終わり・Exception/HTTP/数字なし                                      |
| INV-102    | 共通基盤     | 共通基盤: 操作要件・無効理由エンジン                                   | 未引き取り       | 未移植 (共通基盤: 操作要件・無効理由エンジン)                                   | busy は単独でも理由になる                                                          |
| INV-103    | 画面         | 取込                                                                   | **引き取り済み** | PR #240                                                                         | intake: template 未選択→`intake-template`                                          |
| INV-104    | 共通基盤     | 共通基盤: 共通UIコンポーネント                                         | 未引き取り       | 未移植 (共通基盤: 共通UIコンポーネント)                                         | 条件充足で理由消去＋高さ 0（余白残さない）                                         |
| INV-105    | 共通基盤     | 共通基盤: 共通UIコンポーネント                                         | 未引き取り       | 未移植 (共通基盤: 共通UIコンポーネント)                                         | 理由は Tooltip ではなく visible Text                                               |
| INV-106    | 共通基盤     | 共通基盤: 共通UIコンポーネント                                         | 未引き取り       | 未移植 (共通基盤: 共通UIコンポーネント)                                         | 狭幅 700×720 で理由が画面内                                                        |
| INV-107    | 画面         | 設定                                                                   | 未引き取り       | 未移植 (設定)                                                                   | API キー: 未設定→verify 無効+理由                                                  |
| INV-108    | 共通基盤     | 共通基盤: 共通UIコンポーネント                                         | 未引き取り       | 未移植 (共通基盤: 共通UIコンポーネント)                                         | helperText と disabled reason の二重表示禁止                                       |
| INV-109    | 共通基盤     | 共通基盤: 共通UIコンポーネント                                         | 未引き取り       | 未移植 (共通基盤: 共通UIコンポーネント)                                         | Tab 順: 理由 Text は focus 取らず隣ボタン到達可能                                  |
| INV-110    | 画面         | テスト設定（Phase 3 テスト設定）                                       | 未引き取り       | 未移植 (テスト設定（Phase 3 テスト設定）)                                       | profile confirm 理由 ⊇ save 理由（部分集合）                                       |
| INV-120    | 画面         | 取込                                                                   | **引き取り済み** | PR #240                                                                         | 未確認 AI 提案がある間 import 不可                                                 |
| INV-121    | 画面         | 取込                                                                   | **引き取り済み** | PR #240                                                                         | 規則マッチファイルは AI 確認不要                                                   |
| INV-122    | 画面         | 取込                                                                   | **引き取り済み** | PR #240                                                                         | 既存テスト追記時は gradingCriteria 不要                                            |
| INV-123    | 画面         | 取込                                                                   | **引き取り済み** | PR #240                                                                         | 新規テストは criteria 必須                                                         |
| INV-124    | 画面         | 取込                                                                   | **引き取り済み** | PR #240                                                                         | 規則のみなら AI 分類 API 0 回                                                      |
| INV-125    | 画面         | 取込                                                                   | **引き取り済み** | PR #240                                                                         | 取込前に件数・概算費用表示                                                         |
| INV-126    | 画面         | 取込                                                                   | **引き取り済み** | PR #240                                                                         | 単価未設定時は費用を数字で言わない                                                 |
| INV-127    | 画面         | 取込                                                                   | **引き取り済み** | PR #240                                                                         | 完了画面は「採点できる」と言わない                                                 |
| INV-128    | 画面         | ホーム（Phase 2-4）                                                    | **引き取り済み** | PR #235                                                                         | 模範解答 PDF 要求文言なし                                                          |
| INV-129    | 画面         | ホーム（Phase 2-4）                                                    | **引き取り済み** | PR #235                                                                         | 「採点マニュアル PDF」旧呼び名なし                                                 |
| INV-130    | 画面         | 取込                                                                   | **引き取り済み** | PR #240                                                                         | 「画面はまだありません」文言なし                                                   |
| INV-131    | 画面         | 取込                                                                   | **引き取り済み** | PR #240                                                                         | 27 件目失敗でも前 26 答案残存                                                      |
| INV-132    | 画面         | 取込                                                                   | **引き取り済み** | PR #240                                                                         | 取込後 AI 採点起票経路を維持                                                       |
| INV-133    | 画面         | 取込                                                                   | **引き取り済み** | PR #240                                                                         | 起票失敗でも取込成功扱い+理由                                                      |
| INV-134    | 画面         | 取込（副: 共通基盤: API クライアント）                                 | **引き取り済み** | PR #240                                                                         | material role は wire name（`annotation_resource` 等）                             |
| INV-135    | 画面         | 取込（副: 共通基盤: API クライアント）                                 | **引き取り済み** | PR #240                                                                         | PDF upload は `application/pdf` content-type                                       |
| INV-140    | 画面         | 答案キュー                                                             | **引き取り済み** | PR #243                                                                         | キュー順: needs_review 優先、同状態は取込古い順                                    |
| INV-141    | 画面         | 答案キュー                                                             | **引き取り済み** | PR #243                                                                         | 済み答案も一覧から消さない                                                         |
| INV-142    | 画面         | 答案キュー                                                             | **引き取り済み** | PR #243                                                                         | `positionOf` は 1 始まり、未知は 0                                                 |
| INV-143    | 画面         | 答案キュー                                                             | **引き取り済み** | PR #243                                                                         | `nextAfter` は reviewed スキップ、末尾→前の未了                                    |
| INV-144    | 画面         | 答案キュー                                                             | **引き取り済み** | PR #243                                                                         | 設問進捗: partial/manual grading 表示                                              |
| INV-145    | 画面         | 答案キュー                                                             | **引き取り済み** | PR #243                                                                         | `isFullyConfirmed`: 全問確定なら state≠reviewed でも可                             |
| INV-146    | 画面         | 答案キュー                                                             | **引き取り済み** | PR #243                                                                         | 進捗不明時は export 可と言わない                                                   |
| INV-147    | 画面         | ホーム（Phase 2-4）                                                    | **引き取り済み** | PR #235                                                                         | ホーム: `ai_processed` は確認済みに数えない                                        |
| INV-148    | 画面         | ホーム（Phase 2-4）                                                    | **引き取り済み** | PR #235                                                                         | 続きは needs_review 最古優先                                                       |
| INV-149    | 画面         | ホーム（Phase 2-4）                                                    | **引き取り済み** | PR #235                                                                         | 答案キュー入口はホーム「確認済み N/M」タップのみ                                   |
| INV-150    | 画面         | ホーム（Phase 2-4）                                                    | **引き取り済み** | PR #235                                                                         | 溢れテストの要確認も fetch/表示                                                    |
| INV-151    | 画面         | 添削レビュー（副: 答案確定）                                           | **引き取り済み** | PR #244                                                                         | 設問並び: 自然順 number、page 優先                                                 |
| INV-152    | 共通基盤     | 共通基盤: ドメインロジック・設問状態（関連: 添削レビュー）             | 未引き取り       | 未移植 (共通基盤: ドメインロジック・設問状態（関連: 添削レビュー）)             | usable=false + waiting → needsCheck; 待ち無し → graded                             |
| INV-153    | 共通基盤     | 共通基盤: ドメインロジック・設問状態（関連: 添削レビュー）             | 未引き取り       | 未移植 (共通基盤: ドメインロジック・設問状態（関連: 添削レビュー）)             | 人間採点後は stopped job より review 優先                                          |
| INV-154    | 画面         | 答案確定                                                               | 未引き取り       | 未移植 (答案確定)                                                               | 未到達設問があれば確定不可、番号明示                                               |
| INV-155    | 画面         | 答案確定                                                               | 未引き取り       | 未移植 (答案確定)                                                               | 全到達後 1 操作で N 問 approve                                                     |
| INV-156    | 画面         | 答案確定                                                               | 未引き取り       | 未移植 (答案確定)                                                               | 部分失敗: 確定済み数・残り・failedNumber 表示                                      |
| INV-157    | 画面         | 答案確定                                                               | 未引き取り       | 未移植 (答案確定)                                                               | AI 採点不可設問→humanScoreRequired で確定不可                                      |
| INV-158    | 画面         | 答案キュー                                                             | **引き取り済み** | PR #243                                                                         | `review_reason` wire format パース                                                 |
| INV-159    | 画面         | 答案キュー                                                             | **引き取り済み** | PR #243                                                                         | 未知 reason は推測せず空                                                           |
| INV-160    | 画面         | 添削レビュー                                                           | **引き取り済み** | PR #244                                                                         | 要確認と失敗でヘッダー要約文字列が異なる                                           |
| INV-161    | 画面         | 添削レビュー                                                           | **引き取り済み** | PR #244                                                                         | パネル畳んでも失敗件数・次の一手・遷移ボタンが残る                                 |
| INV-162    | 画面         | 添削レビュー                                                           | **引き取り済み** | PR #244                                                                         | 下流「待ち」文言が上流理由（確認待ち vs 失敗で停止）で変わる                       |
| INV-163    | 画面         | 添削レビュー                                                           | **引き取り済み** | PR #244                                                                         | `dagFailureGuidance`: 分類ごとに次の操作が変わる                                   |
| INV-164    | 画面         | 添削レビュー                                                           | **引き取り済み** | PR #244                                                                         | 返す文言に last_error の断片（provider 名・URL・HTTP）が入らない                   |
| INV-165    | 画面         | 添削レビュー                                                           | **引き取り済み** | PR #244                                                                         | 各分類で cause と nextStep が非空。nextStep は操作名指し                           |
| INV-166    | 画面         | 添削レビュー                                                           | **引き取り済み** | PR #244                                                                         | crop_not_the_answer → 回答欄修正を促す（再判定を勧めない）                         |
| INV-167    | 画面         | 取込                                                                   | **引き取り済み** | PR #240                                                                         | GradingKickoffFailure: 409 は両可能性、404 は非 retry                              |
| INV-168    | 共通基盤     | 共通基盤: 共通UIコンポーネント（アプリシェル）                         | 未引き取り       | 未移植 (共通基盤: 共通UIコンポーネント（アプリシェル）)                         | grading unavailable banner: unavailable のみ表示                                   |
| INV-170    | 画面         | 回答欄エディタ（Phase 3 テスト設定）                                   | **引き取り済み** | PR #238                                                                         | 未検出と未割当（absent）を別グループ表示                                           |
| INV-171    | 画面         | 回答欄エディタ（Phase 3 テスト設定）                                   | **引き取り済み** | PR #238                                                                         | 該当グループのみ表示（片方だけのとき他方は出さない）                               |
| INV-172    | 画面         | 回答欄エディタ（Phase 3 テスト設定）                                   | **引き取り済み** | PR #238                                                                         | 全クリア表示は両グループ空のときのみ                                               |
| INV-173    | 画面         | 回答欄エディタ（Phase 3 テスト設定）                                   | **引き取り済み** | PR #238                                                                         | absent グループは「見つけられなかった」表現（断定しない）                          |
| INV-174    | 画面         | 回答欄エディタ（Phase 3 テスト設定）                                   | **引き取り済み** | PR #238                                                                         | 画面に実測比率・件数・% を出さない                                                 |
| INV-175    | 画面         | 回答欄エディタ（Phase 3 テスト設定）                                   | **引き取り済み** | PR #238                                                                         | 出口アクションは該当チップの直上                                                   |
| INV-176    | 画面         | 回答欄エディタ（Phase 3 テスト設定）                                   | **引き取り済み** | PR #238                                                                         | absent のみのとき描画ターゲットは absent 設問                                      |
| INV-177    | 画面         | 回答欄エディタ（Phase 3 テスト設定）                                   | **引き取り済み** | PR #238                                                                         | 読み順と設問番号が一致するとき警告なし                                             |
| INV-178    | 画面         | 回答欄エディタ（Phase 3 テスト設定）                                   | **引き取り済み** | PR #238                                                                         | 読み順食い違い時は警告表示                                                         |
| INV-180    | 画面         | 出力                                                                   | 未引き取り       | 未移植 (出力)                                                                   | 単体: progress→success + path                                                      |
| INV-181    | 画面         | 出力                                                                   | 未引き取り       | 未移植 (出力)                                                                   | `reuse_existing` は即 success                                                      |
| INV-182    | 画面         | 出力                                                                   | 未引き取り       | 未移植 (出力)                                                                   | 409 `unconfirmed_questions`→設問 id 一覧                                           |
| INV-183    | 画面         | 出力                                                                   | 未引き取り       | 未移植 (出力)                                                                   | 409 `no_room_for_score`≠未確認文言                                                 |
| INV-184    | 画面         | 出力                                                                   | 未引き取り       | 未移植 (出力)                                                                   | 未知 conflict code→sidecar message をそのまま                                      |
| INV-185    | 画面         | 出力                                                                   | 未引き取り       | 未移植 (出力)                                                                   | failed→retry で requeue                                                            |
| INV-186    | 画面         | 出力                                                                   | 未引き取り       | 未移植 (出力)                                                                   | ポーリング transient failure は progress 維持                                      |
| INV-187    | 画面         | 出力                                                                   | 未引き取り       | 未移植 (出力)                                                                   | cancelled job retry→新規 requestExport                                             |
| INV-188    | 画面         | 出力                                                                   | 未引き取り       | 未移植 (出力)                                                                   | 一括: 全問確定のみ対象、除外は理由付き                                             |
| INV-189    | 画面         | 出力                                                                   | 未引き取り       | 未移植 (出力)                                                                   | 1 件 refused でも残り続行、失敗一覧                                                |
| INV-190    | 画面         | 出力                                                                   | 未引き取り       | 未移植 (出力)                                                                   | キュー行から export（レビュー画面経由不要）                                        |
| INV-200    | 共通基盤     | 共通基盤: API クライアント                                             | 未引き取り       | 未移植 (共通基盤: API クライアント)                                             | `/healthz` は bogus token でも OK                                                  |
| INV-201    | 共通基盤     | 共通基盤: API クライアント                                             | 未引き取り       | 未移植 (共通基盤: API クライアント)                                             | 正 token で protected API 成功                                                     |
| INV-202    | 共通基盤     | 共通基盤: API クライアント                                             | 未引き取り       | 未移植 (共通基盤: API クライアント)                                             | 誤 token→401 unauthorized                                                          |
| INV-203    | 共通基盤     | 共通基盤: API クライアント                                             | 未引き取り       | 未移植 (共通基盤: API クライアント)                                             | 非 loopback URL→ArgumentError（URL/token を message に含めない）                   |
| INV-204    | 共通基盤     | 共通基盤: API クライアント                                             | 未引き取り       | 未移植 (共通基盤: API クライアント)                                             | unknown transport error→接続詳細なし                                               |
| INV-205    | 共通基盤     | 共通基盤: API クライアント                                             | 未引き取り       | 未移植 (共通基盤: API クライアント)                                             | 409→`conflictCode` + `conflictQuestionIds` 保持                                    |
| UG-01      | 共通基盤     | 共通基盤: サイドカーライフサイクル・起動ゲート                         | **引き取り済み** | PR #237                                                                         | アプリを強制終了してもサイドカーが道連れで終わる（Job Object kill-on-close）       |
| UG-02      | 共通基盤     | 共通基盤: サイドカーライフサイクル・起動ゲート                         | 未引き取り       | 未移植 (共通基盤: サイドカーライフサイクル・起動ゲート)                         | kill-on-close を設定できなかった Job は持たない（保証が有るふりをしない）          |
| UG-03      | 共通基盤     | 共通基盤: サイドカーライフサイクル・起動ゲート                         | 未引き取り       | 未移植 (共通基盤: サイドカーライフサイクル・起動ゲート)                         | Job ハンドルはプロセスの生涯閉じない（`dispose()` でも閉じない）                   |
| UG-04      | 共通基盤     | 共通基盤: サイドカーライフサイクル・起動ゲート                         | 未引き取り       | 未移植 (共通基盤: サイドカーライフサイクル・起動ゲート)                         | 子プロセスは spawn の直後に Job へ登録する（孤児化の窓を最小にする）               |
| UG-05      | 共通基盤     | 共通基盤: ナビゲーション・ルーティング                                 | 未引き取り       | 未移植 (共通基盤: ナビゲーション・ルーティング)                                 | リリースビルドは起動ルートとテーマを環境変数から取らない                           |
| UG-06      | 共通基盤     | 共通基盤: サイドカーライフサイクル・起動ゲート                         | **引き取り済み** | PR #237                                                                         | アプリは `app-data` の場所を決めない（`--app-data-dir` を渡さない）                |
| UG-07      | 共通基盤     | 共通基盤: サイドカーライフサイクル・起動ゲート                         | **引き取り済み** | PR #237                                                                         | 子プロセスの stdout/stderr を常にドレインする                                      |
| UG-08      | 共通基盤     | 共通基盤: サイドカーライフサイクル・起動ゲート                         | **引き取り済み** | PR #237                                                                         | 起動タイムアウトは 60 秒 ―― Defender の初回スキャンを待てる長さ                    |
| UG-09      | 画面         | 出力                                                                   | 未引き取り       | 未移植 (出力)                                                                   | 一括出力は既存ファイルを絶対に上書きしない（`_2`, `_3` へ逃がす）                  |
| UG-10      | 画面         | 取込（副: 共通基盤: フォルダ走査）                                     | **引き取り済み** | PR #240                                                                         | フォルダ走査は隠しファイルと OS メタデータを除き、5,000 件で打ち切る               |
| UG-11      | 画面         | 取込（副: 共通基盤: フォルダ走査）                                     | **引き取り済み** | PR #240                                                                         | 走査が返す `relativePath` は常に `/` 区切り（Windows の `\` を潰す）               |
| UG-12      | 画面         | 取込（副: 共通基盤: フォルダ走査）                                     | **引き取り済み** | PR #240                                                                         | 走査はファイル内容を外に出さない（ダイジェストだけ、しかもストリーム読み）         |
| UG-13      | 共通基盤     | 共通基盤: 共通UIコンポーネント（関連: 取込、設定）                     | 未引き取り       | 未移植 (共通基盤: 共通UIコンポーネント（関連: 取込、設定）)                     | 長いファイル名がファイル選択ボタンを画面外へ押し出さない                           |
| UG-14      | 共通基盤     | 共通基盤: サイドカーライフサイクル・起動ゲート                         | 未引き取り       | 未移植 (共通基盤: サイドカーライフサイクル・起動ゲート)                         | 失敗画面が指すログの場所が、サイドカーが実際に書く場所と一致している               |
| UG-15      | 共通基盤     | 共通基盤: サイドカーライフサイクル・起動ゲート                         | 未引き取り       | 未移植 (共通基盤: サイドカーライフサイクル・起動ゲート)                         | 待たせるときは、待つ理由（初回マイグレーションと Defender スキャン）を出す         |
