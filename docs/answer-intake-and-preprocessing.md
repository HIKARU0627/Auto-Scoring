# 答案 PDF 取込・保存・画像前処理

GitHub Issue #17（親: #3）の実装記録。対象は生徒答案 PDF の取込 API・保存・
画像前処理のみ（Issue #17「対象外」: OCR・AI 採点・並列 queue は後続 Issue）。
依存元は #10（認証付きサイドカー API）・#11（MVP データモデル・ローカル保存）・
#15（複数レイアウト PoC）で、いずれもマージ済みの実装をそのまま利用する。

食い違う場合の優先順位は他の決定書と同じ：本書はここで扱う範囲について
[`simplified-design-specification.md`](./simplified-design-specification.md) §7・§16.4・§23〜25、
[`business-rules-and-evaluation-data.md`](./business-rules-and-evaluation-data.md) §2 (3)(4)、
[`data-model-and-local-storage.md`](./data-model-and-local-storage.md) を具体化する。矛盾する場合は
本書を優先し、同じ PR で上位ドキュメント側も更新する。

## 1. 全体フロー

```text
POST /tests/{test_id}/submissions (multipart)
        ↓
検証（拡張子・宣言MIME・magic bytes・size上限） -- ここまではDB/fileに一切触れない
        ↓
一時ファイルへ書き込み（app-data外のscratch dir）
        ↓
PdfEngine.is_encrypted / page_count（破損・暗号化を検出）
        ↓
content hash（sha256）で再取込判定（§2）
        ↓
ページ網羅性チェック（§3、Testのquestionが要求するpageとPDFの実ページ数を比較）
        ↓
[網羅性OK] 設問ごとに answer_area で切り出し → OpenCV前処理したページ画像を保存
[網羅性NG] 元PDFは保存するが設問切り出しはせず、ページプレビューのみ保存
        ↓
transactional_operation: DBコミット成功後にのみファイルを書き込む（Issue #11の資産をそのまま利用）
```

## 2. 同一 PDF の再取込方針（決定）

Issue #17 受入条件「同一 PDF の再取込方針が決定表どおり動作し、元 PDF を変更しない」
に対応する決定表。実装は `domain/submission_intake.py::decide_reintake`。

| 既存 Submission の有無・状態                              | 判定               | 動作                                                                                                                                   |
| --------------------------------------------------------- | ------------------ | -------------------------------------------------------------------------------------------------------------------------------------- |
| 同一 `(test_id, sha256)` の Submission が存在しない       | `ACCEPT_NEW`       | 新しい `submission_id` で通常どおり取込む                                                                                              |
| 存在し、状態が `error`                                    | `RETRY_EXISTING`   | 同じ `submission_id` を再利用し、`error → unprocessed` を経て再度パイプラインを走らせる。元 PDF は同一バイト列なので再書込みは行わない |
| 存在し、状態が `error` 以外（処理中・要確認・確認済み等） | `REJECT_DUPLICATE` | `409 Conflict` を返し、既存の `submission_id` を含める。DB/file への書込みは一切行わない                                               |

判断の根拠：

- 元 PDF は上書きしない（business-rules §2 (15)）ため、同一内容の再アップロードで
  ファイルを書き直す理由がない。
- 誤って同じファイルを 2 回投入した場合に重複 Submission が量産されるのを防ぐ。
- 一方で、取込処理自体が失敗した（`error` 状態）場合の再試行は、同じファイルを
  もう一度選んでアップロードするだけで成立してほしい（Flutter 側の「再試行」操作が
  複雑にならないようにするため）。
- 生徒を再割当てしたい・別ファイルで再提出したい場合は、内容（バイト列）が変われば
  `sha256` が変わるため自動的に `ACCEPT_NEW` になる。古い誤 Submission は
  Issue #11 で実装済みの一括削除機能（`purge_submission`）で人間が消す。

## 3. ページ網羅性チェックと設問依存（スコープ決定）

Issue #17 追加要件は「ページ欠落・重複・順序違いを検出し、dependency graph に
必要な前提設問が欠ける答案を要確認にする」を求める。一方、設問間の依存関係を
人間が確認して固定する「確定 DAG」は
[`business-rules-and-evaluation-data.md`](./business-rules-and-evaluation-data.md) §4 で
**テスト登録時に構築する**と規定されており、テスト登録画面・API はまだ実装されていない
（本 Issue の対象外）。

**決定**: 確定 DAG が存在しない現段階では、business-rules §4.5
「確定 DAG が存在しないテスト…は逐次処理にフォールバックし、人間へ『依存関係が未確定』の
警告を出す」の安全側を取り、次の粗い判定で代替する。

- `Test` に登録済みの `Question.page` の集合を「期待ページ集合」とする。
- 取込んだ PDF の実ページ数と比較する（`domain/submission_intake.py::PageCoverage`）。
  - 期待ページ集合の最大値より実ページ数が小さい → `missing_pages`（欠落）
  - 期待ページ集合の最大値より実ページ数が大きい → `extra_pages`（超過。重複スキャン等の
    可能性がある兆候として扱う）
- どちらか一方でも該当すれば、**Submission 全体**を `needs_review` にする
  （設問単位の部分成功にはしない）。個別ページの内容比較（実際にどの設問が
  どのページに写っているか）は OCR/レイアウト解析が必要でこの Issue の範囲外のため、
  「ページ数が合わない」ことを機械的に検出できる範囲に留める。
- 期待ページ集合が空（そのテストにまだ Question が登録されていない）場合も
  同様に Submission 全体を `needs_review`（`no_questions_registered`）とする。

**既知の制限（未解決のまま明記する）**: ページ数が一致していても、スキャン順序の
入れ替わり・同一ページの重複スキャン（ページ数は変わらない形の誤り）は、実際の
ページ内容を判定できないため本 Issue では検出できない。実際の確定 DAG 機能と、
ページ内容の同一性判定（OCR/レイアウト解析）は、テスト登録 Issue と OCR Issue が
実装され次第、本チェックを置き換える。

**「前提設問を含むページが欠落した状態では AI 採点を開始しない」の満たし方**:
OCR・AI 採点のジョブ生成自体がまだ実装されていない（Issue #17 対象外）ため、
`needs_review` になった Submission に対して何もジョブを作らないことで自動的に
満たされる。将来の OCR/AI 採点 Issue は、`needs_review` の Submission に対して
ジョブを起票しない、という制約を継続する必要がある。

## 4. Submission 状態機械への当てはめ

`domain/models.py` の状態機械（Issue #11、simplified-design-spec.md §25）を変更せずに
そのまま使う。画像前処理・設問切り出しは「AI が答案を処理する」パイプラインの
最初の段階とみなし、次のように当てはめる。

```text
unprocessed → ai_processing → ai_processed → (問題なければそのまま。後続のOCR/AI採点Issueが引き継ぐ)
                                              ↘ needs_review（ページ網羅性NG、または
                                                 answer_area未定義の設問がある場合）
```

`needs_review` は `ai_processed` からしか到達できない（状態機械の制約）ため、
取込パイプラインは問題の有無に関わらず必ず `ai_processed` を経由してから
`needs_review` へ遷移する。`review_reason` に理由の文字列を記録する
（`missing_pages:2`、`no_questions_registered`、`answer_area_undefined:<question-id,...>` 等）。

再取込（retry）は `error → unprocessed → ai_processing → ai_processed → (…)` を
同一トランザクション内で連続して適用する。

## 5. 検証項目（PDF 妥当性）

`domain/pdf_intake.py::IntakeLimits`（既定値。呼び出し側で上書き可能）:

| 項目               | 既定値                            | 検証内容                                                              |
| ------------------ | --------------------------------- | --------------------------------------------------------------------- |
| 拡張子             | `.pdf` 固定                       | 大文字小文字を無視。`/`・`\`・`..` 等パス区切りを含むファイル名を拒否 |
| 宣言 MIME          | `application/pdf`（未指定は許容） | それ以外の宣言は拒否                                                  |
| magic bytes        | `%PDF-`                           | 拡張子・MIME 詐称を検出                                               |
| ファイルサイズ上限 | 50 MiB                            | 超過は `413`                                                          |
| ページ数上限       | 100 ページ                        | 超過・0 ページは `400`                                                |
| 暗号化             | 拒否                              | `pypdf` の `is_encrypted` で判定。ユーザーへパスワード入力は求めない  |
| 破損               | 拒否                              | `pypdf` の parse 例外を `PdfCorruptedError` に正規化                  |

これらの検証はすべて **DB・`app-data/` への書込みより前**に行う
（`adapters/submission_intake.py::intake_submission`）。失敗時は例外を投げて
戻るだけで、中途半端な行やファイルは残らない
（`adapters/atomic.py::transactional_operation` の保証を利用）。

## 6. 画像前処理の設計判断

simplified-design-specification.md §7.1 の「傾き補正・回転補正・拡大縮小補正・
ノイズ低減・コントラスト調整」を OpenCV（`opencv-python-headless`）で実装する
（`adapters/image/opencv_preprocessor.py`）。

- **拡大縮小補正**: `PdfEngine.render_page_png(..., scale=2.0)` で全ページを
  常に同じ scale（pixel/pt）でラスタライズすることで満たす。ページごとに
  後処理でリサイズし直す必要がない。
- **傾き補正・回転補正**: `cv2.minAreaRect` によるインク画素の外接矩形角度推定 →
  0.3°未満は補正しない（スキャンノイズ扱い）、10°を超える推定は補正量をクリップする
  （90/180/270度の意図的な回転は `PdfEngine` 側の `/Rotate` 処理で既に解決済みのため、
  ここでの補正対象は数度単位のスキャン傾きのみ）。
- **ノイズ低減**: `cv2.fastNlMeansDenoisingColored`。
- **コントラスト調整**: LAB 色空間の L チャンネルへ CLAHE を適用（単純なヒストグラム
  平坦化より色被りが起きにくい）。

**この補正はプレビュー画像にのみ適用する。** 設問ごとの回答欄切り出しは、
`PdfEngine.render_page_png` が返す未加工のラスタに対して `Question.answer_area`
（0〜1 正規化座標、Issue #11 で既存）をそのまま乗じて行う
（`adapters/image/opencv_preprocessor.py::crop_normalized_rect`）。デスキューは
画像全体を回転させるため、回転角度を正規化座標へ逆伝播させない限り単純な
矩形切り出しに使えない。往復変換の実装・検証コストに見合う効果が無い
（プレビュー用の見た目改善が主目的であり、切り出し精度は `Question.answer_area`
自体の正確さに依存する）ため、**意図的に**両者を分離した。将来 OCR
の前処理として画像全体のデスキューが必要になった場合は、
`domain/pdf_geometry.py` が採用した「四隅を変換してから外接矩形を取る」方式
（PoC 3/4 で実績あり）を踏襲して再設計する。

### メモリ使用量

`adapters/submission_intake.py::intake_submission` はページを 1〜`page_count`
まで 1 ページずつ処理する（ラスタライズ → 前処理 → その場でそのページの設問を
切り出し → 次のページへ）。ラスタライズ結果（未加工 PNG）を全ページ分キャッシュ
することはしない。最大 100 ページ（`IntakeLimits.max_pages`）の PDF でも、
同時にメモリへ載る未加工ラスタは常に 1 ページ分に留まる。処理済み（デスキュー後の
プレビュー・切り出し）画像は `StagedFiles`（Issue #11、DB コミット成功後に
まとめて書き込むための保持）に溜まるが、これは「コミットが成功するまでファイルを
書かない」という既存の atomicity 保証とのトレードオフであり、本 Issue の範囲では
そのまま踏襲する。

## 7. データモデルの追加（Issue #17）

`docs/data-model-and-local-storage.md`（Issue #11）が定義した 9 Entity に加えて、
以下を追加する（マイグレーション `0003_answer_intake`）。

### `Submission` への追加カラム

| カラム              | 型      | 用途                                                                 |
| ------------------- | ------- | -------------------------------------------------------------------- |
| `source_pdf_sha256` | String  | 再取込判定キー（§2）                                                 |
| `page_count`        | Integer | 取込時に判明したページ数。以後 PDF を開き直さずに参照できる          |
| `original_filename` | String? | 取込時のファイル名（識別情報に準じローカル限定。§2 (13) と同じ扱い） |
| `review_reason`     | String? | `needs_review` になった理由（§3・§4）                                |

### 新規 Entity: `AnswerImage`

設問ごとに切り出した回答欄画像 1 件を表す（`submission_id` + `question_id` で一意）。

| フィールド      | 型                     | 説明                                                          |
| --------------- | ---------------------- | ------------------------------------------------------------- |
| `id`            | str                    | 主キー                                                        |
| `submission_id` | str (FK)               |                                                               |
| `question_id`   | str (FK)               |                                                               |
| `page`          | int                    | 1始まりページ番号（`Question.page` と一致）                   |
| `image_path`    | str                    | `app-data/` からの相対パス                                    |
| `status`        | `ok` \| `needs_review` | 切り出し成功可否（§6.2 の「回答欄検出失敗」に対応）           |
| `reason`        | str?                   | `needs_review` のときのみ必須（例: `no_answer_area_defined`） |

`Question.answer_area` が未設定（テスト登録がまだ回答欄を確定していない）場合は、
`status=needs_review, reason="no_answer_area_defined"` とし、`image_path` は
そのページの前処理済みプレビュー画像を指す（切り出せないので元画像をそのまま
人間へ提示する、simplified-design-spec.md §24）。

`AnswerImage.__post_init__`（domain）の「`status=ok` なら `reason` は必ず
`None`、`status=needs_review` なら `reason` は必ず非空」という不変条件は、
`answer_images` テーブルの `CHECK` 制約（`ck_answer_images_reason_matches_status`）
としても強制する。アプリ層を経由しない書き込み（手動 SQL・将来のバグ）でも
矛盾した行がコミットされず、読み込み時に初めて `DomainError` になる事態を防ぐ
（`AGENTS.md`「不変条件は実制約で保証する」）。

### 既存 DB のバックフィル（マイグレーション `0003`）

0001/0002 時点で作成された `submissions` 行には `source_pdf_sha256` /
`page_count` が存在しない。カラム追加時の `server_default`（`""` / `1`）は
`ALTER TABLE` を通すためだけの一時値で、`""` のまま放置すると
`Submission.__post_init__` が空ハッシュを拒否し、移行直後の一覧・取得が
`DomainError` で落ちる。`0003_answer_intake.py::_backfill_submission_metadata`
が、カラム追加直後に各行の `source_pdf_path`（Issue #11: 元 PDF は不変で
必ず残る）を実際に読み、真の `sha256` と `pypdf` で数えた `page_count` を
`UPDATE` で書き戻す。ファイルが見つからない行（既に purge 済み、または
手作業で作った古い fixture）は、空文字列の代わりに
`sha256("legacy-submission:<id>")` という「実データのハッシュではないと
分かる」固定値を入れ、`page_count` は `1` にフォールバックする——読み込めない
以上、正確な値の代わりに何かを捏造するくらいなら、行が読み込み不能になる
ことだけは避ける、という優先順位。

## 8. `app-data/` ファイルレイアウトの追加

Issue #11 のレイアウトに、ページプレビューと設問画像を追加する。

```text
app-data/
├─ submissions/<submission-id>/
│   ├─ source.pdf                      # 既存（Issue #11）。書き換えない
│   ├─ pages/page-<N>.png              # 前処理済みページプレビュー（1始まり）
│   └─ questions/<question-id>.png     # 設問ごとの回答欄切り出し画像
```

`LocalFileStore`（Issue #11）に `submission_source_pdf_path` /
`submission_page_image_path` / `submission_question_image_path` を追加し、
パス生成・パストラバーサル防止（既存の `_ensure_within_root`）をそのまま再利用する。

## 9. API

`backend/src/auto_scoring/api/app.py`。すべて既存の Bearer 認証必須ルータ配下
（`docs/sidecar-api.md` §2）。OpenAPI schema → Dart クライアントは
`pnpm run openapi:generate` で再生成し、`app/packages/auto_scoring_api/` にコミットする
（同 §4）。

| メソッド・パス                      | 用途                                                                         |
| ----------------------------------- | ---------------------------------------------------------------------------- |
| `GET /tests`                        | 答案取込画面（§16.4）のテスト選択に使う一覧                                  |
| `POST /tests/{test_id}/submissions` | multipart（`file` + 任意 `student_label`）。本書の中心的な取込エンドポイント |
| `GET /tests/{test_id}/submissions`  | 選択中テストの取込済み答案一覧（進捗表示に使う）                             |
| `GET /submissions/{submission_id}`  | 1件の取込・処理状態を取得                                                    |

エラーの返し方：

| エラー                                       | HTTP status                   | body                                                              |
| -------------------------------------------- | ----------------------------- | ----------------------------------------------------------------- |
| ファイル形式・サイズ・ページ数・暗号化・破損 | `400`（サイズ超過のみ `413`） | `{"detail": "<理由>"}`                                            |
| `test_id` が存在しない                       | `404`                         | `{"detail": "..."}`                                               |
| 重複取込（§2 `REJECT_DUPLICATE`）            | `409`                         | `{"detail": {"message": "...", "existing_submission_id": "..."}}` |

`POST /tests/{test_id}/submissions` はアップロード本体を `_UPLOAD_READ_CHUNK_BYTES`
（1 MiB）単位で読みながら `IntakeLimits.max_size_bytes` を随時チェックし、超えた
時点で読み込みを打ち切って `413` を返す（`api/app.py::_read_upload_within_limit`）。
上限超過の巨大ファイルであっても、まず全body分の `bytes` を確保してから検証する
ことはしない（`AGENTS.md`「trust boundary を跨ぐ入力はすべて検証する」）。

## 10. `app-data/` の実際の格納場所（未決事項）

サイドカーの `--app-data-dir`（既定 `カレントディレクトリ/app-data`）が実データの
格納先になる。Windows 配布時の実際のインストール先・`%LOCALAPPDATA%` 等の採用可否は
`docs/technology-stack.md` §1.2 が「Windows 配布 Issue で決定する」としている範囲のままで、
本 Issue では確定しない。実装・テストではこの CLI 引数で任意のディレクトリを指定できる
ことのみを保証する。

## 11. Flutter 側

`app/lib/features/answer_intake/answer_intake_page.dart`（simplified-design-spec.md §16.4
答案取込画面）。

- テスト選択（`GET /tests`）→ PDF ファイル選択（`file_picker`）→ 任意の生徒ラベル入力 →
  取込。
- アップロード中は `LinearProgressIndicator` を表示（取込進捗）。
- 失敗時はエラーバナー（アイコン+テキスト。色だけに依存しない）と「再試行」ボタンを表示し、
  同じファイル・テスト・ラベルで再送する（取込エラー・再試行）。
- 重複取込は `DuplicateSubmissionException` として区別し、既存の `submission_id` を
  含む文言を表示する。
- 生徒ラベル欄の Enter で取込を実行できる（`TextField.onSubmitted`）。取込ボタンは
  通常のフォーカス移動・Enter/Space で操作できる（Flutter 標準の `FilledButton` の
  挙動をそのまま利用）。
- 取込済み答案一覧は状態ごとに異なるアイコン+日本語ラベルで表示し（§25 の状態機械の
  値をそのまま反映）、`needs_review` の場合は `review_reason` も表示する。
  再取込（同一 `submission_id` での成功）は一覧の既存行を置き換える（先頭に
  追加すると、以前失敗した時点の行と新しい行が両方残ってしまうため）。

`SidecarApiClient` は取込アップロード専用に、他の呼び出しより長いタイムアウト
（既定 5 分、`intakeTimeout`）を設定した別の `Dio`/`DefaultApi` ペアを持つ
（`createSubmission` のみそちらを使う）。最大 100 ページの PDF は全ページの
ラスタライズ・前処理・切り出し・DB commit・ファイル書込みを終えてからサイドカーが
応答するため、他の呼び出しと同じ既定 10 秒では正当なリクエストでもタイムアウトしうる。
タイムアウトで失敗したとクライアントが判断してもサイドカー側は処理を続けて commit
する可能性があり、そのまま再送すると紛らわしい重複エラー（409）になる。

`core/app_dependencies.dart` に `listTests` / `listSubmissions` / `createSubmission` を
関数注入の形で追加した（既存の `healthCheck` と同じスタイル）。実際のサイドカー
プロセス監視・接続確立（`SidecarConnection` を実際に作る部分）はまだ実装されていない
（`docs/technology-stack.md` §1.2 で「Windows 配布 Issue」に位置づけられている）ため、
既定実装は `healthCheck` の `_stubHealthCheck` と同様に、正直に「未接続」を表す
`SidecarErrorKind.unavailable` を返す。`SidecarApiClient` 自体は本 Issue で
`listTests` / `listSubmissions` / `getSubmission` / `createSubmission` を実装済みで、
接続確立後にそのまま使える。

## 12. 検証（受入条件との対応）

| Issue #17 受入条件・検証項目                                                    | 対応                                                                                                                                                                                                 |
| ------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 単一/一括取込の採用方式で Submission が作成され、設問画像が profile と対応する  | `Question.answer_area`（Issue #11）をそのまま利用。`test_submission_intake_service.py::test_happy_path_creates_submission_and_ok_answer_images`                                                      |
| 同一 PDF の再取込方針が決定表どおり動作し、元 PDF を変更しない                  | §2、`test_submission_intake_service.py::test_duplicate_submission_is_rejected` / `::test_retry_reuses_the_errored_submission`                                                                        |
| 不正/暗号化/破損 PDF を安全に拒否し、中途半端な DB/file を残さない              | §5、`test_pdf_intake.py`、`test_submission_intake_service.py::test_encrypted_pdf_is_rejected_without_a_trace` 等                                                                                     |
| 生徒識別情報をログや外部通信へ出さない                                          | `original_filename`/`student_label` はローカル DB のみ。ログ出力コードなし（§28 の既存方針を継続）                                                                                                   |
| 複数 page/回転/破損/oversize/重複 PDF を含む integration test                   | `backend/tests/test_submission_intake_service.py`（複数ページ・欠落ページ）、`test_pdf_engine_intake.py`（暗号化・破損）、`test_pdf_intake.py`（oversize・不正拡張子）                               |
| Flutter の取込進捗・エラー・再試行・keyboard/focus を確認する                   | `app/test/answer_intake_page_test.dart`                                                                                                                                                              |
| 1 答案 3 ページ以上の fixture で全 Question が正しい page/question 順で関連付く | `test_submission_intake_service.py::test_happy_path_creates_submission_and_ok_answer_images`（3ページ・3設問。`result.answer_images`と再取得した永続化済み行の両方で page/question_id の対応を検証） |
| 前提設問を含むページが欠落した状態では AI 採点を開始しない                      | §3。`needs_review` の Submission に対してジョブを起票する経路が存在しない（Job/採点は Issue #17 対象外）                                                                                             |

## 13. 未決事項・引き継ぎ

- 確定 DAG（設問依存）の実装は business-rules §4 のとおりテスト登録 Issue に委ねる。
  本書 §3 の粗い判定は、確定 DAG が実装されるまでの暫定であることを明記する。
- ページの重複スキャン・順序入れ替わりの検出（内容ベース）は OCR/レイアウト解析
  Issue の実装を待つ。
- `app-data/` の実際のインストール先は Windows 配布 Issue で確定する（§10）。
- OCR/AI 採点 Job の起票ロジックは、`needs_review` の Submission にジョブを
  作らない制約を守って実装すること（§3）。

## 14. 2回目のレビュー指摘への対応

- **migration が既存の子行を消していた（重大）**: SQLite は `foreign_keys=ON` の
  接続で `DROP TABLE` すると、`ON DELETE CASCADE` の子行に対して暗黙の
  `DELETE FROM` を実行する。Alembic の SQLite batch mode（`recreate="always"`）は
  `ALTER TABLE` を「新テーブル作成 → コピー → 旧テーブル DROP → リネーム」で
  表現するため、`submissions` を batch 変更するたびに
  recognition_results/grade_results/annotations/reviews/jobs が消えていた。
  `migrations/env.py` が migration 用の接続でだけ `foreign_keys=OFF`
  （`db/engine.py::create_sqlite_engine(..., enforce_foreign_keys=False)`、
  接続確立時に設定 -- トランザクション開始後に変更しても無効なため）にして防ぐ。
  `test_upgrade_preserves_child_rows_of_a_recreated_submissions_table` で
  5 テーブル全てが生き残ることを検証する。
- **再取込キーを UNIQUE 制約にした**: `(test_id, source_pdf_sha256)` を
  `uq_submissions_test_content_hash` として強制する。事前チェック
  （`find_by_content_hash`）と実際の INSERT の間に競合が起きても、負けた側は
  `IntegrityError` を `adapters/submission_intake.py::intake_submission` が
  捕捉し、勝った側の `submission_id` を含む通常の `DuplicateSubmissionError`
  として返す（`test_concurrent_duplicate_insert_is_reported_as_a_race_loss`）。
  既存データに真の重複（同一テストへの同一バイト列の答案が複数存在）がある場合は
  migration 自体が `IntegrityError` で失敗する（§7 の migration docstring参照）。
- **migration 専用の一時デフォルトを削除**: バックフィル後に 2 回目の batch
  recreate を行い、`source_pdf_sha256`/`page_count` の `server_default` を外す。
  これらの列を省略した INSERT は `NOT NULL` 違反で失敗する
  （`test_submission_metadata_columns_require_a_value_after_upgrade`）。
- **アップロードのボディサイズを ASGI 層で強制**: `api/body_size_limit.py` の
  `MaxBodySizeMiddleware` が `Content-Length` ヘッダで即座に拒否し（速い経路）、
  ヘッダが無い/嘘の場合でもストリームのバイト数を数えて超過時点で打ち切る。
  FastAPI の multipart parser が body 全体を `UploadFile` へ spool する前に働く。
  既存の `_read_upload_within_limit`（handler 内のチャンク読込）はこの防御の
  内側の層として残す。
- **アップロードの Content-Type を明示**: Flutter 側 `MultipartFile.fromFile` は
  既定で `application/octet-stream` を送るが、サイドカーは `application/pdf`
  以外の宣言 MIME を拒否するため、これまで実際のアップロードは全て 400 で
  弾かれていた。`contentType: MediaType('application', 'pdf')` を明示し、
  `sidecar_api_client_test.dart` に実サイドカー越しの
  `createSubmission` テストを追加して契約を固定した（未登録の `test_id` を
  指定し、`400` ではなく `404` が返ることで content-type がサイドカー側の
  検証を通過したことを確認する）。
- **ローカルファイル読込失敗を変換**: 選択済み PDF が送信前に削除・切断された
  場合、`MultipartFile.fromFile` は `DioException` ではない例外を投げる。
  `createSubmission` はこれを捕捉し `SidecarApiException` に変換するので、
  画面側の既存のエラーバナー・再試行導線がそのまま使える。
- **アップロード中はテスト選択を無効化**: `AnswerIntakePage` はアップロード中
  テストピッカーの `onChanged` を `null` にする。加えて、アップロード完了時に
  結果を一覧へ反映する前に、送信開始時点でキャプチャした `test_id` が現在の
  選択と一致するかを再確認する（防御的二重チェック）。
- **未実装デフォルトが同期的に throw していた**: `core/app_dependencies.dart` の
  既定実装（`_unavailableListTests` 等）が `=>` 本体で `_unavailable()` を
  直接呼んでおり、`Never` を返す関数の `throw` が Future 化される前に同期的に
  伝播していた。`AnswerIntakePage.initState()` は `listTests()` を
  try/catch 無しで呼ぶため、マウント中にクラッシュしていた。`async` を付けて
  Dart に throw を Future のエラーとして捕捉させる。

## 15. 3回目のレビュー指摘への対応

- **ページジオメトリ検証前のラスタライズ（重大）**: `submission_intake.py` は
  ページ数チェック後、`pdf_engine.render_page_png` で実際に PNG へ描画する前に
  そのページの `page_geometry()`（`displayed_width`/`displayed_height`、回転を
  考慮した表示寸法）を取得し、`domain/pdf_intake.py::validate_render_dimensions`
  へ通す。悪意ある/破損した `MediaBox`/`CropBox` が極端に大きい寸法を宣言する
  PDF は、実際に高解像度ラスタライズしてメモリを枯渇させる前に
  `PdfPageTooLargeError` として拒否される。`IntakeLimits` に
  `max_render_dimension_px`（既定 20,000px、片辺の上限）と
  `max_render_pixels`（既定 40,000,000px、面積の上限）を追加し、
  `RENDER_SCALE` 適用後の実ラスタライズ寸法で判定する。
  `test_page_with_an_absurd_declared_size_is_rejected_before_rendering`
  （縦横 1,000,000pt の宣言を含む 439 バイトの PDF）で検証する。
- **multipart フレーミング分のマージンを ASGI 層に確保**: `MaxBodySizeMiddleware`
  に渡す上限は `IntakeLimits.max_size_bytes` そのままではなく、
  `_MULTIPART_OVERHEAD_BYTES`（64KiB、boundary・各パートのヘッダ・
  `student_label` フィールドなどの分）を上乗せした値にする。ファイル本体は
  `max_size_bytes` ちょうどでも、multipart のフレーミングを含めたリクエスト
  総量はそれよりわずかに大きくなるため、上乗せが無いと正当なアップロードが
  ASGI 層で 413 として弾かれていた（ファイル本体側の上限は
  `_read_upload_within_limit` が別途 `max_size_bytes` で厳密に見る）。
  `test_create_submission_tolerates_multipart_overhead_near_the_limit` で、
  上限ぎりぎりのファイルパートを含むリクエストが 413 にならないことを固定する。
- **リトライのアトミックな claim**: 同じエラー状態の submission に対する
  再取込は、`find_by_content_hash` で「既存あり・エラー状態」と判定した後、
  実際に処理を始めるまでの間に別のリクエストが先に同じ submission を
  掴んでいる可能性がある（読んでから書く、ではレースに勝てない）。
  `SubmissionRepository.claim_for_retry` を追加し、
  `UPDATE ... WHERE state = 'error'` の単一の条件付き UPDATE で
  `error → unprocessed` を移す。`_write_submission` はこの呼び出しが
  `False`（＝他のリクエストが先に掴んだ）を返したら
  `SubmissionRetryConflictError` を送出し、`transactional_operation` の
  ロールバックでこのリクエストが加えたステージ済みファイル・状態変更を
  破棄する。API 層では `409 Conflict`（`DuplicateSubmissionError` と同様の
  扱い）にマップする。`SqlAlchemySubmissionRepository.claim_for_retry` は
  生 SQL の `UPDATE` がセッションの identity map を更新しないため、
  呼び出し後に対象行を明示的に `session.refresh()` して以降の
  `session.get()` が古い状態を返さないようにする。
  リポジトリ層で成功/失敗/2 者競合の 3 パターン、統合テストで
  `intake_submission()` 越しの競合を検証する
  （`test_claim_for_retry_*`、`test_concurrent_retry_is_reported_as_a_race_loss`）。
- **暗黙の一時データルートを確実に片付ける**: `create_app()` に `data_root` を
  渡さない呼び出し（テスト/簡易起動）は、以前は `tempfile.mkdtemp()` 相当の
  ディレクトリを作りっぱなしにしていた。`tempfile.TemporaryDirectory` を使い、
  `atexit.register(scratch.cleanup)` でプロセス終了時に確実に削除する。
- **アップロード中は入力全体を固定**: `AnswerIntakePage` は 2 回目の対応で
  テストピッカーのみアップロード中に無効化していたが、ファイル選択ボタンと
  生徒ラベルの `TextField` は操作可能なままだった。両方とも `_isSubmitting`
  の間は無効化する
  （`test: 'the file picker button and student-label field are disabled
while an upload is in flight'`）。
- **file picker 完了後の `mounted` チェック**: `_pickFile()` は
  `await widget.pickFile()` の直後、`picked == null` を見る前に
  `if (!mounted) return;` を追加した。ネイティブのファイル選択ダイアログが
  開いている間に画面を離れると、その後の `setState` が破棄済みウィジェットに
  対して呼ばれてクラッシュしていた
  （`test: 'disposing the page while a file pick is still pending does not
throw'`）。

## 16. 4回目のレビュー指摘への対応

- **migration 0003 が legacy 重複を batch DDL 前に検出する（重大）**:
  pre-0003 の DB に、同一テスト内で内容が完全に一致する submission が
  2 件以上ある場合（§7 の migration docstring が最初から想定していたケース）、
  以前の実装は `uq_submissions_test_content_hash` を追加する 2 回目の batch
  再作成が実際に失敗するまで気づかなかった。SQLite の batch mode は
  一時テーブル `_alembic_tmp_submissions` を経由してテーブルを再作成するが、
  pysqlite は DDL の前に暗黙で COMMIT するため、失敗時にその一時テーブルと
  1 回目の batch（列追加）の結果がディスクに残ったまま `alembic_version` は
  `0002` のまま、という壊れた状態になっていた。ドキュメント化された
  「重複を手で解消して再実行」という復旧手順は、この状態では
  `_alembic_tmp_submissions already exists` で即座に失敗し機能しなかった。
  `_load_content_hashes`/`_reject_duplicate_content_hashes`
  （`migrations/versions/0003_answer_intake.py`）が、どちらの batch pass
  よりも前に、まだディスク上の `source.pdf` から計算した内容ハッシュだけで
  重複を検出し、あれば `RuntimeError` で即座に中断する。この時点では
  まだ 1 行の DDL も実行していないため、重複を手で削除して
  `upgrade` を再実行すれば本当に revision 0002 からクリーンにやり直せる
  （`test_legacy_duplicate_content_is_rejected_before_any_ddl_and_retry_recovers`）。
- **PDF 処理をイベントループから逃がす**: `POST /tests/{test_id}/submissions`
  はページのラスタライズと OpenCV 前処理を、非同期ハンドラの中で
  同期的に実行していた。uvicorn はシングルワーカーで動かすため、大きい答案の
  intake が数分かかる間、`/healthz` を含む他の全リクエストが応答不能になっていた。
  `api/app.py::_run_intake` にこのパイプライン一式（`SqlAlchemyUnitOfWork` の
  取得から `intake_submission` 呼び出しまで）を切り出し、
  `await asyncio.to_thread(_run_intake, ...)` でワーカースレッドへ逃がす。
  pypdfium2 はプロセス内の複数スレッドから同時に呼び出すことを想定していない
  （公式ドキュメントの multithreading 注意書き）ため、`threading.Lock`
  （`intake_lock`）で実際の intake 実行を直列化する。この直列化自体は
  従来の「イベントループが 1 件ずつ完了させる」動作と実質同じであり、
  スループット面での劣化ではない。`/healthz` はこのロックに触れないため、
  intake 実行中でも即座に応答する
  （`test_healthz_stays_responsive_while_an_intake_is_running`。
  `with TestClient(app) as client:` でアプリ全体が 1 つの event loop を
  共有する状態を再現しないと、この検証は修正前のコードでも偶然パスしてしまう）。
- **リスト読み込み中に完了したアップロードを保持する**: `_selectTest` の
  `listSubmissions` 呼び出しが完了する前に、ユーザーが別のファイルを
  選択して送信を完了させると、`_submit` は新しい結果を `_submissions` へ
  upsert 済みなのに、その後に届く（アップロード開始前に発行された）古い
  `listSubmissions` のレスポンスがそれを丸ごと上書きし、ページを開き直すまで
  新しい submission が一覧から消えていた。`_withLocalOnlyPreserved` が、
  取得結果にまだ含まれていないローカルの項目（＝取得開始後に確定した項目）を
  取得結果の前に残したうえでマージする
  （`test: 'a submission created while the list is still loading is not lost
when the stale list response lands'`）。
- **低い高さのビューポートでも intake フォームをスクロール可能にする**:
  固定の `Column` + `Expanded(child: 一覧)` は、モバイルや高さの低いウィンドウ、
  特に生徒ラベル欄でキーボードが開いた状態で、フォーム部分だけで残り高さを
  超えて `RenderFlex` オーバーフローを起こし、下の要素を隠していた。
  `Column` を `CustomScrollView`（`SliverToBoxAdapter` でフォーム一式、
  `SliverList.separated`/`SliverFillRemaining` で一覧）に置き換え、画面全体を
  1 つのスクロール可能領域にする。一覧は十分な高さがあれば残り領域を占め、
  無ければフォームと一緒にスクロールする
  （`test: 'a short viewport does not overflow the intake form'`）。
- **3 ページ以上の fixture で page/question の対応を実際に検証する**:
  `test_happy_path_creates_submission_and_ok_answer_images` は 2 ページ・
  2 設問の fixture で、3 ページ目以降は「同じ経路なので成立するはず」という
  コメントで済ませていた。3 ページ・3 設問の fixture に拡張し、
  `result.answer_images` と `uow.answer_images.list_for_submission` で
  再取得した永続化済み行の両方について、各ページが正しい `question_id` に
  page 順で対応していることを直接 assert する（§12 の受入条件表を更新）。

## 17. 5回目のレビュー指摘への対応

- **staged 画像の総メモリ量を制限する（重大）**: `adapters.atomic.StagedFiles`
  は DB コミットが成功するまで、ページプレビューと設問切り出し画像を PNG バイト列
  としてメモリに保持し続ける。ページ 1 枚ずつラスタライズしていても、
  各ページの検証（宣言サイズ・ページ数上限・レンダリング寸法）を通過した
  合法的な大きな答案（例: JPEG 圧縮率の高い 50 MiB ぎりぎりの複数ページ PDF）が、
  展開後の PNG では総計ギガバイト単位に膨張しうる。`StagedFiles.add` に
  累積バイト数のカウンタを持たせ、`transactional_operation` へ渡した
  `max_staged_bytes`（`IntakeLimits.max_staged_output_bytes`、既定 300 MiB）を
  超えたら `StagedOutputTooLargeError`（`domain/pdf_intake.py`、`PdfIntakeError`
  のサブクラス、API 層は 413 にマップ）を送出する。これは
  `transactional_operation` の既存の失敗処理（rollback + staged 破棄）にそのまま
  乗るため、DB 行もファイルも残らない
  （`test_max_staged_bytes_bounds_the_running_total_not_just_one_add`、
  `test_decoded_output_exceeding_the_staged_size_cap_is_rejected`）。
- **面積ゼロの解答領域を needs_review に回す**: `NormalizedRect` は
  `width`/`height` が 0 でもドメインモデルとしては許容している。
  `adapters/image/opencv_preprocessor.py::crop_normalized_rect` 自身のクランプ
  （`x1 = max(x0 + 1, ...)` 等）はこれを黙って 1×1px の crop に変換してしまい、
  `_build_answer_image` はそれを `OK` として扱っていたため、意味のない画像の
  まま submission が `ai_processed` に到達し得た。`_build_answer_image` で
  `answer_area` が `None` の場合と同じ扱いにし（ページプレビューへフォール
  バックし `NEEDS_REVIEW`、理由は区別のため `answer_area_zero_area`）、
  `crop_normalized_rect` 自体は呼ばれないようにする
  （`test_zero_area_answer_area_falls_back_to_page_preview_instead_of_a_useless_crop`）。
- **完了済みリトライを古い list レスポンスで上書きしない**: 4 回目の対応
  （§16）で入れた `_withLocalOnlyPreserved`（「fetch 結果に無い id だけ残す」）
  では、リトライが _既存_ の submission id を再利用するケースを取りこぼして
  いた。listSubmissions がエラー行を取得した後、それが返ってくる前にリトライが
  成功すると、フェッチ結果には同じ id がまだ（古い `error` 状態のまま）
  含まれているため、「id が無ければ残す」ルールでは古い方が勝ってしまう。
  `_localUpdateSeq`（送信のたびに増分する単調カウンタ）と、id ごとに
  最後にローカル更新された時点のカウンタ値を記録する
  `_lastLocalUpdateSeq` を導入し、`_selectTest` が fetch を発行した時点の
  カウンタ値（`fetchStartSeq`）より後にローカル更新された id は、fetch 結果に
  同じ id が含まれていても常にローカル側を優先する `_mergeFetchedSubmissions`
  に置き換えた
  （`test: 'a completed retry is not overwritten by a stale in-flight list
response'`）。
- **submissions 一覧の読込失敗はその読込をリトライする**: 共有の
  `_errorMessage` バナーの再試行ボタンは常に `_submit` を呼んでいたため、
  ファイルが既に選択された状態で `listSubmissions` が失敗すると、再試行が
  一覧の再取得ではなくアップロードを実行してしまっていた（ファイル未選択なら
  ボタンは無効のまま何も起きない）。エラーの発生元を `_ErrorKind`
  （`listLoad` / `submit`）として記録し、再試行ボタンの `onPressed` を
  `_errorKind` に応じて「同じ test で `_selectTest` をやり直す」か
  「`_submit` する」かに振り分ける
  （`test: 'retrying a list-load failure reloads the list, not an upload'`）。

## 18. 6回目のレビュー指摘への対応

- **ファイル確定処理失敗後もリトライ可能な状態を維持する（重大）**:
  `adapters.atomic.transactional_operation` は DB コミット成功後に staged
  ファイルを書き込む（`StagedFiles._finalize`）が、ディスク満杯や ACL
  エラーでこの書込みが失敗した場合、DB 側は既に `ai_processed`/
  `needs_review` としてコミット済みでロールバックできない。従来はこの
  失敗がそのまま未捕捉の例外として伝播するだけで、submission は
  「成功扱いだが一部ファイル欠落」のまま固定され、同じ PDF を再送しても
  `decide_reintake` が非 `error` 状態を見て `REJECT_DUPLICATE`（409）を返し、
  手動で `error` に書き換えても retry は `source.pdf` を再書込みしない
  （既存の最適化）ため欠落ファイルを直せなかった。`transactional_operation`
  はこの種の失敗を `FinalizationError`（`adapters/atomic.py`、新設）として
  明示的に区別して送出し、`adapters/submission_intake.py::intake_submission`
  がそれを捕捉して submission を新しいコミットで `error`
  （`review_reason="finalization_failed"`）へ移す。さらに retry 時の
  `source.pdf` 再書込みは「retry でなければ常に書く」から「retry でも
  ファイルが実際に存在しなければ書く」に変更し、どのファイルが失敗して
  いても次の retry で修復できるようにした
  （`test_finalization_failure_marks_error_and_a_retry_heals_the_missing_file`）。
- **画像パス生成前にパスセグメントをサニタイズする**: `Question.id` は
  ドメイン層では非空であることしか要求されないため、`../pages/page-1`
  のような値が「有効な ID」として通ってしまう。これを
  `submission_question_image_path` でファイル名に埋め込むと、
  `_ensure_within_root` は app-data 配下に留まる限り受理してしまい、
  結果的に同じ submission の page preview のパスに解決されて上書きして
  しまう（root からの脱出ではなく、root 内での取り違え）。
  `LocalFileStore._resolve` に渡される全パートを検証する
  `_ensure_safe_path_segment`（`adapters/local_storage.py`）を追加し、
  `/`・`\`・null バイト・空文字・`.`/`..` そのものを拒否する
  （`test_a_question_id_containing_a_path_separator_is_rejected` 等）。
- **リトライを downstream 処理から分離する**: `decide_reintake` は
  submission の状態が `error` であることだけを見て in-place retry を許可
  していたが、Issue #17 の範囲外である将来の OCR/AI 採点が
  recognition/grade/review/job 行を既に作っていた場合、retry は
  `answer_images` だけを差し替えて submission を `ai_processed` に戻すため、
  追記専用の history や未処理の job がそのまま孤立して残ってしまう。
  `SubmissionRepository.has_downstream_processing`（新設。4 テーブルいずれかに
  `submission_id` の行があれば true）を追加し、`decide_reintake` に
  `has_downstream_processing` パラメータを渡して、downstream 処理が
  存在する場合は `error` 状態でも `RETRY_EXISTING` ではなく
  `REJECT_DUPLICATE` にする。実際には OCR/採点はまだ実装されていないため
  現状のフローには影響しないが、将来それらが実装された時点で同じ穴が
  空かないようにする防御的な変更
  （`test_decide_reintake_rejects_an_errored_submission_with_downstream_processing`、
  `test_reintake_of_an_errored_submission_with_downstream_processing_is_rejected`）。
- **追い越された test-list リクエストを破棄する**: `_selectTest` は
  `_selectedTestId != testId` のチェックだけで古いレスポンスを弾いていたが、
  A→B→A と素早く切り替えると、最初の A リクエストが未解決のまま 2 回目の
  A リクエストが発行され、両方とも同じ `_selectedTestId == "A"` を通過して
  しまう。最初の（古い）レスポンスが後から届くと、2 回目のリクエストが
  取得した新しいデータを上書きし、その `finally` ブロックが 2 回目の
  リクエストの loading 状態まで誤って消してしまっていた。`_selectTest`
  呼び出しごとに単調増加する `_selectTestRequestId` を発行し、最後に
  発行されたリクエストのコールバックだけが結果の反映・loading 解除を
  行えるようにした（`_selectedTestId` との比較を `requestId ==
_selectTestRequestId` に置き換え）
  （`test: 'a superseded test-list request cannot overwrite a newer one'`）。
- **render 時の PDF 失敗を intake エラーに変換する**: pypdf にとっては
  有効なページツリー・ジオメトリを持ちながら、PDFium で実際に render
  する時だけ失敗する不正/非対応の content stream を含む PDF があり得る。
  従来この例外は `_write_submission` のページ処理ループから未捕捉のまま
  伝播し、文書化された bad-PDF 拒否（400）ではなく未処理の 500 になって
  いた。`pdf_engine.render_page_png` の呼び出しを try/except で囲み、
  `PdfCorruptedError` に変換する（`is_encrypted`/`page_count`/
  `page_geometry` に対して既に使っているパターンと同じ）
  （`test_a_render_failure_is_reported_as_pdf_corrupted_not_an_unhandled_error`）。

## 19. 7回目のレビュー指摘への対応

- **アップロードを読み込む前に intake 容量を確保する（重大）**:
  `intake_lock`（6 回目の対応）は render/DB フェーズだけを直列化するが、
  それより前の「アップロード本文をメモリへ読み込む」処理（async ハンドラ
  自身、event loop 上）は何も制限していなかった。認証済みクライアントが
  上限付近の PDF を同時に複数アップロードすると、各リクエストが
  `intake_lock` の順番待ちをするだけの間、それぞれが完全な `bytes` を
  保持し続け、個々のリクエストが上限内でも合計でメモリを枯渇させ得る。
  `create_app(..., max_concurrent_uploads=2)` で `threading.Semaphore` を
  用意し、`_read_upload_within_limit` を呼ぶ**前**に非ブロッキングで確保
  できなければ即座に `503` を返す（キューイングはしない。キューイングは
  「bytes を抱えたまま待つリクエスト」を「このハンドラ内で待つリクエスト」に
  置き換えるだけでメモリを何も改善しないため）
  （`test_concurrent_uploads_beyond_capacity_are_rejected_before_reading_the_body`）。
- **中断されたファイル確定処理を起動時に修復する**: `FinalizationError`
  （6 回目の対応）は例外を捕捉できる場合のみ機能する。DB commit 後、
  `_finalize` の前後でプロセスがクラッシュしたり電源が落ちたりすると、
  例外ハンドラは一切実行されず、submission は `ai_processed`/
  `needs_review` のままファイルだけが欠落し、同じ内容を再アップロードしても
  `REJECT_DUPLICATE`（409）になって永久に直せなかった。
  `adapters/submission_intake.py::repair_incomplete_submissions` を追加し、
  `create_app()` の起動時に一度、`ai_processed`/`needs_review` の全
  submission について期待されるファイル（`source.pdf`・各ページ preview・
  各 answer_image crop）の存在を確認し、一つでも欠けていれば `error`
  （`review_reason="finalization_failed"`）に戻す。あわせて、ドキュメント上は
  「起動時に実行する」とされながら実際にはどこからも呼ばれていなかった
  `LocalFileStore.sweep_temp`（Issue #11）も同じタイミングで呼ぶようにした。
  この関数はファイルを再生成するわけではなく、あくまで「再試行可能な状態に
  戻す」だけ -- 実際にファイルを埋めるには、人間が同じ PDF を再度アップロード
  する必要がある（サイドカーはアップロード bytes をリクエスト間で永続化
  しない）
  （`test_repair_incomplete_submissions_moves_a_submission_with_a_missing_file_to_error`、
  `test_starting_the_app_repairs_a_submission_left_incomplete_by_a_prior_crash`）。
- **永続化する student label に上限を設ける**: `student_label` は Issue #11
  導入時から長さ制限のない自由入力の nullable text だった。Flutter UI 経由
  では短いラベルしか送られないが、API を直接叩くクライアントはリクエスト
  サイズ上限のほぼ全てをこの 1 フィールドに詰め込め、それは生の値のまま
  SQLite に保存され、全ての submissions 一覧応答でそのまま返る。
  `domain/models.py::MAX_STUDENT_LABEL_LENGTH`（200）を新設し、
  `Submission.__post_init__` で検証（domain 層）、
  `api/app.py` の `Form(..., max_length=MAX_STUDENT_LABEL_LENGTH)` で
  API 層でも検証（超過は綺麗な `422` になり、domain 層まで到達しない）、
  さらに migration `0004_student_label_length.py` で
  `ck_submissions_student_label_length`
  （`student_label IS NULL OR length(student_label) <= 200`）を DB 制約として
  追加した（3 層目）。0003 の重複チェックと異なり事前チェック/バックフィルは
  行わない -- これまで上限が存在しなかったことを踏まえ、既存データが
  超過していれば batch 再作成が `IntegrityError` で失敗するに任せる（MVP で
  実データがまだ無い前提として許容）
  （`test_submission_student_label_length_is_capped`、
  `test_create_submission_rejects_an_overlong_student_label`、
  `test_check_constraint_rejects_bad_row`）。
- **ネイティブ file picker の失敗を捕捉する**: `_pickFile()` は
  `await widget.pickFile()` を無防備に呼んでおり、platform channel や
  ダイアログの失敗で例外が飛ぶと、ボタンの `onPressed` コールバックから
  未捕捉の非同期エラーとして漏れ、エラー表示もリトライ手段もないまま画面が
  残っていた。try/catch で囲み、`_ErrorKind.filePick` として記録して
  共有のエラーバナー経由でメッセージと「再試行」（`_pickFile` を再度呼ぶ）を
  提供するようにした
  （`test: 'a native file-picker failure shows an error with a working
retry'`）。

## 20. 8回目のレビュー指摘への対応

- **FastAPI が multipart ボディを解析する前にアップロードをゲートする（重大）**:
  7 回目で追加した `intake_capacity`（`threading.Semaphore`）はハンドラ内で
  取得していたが、それは FastAPI がルーティング・依存解決の一環として
  `await request.form()` を実行し、multipart ボディを完全に spool した
  **後**にしか実行されない。`require_token`（Bearer 認証）も同じ依存解決の
  中の一つの `Depends` に過ぎず、ボディの解析より確実に先に走る保証はない。
  つまり有効なトークンを持たないクライアントを含む複数のクライアントが
  上限付近の multipart ボディを同時に送ると、いずれの防御にも引っかかる前に
  パーサ側のメモリ/一時ディスク使用が積み上がり得た。
  `api/submission_upload_gate.py::SubmissionUploadGateMiddleware` を新設し、
  `POST /tests/{test_id}/submissions` にだけ絞って ASGI の `receive` 境界
  （`MaxBodySizeMiddleware` より外側に登録し、それより先に実行される）で
  Bearer トークンの検証と capacity の確保を行う。認証に失敗すれば `401`、
  capacity が枯渇していれば `503` を、いずれもボディを一切読まずに返す。
  ハンドラ側にあった capacity の取得/解放は削除し、このミドルウェアに
  一本化した
  （`test_rejects_a_request_with_no_bearer_token_before_touching_the_body`、
  `test_rejects_when_capacity_is_exhausted_before_touching_the_body`、
  `test_create_submission_requires_auth`）。
- **streamed ボディの超過に対して 413 を維持する**: `MaxBodySizeMiddleware`
  の Content-Length なしパスは、ラップ先のアプリの `receive()` 呼び出し中に
  `_BodyTooLarge` を送出して検知していた。しかし multipart リクエストでは
  その `receive()` 呼び出しは FastAPI 自身の `await request.form()` の内部で
  行われ、FastAPI はそこを丸ごと `except Exception: raise HTTPException(400,
...)` で囲んでいるため、送出した `_BodyTooLarge` は本ミドルウェアの
  `except` に届く前に FastAPI に捕まり、汎用的な `400` に化けて `413` が
  クライアントに届かなかった。「ラップ先が受信中に例外を送出したら検知する」
  設計自体が、ラップ先の例外処理次第で成立しなくなる。
  ミドルウェア自身がメッセージを `max_bytes + 1` バイト分までバッファし、
  上限内で完結すれば全メッセージをラップ先へ再生（replay）し、超過すれば
  ラップ先を一切呼び出さずに自分で `413` を送信するよう変更した -- ラップ先が
  例外をどう扱おうと無関係になる
  （`test_streamed_overflow_yields_413_even_if_the_wrapped_app_swallows_exceptions`）。
- **Windows のドライブ相対パスセグメントを拒否する**:
  `local_storage.py::_ensure_safe_path_segment` は `/`・`\`・`..` 等は
  拒否していたが、コロンは見ていなかった。Windows では `C:foo` のような
  セグメントに区切り文字が一切無いにもかかわらず、
  `Path.joinpath(root, "C:foo.png")` は素の `foo.png` と同じパスに解決される
  ため、`Question.id` が `"C:foo"` と `"foo"` のように衝突する 2 つの値で
  あっても同じ 1 枚の PNG を指してしまい得る。コロンを含む値と、拡張子の
  有無に関わらず Win32 API が予約デバイスとして扱う名前（`CON`・`PRN`・
  `AUX`・`NUL`・`COM1`-`9`・`LPT1`-`9`、大小文字区別なし）を拒否するよう
  `_ensure_safe_path_segment` を拡張した
  （`test_a_question_id_shaped_like_a_windows_drive_relative_path_is_rejected`、
  `test_a_question_id_matching_a_windows_reserved_device_name_is_rejected`）。
- **永続化する original filename に上限を設ける**: `original_filename` は
  拡張子が `.pdf` であることと区切り文字を含まないことしか検証しておらず、
  長さには上限が無かった。multipart のパート単位のヘッダにはサイズ上限が
  無く、ボディ全体の上限（約 50MiB）まで許容してしまうため、API を直接叩く
  クライアントは小さな PDF 本体とは無関係に、この 1 フィールドで DB と
  一覧応答を肥大化させ得た。`domain/models.py::MAX_ORIGINAL_FILENAME_LENGTH`
  （255）を新設し、`domain/pdf_intake.py::validate_filename`（PDF を開く前の
  最も安価なチェック）と `Submission.__post_init__` の双方で検証、
  さらに migration `0005_original_filename_length.py` で
  `ck_submissions_original_filename_length` を DB 制約として追加した
  （0004 と同じ 3 層構成）。`student_label` と異なり `Form(...)` のような
  API 層での宣言的な長さ制限は使えない（`filename` は multipart パートの
  ヘッダであり、FastAPI の Form フィールドではない）ため、API 層の防御は
  「`PdfInvalidTypeError` は既存のハンドラで綺麗な `400` に変換される」という
  既存の仕組みにそのまま乗る形になる
  （`test_validate_filename_rejects_a_name_longer_than_the_limit`、
  `test_submission_original_filename_length_is_capped`）。

### 8回目レビュー対応中に見つかった別件の不具合（2件）

`app/test/sidecar_api_client_test.dart`（実プロセスとしてサイドカーを起動する
統合テスト）がローカル環境で不安定に失敗する件を調査する過程で、レビュー指摘とは
別に実在する不具合を 2 件発見し、あわせて修正した。

- **`sidecar.py` のポート決定に TOCTOU 競合状態があった**: 従来の
  `resolve_port()` は使い捨てのプローブ用ソケットを `bind` してOSが割り当てた
  ポート番号を読み取り、そのソケットを閉じてから番号だけを返し、`run()` が
  後で `uvicorn.run(port=...)` として同じ番号に**改めて** bind し直していた。
  「空きポートが見つかった瞬間」と「実際にそのポートで listen する瞬間」の
  間には `create_app()`（スキーマmigration実行、環境によっては1秒前後）を
  挟む real なギャップがあり、その間にOSが同じポート番号を他の用途に
  割り当ててしまうと、handshakeファイルに書いた番号と実際にuvicornが
  listenするポートがズレる。このマシン上で手動再現に成功した（netstatで
  handshake記載のポートが全く listen されておらず、実際には隣の番号で
  listen されていた）。`_bind_socket()` に置き換え、ソケットを bind した
  まま保持し続け、handshake書き込みから `uvicorn.Server(config).run(sockets=
[sock])` に渡すまで同じソケットオブジェクトを手放さないようにしてギャップを
  完全に無くした
  （`test_bind_socket_zero_returns_an_open_socket_on_a_free_loopback_port`、
  `test_run_binds_loopback_and_hands_off_matching_credentials`）。
- **統合テスト自身の共有サイドカー起動ヘルパーに競合状態があった**: 7回目で
  `setUpAll` をやめて自作の遅延初期化に変えた際、「解決済みの値」だけを
  `if (x != null) return x;` でメモ化していた。`package:test` はこのファイルの
  トップレベル `test()` を厳密に1つずつ順番には実行しない（複数が同時進行し
  得る）ため、最初の起動が完了する前に複数のテストがこのチェックへ到達すると
  全員が「まだ無い」と判定し、それぞれ別々にサイドカープロセスを起動してしまい
  得た。進行中の `Future` 自体を（`await` する前に同期的に）メモ化する
  single-flightパターンに変更し、最初の起動を全員が共有するようにした。

上記2件を修正した上でもなお、このマシンではこのテストファイルだけ約90秒かかる
ことがある。`_waitUntilHealthy` が失敗する際の実際の症状は「接続拒否」ではなく
「接続がタイムアウトする（応答が一切返らない）」で、しかもサイドカー自身は
その直後に確かに該当ポートで listen できていることを確認した。これは
新規生成された未認識の子プロセスへのループバック接続をリアルタイムに検査する
セキュリティソフトの介入によく見られる症状と一致する（本マシンはWindows
Defenderのリアルタイム保護が有効でサードパーティ製AVは無し。管理者権限が無く
除外設定の有無は未確認）。CIは `windows-latest` のホスト型ランナーを使うため
再現しない可能性が高い。アプリケーションコード側でこれ以上確実に解決する手段は
見つかっていない未解決事項として記録する。

## 21. 9回目のレビュー指摘への対応

- **Windows のファイル名として使う前に設問 ID をエンコードする（重大）**:
  `submission_question_image_path()` は `Question.id` をそのままファイル名へ
  埋め込んでいた。domain 層は非空であることしか要求しないため、`?`・`*`・
  `"`・`<`・`>`・`|` のような Windows のファイル名で禁止された文字を含む ID
  は書込みのたびに失敗し続け、大文字小文字だけが異なる 2 つの ID（NTFS は
  ファイル名の大小文字を区別しない）は同じファイルに解決されて、DB の行は
  両方残っているのに片方の crop がもう片方を黙って上書きしてしまい得た。
  `_encode_filename_component()` を新設し、ID の UTF-8 バイト列を hex
  エンコードしてからファイル名に使うようにした。結果は常に `[0-9a-f]` のみで
  構成される（どの環境でも安全）うえバイト完全一致のエンコードなので、大小
  文字や記号が異なる ID は必ず異なるファイル名になる。個別の禁止文字を
  ブロックリストで弾く従来方式をこの呼び出し箇所については置き換える形になる
  （`test_question_ids_differing_only_by_case_do_not_collide`、
  `test_a_question_id_matching_a_windows_reserved_device_name_is_encoded_safely`）。
- **一時ルートのクリーンアップ前に SQLite engine を dispose する**:
  `data_root` を指定せずに `create_app()` を呼ぶと、起動時の repair クエリ
  （および以後のあらゆる DB アクセス）が engine の接続プールに接続を残すが、
  SQLAlchemy は engine 自体を dispose するまでプール内の接続を閉じない。
  Windows は開いたままの DB ファイルを含むディレクトリの削除を拒否するため、
  `scratch.cleanup` だけを登録していた従来のコールバックは `PermissionError`
  を送出し、一時 app-data ディレクトリをリークしていた（本セッション中
  ずっと pytest 実行後に出ていた "Exception ignored in atexit callback" の
  正体がこれだった）。cleanup コールバックを 1 つにまとめ、engine を
  dispose してからディレクトリを削除するようにした
  （`test_default_temp_app_data_dir_cleanup_disposes_the_engine_first`。
  修正前に戻すと実際に落ちることを確認済み）。
- **宣言された MIME タイプを大文字小文字を区別せず比較する**: HTTP メディア
  タイプの type/subtype トークンは大文字小文字を区別しない（RFC 9110
  §8.3.1）が、`validate_declared_mime` は宣言文字列をそのまま
  `ALLOWED_MIME_TYPES` と比較していたため、`Application/PDF` や
  `application/PDF; charset=binary` のような規格に準拠したクライアントの
  宣言を `400` で拒否してしまっていた。allowlist と照合する前にベースの
  メディアタイプを小文字化するようにした
  （`test_validate_declared_mime_is_case_insensitive`）。
