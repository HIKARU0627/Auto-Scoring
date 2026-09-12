# テスト登録とテストプロファイル確認・修正

GitHub Issue [#16](https://github.com/HIKARU0627/Auto-Scoring/issues/16)（親
[#3](https://github.com/HIKARU0627/Auto-Scoring/issues/3)）の実装記録。模範解答PDF・
採点マニュアルPDFを登録し、AIが生成した候補（設問・回答欄・添削記号領域・配点・採点基準・
模範解答）を人間が確認・修正し、設問依存関係グラフ（Issue #26）と合わせて確認済みにして
初めてテスト登録が完了する一連のフローを実装する。

> **⚠ 入力の前提は Issue #95 で変更された。** 本書が記録している「模範解答PDF・採点マニュアル
> PDFを登録する」という入力モデルは、実際の採点者が持っている資料と対応していなかった。
> 現在の仕様は [`simplified-design-specification.md`](./simplified-design-specification.md)
> §4（必須は採点基準PDFと生徒答案PDF）・§6.2（回答欄は答案から解析する）が正である。
> **本書は実装当時の記録として残してあり、実装の作り直しが必要な箇所を示す。**

依存: [#10](https://github.com/HIKARU0627/Auto-Scoring/issues/10)（認証付きサイドカー
API）、[#11](https://github.com/HIKARU0627/Auto-Scoring/issues/11)（MVPデータモデル）、
[#15 PoC 4](https://github.com/HIKARU0627/Auto-Scoring/issues/15)（`Profile` の
draft/confirmedパターン）、[#26](https://github.com/HIKARU0627/Auto-Scoring/issues/26)
（設問依存関係DAG、そのAPIをそのまま利用する）。

> **Issue #103 による更新（配点・採点基準の入力口）**
>
> このドキュメントの以下の記述は、Issue #103 時点では**過去の姿**である。
>
> - 「模範解答PDF」は必須入力ではなくなった（#95 決定 1、Issue #101）
> - **配点・採点基準・模範解答の入力口は、`SCORE`/`RUBRIC`/`MODEL_ANSWER` region から
>   「配点と採点基準」節（`CriteriaDraft`）へ移った。** region 側の経路は
>   Issue #103 以前に登録されたテストのための**後方互換 fallback として残っている**が、
>   画面からは新しく作れない
> - `build_questions_and_rubrics` は region と確定済み `CriteriaDraft` の**両方**を受け取る
>
> 現在の設計は [`criteria-extraction.md`](./criteria-extraction.md) を参照。
> 以下の記述は、fallback 経路がなぜその形なのかの根拠として残している。

## 資料の取込と答案の取込を 2 段に分ける（Issue #306 案 A）

実機では、1 回の取込で「テストを作った直後に同じ処理で答案を上げる」ため、テストが
まだ `draft` の時点で `POST /tests/{id}/submissions` を呼び、必ず 409
（`TestNotReadyError`）になっていた。さらに同じフォルダを取り込むたびに別のテストが
作られ、登録済みの `ready` なテストへ答案が入る経路が画面に存在しなかった。

**採用した設計は案 A**（バックエンドのライフサイクルは変えない）:

1. **第 1 段（対象テストが `ready` でない）**: 資料を取り込み、必要なら新しい
   `draft` テストを作る。**答案は上げない。** 画面は
   「このテストはまだ登録が済んでいないので、答案はこのあと取り込みます」と事実を出し、
   登録完了後に同じフォルダをもう一度取り込むよう案内する。
2. **第 2 段（対象テストが `ready`）**: 既存の `ready` なテストへ答案を取り込み、
   `ai_processed` になった答案の AI 採点を起動する。

**どちらの段かは対象テストの `status` から機械的に決める。** 画面の状態変数
（フラグや step）では持たない。`ready` だけが答案を受け付ける
（`desktop/src/renderer/core/intake-review.ts` の `targetTestAcceptsAnswers`、
バックエンドの `TestNotReadyError` と同じ規則）。

### 既存テストの再利用規則（Issue #306）

同じフォルダのグループに対して毎回新しいテストを作らない。取込プランのグループ名は
フォルダの第 1 階層から作る `suggested_name`（`domain.intake_plan._group_key`）で、
登録するテスト名もこれを使う。**同じ名前の既存テストがあればそれを再利用する**:

- 同名のテストが複数あれば `ready` を優先し、無ければ `ready` でないもののうち
  直近に作られたものを選ぶ（`intake-review.findReusableTest`）。
- 再利用時は**資料を差分だけ足す**。`POST /tests/{id}/materials` は同一
  `(role, sha256)` の再送で既存を返す（`adapters.test_intake.attach_materials`）ため、
  同じ採点基準 PDF を送り直しても二重にならない。
- 再利用は**確定済みの配点・回答欄プロファイル・依存グラフに触れない**。これらは
  `profile.json` / `criteria` / 依存グラフの確定として別に保存されており、
  `materials` の追加はそれらを変更しない。壊す必要がある操作（`draft` へ戻す、
  region を作り直す等）は無い。
- 名前は再利用の唯一の手掛かりであり、フォルダ側にそれ以外の永続的な識別子は無い。
  テスト名を変更すると次回は別テストとして作られる。

### 取り込んだ資料を別ウィンドウで見る（Issue #415）

登録済みテストの資料は `GET /tests/{id}/materials` が役割つき
（`student_answer` / `grading_criteria` / `annotation_resource` / `annotation_sample` /
`reference`）で返す。画面はこれを一覧し、選んだ資料の中身を**別ウィンドウ**で表示する。

- 入口は**テスト設定と添削レビューの両方**（各画面の「資料を開く」）。
- ウィンドウは**メインプロセスが IPC で開く**。renderer の `window.open` は使わず、
  `desktop/src/main/main.ts` の `setWindowOpenHandler` の拒否はそのまま残す。
- **1 枚を使い回す。** 別のテスト・別の資料を開くと中身を差し替え、枚数は増やさない。
- 中身は `page_image_router` と同じページ画像（PDF のみ）。Word/Excel はサーバが 415 を
  返し、画面は役割とファイル名を示して「アプリ内でプレビューできない」と説明する
  （黙って空にしない）。生ファイルは返さない（`docs/sidecar-api.md` §7.6）。
- 別ウィンドウを閉じても採点操作は続く。主ウィンドウを閉じると別ウィンドウも閉じる。
- ウィンドウは主ウィンドウと同じ preload・同じ CSP で、`contextIsolation` /
  `nodeIntegration` / `sandbox` の 3 点を満たす（`desktop/test/architecture.test.ts`）。

### 失敗理由を捨てない（Issue #306）

`createSubmission` は HTTP `status` と `detail` を保持した `SubmissionIntakeError` を
投げ、画面は `core/action-requirements.ts` の文言で理由を出す。少なくとも次の 3 つを
区別する:

| バックエンド                                 | 画面での扱い                                       |
| -------------------------------------------- | -------------------------------------------------- |
| 409 `TestNotReadyError`（`detail` が文字列） | 登録が済んでいない。登録を先に終える               |
| 409 `existing_submission_id` あり            | 同じ答案がすでに入っている（失敗ではない）         |
| それ以外（400 系 / 500 系）                  | 入力の拒否か一時障害か。再試行の可否を文言で分ける |

### ホームの「次にやること」（Issue #306）

`ready` でないテストがある間は、答案が 0 件でも「答案を取り込む」より先に
「登録を続ける」を出す。これで「答案が無い → 取り込み → 失敗 → 登録が途中 →
登録 → 答案が無い」の 2 画面ループに入らない。

## 決定事項

### `Test` の登録ライフサイクル（`draft` → `ready`）

Issue #11時点の `Test` エンティティには状態が無かった。Issue #16で
`domain.models.TestStatus`（`DRAFT`/`READY`）と `Test.status`（既定
`DRAFT`）を追加し、`Test.mark_ready()` で一方向にのみ遷移させる（`READY` から
`DRAFT` へ戻す経路は無い。再度 `mark_ready()` を呼ぶと
`InvalidStateTransition`）。DBは `tests.status` 列（`CHECK (status IN ('draft',
'ready'))`、マイグレーション `0011_test_status`）で同じ制約をミラーする。

**`ready` になる条件**（`POST /tests/{test_id}/complete-registration`、Issue #16
受入条件「全必須項目確認後にだけ登録完了になる」）:

1. テストプロファイルが `confirmed`（後述）
2. 設問依存関係グラフ（Issue #26）が `confirmed`（`get_latest_confirmed` が存在）

どちらか一方でも欠けていれば `409` を返し、不足している項目を日本語で列挙する。両方揃って
初めて `Test.mark_ready()` を呼ぶ（compare-and-set: `TestRepository.mark_ready` は
`WHERE status = 'draft'` の条件付き `UPDATE` で、二重登録レースを避ける）。

**条件 1 を実際に満たせるようにしたのが Issue #105 である。** 実資料には模範解答 PDF が
無い（#95 決定 1）ため、下記のテキスト由来の候補生成では現実のテストのプロファイルを
作れず、**どのテストも `ready` になれなかった**。生徒の答案そのものから回答欄を検出して
確定する経路は [answer-area-detection.md](./answer-area-detection.md) にある。
門の条件は緩めていない —— 満たせるようにした。

### 候補生成: 実PDFテキストのヒューリスティック抽出（PoC 4のタグ付き注釈を置き換え）

PoC 4（Issue #15）の `adapters.pdf.annotation_markers` は、PDFのSquare注釈（開発者が
仕込んだタグ）からRegion候補を作る**検証用の代替実装**であり、実際の模範解答・
マニュアルPDFにはそのような注釈は存在しない（`docs/poc-4-multi-layout-profiles.md`
「PoC限定・要再確認」に明記済み）。Issue #16でこれを実運用の候補生成
（`adapters.pdf.profile_candidate_generation`）に置き換えた。`annotation_markers` は
PoC 4自身の回帰テスト用にそのまま残す。

**Issue #16 実装時点で** `AIProvider`/`OCRProvider` の具体サービス選定が未確定だった
ため、Issue #26のヒューリスティック依存関係analyzer
（`ReferenceHeuristicDependencyAnalyzer`）と同じ方針を取っている: **外部AI呼び出しを
行わない、決定的なテキストパターンマッチング**。

> サービス選定はその後 Issue #81 で確定した（OCR: Google Document AI、AI: 優先度つき
> フォールバック。`technology-stack.md` §3.5）。ただし実アダプタは未実装で、ここの
> ヒューリスティック実装は**接続待ちのまま変えていない**。AI/OCR を使った候補生成へ
> 置き換えるかどうかは別途判断する。

- `adapters.pdf.text_layout_extraction.extract_text_lines` が pypdfium2 の
  `PdfTextPage`（`count_chars`/`get_text_range`/`count_rects`/`get_rect`）を使い、
  ページの全文をpdfiumが返すCRLF区切りで行に分割し、各行の外接矩形（PDFユーザー空間）を
  求める。pdfium自体はレイアウト解析（単語/行/段落検出）を行わないため、「行」は
  pdfiumが返す最小単位に留まる。
- `adapters.pdf.profile_candidate_generation` が `(?:問|大問)\s*(\d+)` パターンで
  設問番号の見出し行を検出し、次の見出しまでの行群をその設問の本文として束ねる
  （`_QuestionBlock`）。
  - 模範解答PDF: 見出し行 → `QUESTION` region（text=見出し文言）、本文行の外接矩形 →
    `ANSWER_AREA` region と `MODEL_ANSWER` region（text=本文結合）。
  - 採点マニュアルPDF: 同じ見出しパターンで設問を束ね、本文全体を `RUBRIC`
    region（text=本文結合）にし、`(\d+)\s*点` にマッチする行があれば `SCORE`
    region（text=マッチした数字）を追加する。
  - `ANNOTATION_AREA`（○×等候補領域）は自動検出の対象にしない。添削記号の配置は
    テキストパターンから推測できる情報ではないため、常に人間の手動追加に委ねる。

### マニュアルPDF由来regionの座標アンカリング

`Profile.signature`（`FormatSignature`）は**模範解答PDF（≒生徒答案）の版面**を表す
（`profile_apply.reapply_profile` が答案と照合するのはこちらのため）。採点マニュアルPDFは
別文書で独自の版面を持ち、そのページ番号・座標を模範解答PDFのregionと同じ
`FormatSignature` に混ぜて持たせることはできない。

そのため `RUBRIC`/`SCORE` regionは**模範解答PDF側の対応する設問見出しのページ**に
アンカリングし、その見出し直下（下端に余白が無ければ上）に小さなプレースホルダー矩形
（既定高さ0.03正規化単位）を置く。座標は仮置きであり、マニュアルPDFから信頼できるのは
**テキスト内容**（採点基準文言、抽出した配点）だけ。実際の位置は人間がテスト設定画面で
移動する前提 —— これはPoC 4がすでに定義していた「自動検出困難な形式は手動指定に倒す」
方針の延長。

### `Region.text` の追加（後方互換）

`domain.profile.Region` に `text: str | None = None` を追加した（Issue #15時点は座標の
みで、テキスト内容を保持しない設計だった）。`MODEL_ANSWER`/`RUBRIC`/`SCORE`/`QUESTION`
regionが実データ（`Question.model_answer`・`RubricCriterion.description`・配点数値）を
運ぶために必要。`to_dict`/`from_dict` は省略時 `None` にフォールバックするため、
Issue #15時点で保存された `profile.json`（`text` キーが無い）もそのまま読み込める。

### Regionから `Question`/`Rubric` への変換（`domain.test_registration`）

`Profile`（PDFレイアウトのregion集合、Issue #15）と `Question`/`Rubric`（実際の採点対象
エンティティ、Issue #11）は別の世界のモデルであり、その橋渡しがIssue #16で新規に必要
だった。`build_questions_and_rubrics` が確定済みregionを `Region.label`（設問番号）で
グルーピングし、変換する:

- `label` ごとに厳密に1つの `QUESTION` region が無ければ、そのlabelは設問にならない
  （手動追加した孤立regionを無視する）。2つ以上あれば `DuplicateQuestionNumberError`
  （Issue #16受入条件「重複question idを拒否する」）。
- 同じ `label` の `ANSWER_AREA`/`ANNOTATION_AREA`/`SCORE` regionのbboxを、それぞれ
  `Question.answer_area`/`comment_area`/`score_area` にする（`NormalizedBBox`
  →`NormalizedRect` は単純な reshape。両者とも top-left 原点・0〜1 なので座標変換は無い）。
- `SCORE` regionのtextから `\d+` を抽出したものを `Question.points` にする。マッチしない
  ・region自体が無い・0以下の場合は `InvalidScoreError`（受入条件「配点不正を拒否する」）。
- `MODEL_ANSWER` region群のtextを結合したものが `Question.model_answer`。
- `RUBRIC` region群のtextを結合したものを1件の `RubricCriterion`
  （`max_points`=配点と同じ、`position=0`）として `Rubric` にする。複数の採点観点への
  自動分割は行わない（人間が編集画面で分割・追加できる設計だが、Issue #16の
  UIスコープでは1criterion固定 —— 下記「UI設計」の未決事項を参照）。

**Issue #103 以降**: 上の 3 項目（`SCORE`/`MODEL_ANSWER`/`RUBRIC`）は、
**確定済みの `CriteriaDraft` がそれを持たないときの fallback** になった。
ドラフトがあればそちらが優先し、採点基準は 1 件固定ではなく
**PDF から読んだ件数ぶんの `RubricCriterion`** になる。region 側は座標だけを担う。
詳細は [`criteria-extraction.md`](./criteria-extraction.md) §6。

**Issue #120 以降**: `score_area`/`comment_area` は、`SCORE`/`ANNOTATION_AREA`
region が無いとき **`answer_area` から導出される**
（`domain.annotation_layout.derive_mark_areas`）。#103 が `SCORE` 領域を画面から
外した結果、新経路で登録したテストは両方とも `None` になり、添削済み PDF が
無記入のまま出力されていた。手で置いた region があればそちらが優先される点は
変わらない。導出の規約と、それでも決まらないとき出力前に断ることは
[`pdf-export.md`](./pdf-export.md) §2.2.1。

**Issue #159 以降**: 導出されるのは **`comment_area` だけ**になった。`score_area` は
`SCORE` region が無ければ `None` のままで、点数の位置は**出力時**に
ページ左余白へ解決される（`domain.pdf_export.fallback_score_areas`）。
導出した帯が実機で筆跡・印字の上に載っていたためで、計測と判断は
[`pdf-export.md`](./pdf-export.md) §2.2.3。手で置いた `SCORE` region が
優先される点は変わらない。

**Issue #161 以降**: **`answer_area` からの導出は無くなった。**`comment_area` も
`ANNOTATION_AREA` region が無ければ `None` のままで、注釈コメントは**出力時**に
末尾の注釈ページへ解決される（`domain.pdf_export.build_note_pages`）。
同じ帯がコメント側でも筆跡に重なっていたためで（最悪 19.1%）、しかもコメントは
散文なので #150 の幅3%の左余白帯には入らない。実答案8教科を測っても、文が入るだけの
空白は答案上に無かった。計測と判断は [`pdf-export.md`](./pdf-export.md) §2.3.2。
手で置いた `ANNOTATION_AREA` region が優先される点は変わらない。

### Profile確認は一方向・一度きり

`Profile.confirm()` はPoC 4から一方向（DRAFT→CONFIRMED）。Issue #16のAPI
（`POST /tests/{test_id}/profile/confirm`）は既にCONFIRMEDのprofileへの再confirmを
`409` で拒否する。個々のregionに対する「このregionだけ確認済み」という操作は無い ——
`Profile.__post_init__` がDRAFTのprofileに`confirmed=true`のregionが混じることを
そもそも禁止しているため、confirm操作自体が「今のDRAFT regionセット全体を一括承認する」
という単一の行為になる。人間はconfirmを押す前に `PUT /profile` で何度でも内容を
編集できる。

confirmは`ProfileResponse.revision`（`Profile.revision`、`/profile/analyze`・
`PUT /profile`のたびに増分、confirm自体では変わらない）へのcompare-and-setでもある
（PRラウンド8）——`POST /profile/confirm`は`revision`をbodyで要求し、profileが
現在保持するrevisionと一致しない場合は`409`で拒否する。2つのクライアントが同じ
testをreviewしている場合、client Aの保存～confirmの間に別のPUT/analysisが割り込むと、
このrevisionチェックが無ければclient Aはレビューしていないregionセットを自分の
attestationで確定してしまう。テスト単位のlock（上記）はrequest同士を直列化するだけで、
「後から来たrequestが正当にprofileを変更する」ケースまでは防げないため、別途この
compare-and-setが必要だった。

### API一覧（`api.test_registration_router`）

すべて既存のBearer認証必須ルータ配下（`docs/sidecar-api.md` §2）。

| メソッド・パス                                   | 用途                                                           |
| ------------------------------------------------ | -------------------------------------------------------------- |
| `POST /tests`                                    | 模範解答PDF+採点マニュアルPDFを検証・保存し `draft` Testを作成 |
| `GET /tests/{test_id}`                           | テストの現在の登録状態                                         |
| `POST /tests/{test_id}/profile/analyze`          | 候補生成（再実行可、confirm後は409）                           |
| `GET /tests/{test_id}/profile`                   | 現在のprofile（draft/confirmed）                               |
| `PUT /tests/{test_id}/profile`                   | regions全体を人間の修正結果で置換（confirm後は409）            |
| `POST /tests/{test_id}/profile/confirm`          | 全regionを一括確認し、Question/Rubricを確定                    |
| `POST /tests/{test_id}/complete-registration`    | profile・依存グラフ双方confirmed後にreadyへ                    |
| `POST /tests/{test_id}/dependency-graph/analyze` | Issue #26既存API。そのまま利用                                 |
| `POST /tests/{test_id}/dependency-graph/confirm` | Issue #26既存API。そのまま利用                                 |

PDF検証（拡張子・宣言MIME・magic bytes・size上限・page数上限・暗号化・破損）は
`adapters.test_intake.register_test` が `domain.pdf_intake`（Issue #17で確立済み）を
そのまま再利用する。模範解答・マニュアルの2ファイルのうちどちらかが不正なら両方とも
保存されない。

### テスト設定画面のUI設計: フィールド編集、PDFオーバーレイではない

簡易設計書 §13 は編集中PDFの表示方針として「PDF + Annotation Overlay」を掲げているが、
Issue #16のテスト設定画面はこの方式を採用せず、**region一覧をテキストフィールド
（種類・設問番号・ページ番号・x0/y0/x1/y1・テキスト）で直接編集する**UIとした。

- 理由: pdfrxベースのPDFオーバーレイ編集（ドラッグでの矩形移動・リサイズ、PDF表示との
  同期）はそれ自体が独立した実装量の大きい機能であり、Issue #16のスコープ（候補生成→
  確認→確定のフロー全体、および設問依存関係グラフの確認UIとの統合）を優先した。
- 影響: 人間はregionの位置を数値で入力する（0〜1正規化座標）。実際の塾利用でこの
  UXが十分かは未検証。
- **未決事項**: PDFオーバーレイでのビジュアル編集（ドラッグ&ドロップでの矩形調整）は
  後続Issueで追加を検討する。追加時は既存の `PUT /profile` API・`RegionModel`
  スキーマをそのまま使える設計にしてある（座標系はpdfrx/PoC3と同じtop-left原点0〜1）。
- 同様に、`Rubric` の複数criteriaへの分割編集UIも今回は実装しない（1criterion固定、
  上記「Regionから Question/Rubric への変換」参照）。分割が必要になった場合は
  `RubricCriterion` のCRUD APIを別途追加する。

## 検証

- `backend/tests/test_domain_models.py`: `Test.mark_ready` の一方向遷移。
- `backend/tests/test_profile.py`: `Region.text` の往復・後方互換（`text`キー無しの
  旧`profile.json`も読み込める）。
- `backend/tests/test_text_layout_extraction.py`: 実PDFからの行テキスト・矩形抽出。
- `backend/tests/test_profile_candidate_generation.py`: 設問番号パターン検出・
  RUBRIC/SCOREのマニュアルPDFアンカリング・`generate_profile_candidates`の統合。
- `backend/tests/test_test_registration.py`: `build_questions_and_rubrics` の
  グルーピング・配点不正・重複question id・未検出設問なしの拒否。
- `backend/tests/test_test_registration_api.py`: 登録→解析→編集→確定→依存グラフ確定→
  登録完了の一連のAPIフロー、不正PDF拒否、confirm後の編集不可、プロセス再起動後の
  profile復元（Issue #16受入条件「保存後の再起動で修正内容が復元される」）。
- `app/test/test_registration_page_test.dart` / `test_settings_page_test.dart`:
  テスト登録画面・テスト設定画面のwidget test（フォームバリデーション、エラー表示と
  再試行、region編集と保存、依存グラフ確認、登録完了ボタンの活性制御）。

## レビュー対応（PRラウンド1）

- **`ready` の強制を答案取込側にも配線**: `GET /tests`（答案取込のテスト選択）は
  `TestStatus.READY` のテストのみ返し、`intake_submission`（Issue #17）も
  `draft` のテストへのsubmission作成を`TestNotReadyError`（409）で拒否する。
  従来は`Test`行の存在確認のみだったため、profile/依存グラフが未確認のまま
  答案処理を始められてしまっていた。
- **profile確定は保存してから確定する**: テスト設定画面の「確定」操作は、まず
  現在のworking copyを`PUT /profile`で保存してから`POST /profile/confirm`を
  呼ぶ。以前は未保存の編集がconfirmで黙って破棄され得た。
- **登録リクエストのボディ上限を2ファイル分にする**: `MaxBodySizeMiddleware`は
  アプリ全体で共有される1つの上限であり、`POST /tests`は模範解答・マニュアルの
  2ファイルを1つのmultipartボディで受け取るため、`IntakeLimits.max_size_bytes`
  の2倍+multipartオーバーヘッドをASGI層の上限にした。
- **依存関係分析に問題文を渡す**: `Question`にはまだ問題文（prompt_text）を
  保存する列が無い（`dependency-graph.md`参照）。テスト設定画面は確定済み
  `QUESTION` regionのtextを`{test_id}:{label}`形式のquestion_idに対応付けて
  `QuestionTextOverride`として渡すようにした。
- **`UpdateProfileRequest.regions`を必須化**: `default_factory=list`だと
  `{}`のような不正bodyが422にならず全region削除として成功してしまっていた。
- **配点テキストの数値抽出を厳格化**: `\d+`の単純な検索は`"-5"`や`"5.5"`から
  正の整数`5`を抜き出してしまい、後続の非正数チェックをすり抜けていた。直前直後に
  `-`/`.`/数字が無い数字列のみを配点として認める正規表現に変更した。
- **登録PDFのfinalization失敗を補償する**: `Test`行のcommit後にPDFのディスク
  書き込みが失敗すると（`FinalizationError`）、`Submission`と異なり`Test`には
  再試行用の`error`状態が無いため、可視のdraft testが永久に壊れたまま残って
  いた。同じトランザクション内で`Test`行と書き込み済みファイルを削除する補償を
  追加した。
- **profile確定をDB/ファイル間で回復可能にする**: Question/Rubricのcommit後に
  `profile.json`の書き込みが失敗すると、再試行時に同じ決定的IDでのinsertが
  UNIQUE制約違反になり詰まっていた。DB書き込みを「既存なら追加しない」冪等な
  ものにし、再試行はファイル書き込みだけをやり直せるようにした。
- **PDFiumの呼び出しを直列化する**: `analyze_profile`と`create_test`内のPDF
  検証は、答案取込パイプラインが使う`intake_lock`と同じロックを共有するように
  した。pypdfium2はプロセス内マルチスレッドで安全に呼べないため、以前は
  analysisと答案取込が同時に走るとPDFiumへ複数スレッドから同時アクセスし得た。
- **設問領域をページ境界で分割する**: 設問本文が次の見出しの前にページをまたぐ
  場合、`_question_blocks`は以前ページをまたいでも同じblockに行を積んでいた。
  異なるページのジオメトリで座標をunion/正規化すると誤った領域になるため、
  ページ境界で必ずblockを打ち切るようにした（本文の後半はどのblockにも属さなく
  なる—§未決事項参照）。

## レビュー対応（PRラウンド4）

- **設問の各領域を同一ページに限定する**: `Question.page`は単一のページで、
  `answer_area`/`score_area`/`comment_area`は自身のページを持たず常に
  `question.page`に対して解釈される（`adapters.submission_intake`は
  `answer_area`を`question.page`の画像からcropする）。レビュアーが
  `ANSWER_AREA`/`SCORE`/`ANNOTATION_AREA`regionを対応する`QUESTION`と異なる
  ページに置くと、別ページ用の座標で誤ったページをcropしてしまっていた。
  `build_questions_and_rubrics`が`CrossPageRegionError`（422）で拒否するよう
  にした。ページをまたぐ設問そのものの表現は引き続き未設計（下記「未決事項」）。
- **依存関係edgeの`provides`をレビュアーが選択できるようにする**: 手動追加した
  edgeは常に`recognized_text`固定で、編集ダイアログも`provides`を表示・編集
  できなかった。`_EdgeEditDialog`に非空必須のprovisionチェックボックスを追加
  した。
- **中断されたPDF finalizationからtest登録を回復可能にする**: `Test`行のcommit
  後、両方のPDFがディスクに書き込まれる前にプロセスが終了すると、
  `FinalizationError`の補償（同一プロセス内のみ動作）が実行されず、PDFが
  欠けたdraftが永久に残り、どのendpointからも削除・再試行できなかった。
  `repair_incomplete_test_registrations`を起動時sweepに追加し、登録PDFが
  欠けている`draft`テストを削除する（`Submission`と異なり`Test`にリトライ用の
  `error`状態は無いため、再試行は新規idでの再登録になる）。
- **test永続化前にpage geometryを検証する**: ページ数の検証だけでは、CropBox/
  MediaBoxの交差が無効だったり`/Rotate`が90度単位でないPDFを検出できず、登録が
  それを受理・永続化してしまっていた（`/profile/analyze`が初めて
  `page_geometry`を呼んだ時に未捕捉の`ValueError`が500になり、使用不能なdraft
  が残っていた）。intake時に全ページの`page_geometry`を検証し、失敗を
  `PdfGeometryError`（400）に変換するようにした。

## レビュー対応（PRラウンド5）

- **クラッシュ復旧時に移行済みの既存testを保護する**: PRラウンド4の
  `repair_incomplete_test_registrations`は「登録PDFがディスクに無い」ことだけを
  中断registrationの判定基準にしていた。migration 0011は本Issue以前から存在する
  全`Test`行に`status='draft'`をバックフィルするが、それらは`register_test`を
  一度も通っていないためPDFを持ったことが無い。本番環境でmigration 0011を含む
  このリリースへアップグレードした初回起動で、この判定が既存testを全て
  「中断されたregistration」と誤分類し、連鎖してQuestionsとSubmissionsごと
  削除してしまうデータ消失バグだった。`register_test`がDB commit前に
  `.registration-marker`という永続マーカーファイルを書き込むようにし（一度
  書いたら削除しない）、sweepはこのマーカーを持つ`draft`testのみを中断
  registrationの候補にするよう変更した——マーカーの無い行は本Issue以前からの
  行として常に保護される。アップグレード経路（マーカーもPDFも無い既存行が
  再起動後も残ること）を回帰テストで検証した。
- **SQLiteに保存する前にscoreの範囲を制限する**: `QuestionRow.points`/
  `RubricCriterionRow.max_points`はSQLiteの符号付き64bit `INTEGER`列だが、
  `_extract_points`の`int()`にはそのような上限が無く、`uow.questions.add()`が
  未捕捉の`OverflowError`（500）を送出していた。`build_questions_and_rubrics`
  で`2**63 - 1`を超えるscoreを`InvalidScoreError`（422）として拒否するように
  した。
- **設定画面から戻った後にtest statusを更新する**: `TestListPage`はdraft test
  を開いて`TestSettingsPage`へpushした後、その結果を無視していたため、
  登録完了後に戻ってもタイルが手動refreshするまで「下書き」のままだった。
  pushをawaitし、戻った後に一覧を再取得するようにした（あわせて、
  `_reload`の`setState(() => _testsFuture = future)`が代入式の戻り値
  （`Future`自体）を返してしまいFlutterが例外を投げる既存の潜在バグも修正した）。
- **非有限の座標値を拒否する**: `_RegionEditDialog`で`double.tryParse('NaN')`は
  非nullの`double.nan`を返すため、範囲・順序比較が全てfalseになりバリデーション
  をすり抜けていた。パースした座標が全て有限であることを明示的に要求するように
  した。

## レビュー対応（PRラウンド6）

- **旧テストのアップグレード経路（grandfathering）**: PRラウンド5は
  `repair_incomplete_test_registrations`による誤削除は防いだが、migration
  0011がバックフィルする既存test自体は`draft`のまま、`ready`専用ゲート
  （`GET /tests`・`intake_submission`）から永久に締め出されていた——登録PDFも
  profileも持たない以上、本Issueが導入したconfirm/readyフローを通って`ready`
  になる手段が無い。本Issue以前は`draft`/`ready`の区別自体が存在せず、答案取込は
  どのtestも無条件に受理していたため、既存行は旧契約の下で既に「使用可能」
  だった。migration 0011のバックフィル値を`draft`から`ready`に変更し、既存行を
  旧来通り無条件に使用可能な状態へgrandfatherした（`server_default`は
  一時的なものなので、以後の新規登録の既定値には一切影響しない）。0007時点の
  スキーマへ直接test行を挿入してアップグレードし、`status='ready'`になることを
  検証する回帰テストを追加した。
- **候補生成でも不正なscore構文を拒否する**: `profile_candidate_generation`の
  `_SCORE_PATTERN`は`\d+`のみで`-5点`/`5.5点`から`5`だけを抜き出してしまい、
  確定時の厳格な`_SCORE_NUMBER_PATTERN`とは非対称だった。候補生成の時点で
  レビュアーに誤った値を提示しないよう、同じ符号/小数点境界を`_SCORE_PATTERN`
  にも適用した（該当行にマッチしなくなり、SCORE regionは生成されず人間が
  手動入力する）。
- **抽出したテキスト矩形を表示ページにクリップする**: PDFiumはCropBoxの外側に
  はみ出した/隠れたテキストの矩形をそのまま返すことがあり、正規化すると0未満・
  1超の座標になって`NormalizedBBox`が`ValueError`を送出していた
  （`analyze_profile`はこれを変換せず500になる）。`_rect_to_bbox`が座標を
  `0..1`にクリップし、クリップの結果面積がゼロに潰れた場合は極小サイズへ
  ずらして正の面積を保つようにした。
- **設問ラベルの長さを制限する**: `Question.id`（`f"{test_id}:{number}"`）は
  `LocalFileStore.submission_question_image_path`でhexエンコードされ
  （UTF-8バイト長が倍になる）、`write_atomic`が更にUUID付きの一時ファイル名で
  包む。Windowsのファイル名コンポーネント上限（255文字）に対し、32文字の
  test IDだけで大半を使ってしまうため、無制限のラベル（`Region.label`は
  profile APIで無制限）が約74 ASCII文字を超えると、profile確定後・答案の
  finalization時に初めて失敗する不変な状態になっていた。`number`のUTF-8
  バイト長を`_MAX_QUESTION_NUMBER_BYTES`（40バイト、安全マージンを取って
  上記上限より十分小さい値）で制限し、`QuestionNumberTooLongError`（422）で
  拒否するようにした。
- **巨大すぎるscore文字列を`int()`呼び出し前に拒否する**: 桁数無制限の
  `_SCORE_NUMBER_PATTERN`は、数千桁のSCORE region textに対し
  `int(match.group())`自体がPythonの整数文字列変換の桁数上限
  （既定4300桁）を超えて`ValueError`を送出し得た（`confirm_profile`は
  `DomainError`しか変換しないため500になる）。パターンをSQLite上限の桁数
  （19桁、`len(str(2**63 - 1))`）に制限し、それより長い数字列は
  マッチ自体しないようにした（`_extract_points`は「score無し」として扱い、
  通常通り`InvalidScoreError`になる）。

## レビュー対応（PRラウンド7）

- **analysisが使うパーサー（pdfium）でもintake時に検証する**: `_validate_one_pdf`
  はpypdf（`page_count`/`is_encrypted`/`page_geometry`）だけで検証しており、
  pypdfiumium2は一度も開かれていなかった。pypdfが読める（時に黙って修復して
  しまう）が構造が壊れているPDFを、後で`generate_profile_candidates`が
  `extract_text_lines`経由でpdfiumから開こうとして初めて拒否されると、
  `analyze_profile`はその例外を変換せず500になり、しかもTest行・PDFは既に
  永続化済みのため`PUT /profile`が要求するprofileが一切無いまま取り残されて
  いた。intake時にも各ページで`extract_text_lines`を実際に呼び出し、失敗を
  `PdfCorruptedError`（400）に変換することで、`generate_profile_candidates`が
  後で遭遇する不正PDFをtest登録の時点で確実に拒否するようにした。
- **page-geometry解析の全ての失敗経路を正規化する**: `page_geometry`
  （pypdf）はCropBox/MediaBox/rotationを継承チェーンから解決する際、
  `PageGeometry.__post_init__`自身が送出する`ValueError`以外にも
  `KeyError`/`TypeError`/pypdfの独自パースエラーを送出し得たが、
  `except ValueError`しか捕捉していなかった。`page_geometry`呼び出しに
  broadな`except Exception`を追加し、`ValueError`（ジオメトリ自体が不正）は
  引き続き`PdfGeometryError`に、それ以外（ページ自体が読めない）は
  `PdfCorruptedError`に変換するようにした。

## レビュー対応（PRラウンド8）

- **profile確定をレビュー済みrevisionに固定する**: 上記「Profile確認は一方向・
  一度きり」参照。`Profile.revision`と`ConfirmProfileRequest.revision`による
  compare-and-setを追加し、2クライアントが同じtestをreviewしている場合に
  未レビューのregionが黙って確定されてしまうのを防いだ。
- **実際のscoreトークンをparseする**: `_extract_points`が「テキスト中の最初の
  独立した整数」を返していたため、「問1 配点5点」のような記述的な入力で
  設問番号の「1」を配点として誤って永続化し得た。「点」に直接紐づく数値を
  優先し、それが無い場合はテキスト全体が曖昧さ無く1つの整数であることを
  要求するようにした（`_SCORE_WITH_UNIT_PATTERN`追加）。
- **`PUT /profile`をbodyパース前にgateする**: `SubmissionUploadGateMiddleware`
  の`_GATED_ROUTES`に`PUT /tests/{id}/profile`を追加した。無制限のregion
  JSONは、multipart uploadに対してこのmiddlewareが防いでいるのと同じ
  認証前body解析メモリ枯渇を`request.json()`経由で再現し得た。
- **PDFiumのtext indexをUTF-16単位で数える**: `_lines_from_textpage`が
  Pythonの`len()`（コードポイント数）を`FPDFText_GetCharIndexFromTextIndex`
  の`text_index`にそのまま累積していたが、このAPIはUTF-16コード単位で数える。
  絵文字や🈁のような非BMP文字（サロゲートペア、UTF-16で2単位）を含む行の後、
  `text_index`がずれて以降の行のrectangleが誤った文字に割り当てられ得た。
  `_utf16_length`ヘルパーでUTF-16単位の長さを計算するようにした。
- **全ページ見出しplaceholderを非退化に保つ**: `_placeholder_bbox_below`が、
  見出しrectangleがページ全体の高さにclipされる場合（y0=0, y1=1）に
  `y0 == y1 == 0`を計算し、`NormalizedBBox`が未捕捉の`ValueError`を送出して
  いた（`/profile/analyze`中にのみ発生するため、登録自体は成功し、以後の
  analysisが常に500になる永続的なdraftが残っていた）。両方の配置（下・上）が
  収まらない退化ケースでは、ページ内に収まる極小の正の高さへずらすようにした。
- **永続化するtestメタデータに上限を設ける**: `name`/`subject`は認証済み
  呼び出し元がbody制限まで送信でき、全ての登録一覧responseでそのまま
  返却されていた。`MAX_TEST_NAME_LENGTH`/`MAX_TEST_SUBJECT_LENGTH`
  （各200文字）を`Test.__post_init__`に追加し、`POST /tests`ハンドラでも
  早期に同じ上限で拒否するようにした。
- **[app] リスト再読み込み失敗を処理する**: `TestListPage._reload`が
  `await future`で失敗をそのまま再送出しており、`FutureBuilder`がエラーを
  描画しているにもかかわらず、`RefreshIndicator.onRefresh`やタイルの
  `onTap`から未処理の非同期例外が発生していた。`_testsFuture`には失敗した
  Futureをそのまま渡しつつ、`_reload`自身の`await`は`try`/`catch`で
  捕捉するようにした。

## 未決事項

- PDFオーバーレイでのregion視覚編集（上記「UI設計」）。
- Rubricの複数criteriaへの分割編集UI。
- 候補生成の精度は実データ未検証（PoC 1/2同様、実際の塾PDFでの評価が必要）。設問番号
  パターン（`問\d+`/`大問\d+`）や配点パターン（`\d+点`）以外の表記（例:
  「(1)」「Q1」「配点：5」）は現状検出できない —— 検出できなかった場合は
  `PUT /profile` での手動追加にフォールバックする設計だが、フォールバック発生率は
  未計測。
- 設問本文がページをまたぐ場合、後半（次ページの行）は自動検出の対象にならない
  （上記「PDFiumの呼び出しを直列化する」の下、ページ境界分割を参照）。かつては
  人間が`PUT /profile`で次ページ側に回答欄領域を手動追加するfallbackを想定して
  いたが、`Question.page`が単一ページ・各areaがpageを持たない現行モデルでは
  それは誤ったページのcropを招くため、`build_questions_and_rubrics`が
  `CrossPageRegionError`で拒否するようにした（上記「レビュー対応（PRラウンド
  4）」参照）。ページをまたぐ領域そのものをどう表現するか（複数regionを1設問に
  束ねる、regionに複数ページのbboxを持たせ、`Question`/`NormalizedRect`側も
  ページ単位に拡張する等）は未設計のまま——今のところ、ページをまたぐ設問は
  QUESTION regionと同じページ内に収まるよう手動で調整してもらう必要がある。
  **Issue #105 で、これが仮定ではなく実在することが確認された**: 計測した実資料
  11教科のうち1教科が、1設問の解答欄を「（その1）」「（その2）」として2ページに
  分けて印字している。回答欄の検出はその両方を返し、確定時に
  `CrossPageRegionError` がそう言う（黙って片方を捨てない）。表現方法そのものは
  引き続き未設計で、別Issueとして扱う。
