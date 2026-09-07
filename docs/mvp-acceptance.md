# MVP 受入検証 — §31 実装項目とテストの対応

GitHub Issue [#25](https://github.com/HIKARU0627/Auto-Scoring/issues/25)（[MVP 10]
MVPのE2E受入・性能・セキュリティ検証。親 [#3](https://github.com/HIKARU0627/Auto-Scoring/issues/3)）。

本書は**新機能の記録ではない**。簡易設計書 §31 が「最初のMVPで実装する」と定めた
13項目それぞれについて、**どのテストが、どこまでを、どの前提で証明しているか**を
一覧にし、自動化できなかったものを別Issueとして名指しする。#25 の受入条件

> 簡易設計書 §31 の全実装項目が自動E2Eまたは記録付き手動testに対応する。

に対する回答が §1 の表である。

---

## 1. §31 実装項目 → 検証手段

| #   | §31 の項目        | 主たる自動テスト                                                                                                                                                                                                               | 補足                                                                                                                                           |
| --- | ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | テスト登録        | `backend/tests/test_e2e_acceptance.py::test_register_take_in_three_answers_and_process_them_while_reviewing`（`register_ready_test` が登録→profile候補生成→人間修正→confirm→DAG confirm→complete-registration を実HTTPで通す） | 層単位の網羅は `test_test_registration_api.py` / `test_dependency_graph_api.py`                                                                |
| 2   | 模範解答PDF読込   | 同上（`POST /tests` の `model_answer`）。`MODEL_ANSWER` regionが `Question.model_answer` になり、無ければ採点自体が拒否されることまで通る                                                                                      | `test_test_intake.py`, `test_grading_processor.py`                                                                                             |
| 3   | マニュアルPDF読込 | 同上（`POST /tests` の `manual`）。`RUBRIC` regionが `Rubric` になり、無ければ採点が拒否される                                                                                                                                 | 同上                                                                                                                                           |
| 4   | 生徒答案PDF読込   | 同上（`upload_answer` → 実PDFレンダリング + 実OpenCV前処理 → 回答欄crop）                                                                                                                                                      | `test_api_submissions.py`, `test_submission_intake_service.py`                                                                                 |
| 5   | PDF表示           | `app/test/pdf_review_page_test.dart::Issue #25: 受入 -- 幅・focus・accessibility label`（desktop標準幅/狭幅の両方で `PdfViewer` が出る）                                                                                       | 座標の正しさは同ファイルの overlay 系テスト（**Linuxでは pdfium 未同梱のため8件失敗。§4**）                                                    |
| 6   | AI文字認識        | `test_e2e_acceptance.py::test_register_..._while_reviewing`（全設問がOCRされ `RecognitionResult` になる）、`::test_a_failing_ocr_provider_fails_the_job_and_a_human_retry_recovers_it`                                         | 低Confidence時の扱いは `::test_a_low_confidence_reading_is_held_for_a_human_and_never_auto_confirmed`                                          |
| 7   | AI採点            | `test_e2e_acceptance.py::test_register_..._while_reviewing`、`::test_a_failing_ai_provider_fails_the_job_with_its_own_classified_reason`                                                                                       | 設問依存を含む順序制御は `test_e2e_dag_parallelism.py` 全体                                                                                    |
| 8   | 点数表示          | `app/test/pdf_review_page_test.dart::shows recognition, score, rationale, rubric, and dual confidence ...`                                                                                                                     | 出力側は #13 の `test_the_exported_pdf_carries_the_reviewed_score`（確定した点数がPDFのテキスト層に載ることを確認）                            |
| 9   | ○×表示            | `app/test/pdf_review_page_test.dart::places a target-anchored annotation on the PDF overlay ...` ほか overlay 系                                                                                                               | 位置不明時の退避は `test_e2e_acceptance.py::test_an_annotation_whose_target_text_is_not_on_the_page_falls_back_to_the_comment_area`            |
| 10  | コメント表示      | `app/test/pdf_review_page_test.dart::shows the AI grade comment (総評コメント), distinct from the rationale`                                                                                                                   | 出力側は #13 と同じ                                                                                                                            |
| 11  | AI結果修正        | `test_e2e_acceptance.py::test_correcting_approving_and_undoing_leaves_a_complete_history`、`app/test/pdf_review_page_test.dart::Issue #22: ... 修正 ...`                                                                       | 履歴とUndoの詳細は `test_review_api.py` / `docs/review-edit-history.md`                                                                        |
| 12  | AI結果承認        | 同上（`review/approve` と Undo を含む1本）、`app/test/pdf_review_page_test.dart::Issue #22: ... 承認して次へ ...`                                                                                                              | 承認なしに確定しないことは #6 の低Confidenceテストが背理で示す                                                                                 |
| 13  | 添削済みPDF出力   | `test_e2e_acceptance.py::test_exporting_a_fully_reviewed_answer_never_touches_the_original_pdf`、`::test_export_is_refused_while_any_question_is_still_unconfirmed`                                                            | 文字描画を伴う出力は `::test_the_exported_pdf_carries_the_reviewed_comment_text` と `::test_the_exported_pdf_carries_the_reviewed_score`（§4） |

§31 に**未対応の項目は無い**。ただし 5・8・9・10・13 の一部は、Linux 上では実行できない
（§4）。「記録付き手動test」で埋めているのは §6 の #53 のみ。

---

## 2. 検証の境界 — なぜ provider が差し替えてあるか

Issue #25 本文の「検証の境界」に従い、**通常CIは dummy / scripted provider で完全に
再現可能**にした。`backend/tests/test_e2e_acceptance.py` は

- **実物**: `create_app` + `TestClient`(lifespan起動) / 実SQLite / 実 `LocalFileStore` /
  実PDFレンダリング / 実OpenCV前処理 / 実 `JobQueueService` / 実 `GradingJobProcessor`
- **差し替え**: `OCRProvider` と `AIProvider` だけ

という構成である。この2つを差し替えるのは、**そこに置くべきものがまだ決まっていない**から:
`docs/business-rules-and-evaluation-data.md` §3 の判断事項 **A（OCRサービス）**と
**B（AIモデル）**は未決定で、判断者はプロジェクトオーナー、実APIキーも未提供。
§3.1 は確定前に特定providerのSDK・レスポンス形式へ依存した実装を進めることを禁じている。

live provider での疎通・schema・cleanup 検証は **#54** に切り出した。

**scriptの鍵は回答欄のcropバイト列**である。これは実装の都合ではなく §2 (2) そのもの:
providerへ渡るものに生徒識別情報・ファイル名・submission idが一切含まれないため、
**テストから見ても答案を区別できるのはcropしかない**。
`test_no_student_identifying_data_reaches_either_provider` がこれを実payloadに対して直接assertする。

---

## 3. 決定論 — 時間に依存するassertionを書かないための方針

`docs/job-queue.md`「Linux環境で…決定的に失敗していた原因（Issue #50）」の記録に従う。
本Issueで追加したテストは次を守っている。

- **provider の結果は `start()` 前にすべて確定させる**。実行途中でテストが結果を差し替えない。
- **並列実行の証明に実時間を使わない**。`tests/fakes.py` の `FakeJobProcessor` が
  jobごとの開始/終了を**単調増加のイベントカウンタ**（`ProcessingSpan`）で記録し、
  依存順（`before.finished < after.started`）と重なり（`overlaps`）をその上で判定する。
  実時刻でも `FakeClock` の仮想時刻でもないのは、前者がレースになり、後者は
  「誰かがsleepしないと進まない」ため同時実行中の2 jobを区別できないからである。
- **「並列に動いた」を積極的に証明する**。`FakeJobProcessor(release_at_concurrency=N)` は
  N個が同時に処理中になるまでラッチを開かない。直列化するキューはラッチを開けられず
  **失敗する**——「上限を超えなかった」という直列実行でも成立する弱い条件に逃げない。
  ラッチは開かないまま一定時間で諦めて全員を通す（`latch_timed_out`）。永久に待つと
  キューの不具合がテストの**ハング**になり、失敗より始末が悪いため。
- **実時間のポーリングは失敗を打ち切るためだけに使う**。`wait_until_settled` の timeout は
  「落ちるまでの上限」であって、通るassertionがその値に依存することはない。
  再試行待ちの一時的な FAILED を終状態と誤認しないよう、判定は
  `RetryPolicy.should_retry` と同じ規則を使う。

追加した17テスト（backend）は Ubuntu 上で連続実行し、いずれもflakeしないことを確認した
（DAG側4件×25回、E2E全体×8回）。

---

## 4. プラットフォーム差 — Linuxでの実行

MVPの対象OSは Windows のみ（§2 (1)）で、CIは `windows-latest` で回る
（`docs/quality-gates.md`）。開発は一部 Ubuntu 上で行うため、**両OSで同じ検証強度が
得られること**を要件として扱う。Issue #60 以前は Linux で常に21件が失敗しており、
変更のたびに「既知の失敗か新規の失敗か」を人手で選り分ける必要があった。

### 4.1 解消した21件（Issue #60）

| 対象                                                                                   | 件数 | 原因                                                                                                                                                                      | 対処                                                                                                      |
| -------------------------------------------------------------------------------------- | ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| `test_export_processor.py` / `test_export_api.py` / `test_pdf_annotation_rendering.py` | 13   | `JapaneseFontNotFoundError`。PDF出力の文字描画はWindows同梱の日本語フォントを使う（`pdfium_pypdf_engine._JAPANESE_FONT_CANDIDATES`、`docs/pdf-export.md`）                | Issue #25 が `test_e2e_acceptance.py` に実装した手法を `backend/tests/font_support.py` へ切り出して横展開 |
| `app/test/pdf_review_page_test.dart` の overlay 系                                     | 8    | `flutter test` が pdfium を解決できない。`pdfium_dart` はビルド済みFlutterアプリの隣か `.dart_tool/native_assets.yaml` しか見ず、Linux の `flutter test` にはどちらも無い | build hook が実際にダウンロード済みの `libpdfium.so` を `Pdfrx.pdfiumModulePath` へ渡す                   |

どちらも**assertionは一切変えていない**。Windows では従来どおり本番の解決経路が使われ、
フォント候補への追記も pdfium のパス指定も起きない。

### 4.2 フォント解決の方針（`backend/tests/font_support.py`）

- Windows 同梱フォントが1つも無い環境でのみ、**そのテストが実際に必要とするグリフを
  持つ**ローカルフォントを候補リストの**末尾へ追記**する。Windows では本物が先に
  見つかるので何も起きない。
- 「必要とするグリフ」は、そのテストの**assertionが依存する文字**であって、fixture が
  ページに描くもの全部ではない。出力のパス・sha256・冪等性を見るテストは、隣に描かれた
  点数がグリフになったか notdef になったかを問わない。ここを広く取ると、本来ちゃんと
  検証できるテストまで skip になる。
- どのフォントでも描けないときだけ `pytest.skip` する。assertion を緩めて緑にはしない。
- reportlab のフォント登録はプロセス全体で名前をキーに持たれ、同名の再登録は黙って
  無視される。そのため `lru_cache` だけでなく `pdfmetrics._fonts` も落とす
  （`forget_registered_font`）。これを `backend/tests/conftest.py` の autouse fixture で
  **全テスト共通**にしてあり、先に走ったモジュールが後続のフォントを決めてしまうことは無い。

### 4.3 Ubuntu 側の必要フォント（skip は 0 件）

素の Ubuntu イメージには**日本語と Latin を同時に描けるフォントが無い**。
`DroidSansFallbackFull` は唯一の漢字対応 TrueType だが数字を一切持たず、`DejaVuSans` は
その逆で、同梱の Noto CJK は CFF アウトラインなので reportlab の `TTFont` が読めない。
そのため、**同一ページに点数と日本語コメントの両方を描いて両方を検証する**次の2件は、
両方のグリフを持つ1つのフォントを要求する。

| テスト                                                                                                   | 要求するグリフ                                                                                    |
| -------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| `test_pdf_annotation_rendering.py::test_score_and_long_japanese_comment_text_render_within_their_rects`  | 点数と長文日本語コメントが**同時に**それぞれのrect内へ描かれること                                |
| `test_export_processor.py::test_repair_regenerates_from_the_recorded_snapshot_not_a_later_review_change` | 修復生成されたPDFの点数が記録時のスナップショット（`4/5`）であり、後から入った `2/5` ではないこと |

Ubuntu 開発機には **`fonts-ipafont-gothic` を導入済み**
（[orca-remote-environment.md](./orca-remote-environment.md) §8.1）。IPAゴシックは日本語と
Latin/数字の両方を持ち `font_support.py` の候補にも入っているため、上記2件も実行され、
**skip は 0 件**になる。導入していない環境ではこの2件だけが skip され、その分は Windows
CI でのみ検証されることになる（skip の理由はメッセージに出る）。

なお Issue #25 の時点で、点数とコメントの文字描画を伴う受入テストを2本に分けてある
（`test_the_exported_pdf_carries_the_reviewed_comment_text` / `::_the_reviewed_score`）。
分けたのは同じ理由 —— 1本のままだとフォントの無い Linux では必ず skip になるからで、
分けたことで**両OSで実行される**。以前は `skipif` で Windows 限定にしていたが、
**ローカルで一度も走らないテストだったために assertion が `exists()` と `size > 0` のまま
気づかれず残っていた**（レビュー ラウンド1 P2-1）。走らせられるようにしたこと自体が
その再発防止である。

### 4.4 件数

| スイート | Issue #60 以前（`origin/main`）            | 現在（Ubuntu, 2026-09-07）         |
| -------- | ------------------------------------------ | ---------------------------------- |
| backend  | 1049 passed / 13 failed（既知）/ 0 skipped | 1062 passed / 0 failed / 0 skipped |
| Flutter  | 157 passed / 8 failed（既知）              | 176 passed / 0 failed              |

Flutter の総数が増えているのは Issue #57（#58）が
`sidecar_supervisor_integration_test.dart` へテストを追加したため。

`pnpm run check` 全体は依然として Ubuntu では完走しない。`build:app`
（`flutter build windows`）と `openapi:check`（Java 必須）が残るためで、これは
テストの問題ではない（[orca-remote-environment.md](./orca-remote-environment.md) §8）。

---

## 5. 性能測定 — 判断事項E の判断材料であって、基準の決定ではない

> **ここに書かれた数値は決定ではない。** 並列AI処理数は
> `docs/business-rules-and-evaluation-data.md` §3 の**判断事項E（未決定）**であり、
> 判断者はプロジェクトオーナー（@HIKARU0627）である。`max_concurrency=2` は
> 同§が自ら「暫定」と明記した既定値にすぎない。確定作業は **#55**。

再現コマンド（`backend/` から。完全に合成データ、認証情報不要）:

```bash
uv run python poc/issue_25_queue_throughput/report.py
uv run python poc/issue_25_queue_throughput/report.py --answers 6 --latency 1.0
```

**暫定値 `max_concurrency=2` を含む、並列度ごとの測定。** 擬似provider遅延 0.05 s/呼び出し、
答案12件 × 設問2（1設問 = OCR 1回 + AI 1回）:

| 並列度            | 取込 合計(s) | キュー処理 合計(s) | 1答案あたり(s) | スループット(答案/分) | エラー率 |
| ----------------- | ------------ | ------------------ | -------------- | --------------------- | -------- |
| 1                 | 13.48        | 2.65               | 0.221          | 271.8                 | 0.00     |
| **2（暫定既定）** | 13.38        | **1.35**           | **0.113**      | **532.1**             | **0.00** |
| 3                 | 13.50        | 0.89               | 0.074          | 810.2                 | 0.00     |
| 4                 | 13.63        | 0.68               | 0.057          | 1058.6                | 0.00     |

擬似provider遅延 1.0 s/呼び出し、答案6件 × 設問2:

| 並列度            | 取込 合計(s) | キュー処理 合計(s) | 1答案あたり(s) | スループット(答案/分) | エラー率 |
| ----------------- | ------------ | ------------------ | -------------- | --------------------- | -------- |
| 1                 | 6.76         | 24.12              | 4.020          | 14.9                  | 0.00     |
| **2（暫定既定）** | 6.71         | **12.07**          | **2.012**      | **29.8**              | **0.00** |
| 3                 | 6.84         | 8.06               | 1.343          | 44.7                  | 0.00     |
| 4                 | 6.74         | 6.05               | 1.008          | 59.5                  | 0.00     |

読み取れること:

- キュー機構自体はほぼ線形にスケールする（並列1比で並列4が3.90〜3.99倍）。
  **並列度の上限を決めるのはキュー側のオーバーヘッドではなく外部providerのレート制限**であり、
  それは採用provider（判断事項A・B）が決まるまで存在しない。
- **エラー率は常に 0.00**。決定論的な擬似providerには失敗する要因が無いため、この列は
  「測れていない」と読むのが正しい。意味のあるエラー率は実providerでの実測（#54・#35）を要する。
- 副次的な発見: **取込が1答案あたり約1.1秒かかり、並列度の影響を受けない**。
  PDFレンダリングが `pdfium_lock` で直列化されているため（`api/app.py` の意図した設計）。
  答案件数が増えると、AI並列度よりも取込が支配的になる領域がある。E を判断する際は
  「AI並列度を上げても全体時間がそれほど縮まない答案件数がある」ことを併せて考慮されたい。

### 5.1 「UIが操作可能なまま」の代替検証

受入条件は「**決定済み性能基準の答案件数**で、UIが操作可能なままqueueが処理を完了する」だが、

- **答案件数**: 決定済み基準が存在しない（#55）。上表は合成データの任意件数である。
- **「UIが操作可能なまま」**: backendテストに操作すべきUIは無い。**代替として、キュー処理が
  実際に進行中である間、sidecarがreview系エンドポイントへ応答し続けることを検証**した
  （`test_register_take_in_three_answers_and_process_them_while_reviewing`）。
  「進行中である間」を確実にするため、後続答案のOCR呼び出しをラッチで止め、
  同時実行数が設定値に達したことを確認してからレビュー読み取りを行っている——
  scripted providerは即座に返るので、単に同時投入しただけでは
  レビュー要求が飛ぶ前にキューが空になり、何も証明しない。

**これは代替検証である。** UI自体の応答性は #53 の clean VM 手動受入で確認する。

---

## 6. 未達項目 — 別Issueに切り出したもの

Issue #25 本文の

> 未達項目は曖昧な「今後対応」にせず、再現手順・影響・blockする受入条件を別Issueにする。

に従い、次の3件を独立したIssueにした。いずれも本PRのスコープ外である。

| Issue                                                       | 内容                                           | 何が決まれば着手できるか                                                  |
| ----------------------------------------------------------- | ---------------------------------------------- | ------------------------------------------------------------------------- |
| [#53](https://github.com/HIKARU0627/Auto-Scoring/issues/53) | clean Windows VM でのE2E受入（人間作業）       | clean な Windows 11 VM。A/B/C/E の確定は不要                              |
| [#54](https://github.com/HIKARU0627/Auto-Scoring/issues/54) | live OCR/AI provider での疎通・schema・cleanup | 判断事項 **A**・**B** の確定 + 実APIキー                                  |
| [#55](https://github.com/HIKARU0627/Auto-Scoring/issues/55) | 判断事項 **E** と性能基準の答案件数の確定      | A・B の確定と #35（本番規模データでのAI採点実測）。#35 自体が実データ待ち |

---

## 7. セキュリティ検証で「生徒識別情報」として扱ったもの

`docs/business-rules-and-evaluation-data.md` §2 (2) は種別（氏名・生徒ID・出席番号・
学校名・答案ファイル名）を列挙するが、assertionには具体的な値が要る。
`test_no_student_identifying_data_reaches_either_provider` が実際に検査するのは:

| 検査対象                                                | 扱い                                                                                                                                 |
| ------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| `student_label`（例: `3年B組 山田太郎`）                | **禁止**。`GradingRequest` の全テキストフィールドに現れないこと                                                                      |
| `submissionId`                                          | **禁止**。§2 (13) の内部識別子で、答案1通＝生徒1人に対応するため                                                                     |
| 答案PDFのファイル名                                     | **禁止**。§2 (2) が明示                                                                                                              |
| 当該設問以外の `question_id`                            | **禁止**。1回の送信は1設問分（§2 (2)「同一答案の無関係な設問」）                                                                     |
| `testId`（および `questionId` / criterion id の接頭辞） | **許可**。生徒ではなくテストを識別する。設問idとrubric criterion idが構造上これを含むため不可避                                      |
| ページ全体のラスタ画像                                  | **禁止**。氏名欄を含むため（§2 (2)）。送られたバイト列が回答欄cropと一致し、ページ画像と一致せず、かつページ画像より小さいことを確認 |

ログ側（§28、`test_neither_the_api_token_nor_the_answer_body_is_written_to_the_log`）は、
登録→取込→認識→採点→レビューの1周をDEBUGレベルで捕捉し、**APIトークン・答案本文・
`student_label`** のいずれも記録に現れないことを確認する。
`_RedactingFilter` が「出てしまったトークンを消す」ことは `test_sidecar.py` が既に担保しており、
ここが足すのは「そもそもそういう記録を出さない」ほうである。

CI artifact については、`docs/windows-distribution.md` §9 が構成上の保証を記録している
（`packaging/auto-scoring-sidecar.spec` の `datas` と `installer/auto-scoring.iss` の
`[Files]` がビルド出力しか参照せず、`.env*` を一切拾わない）。

---

## 8. 上位ドキュメントへの反映

| 文書                                    | 反映内容                                                      |
| --------------------------------------- | ------------------------------------------------------------- |
| `business-rules-and-evaluation-data.md` | §3 (E) に本書 §5 の測定結果と #55 への参照を追記              |
| `job-queue.md`                          | 決定論方針（本書 §3）は同書のIssue #50 の記録を前提にしている |
| `windows-distribution.md` §10           | clean VM 受入の実施は #53                                     |
| `backend/poc/README.md`                 | 性能測定プローブの実行方法                                    |
