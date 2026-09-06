# 添削レビュー画面 (PDF + Annotation Overlay)

GitHub Issue [#21](https://github.com/HIKARU0627/Auto-Scoring/issues/21)（親
[#3](https://github.com/HIKARU0627/Auto-Scoring/issues/3)）の実装記録。対象は
Flutter側の添削レビュー画面（`app/lib/features/pdf_review/`）と、それを支える
最小限のバックエンド read API（`backend/src/auto_scoring/api/review_router.py`）。
承認・修正の永続化と最終PDF生成は Issue #21 の対象外（後続Issue）。

## 1. 実装したもの

- `PdfReviewPage`（`app/lib/features/pdf_review/pdf_review_page.dart`）:
  Material 3 の Navigation Rail（設問一覧）+ `pdfrx` PDF viewer + Inspector
  （AI認識文字・点数・根拠・採点基準・Recognition/Grading Confidence・
  設問コメント）+ action bar（修正/却下/承認して次へ）。
- `backend/src/auto_scoring/api/review_router.py`: 既存の
  `RecognitionResult`/`GradeResult`/`Annotation`/`Question`/`Rubric`
  domain・repository（Issue #11 で実装済み）を読み取り専用でHTTPへ公開する
  最小限のエンドポイント（下記§3）。
- `app/lib/core/pdf_review_geometry.dart`: 0〜1正規化座標をpdfrxが報告する
  ページ実寸へ変換する純粋関数（PoC 3 の座標契約をそのまま利用）。
- `app/lib/core/confidence_level.dart`: Confidenceの高/中/低の表示用分類。

## 2. 決定事項・未決事項

### 2.1 バックエンドread APIをこのIssueで追加した

Issue #21 の本文は Flutter 側の画面実装のみを列挙しているが、Flutter は DB
ファイルへ直接アクセスしない設計（`docs/data-model-and-local-storage.md` §8
「Flutter が DB ファイルへ直接アクセスしない」）であり、実装済みの
`RecognitionResult`/`GradeResult`/`Annotation`/`Question`/`Rubric` を読む
REST エンドポイントは Issue #21 着手時点で存在しなかった（既存の
`recognitions_router.py` は文字認識のみ）。元PDFバイト列を取得する
エンドポイントも存在しなかった。これらが無いと本画面の受入条件
（AI認識文字・score・根拠・rubric・2種類のconfidence・annotationを同一設問に
対応付けて表示する）を実データで満たせないため、本Issueのlabel
`area: ai-grading` の範囲内として、読み取り専用のエンドポイントを追加した
（永続化・書き込み系エンドポイントは追加していない）。

### 2.2 pdfrxを新規依存として追加した

`pdfrx: ^2.4.7`。既存依存では PDF 表示ができないため、AGENTS.md
「新しい依存関係は既存コード・標準ライブラリ・既存依存で満たせない場合のみ
追加する」に従い追加した。`pdfrx` は pdfium を包み、PoC 3
（`docs/poc-3-pdf-coordinates.md`）が座標往復を検証したのと同じレンダリング
エンジンであるため、正規化座標の変換契約をそのまま使える。

### 2.3 Confidenceの高/中/低の閾値は表示専用の仮決定

低Confidenceの基準値は業務ルールとして未決定
（`docs/business-rules-and-evaluation-data.md` §3 (C)、
`docs/data-model-and-local-storage.md` §9）。本画面はテキスト/アイコンでの
区別が受入条件のため、`ConfidenceLevel`（`app/lib/core/confidence_level.dart`）
に **表示分類専用**（0.9以上=高、0.7以上=中、それ未満=低）の閾値を仮に置いた。
この閾値は何もゲーティングしない（自動確定・ブロックの類は一切行わない）。
業務閾値が確定したら、この分類も合わせて見直すこと。

### 2.4 annotationの表示位置は`anchor_text`から解決する（R3レビュー対応）

実際の`GradingJobProcessor`が永続化するannotationは、種類を問わず常に
`anchor_text`のみを持ち`rect`は設定しない（AIにPDF座標を直接推測させない
という簡易設計書 §12.1の方針どおり、座標決定はアプリ側の責務）。当初
このIssueでは`anchor_text`→座標の解決を実装しておらず、フィルタが
一切マッチしないため実データではoverlayが何も描画されない状態だった
（R3レビュー指摘）。

`app/lib/core/pdf_review_geometry.dart`の`resolveAnnotationRect`が、
簡易設計書 §12.1-12.4の手順をそのまま実装する。

1. `annotation.rect`が既に設定されていればそれをそのまま使う（APIの
   契約上あり得るが、現状どの書き込み経路も設定しない）。
2. なければ`anchor_text`を、その設問のOCR`RecognitionResult.boxes`と
   完全一致で突き合わせ、一致した語のBounding Boxを使う（§12.3）。
3. `○`・`×`・`△`・`点数`（`fixedPositionAnnotationKinds`）は特定の語では
   なく解答全体に対する印なので、上記で解決できなければ設問の
   `score_area`（Annotation配置領域）へフォールバックする（§12.2）。
4. それでも解決できないもの（`anchor_text`が一致せず、かつ固定位置種別
   でもないもの）は`null`を返し、呼び出し側が設問のInspector内
   「設問コメント」欄へ退避表示する（§12.4）。

**R5レビュー対応**: 上記2.のOCR Bounding Boxは、`adapters/submission_
intake.py`が答案areaごとに`crop_normalized_rect`でpageからcropした
answer画像に対して正規化された座標であり、page全体に対する正規化座標
ではない（`RecognitionJobProcessor`はこのcrop画像をそのままOCR provider
へ渡し、providerが返すbox座標を一切re-projectionせずに永続化する）。
`_findAnchorTextRect`が`box.x`/`box.y`をそのままpage正規化rectangleへ
コピーしていたため、答案areaがpage全体でない設問では、crop分のoffsetと
scaleが失われ、annotationが誤った位置（＝誤ったコンテンツの上）に配置
されていた（R5レビュー指摘）。

`resolveAnnotationRect`へ`questionAnswerArea`（`Question.answer_area`）を
追加の引数として渡し、`_cropRelativeToPage`が
`page.x = area.x + box.x * area.width`（y/width/heightも同様）で
box座標をpage正規化座標へ変換してから使う。`crop_normalized_rect`は
軸並行なcrop（offset・scaleのみ、回転なし）であるため、この一次変換で
厳密に一致する。`answer_area`が未確定の設問は
`_build_answer_image`がpage全体をそのままOCRへ渡す（`NEEDS_REVIEW`、
簡易設計書 §24）ため、この場合はidentity（offset 0, scale 1）の
crop領域として扱い、既存の（page全体を答案areaとする）挙動を保つ
（`_fullPageArea`）。

### 2.5 承認・修正・却下はこの画面のメモリ内でのみ保持する

Issue #21 の対象外どおり、`PdfReviewPage`のaction bar（修正/却下/承認して次へ）
は`ReviewDecision`をこの画面のState内でのみ保持し、バックエンドへは一切
送信・永続化しない。「修正」は同一セッション内のみ保持されるメモをInspector
内のテキストフィールドへ入力できるだけで、`Review`/`GradeResult`エンティティ
への書き込みは行わない。承認・修正の永続化・最終PDF生成は後続Issueで扱う。

### 2.6 キーボードショートカットは暫定

簡易設計書 §17 の候補（Enter=承認して次へ、E=編集、X=却下、↑↓=設問移動）を
そのまま採用したが、§33 未決定事項12「キーボードショートカット」は依然未確定
のまま。確定した場合はこのマッピングを合わせて見直すこと。

### 2.7 座標往復の検証範囲

受入条件「代表fixtureでPDFとoverlayがzoom/scroll/回転後も一致する」に対し、

- `app/test/pdf_review_geometry_test.dart`: PoC 3
  （`backend/tests/test_pdf_engine_roundtrip.py::_TEST_POINTS`）と同じ5点の
  正規化座標を使い、`normalizedRectToLocal`（座標変換の純関数）がA4縦・
  A4を90°回転した表示寸法の両方で正しいピクセル位置を返すこと、ズームに
  比例してスケールすることを検証する。
- `app/test/pdf_review_page_test.dart`:
  `docs/poc-3-pdf-coordinates/samples/a4-portrait.pdf`
  （PoC 3が生成した実PDF fixture）を実際に`pdfrx`/pdfiumでレンダリングし、
  正規化座標(0.5, 0.5)のannotationが実際の画面上でpdfrxが報告したページ
  実寸（`pageOverlaysBuilder`が包む`Positioned`）に対して期待位置へ乗ることを
  検証する。

PoC 3が検証した回転・CropBox・非ゼロ原点MediaBoxの全fixtureをこの画面の
自動テストで再検証してはいない（代表fixture1点のみ、受入条件の文言どおり）。
残りのfixtureでの目視確認は、Windowsデスクトップビルドでの手動確認に委ねる。

### 2.8 pollingはsubmission状態でなく設問ごとのAI結果有無で判断する（R3レビュー対応）

当初pollingの継続条件をsubmissionの`unprocessed`/`ai_processing`状態に
結び付けていたが、`submission_intake.py`が示すとおりsubmissionの状態遷移
（`UNPROCESSED→AI_PROCESSING→AI_PROCESSED`）は取込時に同期的に完了し、
設問ごとのjob（Issue #18のjob queue）が作られるより前に`ai_processed`へ
進んでしまう。つまり本番のタイミングでは、実際にjobがqueued/runningの間
ずっとsubmissionは既に`ai_processed`を報告しており、状態ベースの条件は
実質的に一度もpollingを継続させない（R3レビュー指摘）。

`_updatePolling()`は当初`QuestionReviewState.hasAnyAiResult`
（`latestOcrRecognition != null || latestAiGrade != null`）が`false`である
限りpollingを継続する方式に変更したが、これも不十分だった
（R4レビュー指摘、下記）。submissionの状態文字列は一切参照しない。
AppBarの手動更新ボタン（`review-refresh-button`）は変更なし。pollingは
引き続き`silent`フラグ付きで実行し、読み込み中スピナーやエラーバナーが
定期的にちらつくのを防ぐ。

**R4レビュー対応**: `GradingJobProcessor.process`はOCR認識（recognition半分）
を独立したtransactionで先にcommitしてから、採点半分でAI providerを呼び出す
（`jobs/grading_processor.py`）。そのため通常の採点jobが「OCR結果はcommit
済みだがAI providerの応答をまだ待っている」状態（job状態は`running`）でも
`latestOcrRecognition`は既に非nullになり、`hasAnyAiResult`ベースの条件は
gradeが1件も存在しないままpollingを停止させてしまい、手動更新するまで
画面が「未採点」のまま固まっていた。

`GET /submissions/{submission_id}/jobs`（Issue #18で実装済み、本Issueでは
新規に消費するだけ）から取得した設問ごとのJob一覧を使う。Jobsの取得は
submissionの取得と同様best-effort（`_refreshJobs`、失敗しても既知の一覧を
保持するだけで画面全体は壊さない）。`FAILED`はbackendの再試行ポリシーに
よって`QUEUED`へ自動的に戻り得るが、それは他の終端状態と同じく手動更新
ボタンに委ねる（P1 review）。

**R5レビュー対応**: `_isAwaitingGrade`は当初「gradeが1件でも存在すれば
即座にfalse（pollingを止めてよい）」だったが、これは設問が新しい確定済み
依存グラフversionの下で再submitされた場合（Issue #18）を考慮していな
かった。再submitは同じ設問に新しいJobを作るが、append-only履歴の
`latestAiGrade`は古い試行のgradeを引き続き返すため、`_latestJobFor`が
新しいJobをqueued/running/blockedとして報告していても、古いgradeの存在
だけでpollingが止まり、新しい試行が完了してもreviewerには古いscore・
annotationが残り続けていた（R5レビュー指摘）。

`_isAwaitingGrade(review, questionId)`は次の順で判定する。

1. その設問のJobが1件も無ければ、gradeが無い間だけ継続する（Jobが後から
   作られる可能性に備える、従来どおり）。
2. 最新Jobが終端状態（`_terminalJobStates`）でなければ無条件に継続する
   （新しい試行が走っている可能性があるため、たまたま古いgradeが
   キャッシュにあっても関係ない）。
3. 最新Jobが終端状態なら、`latestAiGrade`が無いか、その`created_at`が
   最新Jobの`created_at`以前（＝その試行より前に書かれたgrade）である間
   だけ継続する。gradeは常にそれを生成したJobの作成より後に書き込まれる
   ため、`grade.created_at`がJobの`created_at`より後であることが「この
   gradeはこのJobの結果である」ことの確認になる。

3.の判定により、新しいJobが実際にはterminalに達しているのにまだ古い
gradeしか観測できていない（次のfetchでまだ追いついていない）窓では
継続してもう一度fetchし、追いついた時点で自然に停止する。

pollingが導入する race condition に対処している。

- **世代トークンによる直列化**: `QuestionReviewState.fetchGeneration`を
  fetch開始のたびにインクリメントし、結果を適用する直前にまだ最新の世代か
  確認する。3秒間隔のpollingが前回のrefresh完了より早く発火した場合（遅い
  requestが複数並走した場合）でも、古いrequestが後から完了して新しい結果を
  上書きしないようにする。あわせて`_pollInFlight`フラグで前のpollが
  完了するまで次のtickを開始しない。
- **表示中fetchのloading状態を保護する**（R3レビュー指摘）: silentな
  pollは、その設問が既に（手動更新やタブ切替による）表示ありfetch中
  （`review.loading == true`）であれば何もせず即座に戻る。これが無いと、
  表示ありfetchの途中でsilent pollが割り込んで`fetchGeneration`を進め、
  そのsilent fetch自体が失敗した場合に表示ありfetch側の`loading`を誰も
  `false`へ戻さず、スピナーが永久に残ってしまう。
- **recognition/gradeのcommitタイミングの競合**（R5レビュー指摘）:
  `GradingJobProcessor.process`は採点半分のOCR訂正結果
  （`grading-recognition:`、stage=`grading`）をgrade・annotationと
  同一transactionでcommitするが、これはOCR半分の`RecognitionResult`
  （stage=`ocr`）の別のtransactionより後に発生する。`_ensureReviewLoaded`
  が`listRecognitions`を呼んだ直後・`listGrades`を呼ぶ前にこのcommitが
  割り込むと、取得した`recognitions`はまだ古いまま（`grading`段階の行が
  無い）なのに、`grades`は新しいgradeを含んでしまう。gradeが存在すれば
  pollingが停止し得るため、この不整合を放置すると「採点AIの認識結果」欄が
  手動更新まで欠落したままになる。fetch後に「最新のAI gradeと同じ
  `created_at`を持つrecognitionが取得済みrecognitions内にあるか」を
  確認し、無ければrecognitionsだけをもう一度取得し直す
  （`consistentRecognitions`）。annotationはgradeと同一transactionで
  commitされるため、この競合の対象にならない。

### 2.9 keyboardショートカットはnote編集中は無効化する

`note field`（修正コメント欄）がfocusを持っている間は、`CallbackShortcuts`の
bindingsを空map（`_shortcutBindings`）にする。`CallbackShortcuts`は
bindingsに一致するキーを、callbackの中身に関わらず無条件に「処理済み」として
消費してしまうため、callback内でfocus判定をしても手遅れ（キー入力そのものが
note fieldへ届かなくなる）。bindingsの登録自体をfocus状態に応じて外す方式を
採用した。

### 2.10 InspectorはOCRと採点AIの認識結果を別々に表示する（R3レビュー対応）

`RecognitionResult`には、OCR自体の認識結果（Issue #19の文字認識job、
id接頭辞`recognition:`）と、採点AIが採点時に独自に読み直し訂正した認識結果
（`GradingJobProcessor`、id接頭辞`grading-recognition:`）の2種類があり、
どちらも`source=ai`のため`source`だけでは区別できない
（`docs/ai-grading-pipeline.md`「AI graderが訂正した認識結果を保持する」）。
当初Inspectorは`source`のみでグルーピングしていたため、この2段階が
同一の「AI認識文字」欄へ意図せず統合されていた（R3レビュー指摘）。

`RecognitionResponse`（`recognitions_router.py`）へ`stage`
（`"ocr" | "grading" | "human"`）フィールドを追加し、id接頭辞と
`source == human`から機械的に導出する（`_recognition_stage`）。
Inspectorは`latestOcrRecognition`（`stage == 'ocr'`）と
`latestGradingRecognition`（`stage == 'grading'`）を別々のセクション
（「OCR文字認識信頼度」欄と「採点AI文字認識信頼度」欄）として表示する。
pollingの継続判定（2.8）も`latestOcrRecognition`の有無のみを見る
（採点AIの訂正結果はグレーディングjob完了後にしか現れないため）。

### 2.11 設問番号の並び順は数字/英字混在でも推移的な自然順にする（R3レビュー対応）

設問番号（`Question.number`）は`"1"`のような単純な数字だけでなく、
`"1a"`のような枝番も許容される。当初の比較関数は
`int.tryParse`で両辺を数値化できたときだけ数値比較し、片方でも失敗したら
文字列比較にfall backしていたが、これは推移律を満たさない
（例: `"2" < "10"`、`"10" < "1a"`、`"1a" < "2"`が同時に成立してしまい、
安定した全順序にならない）。

`_compareQuestionNumbers`は`_tokenizeForNaturalSort`で文字列を数字の連続と
非数字の連続に分割し、トークンを先頭から順に比較する一貫した規則に
書き換えた: 同じ位置のトークンが両方数字ならその数値で、両方非数字なら
辞書式で比較し、型が異なる場合は常に「数字トークン側を小さい」とみなす
（共通の型付けルールを型ペアごとに変えないことで推移律を保証する）。
共通接頭部が一致してどちらかのトークン列が尽きた場合は、短い方を先とする。

### 2.12 annotationは表示中のgrading試行だけに限定する（R4レビュー対応）

設問は複数回グレーディングされ得る（Issue #18: 新しい確定済み依存グラフ
version下での再submitは新しいJobを作り、`GradingJobProcessor.process`は
そのたびに新しい`GradeResult`と新しいannotation群を追加する。append-only
履歴のため古い試行の行は削除されない）。当初はannotation一覧を無条件に
全件overlay/フォールバック表示していたため、Jobが再発行されると、
Inspector/overlayが現在の`displayGrade`（最新のgrade）を示しているにも
関わらず、過去の試行の（矛盾し得る）markがそのまま重ねて表示され続けて
いた（R4レビュー指摘）。

`Annotation`はどの`GradeResult`から生まれたかを指すidを持たない
（`GradingJobProcessor.process`が同じtransaction・同じclock読み取り
`now`から両方を作るだけで、互いのidを記録し合わない）。スキーマ変更を
避け、`QuestionReviewState.annotationsForDisplayedAttempt`が
`annotation.createdAt == displayGrade.createdAt`（両方とも同じ`now`から
書き込まれる）で一致するものだけに絞り込む。`displayGrade`が存在しない
（まだ一度もグレーディングが完了していない）場合は空リストを返す。
overlay（`_buildAnnotationOverlay`）・フォールバック一覧
（`_fallbackAnnotationsFor`）の両方がこのフィルタ済み一覧だけを参照する。

この方式は、人がgradeを確定した後（`displayGrade`が`latestHumanGrade`に
切り替わった後）は、どのAI annotationの`created_at`も人のgradeの
`created_at`と一致し得ないため、AIの古いmarkが人の確定後の点数の隣に
残り続けるケースも合わせて解消する（「human overrides AI」の既存方針と
一貫した挙動）。

## 3. 追加したAPI（読み取り専用）

| メソッド | パス                                                               | 用途                                                           |
| -------- | ------------------------------------------------------------------ | -------------------------------------------------------------- |
| GET      | `/tests/{test_id}/questions`                                       | 設問一覧（各設問領域＋rubric）                                 |
| GET      | `/submissions/{submission_id}/source-pdf`                          | 元答案PDFバイト列（`application/pdf`）                         |
| GET      | `/submissions/{submission_id}/questions/{question_id}/grades`      | 採点結果の履歴（AI/human、両Confidence・AIの総評コメント含む） |
| GET      | `/submissions/{submission_id}/questions/{question_id}/annotations` | annotation一覧                                                 |

いずれも `SqlAlchemyUnitOfWork` 経由の読み取りのみで、DBへの書き込みは行わない。
OpenAPIスキーマは `pnpm run openapi:export` / `openapi:generate` で
`backend/openapi/openapi.json` と `app/packages/auto_scoring_api/` へ反映済み。

## 4. 検証

- `backend/tests/test_review_api.py`: 上記4エンドポイントのHTTP統合テスト。
  `GradeResultResponse.comment`のAI総評コメント含む。
- `backend/tests/test_recognitions_api.py`:
  `test_list_recognitions_distinguishes_ocr_from_grading_stage`で、
  同じ`source=ai`のOCR/採点AI訂正の2行と`source=human`の1行から
  `stage`が`"ocr"`/`"grading"`/`"human"`へ正しく振り分けられることを検証。
- `app/test/pdf_review_geometry_test.dart`: 座標変換の純関数テスト（PoC 3
  fixture再利用）に加え、`resolveAnnotationRect`（§2.4）の単体テストとして
  明示rectの優先、`anchor_text`のOCR Bounding Boxへの解決（答案areaが
  page全体の場合、および答案areaがpageの一部分にcropされている場合の
  両方で、crop相対座標からpage正規化座標への変換が正しいこと。R5レビュー
  対応）、固定位置種別（○・×・△・点数）4種すべてでのscore_areaへの
  フォールバック、`anchor_text`が一致しない場合の固定位置種別の
  score_areaフォールバック、非固定位置種別で何も解決できない場合に`null`
  を返すことを検証。
- `app/test/pdf_review_page_test.dart`: loading/empty/error状態、
  認識文字・点数・根拠・rubric（`question.rubric`の定義自体）・2種の
  Confidenceの同時表示、AI/human結果がsource別に区別されること、
  annotationのoverlay配置（選択中の設問のみに限定されナビゲーション履歴に
  依存しないこと）とフォールバック、AIの総評コメント表示、note field編集中は
  keyboardショートカットが無効化されること、AI gradeが存在するまで承認が
  ブロックされること、silent poll成功時に古いerrorがクリアされること、
  設問番号が辞書式でなく自然順（1, 2, ..., 10）でソートされること、
  設問番号が数字/英字混在（`"1a"`, `"2"`, `"10"`）でも推移的な順序に
  なること（§2.11）、submissionが既に`ai_processed`を報告していても
  その設問にまだAI結果が無ければpollingを継続すること（§2.8）、
  text系annotationが実際のOCR単語Bounding Box（自身のrectではなく）へ
  配置されること、固定位置markがOCR未一致時に設問のscore_areaへ
  フォールバックすること、OCRと採点AI訂正の2つの認識段階が並べて
  表示されること（§2.10）、処理中submissionが手動更新で追随すること、
  設問データ未読み込み時に承認/却下がブロックされること、キーボードでの
  設問移動・承認、action barのキーボード到達性、狭幅・低い高さの
  レイアウトでのoverflow無し、多数設問時のNavigation Railのスクロール、
  OCR認識が既に届いていてもgradeが無い間（Jobが`running`のまま）は
  pollingを継続し承認もブロックされ続けること（§2.8、R4レビュー対応）、
  複数回グレーディングされた設問で現在表示中の試行（`displayGrade`と
  同じ`created_at`）のannotationだけがoverlayされ、古い試行のmarkが
  残らないこと（§2.12、R4レビュー対応）、答案areaがpage全体でない設問の
  text系annotationがOCR box座標を答案areaで変換したpage位置へ配置される
  こと（R5レビュー対応）、再submitで新しい試行のJobがqueued/running/
  blockedの間は古い試行のgradeがキャッシュに残っていてもpollingを継続し、
  新しい試行のgradeが実際に届くまで止めないこと（§2.8、R5レビュー対応）、
  recognitionとgradeのcommitタイミングが競合し新しいgradeだけが先に見えた
  場合でも、対応する採点AIの認識結果をもう一度取得して欠落させないこと
  （§2.8、R5レビュー対応）、を検証。
