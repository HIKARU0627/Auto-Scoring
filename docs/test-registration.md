# テスト登録とテストプロファイル確認・修正

GitHub Issue [#16](https://github.com/HIKARU0627/Auto-Scoring/issues/16)（親
[#3](https://github.com/HIKARU0627/Auto-Scoring/issues/3)）の実装記録。模範解答PDF・
採点マニュアルPDFを登録し、AIが生成した候補（設問・回答欄・添削記号領域・配点・採点基準・
模範解答）を人間が確認・修正し、設問依存関係グラフ（Issue #26）と合わせて確認済みにして
初めてテスト登録が完了する一連のフローを実装する。

依存: [#10](https://github.com/HIKARU0627/Auto-Scoring/issues/10)（認証付きサイドカー
API）、[#11](https://github.com/HIKARU0627/Auto-Scoring/issues/11)（MVPデータモデル）、
[#15 PoC 4](https://github.com/HIKARU0627/Auto-Scoring/issues/15)（`Profile` の
draft/confirmedパターン）、[#26](https://github.com/HIKARU0627/Auto-Scoring/issues/26)
（設問依存関係DAG、そのAPIをそのまま利用する）。

## 決定事項

### `Test` の登録ライフサイクル（`draft` → `ready`）

Issue #11時点の `Test` エンティティには状態が無かった。Issue #16で
`domain.models.TestStatus`（`DRAFT`/`READY`）と `Test.status`（既定
`DRAFT`）を追加し、`Test.mark_ready()` で一方向にのみ遷移させる（`READY` から
`DRAFT` へ戻す経路は無い。再度 `mark_ready()` を呼ぶと
`InvalidStateTransition`）。DBは `tests.status` 列（`CHECK (status IN ('draft',
'ready'))`、マイグレーション `0008_test_status`）で同じ制約をミラーする。

**`ready` になる条件**（`POST /tests/{test_id}/complete-registration`、Issue #16
受入条件「全必須項目確認後にだけ登録完了になる」）:

1. テストプロファイルが `confirmed`（後述）
2. 設問依存関係グラフ（Issue #26）が `confirmed`（`get_latest_confirmed` が存在）

どちらか一方でも欠けていれば `409` を返し、不足している項目を日本語で列挙する。両方揃って
初めて `Test.mark_ready()` を呼ぶ（compare-and-set: `TestRepository.mark_ready` は
`WHERE status = 'draft'` の条件付き `UPDATE` で、二重登録レースを避ける）。

### 候補生成: 実PDFテキストのヒューリスティック抽出（PoC 4のタグ付き注釈を置き換え）

PoC 4（Issue #15）の `adapters.pdf.annotation_markers` は、PDFのSquare注釈（開発者が
仕込んだタグ）からRegion候補を作る**検証用の代替実装**であり、実際の模範解答・
マニュアルPDFにはそのような注釈は存在しない（`docs/poc-4-multi-layout-profiles.md`
「PoC限定・要再確認」に明記済み）。Issue #16でこれを実運用の候補生成
（`adapters.pdf.profile_candidate_generation`）に置き換えた。`annotation_markers` は
PoC 4自身の回帰テスト用にそのまま残す。

`AIProvider`/`OCRProvider` の具体サービス選定はPoC後まで未確定
（`technology-stack.md` §3.5）のため、Issue #26のヒューリスティック依存関係analyzer
（`ReferenceHeuristicDependencyAnalyzer`）と同じ方針を取る: **外部AI呼び出しを行わない、
決定的なテキストパターンマッチング**。

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

### Profile確認は一方向・一度きり

`Profile.confirm()` はPoC 4から一方向（DRAFT→CONFIRMED）。Issue #16のAPI
（`POST /tests/{test_id}/profile/confirm`）は既にCONFIRMEDのprofileへの再confirmを
`409` で拒否する。個々のregionに対する「このregionだけ確認済み」という操作は無い ——
`Profile.__post_init__` がDRAFTのprofileに`confirmed=true`のregionが混じることを
そもそも禁止しているため、confirm操作自体が「今のDRAFT regionセット全体を一括承認する」
という単一の行為になる。人間はconfirmを押す前に `PUT /profile` で何度でも内容を
編集できる。

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

## 未決事項

- PDFオーバーレイでのregion視覚編集（上記「UI設計」）。
- Rubricの複数criteriaへの分割編集UI。
- 候補生成の精度は実データ未検証（PoC 1/2同様、実際の塾PDFでの評価が必要）。設問番号
  パターン（`問\d+`/`大問\d+`）や配点パターン（`\d+点`）以外の表記（例:
  「(1)」「Q1」「配点：5」）は現状検出できない —— 検出できなかった場合は
  `PUT /profile` での手動追加にフォールバックする設計だが、フォールバック発生率は
  未計測。
