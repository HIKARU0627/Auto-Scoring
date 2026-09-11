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

> **⚠ 本表は Issue #95 より前の §31（旧 13 項目）に対する記録である。**
> Issue #95 で §31 の実装項目が差し替わった（決定 1〜10）。**本表は旧項目の受入状況を
> 示すものであって、現行 §31 を満たしていることを示さない。**
> **#95 で追加・変更された項目は §1.1 に「未対応」として分けてある。**

| #   | §31 の項目                                 | 主たる自動テスト                                                                                                                                                                                                               | 補足                                                                                                                                                                                                                                 |
| --- | ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1   | テスト登録                                 | `backend/tests/test_e2e_acceptance.py::test_register_take_in_three_answers_and_process_them_while_reviewing`（`register_ready_test` が登録→profile候補生成→人間修正→confirm→DAG confirm→complete-registration を実HTTPで通す） | 層単位の網羅は `test_test_registration_api.py` / `test_dependency_graph_api.py`                                                                                                                                                      |
| 2   | 模範解答PDF読込（**#95 で §31 から削除**） | 同上（`POST /tests` の `model_answer`）。`MODEL_ANSWER` regionが `Question.model_answer` になり、無ければ採点自体が拒否されることまで通る                                                                                      | `test_test_intake.py`, `test_grading_processor.py`                                                                                                                                                                                   |
| 3   | マニュアルPDF読込                          | 同上（`POST /tests` の `manual`）。`RUBRIC` regionが `Rubric` になり、無ければ採点が拒否される                                                                                                                                 | 同上                                                                                                                                                                                                                                 |
| 4   | 生徒答案PDF読込                            | 同上（`upload_answer` → 実PDFレンダリング + 実OpenCV前処理 → 回答欄crop）                                                                                                                                                      | `test_api_submissions.py`, `test_submission_intake_service.py`                                                                                                                                                                       |
| 5   | PDF表示                                    | `app/test/pdf_review_page_test.dart::Issue #25: 受入 -- 幅・focus・accessibility label`（desktop標準幅/狭幅の両方で `PdfViewer` が出る）                                                                                       | 座標の正しさは同ファイルの overlay 系テスト（**Linuxでは pdfium 未同梱のため8件失敗。§4**）                                                                                                                                          |
| 6   | AI文字認識                                 | `test_e2e_acceptance.py::test_register_..._while_reviewing`（全設問がOCRされ `RecognitionResult` になる）、`::test_a_failing_ocr_provider_fails_the_job_and_a_human_retry_recovers_it`                                         | 低Confidence時の扱いは `::test_a_low_confidence_reading_is_held_for_a_human_and_never_auto_confirmed`                                                                                                                                |
| 7   | AI採点                                     | `test_e2e_acceptance.py::test_register_..._while_reviewing`、`::test_a_failing_ai_provider_fails_the_job_with_its_own_classified_reason`                                                                                       | 設問依存を含む順序制御は `test_e2e_dag_parallelism.py` 全体                                                                                                                                                                          |
| 8   | 点数表示                                   | `app/test/pdf_review_page_test.dart::shows recognition, score, rationale, rubric, and dual confidence ...`                                                                                                                     | 出力側は #13 の `test_the_exported_pdf_carries_the_reviewed_score`（確定した点数がPDFのテキスト層に載ることを確認）                                                                                                                  |
| 9   | ○×表示                                     | `app/test/pdf_review_page_test.dart::places a target-anchored annotation on the PDF overlay ...` ほか overlay 系                                                                                                               | 位置不明時の退避は `test_e2e_acceptance.py::test_an_annotation_whose_target_text_is_not_on_the_page_falls_back_to_the_comment_area`                                                                                                  |
| 10  | コメント表示                               | `app/test/pdf_review_page_test.dart::shows the AI grade comment (総評コメント), distinct from the rationale`                                                                                                                   | 出力側は #13 と同じ                                                                                                                                                                                                                  |
| 11  | AI結果修正                                 | `test_e2e_acceptance.py::test_correcting_approving_and_undoing_leaves_a_complete_history`、`app/test/pdf_review_page_test.dart::Issue #22: ... 修正 ...`                                                                       | 履歴とUndoの詳細は `test_review_api.py` / `docs/review-edit-history.md`。**AI が採点結果を出さなかった設問**を人が採点する経路は `test_review_api.py::test_a_question_with_no_ai_grade_can_be_graded_by_a_person` ほか（Issue #118） |
| 12  | AI結果承認                                 | 同上（`review/approve` と Undo を含む1本）、`app/test/pdf_review_page_test.dart::Issue #22: ... 承認して次へ ...`                                                                                                              | 承認なしに確定しないことは #6 の低Confidenceテストが背理で示す                                                                                                                                                                       |
| 13  | 添削済みPDF出力                            | `test_e2e_acceptance.py::test_exporting_a_fully_reviewed_answer_never_touches_the_original_pdf`、`::test_export_is_refused_while_any_question_is_still_unconfirmed`                                                            | 文字描画を伴う出力は `::test_the_exported_pdf_carries_the_reviewed_comment_text` と `::test_the_exported_pdf_carries_the_reviewed_score`（§4）                                                                                       |

**旧 §31（13 項目）に未対応の項目は無い。** ただし 5・8・9・10・13 の一部は、
Linux 上では実行できない（§4）。「記録付き手動test」で埋めているのは §6 の #53 のみ。

**これは「現行の §31 を満たしている」という意味ではない**（§1.1）。

### 1.1 Issue #95 で §31 に追加・変更された項目 — **いずれも未対応**

下記は **Issue #95（docs のみの変更）で仕様に入った項目**であり、
**実装も自動テストも存在しない。** 既存テストがこれらを受入済みにしているわけではない。

| §31 の項目                                | 状況       | 参照                                                |
| ----------------------------------------- | ---------- | --------------------------------------------------- |
| 採点基準PDF読込（模範解答PDFの置換）      | **未対応** | 簡易設計書 §4.1（決定 1）                           |
| 添削資料（Word / Excel）読込              | **未対応** | 簡易設計書 §4.2（決定 3）                           |
| 資料の役割判定・構造抽出（LLM）と人の確認 | **未対応** | 簡易設計書 §4.3（設計方針）                         |
| 抽出失敗時の全項目手入力                  | **未対応** | 簡易設計書 §4.4（決定 8）                           |
| 答案からの回答欄解析                      | **未対応** | 簡易設計書 §6.2（決定 2）                           |
| テスト登録と答案取込の 1 操作への統合     | **未対応** | 簡易設計書 §6.3（決定 9）                           |
| ディレクトリごとの取り込み（オプション）  | **未対応** | 簡易設計書 §6.3.2（決定 9）                         |
| 設問ごとの点数 ＋ **合計点**の出力        | **未対応** | 簡易設計書 §14.1（決定 5）                          |
| 数式・英作文・図・グラフの採点            | **未対応** | 簡易設計書 §33.1（決定 10）。**実現可能性も未検証** |

> **本表は #101 / #103 / #105 のマージ前の状態である（2026-09-09 追記）。**
> 上記のうち「答案からの回答欄解析」「抽出失敗時の全項目手入力」「ディレクトリごとの
> 取り込み」「採点基準PDF読込」に相当する経路は実装され、**その経路を取込から
> PDF出力まで通す end-to-end テストが `backend/tests/test_e2e_intake_to_export.py`
> にある**（Issue #116。§2.1）。ただし本表の各行を「対応済み」に書き換えるには、
> テストの有無ではなく **§31 の項目そのものを満たしているか**の再監査が要る。
> それは本表の更新Issueで行う。ここでは**表が古いという事実だけ**を記録する。

**既存実装との食い違いで、見直しが要ると分かっているもの**:

| 箇所                                                       | 内容                                                                                                                                                                                                                                                                             |
| ---------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `test_no_student_identifying_data_reaches_either_provider` | **見直し不要と判明**（2026-09-09）。採点は回答欄の切り出しのみという現行仕様と一致する（§7）。回答欄の検出はページ全体を送る別経路（Issue #105）で、このテストの対象ではない                                                                                                     |
| OCR を前提にした採点処理                                   | 決定 10 で OCR は採点の前提から外れた（簡易設計書 §8.1）。OCR 失敗で採点を止めない                                                                                                                                                                                               |
| `RecognitionResult` の「誰が読んだか」                     | 採点AIの読み取りは既にOCRとは別レコードで保存されている（`grading_processor.py`）が、**`source` は両方とも `ai`** で、区別は id 接頭辞 `grading-recognition:` だけが担っている。§8.1.3 の照合をUIで行うには**どちらが読んだかを明示的に持たせる見直しが要る**（簡易設計書 §9.2） |

---

## 2. 検証の境界 — なぜ provider が差し替えてあるか

Issue #25 本文の「検証の境界」に従い、**通常CIは dummy / scripted provider で完全に
再現可能**にした。`backend/tests/test_e2e_acceptance.py` は

- **実物**: `create_app` + `TestClient`(lifespan起動) / 実SQLite / 実 `LocalFileStore` /
  実PDFレンダリング / 実OpenCV前処理 / 実 `JobQueueService` / 実 `GradingJobProcessor`
- **差し替え**: `OCRProvider` と `AIProvider` だけ

という構成である。この2つを差し替えるのは、**そこに置くべき実アダプタがまだ無い**から:
`docs/business-rules-and-evaluation-data.md` §3 の判断事項 **A（OCRサービス）**と
**B（AIモデル）**は Issue #81 で確定した（A: Google Document AI、B: 優先度つきフォールバック）
が、実アダプタは未実装で実APIキーも未提供である。確定後も §3.1 は特定providerの
SDK・レスポンス形式への依存を`OCRProvider`/`AIProvider`の内側に閉じることを求める。

live provider での疎通・schema・cleanup 検証は **#54** に切り出した。

**scriptの鍵は回答欄のcropバイト列**である。これは実装の都合ではなく §2 (2) そのもの:
providerへ渡るものに生徒識別情報・ファイル名・submission idが一切含まれないため、
**テストから見ても答案を区別できるのはcropしかない**。
`test_no_student_identifying_data_reaches_either_provider` がこれを実payloadに対して直接assertする。

### 2.1 新しい登録経路の end-to-end（Issue #116）

`test_e2e_acceptance.py` が通すのは **#101 以前の登録経路**である（`POST /tests` ＋
手書きの `PUT /profile`）。#101 / #103 / #105 が入れた経路——取込の計画 → 配点と
採点基準の抽出・確定 → 回答欄の検出・確定 → `ready`——は、それぞれ層単位のテストは
あったが、**採点・レビュー・出力と繋がったテストが1本も無かった**。
`backend/tests/test_e2e_intake_to_export.py` がその交点である。

差し替えの範囲は #25 より広い。**外部サービスだけ**という原則は同じだが、
新経路は外部サービスを4つ使うため、内訳を明示しておく。

| 差し替えたもの         | 理由                                                                  |
| ---------------------- | --------------------------------------------------------------------- |
| 採点基準の抽出         | 判断 B の provider。実物は非決定的で、#95 が人の確認を必須にした理由  |
| 回答欄検出             | 同上。出力は実物の `parse_answer_area_detection` を通している         |
| OCR                    | 判断 A。実アダプタは #114 で入ったが、live 疎通は #54（§2）           |
| AI採点                 | 判断 B。同上                                                          |
| 資料の役割判定（分類） | **呼ばれない。** fixture のファイル名は全てテンプレート規則に一致する |

**このリポジトリの実装は1つも差し替えていない。** `Question` / `Rubric` /
`Profile` / `DependencyGraph` はいずれも、それを書くエンドポイントが書いている。
`test_answer_area_registration_flow.py` が #101 / #103 の未マージ中に行っていた
DB直書きの代替も、同じIssueで外して実経路に繋いだ。

**OCR未注入（出荷される姿）の記録**: `create_app` に OCR provider を渡さないと
`UnconfiguredOCRProvider` が入る。`AUTO_SCORING_DOCUMENT_AI_PROCESSOR` を設定して
いない端末が実際に走らせる姿であり、**壊れた設定ではなくサポートされた設定**である
（簡易設計書 §24「OCR失敗: **採点は止めない。**」）。同モジュール末尾の3本が
その現実を固定している。

- 依存エッジが無ければ、採点結果は残り、人が全設問を確認すれば**出力まで到達する**。
- 依存エッジがあっても、**後続設問は人を待たずに動く**。OCR の読み取りが存在しない
  端末には比較すべき Recognition Confidence が無いため、ゲートは採点AI自身の
  読み取りと Grading Confidence の2つになる
  （`docs/ocr-recognition-pipeline.md` §8.2）。
- **ただし OCR が読んだうえで自信が無かった場合は、従来どおり止まる。**
  `resume` で人が開けるまで後続は動かない（業務ルール §4.4）。3本目がこれを固定する。
  「この端末に OCR が無い」と「OCR が読めなかった」は別の事実であり、前者を
  緩めたことで後者まで緩んでいないことを、2本を並べて走らせることで示している。

> **この節は Issue #114 で書き換えた。** それ以前は `NullOCRProvider` が
> confidence 0.0 を返すため**全設問が `usable=False`** になり、依存エッジのある
> 設問は `resume` を押すまで `blocked` のままだった。当時の記述は「動くはず」ではなく
> 「いまこうなる」を写したもので、判断を #114 に預けていた。#114 がそれを変えたので、
> 予告どおりテストが落ち、テストと本節を新しい現実に合わせた。

**「OCR が直れば全部流れる」という意味ではない。** ここで言えるのは
**OCR が無いことでは連鎖が止まらなくなった**ことだけである。実データでの試走では
別の理由（採点 provider の恒久失敗 #117 / #121、回答欄の検出ずれ #122）で止まる
設問が観測されており、それらは本節の対象外である。

### 2.2 live provider 検証 — 実機検証 #6 と #10 の実測

実 provider へ実際にデータを送る **live 実測の再現手順**は
`docs/quality-gates.md` の「Provider cleanup の検査と live 実測の再現手順（Issue #54）」
にある。**本節は再現手順を重複して書かず、その手順で得られた実測の記録だけを残す。**
実データの内容（答案・設問文・解答文・赤入れの文言・教科名・ファイル名）は一切書かない。
件数・比率・秒・費用だけを載せる。

#### 出典

| 出典                                                           | 内容                                                                                                            | 参照                                                                                   |
| -------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| 実機検証 #6                                                    | 2026-09-10、main `23fb26a`。GUI を使わず `auto-scoring-sidecar` の HTTP API を直接叩いた run                    | Issue [#3](https://github.com/HIKARU0627/Auto-Scoring/issues/3) の 2026-09-10 コメント |
| 実機検証 #10                                                   | 2026-09-11、main `3e51d3f` のビルド。Electron の画面操作で 11 教科の登録段取りを通した run                      | Issue [#3](https://github.com/HIKARU0627/Auto-Scoring/issues/3) の 2026-09-11 コメント |
| PR [#309](https://github.com/HIKARU0627/Auto-Scoring/pull/309) | Issue [#54](https://github.com/HIKARU0627/Auto-Scoring/issues/54)。cleanup の offline 検査と ADC 前提の再現手順 | PR #309                                                                                |

#### provider と認証

- AI 採点・採点基準の抽出: **Vertex AI Gemini**（#6 は `gemini-2.5-flash`）。
- OCR: **Google Document AI**。
- 認証は **いずれも ADC（Application Default Credentials）** である。**API キーを secret として
  CI のジョブへ渡す方式では動かない。** `gcloud auth application-default login`、またはホストに
  付与済みの service account / Workload Identity を使う。必要な環境変数の**名前だけ**は
  `backend/.env.example`（PR #309）に列挙してある。

#### 認証の結果（実機検証 #6）

| provider / 経路            | 結果                                                                                                            |
| -------------------------- | --------------------------------------------------------------------------------------------------------------- |
| Vertex AI（抽出・AI 採点） | 呼び出し **45 回すべて 200**。入力 156,768 / 出力 159,243 トークン。`ProviderUnavailable`・429 は **0 件**      |
| Google Document AI（OCR）  | リクエスト **23 回すべて 200**（gRPC status 0）                                                                 |
| 採点基準の抽出             | 11 教科で完走。crashed **0** / schema violations **0** / provider unavailable **0**、questions extracted **51** |

#### request の形（1 設問分）

- 1 採点ジョブ = 1 設問。provider へ送られた各回は、当該設問 1 つ分の**回答欄 crop のみ**で、
  生徒識別情報・ファイル名・設問 id を送らない（自動 assertion は #25 の
  `test_no_student_identifying_data_reaches_either_provider`）。
- AI 採点は crop を **`inlineData`** で同期送信する。Document AI は **`rawDocument` +
  `skipHumanReview: true`** の単発 POST で送る。どちらも upload / batch / GCS 経路を持たない。

#### response schema 適合

- AI 採点: **22 件すべて**が `AIGradingResult` として永続化。schema 違反として分類された恒久失敗は
  **0 件**（唯一の恒久失敗は AI 自身が返した `crop_not_the_answer` 1 件）。
- 採点基準の抽出: 11 教科で完走し **schema violations 0**（PR #107 の記録と一致）。
- 自由文 parse への fallback は無い。応答は毎回 `parse_ai_grading_result` で再検証される
  （`docs/ai-grading-pipeline.md`）。

#### cleanup

- **offline 検査（PR #309）**: `backend/tests/test_provider_cleanup.py` が、採用 2 provider の送信が
  同期・インラインで、リモート資源も `auto-scoring-*` 一時ディレクトリも残さないこと、一時ファイルを
  書く唯一の経路（Codex app-server フォールバック）が呼び出し後に workspace を削除することを、
  network・credential 無しで固定する。既定の `uv run pytest` に含まれる。
- **live 実測: 未計測。** #6 のレポートにも `out/` にも、実行後に一時ファイル / アップロード資源が
  消えたことの記録は無い。実データ経路での cleanup の実測は #54 から切り出されて残っている。

#### 件数（実機検証 #6、11 教科）

| 項目                   | 値                               |
| ---------------------- | -------------------------------- |
| 対象教科               | 11                               |
| 端から端まで通った教科 | 10 / 11（残る 1 教科は #215）    |
| crashed                | 0                                |
| schema violations      | 0                                |
| provider unavailable   | 0                                |
| questions extracted    | 51                               |
| Document AI リクエスト | 23（すべて 200）                 |
| AI 採点が付いた設問    | 22                               |
| 費用                   | $0.4796（≒ 74 円、11 教科 1 回） |

#### #10 による独立した裏付け

実機検証 #10（2026-09-11、main `3e51d3f` のビルド）は、**Electron の画面操作だけ**で 11 教科の
登録段取り（ホーム → 取り込み → 配点の AI 抽出 → 回答欄の自動検出 → 回答欄確定 → 依存グラフ確定
→ 登録完了）を通した。登録到達 **11/11**、検出エラー **0 件**、抽出設問の合計は **51** で、
**#6 の `questions extracted: 51` と一致**した。

#6 は API 直叩き、#10 は Electron の画面操作で、**経路（API 直叩き vs 画面操作）が違うのに同じ 51**
になった。したがって **Electron 経路でも認証・抽出・schema 適合が #6 と同じに効いている**と言える
（#54 の棚卸しコメントが「#8 が通れば追加の裏付けになる」としていた項目）。

ただし **#10 が通ったのは登録段取りまで**で、採点・確定・PDF 出力には到達していない。
費用表示は単価未設定のため「0 円」ではなく未設定を表示した（#187 の受入条件どおり）。

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

> **ここに書かれた数値は決定ではない。** 並列AI処理数
> （`docs/business-rules-and-evaluation-data.md` §3 の判断事項E）は、測定の後に
> プロジェクトオーナー（@HIKARU0627）が **Issue #81 で既定 4 に確定**した。以下の表は
> 測定当時の暫定既定 `max_concurrency=2` を含む合成データの測定であり、**数値そのものが
> 基準になったわけではない**（採用providerのレート制限は依然未実測。§3.1 E）。
> 残る「性能基準の答案件数」の確定は **#55**（#35 の実データ待ち）。

再現コマンド（`backend/` から。完全に合成データ、認証情報不要）:

```bash
uv run python poc/issue_25_queue_throughput/report.py
uv run python poc/issue_25_queue_throughput/report.py --answers 6 --latency 1.0
```

**測定当時の暫定値 `max_concurrency=2` と、確定した既定 4 を含む、並列度ごとの測定。**
擬似provider遅延 0.05 s/呼び出し、
答案12件 × 設問2（1設問 = OCR 1回 + AI 1回）:

| 並列度                  | 取込 合計(s) | キュー処理 合計(s) | 1答案あたり(s) | スループット(答案/分) | エラー率 |
| ----------------------- | ------------ | ------------------ | -------------- | --------------------- | -------- |
| 1                       | 13.48        | 2.65               | 0.221          | 271.8                 | 0.00     |
| 2（測定当時の暫定既定） | 13.38        | 1.35               | 0.113          | 532.1                 | 0.00     |
| 3                       | 13.50        | 0.89               | 0.074          | 810.2                 | 0.00     |
| **4（確定した既定）**   | **13.63**    | **0.68**           | **0.057**      | **1058.6**            | **0.00** |

擬似provider遅延 1.0 s/呼び出し、答案6件 × 設問2:

| 並列度                  | 取込 合計(s) | キュー処理 合計(s) | 1答案あたり(s) | スループット(答案/分) | エラー率 |
| ----------------------- | ------------ | ------------------ | -------------- | --------------------- | -------- |
| 1                       | 6.76         | 24.12              | 4.020          | 14.9                  | 0.00     |
| 2（測定当時の暫定既定） | 6.71         | 12.07              | 2.012          | 29.8                  | 0.00     |
| 3                       | 6.84         | 8.06               | 1.343          | 44.7                  | 0.00     |
| **4（確定した既定）**   | **6.74**     | **6.05**           | **1.008**      | **59.5**              | **0.00** |

読み取れること:

- キュー機構自体はほぼ線形にスケールする（並列1比で並列4が3.90〜3.99倍）。
  **並列度の上限を決めるのはキュー側のオーバーヘッドではなく外部providerのレート制限**であり、
  それは採用provider（判断事項A・B、Issue #81 で確定）の実測（#54・#35）まで存在しない。
  既定4は「レート制限に当たらない」保証ではない。
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

| Issue                                                       | 内容                                           | 何が決まれば着手できるか                                                                                                     |
| ----------------------------------------------------------- | ---------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| [#53](https://github.com/HIKARU0627/Auto-Scoring/issues/53) | clean Windows VM でのE2E受入（人間作業）       | clean な Windows 11 VM。A/B/C/E の確定は不要                                                                                 |
| [#54](https://github.com/HIKARU0627/Auto-Scoring/issues/54) | live OCR/AI provider での疎通・schema・cleanup | A・B は Issue #81 で確定済み。OCR の実アダプタも #114 で入った。残るブロックは**実 API キー / ADC と Document AI processor** |
| [#55](https://github.com/HIKARU0627/Auto-Scoring/issues/55) | 判断事項 **E** と性能基準の答案件数の確定      | E は Issue #81 で確定（既定4）。残る答案件数は #35 の実データ待ち                                                            |

---

## 7. セキュリティ検証で「生徒識別情報」として扱ったもの

> **本節の検査は「採点」経路のものであり、2026-09-09 の決定と一致している。**
> 送信範囲は**目的で決まる**（`business-rules-and-evaluation-data.md` §2 (2)、簡易設計書 §26.1.1）。
>
> | 目的             | 送るもの             | 本節の対象           |
> | ---------------- | -------------------- | -------------------- |
> | **採点**         | **回答欄の切り出し** | **これが本節**       |
> | **回答欄の検出** | ページ全体の画像     | 別経路（Issue #105） |
>
> 下表の「ページ全体のラスタ画像＝禁止」は、**採点のペイロードとしては現行仕様どおり**である。
> **以前ここに「決定 7 に合わせた見直しが要る」と書いたが、採点経路については誤りだった。**
> 決定 7 で緩和されたのは資料側と検出であって、採点のペイロードではない。
> **このテストは採点経路の受入条件として維持する。**
>
> 回答欄の検出（Issue #105）は**ページ全体を送る別経路**で、本節の対象ではない。
> そちらでは**記入されていれば氏名が渡る**（業務ルール §2 (2)）。

`docs/business-rules-and-evaluation-data.md` §2 (2) は種別（氏名・生徒ID・出席番号・
学校名・答案ファイル名）を列挙するが、assertionには具体的な値が要る。
`test_no_student_identifying_data_reaches_either_provider` が実際に検査するのは:

| 検査対象                                 | 扱い                                                                                                                                                                                                                                                                                                                                              |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `student_label`（例: `3年B組 山田太郎`） | **禁止**。`GradingRequest` の全テキストフィールドに現れないこと                                                                                                                                                                                                                                                                                   |
| `submissionId`                           | **禁止**。§2 (13) の内部識別子で、答案1通＝生徒1人に対応するため                                                                                                                                                                                                                                                                                  |
| 答案PDFのファイル名                      | **禁止**。§2 (2) が明示                                                                                                                                                                                                                                                                                                                           |
| `question_id`（当該設問のものを含む）    | **禁止**。1回の送信は1設問分（§2 (2)「同一答案の無関係な設問」）。Issue #117 以降は当該設問のidも送らない                                                                                                                                                                                                                                         |
| `testId`                                 | **禁止**（Issue #117 以降）。生徒ではなくテストを識別するので §2 (2) の対象ではないが、送る必要がもう無い。設問idとrubric criterion idを送っていたため従来は不可避だったところ、モデルに識別子を転記させる設計そのものをやめた（`ai-grading-pipeline.md`「モデルに識別子を転記させない」）ので、`GradingRequest` の全テキストフィールドから消えた |
| ページ全体のラスタ画像                   | **禁止**。氏名欄を含むため（§2 (2)）。送られたバイト列が回答欄cropと一致し、ページ画像と一致せず、かつページ画像より小さいことを確認                                                                                                                                                                                                              |

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

---

## 9. cut-over に向けたテスト参照の棚卸し（Issue #246 準備）

GitHub Issue [#246](https://github.com/HIKARU0627/Auto-Scoring/issues/246)（親 [#201](https://github.com/HIKARU0627/Auto-Scoring/issues/201)）。

最高責任者が定めたフロントエンド cut-over の第 4 条件:

> - **`docs/mvp-acceptance.md` の対応表を新しいテストへ張り替えること**

の実施準備として、本書内で現行の Flutter テスト（`app/test`）を参照している箇所をすべて棚卸しした。
**本 Issue では張り替えは行わず、棚卸し（現状と移行先の対応関係の記録）のみを行う。** 実際の張り替えは cut-over の Issue で実施する。

### 9.1 `app/test` 参照箇所の総数

本書内で `app/test` を指している行は **合計 7 行**（§1 表の 6 行 + §4.1 表の 1 行）である。加えて、§4.4 に Flutter テストスイート全体の件数記録がある。

| 箇所                        | 項目 / 対象               | 現行の `app/test` 参照                                                                                       | 新スタック対応状況                              |
| --------------------------- | ------------------------- | ------------------------------------------------------------------------------------------------------------ | ----------------------------------------------- |
| **§1 表 5 行目 (行 29)**    | PDF表示                   | `app/test/pdf_review_page_test.dart::Issue #25: 受入 -- 幅・focus・accessibility label`                      | **対応テストあり** (`desktop/test/`)            |
| **§1 表 8 行目 (行 32)**    | 点数表示                  | `app/test/pdf_review_page_test.dart::shows recognition, score, rationale, rubric, and dual confidence ...`   | **部分対応**（受入統合テストは**まだ無い**）    |
| **§1 表 9 行目 (行 33)**    | ○×表示                    | `app/test/pdf_review_page_test.dart::places a target-anchored annotation on the PDF overlay ...` ほか        | **対応テストあり** (`desktop/test/`)            |
| **§1 表 10 行目 (行 34)**   | コメント表示              | `app/test/pdf_review_page_test.dart::shows the AI grade comment (総評コメント), distinct from the rationale` | **部分対応**（受入統合テストは**まだ無い**）    |
| **§1 表 11 行目 (行 35)**   | AI結果修正                | `app/test/pdf_review_page_test.dart::Issue #22: ... 修正 ...`                                                | **部分対応**（UI 一連受入テストは**まだ無い**） |
| **§1 表 12 行目 (行 36)**   | AI結果承認                | `app/test/pdf_review_page_test.dart::Issue #22: ... 承認して次へ ...`                                        | **まだ無い**（答案確定画面の移植で作る）        |
| **§4.1 表 2 行目 (行 192)** | overlay 系 Linux 実行制約 | `app/test/pdf_review_page_test.dart` の overlay 系 (8件)                                                     | **構造的に解消**（Flutter 廃止に伴い不要化）    |

### 9.2 各行の詳細と新スタックでの対応先・作成計画

#### 1. 行 29 (§1 表 項目 5: PDF表示)

- **現行参照:** `app/test/pdf_review_page_test.dart::Issue #25: 受入 -- 幅・focus・accessibility label`（desktop標準幅/狭幅の両方で `PdfViewer` が出る）
- **新スタックの対応先:**
  - `desktop/test/pdf-review-geometry.test.ts` (INV-050, INV-051, INV-062, INV-063)
  - `desktop/test/renderer/pdf-review-page.test.tsx` (INV-014, INV-068, INV-069, INV-201-01, INV-067, INV-070, INV-071)
  - `desktop/test/renderer/home-escape.test.tsx` (脱出・アクセシビリティ)
- **状況:** **対応テストあり**。PoC 6 (Issue #207) および MIG-01〜03 の決定により、新スタックでは Flutter の `Pdfrx`/`PdfViewer` を廃止し、サイドカーが生成したページ画像を `PageImageViewer.tsx` で表示するアーキテクチャに刷新された。PR #244 で Vitest による描画・幾何計算テストが固定済み。

#### 2. 行 32 (§1 表 項目 8: 点数表示)

- **現行参照:** `app/test/pdf_review_page_test.dart::shows recognition, score, rationale, rubric, and dual confidence ...`
- **新スタックの対応先:** **部分対応（完全な受入統合テストはまだ無い）**
  - 単体・個別検証: `desktop/test/renderer/pdf-review-page.test.tsx` の `describe("confidence display (INV-068, INV-069)")` にて確信度バッジ表示および無記入時の 0 点理由表示がテストされている。
- **まだ無いテストの作成先:** 添削レビュー画面インスペクターにおいて「認識文字・得点・根拠・ルーブリック・2系統の確信度」が同時に正しく描画されることを検証する受入テストは、**添削レビュー画面のフォローアップ Issue または cut-over 準備 Issue で作成すべき**。

#### 3. 行 33 (§1 表 項目 9: ○×表示)

- **現行参照:** `app/test/pdf_review_page_test.dart::places a target-anchored annotation on the PDF overlay ...` ほか overlay 系
- **新スタックの対応先:** **対応テストあり**
  - `desktop/test/pdf-review-geometry.test.ts` (INV-050〜063: explicit rect, target-anchored OCR box, crop座標変換, 最小run, 異常系など 15 件)
  - `desktop/test/renderer/pdf-review-page.test.tsx` (INV-064: ターゲット未一致時の設問コメント欄退避)
- **状況:** PR #244 にて画像画素寸法に基づく幾何変換とアノテーション解決ロジックが Vitest で完全に固定済み。

#### 4. 行 34 (§1 表 項目 10: コメント表示)

- **現行参照:** `app/test/pdf_review_page_test.dart::shows the AI grade comment (総評コメント), distinct from the rationale`
- **新スタックの対応先:** **部分対応（完全な受入統合テストはまだ無い）**
  - 単体・個別検証: `desktop/test/renderer/pdf-review-page.test.tsx` (INV-064: 未解決アノテーションの設問コメント欄表示)。
- **まだ無いテストの作成先:** 総評コメント（AI grade comment）が採点理由（rationale）と明確に区別されてインスペクターに描画されることを確認する受入テストは、**添削レビュー画面のフォローアップ Issue または cut-over 準備 Issue で作成すべき**。

#### 5. 行 35 (§1 表 項目 11: AI結果修正)

- **現行参照:** `test_e2e_acceptance.py::test_correcting_approving_and_undoing_leaves_a_complete_history`、`app/test/pdf_review_page_test.dart::Issue #22: ... 修正 ...`
- **新スタックの対応先:** **部分対応（UI 一連受入テストはまだ無い）**
  - バックエンドの履歴・Undo 保証（`test_e2e_acceptance.py`）はそのまま存続。
  - フロントエンド: `desktop/test/renderer/pdf-review-page.test.tsx` (INV-071) にて却下アクション（`review-reject-button`）と理由送信のテストが存在する。
- **まだ無いテストの作成先:** 画面上での編集（edit）、再採点（regrade）、承認（approve）、Undo の一連のユーザー操作が整合して通ることを検証する UI 統合テストは、**添削レビュー画面のフォローアップ Issue または cut-over 準備 Issue で作成すべき**。

#### 6. 行 36 (§1 表 項目 12: AI結果承認)

- **現行参照:** 同上（`review/approve` と Undo を含む1本）、`app/test/pdf_review_page_test.dart::Issue #22: ... 承認して次へ ...`
- **新スタックの対応先:** **まだ無い**
  - 現状: 設問単位の承認ゲート（未読時の承認禁止・Enter 無効化）は `desktop/test/renderer/pdf-review-page.test.tsx` (INV-201-01, INV-067) でテスト済み。
  - 不足点: 設問を順次承認して「次へ」進み、最終的に全問承認後に答案を確定するフロー全体のテストが存在しない。
- **まだ無いテストの作成先:** **答案確定画面（未移植、未引き取り 7 件: INV-201-02, INV-201-08, INV-005, INV-154〜INV-157）の移植で作られるべき**。答案確定画面の移植時に「未到達設問がある場合の確定禁止」「全到達後の一括承認」「確定後の次答案への遷移」を検証するテストが実装される。

#### 7. 行 192 (§4.1 表 2 行目: Linux での overlay 系 8 件の失敗)

- **現行参照:** `app/test/pdf_review_page_test.dart` の overlay 系 (8件)
- **新スタックの対応先:** **構造的に解消（該当行は cut-over 時に削除）**
  - 背景: Flutter では `pdfium_dart` が Linux 上の `flutter test` でネイティブバイナリを解決できず 8 件失敗していた（Issue #60）。
  - 新スタック: Electron renderer は PDF を直接描画せず、サイドカーが pypdfium2 で生成したページ画像を `PageImageViewer.tsx` で描画する。座標計算（`desktop/test/pdf-review-geometry.test.ts`）は純粋関数として実行されるため、Linux / Windows の環境差やネイティブバイナリ解決エラー自体が構造的に消滅した。
  - cut-over 時の方針: §4.1 の本行および Flutter 固有の workaround 記述（`build hook が libpdfium.so を渡す`）は cut-over 時に削除するか、歴史的記録として「Electron 移行により解消済み」と注記する。

#### 参考: 行 244-246 (§4.4 スイート件数表)

- `| Flutter | 157 passed / 8 failed（既知） | 176 passed / 0 failed |`
- cut-over 時の方針: Flutter スイートの行を削除し、`desktop`（Vitest 250+ 件、Playwright e2e）の実績件数に差し替える。

### 9.3 張り替え作業のロードマップ（cut-over Issue への申し送り）

1. **未移植画面の移植とテスト作成:**
   - 答案確定画面（Issue #245 等）の移植により、項目 12（AI結果承認・一括承認・答案確定）の新スタックテストを確立する。
2. **添削レビュー画面の受入テスト補完:**
   - 項目 8（点数・確信度・ルーブリック統合受入）、項目 10（総評コメント区別）、項目 11（編集・再採点・Undo一連操作）の Vitest 統合テストを `desktop/test/renderer/pdf-review-page.test.tsx` に追記する。
3. **cut-over Issue での対応表張り替え:**
   - 本書 §1 の表の `app/test/...` 参照 6 行を、上記の `desktop/test/...` テストへ一括して書き換える。
   - §4 の Linux プラットフォーム差の記述から Flutter 固有の記述（pdfium 解決 hook）を整理し、§4.4 のテスト件数表を新スタックのものへ更新する。
