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

### 2.4 target Bounding Boxを持たないannotationの扱い

`Annotation.rect` が null の場合（コメントに位置指定が無い場合、または
`underline`/`box` が `anchor_text` のみを持つ場合）は、設問のInspector内
「設問コメント」欄へ退避表示する（簡易設計書 §12.4）。`anchor_text` を
OCRの`RecognitionResult.boxes`と突き合わせて実際の画面位置へ解決する処理は
本Issueでは実装していない（後続Issueの対象）。そのため現状は
`anchor_text`のみを持つ`underline`/`box`も、位置未解決として同じ
フォールバック欄に表示する。

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

### 2.8 処理中submissionはpollingで更新する

`unprocessed`/`ai_processing`状態のsubmissionを開いた場合、設問ごとの
recognition/grade/annotationが空で返るのは「未処理」であって「確定した空」
ではない。AI採点はバックエンドのjob queue（Issue #18）が設問単位で非同期に
進めるため、レビュー画面を開いたままの間にAIが結果を出し得る。この画面は
push通知を持たないため、3秒間隔のpolling（`Timer.periodic`、submission状態
が処理中でなくなったら停止）と、AppBarの手動更新ボタン
（`review-refresh-button`）の両方で追随する。pollingは`silent`フラグ付きで
実行し、読み込み中スピナーやエラーバナーが定期的にちらつくのを防ぐ。

## 3. 追加したAPI（読み取り専用）

| メソッド | パス                                                               | 用途                                         |
| -------- | ------------------------------------------------------------------ | -------------------------------------------- |
| GET      | `/tests/{test_id}/questions`                                       | 設問一覧（各設問領域＋rubric）               |
| GET      | `/submissions/{submission_id}/source-pdf`                          | 元答案PDFバイト列（`application/pdf`）       |
| GET      | `/submissions/{submission_id}/questions/{question_id}/grades`      | 採点結果の履歴（AI/human、両Confidence含む） |
| GET      | `/submissions/{submission_id}/questions/{question_id}/annotations` | annotation一覧                               |

いずれも `SqlAlchemyUnitOfWork` 経由の読み取りのみで、DBへの書き込みは行わない。
OpenAPIスキーマは `pnpm run openapi:export` / `openapi:generate` で
`backend/openapi/openapi.json` と `app/packages/auto_scoring_api/` へ反映済み。

## 4. 検証

- `backend/tests/test_review_api.py`: 上記4エンドポイントのHTTP統合テスト。
- `app/test/pdf_review_geometry_test.dart`: 座標変換の純関数テスト（PoC 3
  fixture再利用）。
- `app/test/pdf_review_page_test.dart`: loading/empty/error状態、
  認識文字・点数・根拠・rubric（`question.rubric`の定義自体）・2種の
  Confidenceの同時表示、AI/human結果がsource別に区別されること、
  annotationのoverlay配置（選択中の設問のみに限定されナビゲーション履歴に
  依存しないこと）とフォールバック、処理中submissionが手動更新で追随する
  こと、設問データ未読み込み時に承認/却下がブロックされること、キーボード
  での設問移動・承認、action barのキーボード到達性、狭幅・低い高さの
  レイアウトでのoverflow無し、多数設問時のNavigation Railのスクロール、を
  検証。
