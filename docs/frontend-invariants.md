# フロントエンド不変条件 — `app/test` からの棚卸し

GitHub Issue [#204](https://github.com/HIKARU0627/Auto-Scoring/issues/204)（親 [#201](https://github.com/HIKARU0627/Auto-Scoring/issues/201) Flutter → Electron 移行）。

**この文書の目的:** `app/test` が固定している振る舞いを、実装が書き直されても失われない形で外に出す。
要約ではなく、**移植先（Electron）のテストが再現すべき約束の正本**である。

## 0. 棚卸しの範囲と件数

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

## 14. Electron 移行時の使い方

1. **新画面・新コンポーネントを足す前に** §1 の INV-201 と §3 の INV-020 を確認する。
2. **画面移植 PR** は、その画面に関係する INV を Vitest/Playwright で再固定する。INV ID を PR 説明に書く。
   本一覧は各 PR が INV 番号で参照する正本であり、170 件を画面ごとの PR で積み上げて覆う運用の詳細は
   [`frontend-migration.md`](./frontend-migration.md) §3「不変条件の引き取りを PR で積み上げる」。
3. **PoC 6（#202）完了後**、§5 の座標系 INV は選択した PDF 表示方式でも同じ許容誤差（0.004）で再検証する。
4. 本一覧は **網羅の終点ではない**。`app/test` にテストが増えたら同 PR で本書も更新する。

関連: [`frontend-migration.md`](./frontend-migration.md)、[`design-tokens.md`](./design-tokens.md)、[`mvp-acceptance.md`](./mvp-acceptance.md) §1（フロント検証の対応表）。
