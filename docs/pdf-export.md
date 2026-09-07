# 添削済みPDF出力

GitHub Issue [#23](https://github.com/HIKARU0627/Auto-Scoring/issues/23)（親
[#3](https://github.com/HIKARU0627/Auto-Scoring/issues/3)）の実装記録。対象は
全設問の人間レビュー完了後、元PDFを変更せず確定済みAnnotationを描画した新しい
添削済みPDFを生成する機能一式 -- バックエンドの生成・永続化・API
(`backend/src/auto_scoring/domain/pdf_export.py` /
`domain/annotation_layout.py` / `adapters/pdf/pdfium_pypdf_engine.py` の
`render_annotations` / `jobs/export_processor.py` /
`api/export_router.py`) と、Flutter側の出力実行・進捗・保存先表示・再試行
(`app/lib/features/pdf_review/export_dialog.dart`)。

依存: #12（PDF座標往復・`PdfEngine`契約、PoC 3）、#22（レビュー操作履歴 --
`domain.review_workflow.effective_latest_review`/`resolve_effective_grade`
をそのまま再利用する）。

## 1. 全体フロー

```text
POST /submissions/{id}/export
        ↓
未確認設問チェック（domain.pdf_export.unconfirmed_question_ids）
  → 1件でもあれば409、対象question_idを返して終了
        ↓
review-version snapshotを計算し、直近の成功Exportと比較
（domain.pdf_export.decide_reexport）
        ↓
[reuse_existing] 何もせず既存Exportをそのまま返す（200）
[accept_new / accept_new_superseding] Job(kind=EXPORT)を作成しqueueへ投入（202）
        ↓
ExportJobProcessor.process（jobs/export_processor.py）
  1. 設問ごとに resolve_effective_grade で確定Gradeを解決
  2. build_export_marks でAnnotationを座標解決（annotation_layout.py）
  3. app-data外のtemp fileへ PdfEngine.render_annotations で生成
  4. page数などを検証（失敗すればここで打ち切り、DB/app-dataに一切触れない）
  5. transactional_operation: Export行のcommit成功後にのみ
     app-data/exports/ へatomic rename
```

## 2. Annotation位置解決（`domain/annotation_layout.py`）

`app/lib/core/pdf_review_geometry.dart`（Issue #21/#22）の
`resolveAnnotationRect`をPythonへ移植したもの。添削レビュー画面が確定させた
Annotationの位置と、最終PDFに描画される位置が一致することを保証するため、
Dart側と同じ解決順序（簡易設計書 §12.1-12.4）を踏襲する:

1. `Annotation.rect`が明示されていればそのまま使う。
2. `anchor_text`があれば、そのGrade attemptのOCR `RecognitionResult.boxes`と
   完全一致で突き合わせ、`Question.answer_area`でcrop相対座標をpage相対座標へ
   変換する（新しい試行を優先、`recognitions_up_to_attempt`で
   attemptスコープを絞る）。
3. ○×△・点数などの固定位置種別は`Question.score_area`へフォールバックする。
4. それでも解決できないものは`None`を返す。

Dart側とPython側は別言語のため実装は共有できない。両者が同じ挙動になることは
`app/test/pdf_review_geometry_test.dart`と
`backend/tests/test_annotation_layout.py`をそれぞれ用意して担保する。

### 2.1 SCOREの描画文字列は確定Gradeから直接組み立てる

AIが提案するSCORE種別Annotationの`comment`フィールドは自由文字列であり、
人間が編集で点数を修正した後もAI提案時点の文字列のまま残り得る
（`docs/review-edit-history.md` §5「Annotationの図形編集はIssue #22の
対象外」）。出力するSCOREテキストは`Annotation.comment`を一切使わず、
その設問の確定`GradeResult.score`（`f"{awarded}/{maximum}"`）から
毎回組み立てる（`domain.pdf_export.build_export_marks`）。こうすることで、
表示される点数が常に実際に確定した点数と一致することを保証する。

### 2.2 位置解決できないAnnotationは`comment_area`へ退避する

`resolve_annotation_rect`が`None`を返した場合（固定位置種別でもなく、
`anchor_text`もOCRと一致しない場合）、`Question.comment_area`
（簡易設計書 §12.4「設問単位のコメント領域へ退避させる」）へ描画する。
`comment_area`も未設定の場合はそのAnnotationの描画を諦める（スキップする）
--

テスト登録時に`comment_area`は常に設定される前提（`docs/test-registration.md`）
のため実運用では発生しないはずだが、万一発生した場合に例外で全体を失敗させる
より、確定した他のAnnotationは出力しきる方を選んだ。**未決事項**:
`comment_area`が未設定のテストに対する挙動は改善の余地がある
（例えば設問ごとの警告一覧をログへ残す等）。

## 3. `PdfEngine.render_annotations`（Issue #23で追加）

`domain/pdf_engine.py`の`PdfEngine`契約へ新しいメソッドを追加した。
既存の`stamp_markers`（PoC 3由来、赤い正方形1種類のみ）は
`backend/poc/`・複数のテストfixture生成に使われ続けているため、シグネチャを
変更せずそのまま残し、代わりに新しいメソッドを追加した（`pdf_engine.py`の
元のdocstringは「`stamp_markers`を将来widenする」と書いていたが、
利用箇所が異なるため別メソッドとした）。

- `AnnotationMark`（`domain/pdf_engine.py`）: 種別・page正規化rect・
  （score/commentのみ）描画文字列を持つ値オブジェクト。座標決定は
  ドメイン層（`domain.pdf_export.build_export_marks`）の責務のまま。
- 実装（`adapters/pdf/pdfium_pypdf_engine.py`）は既存の
  `_overlay_pdf`/`_filled_square`と同じ「対象pageのMediaBoxと同じ
  MediaBoxを持つ1ページのオーバーレイPDFを作り`merge_page`で重ねる」
  方式を踏襲する。○×△・下線・囲みはpypdfの生content stream命令
  （`_filled_square`と同じ流儀）ではなく、reportlabの`Canvas`
  （楕円・直線・矩形・パス）で描画する。

### 3.1 新規依存: reportlab

コメント・点数のテキスト描画には日本語フォントの埋め込みが要る。
`pypdf`/`pypdfium2`にはテキストレイアウト・フォント埋め込みAPIが無く、
既存の手書きバイト列PDF生成（`_overlay_pdf`）へCID
フォント埋め込みを自前実装するのは著しく過大な工数になるため、
AGENTS.md「既存コード・標準ライブラリ・既存依存で満たせない場合のみ追加」
に従い`reportlab`（BSD系ライセンス、PyMuPDFのようなAGPL/商用ライセンス
問題が無い）を新規依存として追加した（`backend/pyproject.toml`）。
`Canvas`はTrueTypeフォントを`pdfmetrics.registerFont(TTFont(...))`
経由で登録すると、保存時に自動的にサブセット埋め込みする。

### 3.2 日本語フォントの解決（Windows専用の暫定方針）

MVPの対象OSはWindowsのみ（簡易設計書 §3.1）で、CIも`windows-latest`
（`docs/quality-gates.md`）のため、OS同梱の日本語フォントをそのまま使う
方針にした。フォントファイルをリポジトリへ同梱・再配布する必要が無く、
ライセンス上のリスクも増えない。候補は優先順位付きリストで解決する
（`adapters/pdf/pdfium_pypdf_engine.py`の`_JAPANESE_FONT_CANDIDATES`）:

```text
C:\Windows\Fonts\YuGothM.ttc
C:\Windows\Fonts\meiryo.ttc
C:\Windows\Fonts\msgothic.ttc
C:\Windows\Fonts\msmincho.ttc
```

いずれも存在しない場合は`JapaneseFontNotFoundError`を送出し、
export jobはFAILED（`ErrorCategory.PERMANENT`）として記録される
（形の崩れた文字やフォールバック描画で誤魔化さない）。純粋な図形種別
（○×△・下線・囲み）はフォントに一切依存しないため、コメント/点数の
Annotationを一切含まない設問だけの出力はフォント未検出でも失敗しない。

**未決事項**: macOS/Linux対応時はこの解決方式が使えないため、フォント
ファイルをアプリへ同梱するか、embeddable Google Noto Sans JPなどの
再配布可能フォントを採用するかを別Issueで決定する必要がある。

**テストだけの回避（製品挙動は不変）**: 上記の候補が1つも無い環境では、
文字描画を伴うテストは`backend/tests/font_support.py`が
**そのテストのassertionが必要とするグリフを実際に持つ**ローカルフォントを
候補リストの末尾へ追記してから走る。Windowsでは本物が先に見つかるため
何も起きず、**製品コードと`_JAPANESE_FONT_CANDIDATES`は変更していない**。
描けるフォントがどれも無いときはassertionを緩めずskipする
（[mvp-acceptance.md](./mvp-acceptance.md) §4）。

## 4. `Export`エンティティとJob

Issue #23の実施内容「出力job、hash、生成時刻、元Submission、review version
を保存する」への対応。

- `Job`（kind=`export`、`domain/models.py`の`JobKind.EXPORT`は Issue #11の
  時点で既に列挙値として存在していたが、本Issueまで生成する経路が無かった）
  が出力の実行単位。`question_id`/`dependency_graph_version`は常に`None`
  （submission単位の処理であり、設問DAGスケジューリングの対象外）。
  進捗表示・再試行は既存の`GET /jobs/{id}`・`POST /jobs/{id}/retry`を
  そのまま再利用する（Issue #18で実装済みのjob queueは`question_id`が
  `None`のjobを既に正しく素通りする -- `_finalize_result`の
  `if current.question_id is not None:`分岐）。
- `Export`（新規テーブル、migration `0014_exports`）は**成功した出力のみ**
  記録する。失敗した試行はJobの`state=failed`にのみ残る（「失敗した
  Export」という行は存在しない）。`job_id`にUNIQUE制約を張り、
  `ExportJobProcessor`は処理開始時に`export_id(job)`
  （`f"export:{job.id}"`、`grade_result_id`/`recognition_result_id`と同じ
  決定的id方式）で既存行を確認する -- クラッシュ後の再起動でjobが再実行
  された場合に二重生成・二重挿入を防ぐ（`jobs/grading_processor.py`の
  `existing_grade`チェックと同じ冪等性パターン）。
- `review_versions`（`QuestionReviewVersion`のtuple）は出力時点の各設問の
  review履歴の長さ（= 最新`Review.version`）のスナップショット。次回出力
  要求時に「前回から何か変わったか」を判定する材料になる（§5）。

## 5. 再出力方針の決定表（Issue #23受入条件）

`docs/answer-intake-and-preprocessing.md` §2「同一PDFの再取込方針」と同じ
決定表形式で記録する。実装は`domain.pdf_export.decide_reexport`。

| このSubmissionの既存Exportの状態                                                                  | 判定                     | 動作                                                                                                                      |
| ------------------------------------------------------------------------------------------------- | ------------------------ | ------------------------------------------------------------------------------------------------------------------------- |
| 成功したExportが1件も無い                                                                         | `accept_new`             | 新規ファイルを生成する                                                                                                    |
| 直近の成功Exportのreview-version snapshotが現在と完全一致（どの設問も再editもUndoもされていない） | `reuse_existing`         | 新規ファイルを生成せず、既存Exportをそのまま返す                                                                          |
| 直近の成功Exportのreview-version snapshotと現在が異なる（少なくとも1設問の履歴が進んだ）          | `accept_new_superseding` | `LocalFileStore.allocate_export_path`の連番規則で新規ファイルを生成する。以前の成功Exportのファイル・DB行は一切変更しない |

判断の根拠:

- 誤って同じ「出力」ボタンを連打した場合に、内容が同一のファイルを
  無意味に量産しない（`answer-intake-and-preprocessing.md`の同一PDF
  再取込方針と同じ理由）。
- 一方でレビューが実際に変わった（Undo・再edit・再承認）後の出力要求は、
  常に新しい内容を反映した新規ファイルであるべきで、古い出力を黙って
  上書きしてはならない（business-rules-and-evaluation-data.md §2 (15)
  「元PDFは上書きしない」と同じ精神を出力ファイルにも適用する）。
- 比較は`Export.id`やタイムスタンプではなく、設問ごとのreview履歴の長さの
  値そのもので行う。「どちらが古いか」ではなく「レビュー状態が同じか」を
  問うだけなので、この判定に順序関係は要らない。

## 6. ファイル名・衝突・atomic write（既存決定の再確認）

出力ファイル名規則（`<元ファイル名>_corrected.pdf`、衝突時は
`_corrected_2`と連番）と保存先（`app-data/exports/`）は
`business-rules-and-evaluation-data.md` §2 (14)・
`docs/data-model-and-local-storage.md` §5で既に決定済みで、
`adapters/local_storage.py`の`LocalFileStore.allocate_export_path`
（Issue #11時点で実装済み、本Issueまで呼び出し元が無かった）がそのまま使える。

`ExportJobProcessor`は次の順序を守る（Issue #23受入条件「失敗・cancel時に
元PDFと以前の成功出力を変更せず、壊れた完成ファイルを残さない」）:

1. app-data外のscratch temp fileへ生成する（生成失敗はここで検知、
   app-data・DBに一切触れない）。
2. 生成物を`PdfEngine.page_count`で検証する（page数が元PDFと一致しない
   場合は失敗として扱う）。
3. 検証済みのバイト列とExport行を`adapters.atomic.transactional_operation`
   で束ね、DB commitが成功した後にのみ`LocalFileStore.write_atomic`
   （同一ディレクトリへの一時ファイル→`os.replace`）で書き込む。

`ExportJobProcessor`の実行全体は`api.app.create_app`が既に持っている
PDFium直列化用ロック（旧`intake_lock`、本Issueで`pdfium_lock`へ改名し
export処理とも共有）の中で行う。これはPDFium自体のスレッド安全性のためだが、
副次的に「同じファイル名stemを持つ2つのsubmissionへの同時export」が
`allocate_export_path`の空きファイル名チェックで衝突するレースも防ぐ
（このロックが無いと、2つのexport jobが同時に同じ`<stem>_corrected.pdf`
を「空いている」と判定し、片方がもう片方の出力を`os.replace`で
上書きしてしまう可能性があった）。

## 7. Job queueの複数kind対応

Issue #18のjob queue（`jobs/queue.py`）は「`JobQueueService`は常に
1つの`JobProcessor`だけを持つ」設計だったが、それまでシステム内の
job kindが`GRADING`のみだったため単一processorで問題が無かった。本Issueで
`EXPORT`という2つ目のkindが生まれたため、`jobs/routing_processor.py`の
`ByKindJobProcessor`（`job.kind`で委譲先を振り分けるだけの薄いラッパー）を
新設し、`api.app.create_app`が既定で
`ByKindJobProcessor(default=GradingJobProcessor, overrides={EXPORT:
ExportJobProcessor})`を組み立てて`JobQueueService`へ渡す。`job_processor`
引数を直接渡すテスト・呼び出しは従来どおり「その1つのprocessorが全kindを
処理する」という既存の上書き挙動を維持する（この場合`ByKindJobProcessor`
は使われない）。`JobQueueService`自体には一切変更を加えていない。

## 8. API

`backend/src/auto_scoring/api/export_router.py`に追加:

| メソッド | パス                                   | 用途                                                                       |
| -------- | -------------------------------------- | -------------------------------------------------------------------------- |
| POST     | `/submissions/{submission_id}/export`  | §1のフロー。409（未確認設問）/ 200（`reuse_existing`）/ 202（新規job投入） |
| GET      | `/submissions/{submission_id}/exports` | 成功したExport一覧（保存先表示・出力履歴）                                 |

進捗・再試行は新規エンドポイントを作らず、Issue #18で実装済みの
`GET /jobs/{job_id}` / `POST /jobs/{job_id}/retry` /
`GET /submissions/{submission_id}/jobs`をそのまま再利用する
（kind=exportのJobもこれらのエンドポイントで等しく扱える）。

## 9. Flutter側

`app/lib/features/pdf_review/export_dialog.dart`の`ExportDialog`が
「出力実行→進捗→保存先表示/再試行」の全ライフサイクルを1つのdialogで
完結させる。添削レビュー画面（`pdf_review_page.dart`）のAppBarへ
「PDF出力」ボタン（`review-export-button`）を追加し、このdialogを開くだけ。

- 出力要求（`AppDependencies.requestExport`）が409を返した場合、
  `SidecarApiException.unconfirmedQuestionIds`（新設フィールド、
  `sidecar_api_client.dart`の`_translate`が409レスポンスの
  `detail.question_ids`から抽出する）を読み、未確認設問一覧を表示する。
- `decision: reuse_existing`ならjobを一切pollせず即座に保存先を表示する。
- 新規job投入時は`GET /jobs/{id}`（`AppDependencies.getJob`、新設）を
  1秒間隔でpollし、`succeeded`になったら`listExports`で該当jobの
  `file_path`を取得して表示する。`failed`/`cancelled`ならエラーと
  「再試行」ボタン（`POST /jobs/{id}/retry`、`AppDependencies.retryJob`、
  新設）を表示する。
- 既存のreview action（edit/reject/regrade/approve/undo, Issue #22）と
  同じく、Flutter側は永続化された状態を都度取得するだけで、dialog自身は
  出力結果を推測・キャッシュしない。

## 10. 検証

- `backend/tests/test_annotation_layout.py`: `resolve_annotation_rect`
  （明示rect・anchor_text解決・crop→page座標変換・ゼロ面積answer_areaの
  扱い・複数attemptでの最新優先・固定位置種別のscore_areaフォールバック・
  未解決時`None`）、attemptスコープ関数の単体テスト。
- `backend/tests/test_pdf_export.py`: 未確認判定・review-version
  snapshot・`decide_reexport`の3分岐・`build_export_marks`
  （SCOREはGradeの点数を描画・COMMENTはAnnotation自身のコメントを描画・
  `comment_area`フォールバック・未解決時スキップ・attemptスコープの
  絞り込み）の単体テスト。
- `backend/tests/test_pdf_annotation_rendering.py`: 実`pypdf`+`pdfium`で
  ○×△・下線・囲みの各形状がpixel検査（PoC 3と同じ「赤色検出」手法）で
  正しい位置に描画されること、点数・長い日本語コメント（複数行折り返し）が
  対応するrect内に描画されること、複数page文書で他pageを汚さないこと、
  回転pageでも正しい位置に描画されること、フォント未検出時に
  `JapaneseFontNotFoundError`で失敗し出力ファイルを残さないこと、
  フォント未検出でも図形のみのAnnotationは影響を受けないことを検証。
  点数と日本語コメントを同時に描く1件は両方のグリフを持つフォントを要求する
  （素のUbuntuには無い。`fonts-ipafont-gothic`で解決 ——
  §3.2、mvp-acceptance.md §4.3）。
- `backend/tests/test_export_processor.py`: 実SQLite + 実
  `PdfiumPypdfEngine`で、Export生成・記録・sha256一致・元PDF不変、
  未確認設問がある場合の拒否（Export行・ファイルとも作られない）、
  同一jobの再実行に対する冪等性、同一submissionへの2回目の出力が
  連番ファイルを生成し1回目のファイルを変更しないこと、生成失敗時に
  Export行・ファイルとも作られず元PDFも変更されないこと、失敗した
  再試行が既存の成功Exportへ影響しないことを検証（失敗注入含む）。
- `backend/tests/test_export_api.py`: `TestClient` + 実queueで
  `POST/GET .../export(s)`をエンドツーエンドに検証（404・409＋対象
  question_id・202＋job実行完了までのpolling・`reuse_existing`の200）。
- `app/test/export_dialog_test.dart`: 進捗→成功表示、`reuse_existing`の
  即時表示、未確認設問一覧表示、失敗→再試行→成功のライフサイクル全体を
  widget testで検証。

## 11. 対象外（Issue本文どおり）

- 元PDFへの上書き、クラウド保存、一括外部配信はMVP対象外
  （簡易設計書 §14・§26、business-rules-and-evaluation-data.md §2 (14)(15)）。
- Export結果のFlutter内プレビュー表示（保存先パスの表示のみ）。
