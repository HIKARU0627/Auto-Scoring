# 本番OCR文字認識パイプライン

GitHub Issue [#19](https://github.com/HIKARU0627/Auto-Scoring/issues/19)（親
[#3](https://github.com/HIKARU0627/Auto-Scoring/issues/3)）。設問画像から認識
文字・Bounding Box・Recognition Confidenceを取得し、低信頼または失敗を人間確認
へ送る本番パイプラインを実装する。

依存: [#13](https://github.com/HIKARU0627/Auto-Scoring/issues/13)（PoC 1。
`OCRProvider`契約・`domain/ocr.py`・`domain/ocr_metrics.py`を実装済み）、
[#17](https://github.com/HIKARU0627/Auto-Scoring/issues/17)（答案PDF取込・
`AnswerImage`）、[#18](https://github.com/HIKARU0627/Auto-Scoring/issues/18)
（`JobProcessor`境界・並列AI処理キュー）。

対象外: 採点判断（`AIProvider`）と最終Annotation生成は後続Issueで扱う。

> **⚠ OCRの位置づけはIssue #95 決定10で変わった。** 決定10で数式・英作文・図グラフが
> 採点対象になり、**OCRは採点の前提ではなくなった**（採点の入力は答案のページ画像）。
> OCRに残る役割は「AIが生徒の字をどう読んだかを人が検算する」ことと、
> **文字に紐づくAnnotationのBounding Boxを供給する**ことの2つである。
> 現在の仕様は [`simplified-design-specification.md`](./simplified-design-specification.md)
> §8.1 が正。**本書のうち「OCR失敗＝採点不可」を前提にした箇所は見直しが要る**
> （§24: OCRが失敗しても採点は止めない）。本書は実装当時の記録として残してある。

## 決定事項

### OCRサービス: Google Document AI（業務ルール §3 (A)、Issue #81 で確定）— 既定は依然 `NullOCRProvider`

PoC 1（`docs/poc-1-japanese-handwriting-ocr.md`）は`OCRProvider`契約と
メトリクス集計基盤を実装したが、credentials・評価データセットが揃わず、実 OCR
アダプタの実測は行われなかった（同docs §0.1・§6・§9.3参照）。Issue #20 の実装時点で
§3 (A) は未確定であり、業務ルール決定書 §3.1 は実装を
「`OCRProvider`インターフェースとダミー実装まで」に限定していた。

その後、[Issue #81](https://github.com/HIKARU0627/Auto-Scoring/issues/81)で
オーナーが **Google Document AI** に確定した（PoC 1 の第一候補だった Cloud Vision
からの変更）。ただし実アダプタは未実装で、実 API キーも未提供のため、本パイプラインの
既定は下記のとおり`NullOCRProvider`のままである。

本Issueはこの制約の中で本番**パイプライン**（境界・正規化・永続化・分類・
Confidence運用）を実装する。`create_app()`の`job_processor`既定値を
`NullJobProcessor`（Issue #18のプレースホルダ）から
`RecognitionJobProcessor`（後述）へ置き換えるが、その`RecognitionJobProcessor`
自体が呼ぶ`OCRProvider`の既定実装は`auto_scoring.adapters.ocr.null_provider.
NullOCRProvider`とする。`NullJobProcessor`と同じ理由（正直に「未設定」を報告する）
で、`NullOCRProvider`は常にConfidence 0.0・空文字の1トークンを返し、ネットワークに
一切アクセスしない。結果として、実アダプタが`create_app(ocr_provider=...)`で
注入されるまで、すべての設問が自動的にneeds_review（`Job.usable=False`）に
倒れる — 「OCR精度を前提にした自動確定フローを組まない」（§3.1 A）を構造的に
満たす。

実OCRアダプタ（Google Document AI）の追加は別Issueで行う（実 API キーでの疎通検証は
#54）。Document AI のレスポンス形式・Bounding Box 座標系への依存は`OCRProvider`実装の
内側に閉じ、座標変換・後処理へ漏らさない（§3.1 A）。`OCRProvider`のcontract test
（`backend/tests/test_ocr_provider_contract.py`の`OCRProviderContract`）へ
新しいサブクラスを追加するだけで済むよう、`domain/ocr.py`のポート定義は変更
していない。

### `RecognitionJobProcessor`: `JobProcessor`のOCR半分だけを実装する

`docs/job-queue.md`が決定した「1 Question = 1 Job（`JobKind.GRADING`）、
Job内部でOCR→採点をどう分けるかはJobProcessor実装側の自由」という設計を受け、
`auto_scoring.jobs.recognition_processor.RecognitionJobProcessor`は
**OCR認識のみ**を行う`JobProcessor`実装として追加した。採点（`AIProvider`）は
別Issueの対象のため、このprocessorが完了させたJobの`ProcessingResult`は
認識結果だけから決まる:

1. `job.question_id`が無ければ即座に`FAILED`(`PERMANENT`)。
2. `AnswerImageRepository`から該当`(submission_id, question_id)`の画像を取得
   （`domain.models.find_answer_image`、複数該当時は最新の`created_at`を採用）。
   無ければ`FAILED`(`PERMANENT`)。
3. 画像が`AnswerImageStatus.NEEDS_REVIEW`（Issue #17 §7.1: 回答欄検出失敗で
   信頼できない切り出し）なら、**providerを一切呼ばず**
   `SUCCEEDED`(`usable=False`)を返す。誤った領域画像を外部へ送信しない
   （業務ルール §2 (2)）ためであり、この場合`RecognitionResult`も作らない —
   人間が元ページ画像を見て手動入力する（後述の手動入力API）。
4. それ以外は`OCRProvider.recognize()`を呼ぶ（`asyncio.to_thread`でイベント
   ループをブロックしない。ネットワーク呼び出し中はDBトランザクションを保持
   しない — `jobs/queue.py`と同じ規約）。
5. 結果は`domain.ocr.overall_confidence()`（全トークンの**最小**Confidence。
   平均ではない — 1箇所でも読み取れない語があれば設問全体をneeds_reviewに
   倒す、という受入条件を平均は握りつぶし得るため）で1つのConfidenceへ集約し、
   `RecognitionResult`（`source=ai`、常に）として永続化する。
6. `Job.usable`は`overall_confidence(...) >= 設定された閾値`。**閾値未満でも
   `RecognitionResult`は必ず保存され、`FAILED`にはしない** — 「認識不能を
   推測で埋めない」「決定済みConfidence閾値未満はneeds_reviewとし自動確定
   しない」という受入条件どおり、低Confidenceの読み取りは失敗ではなく
   「完了したが要確認」の結果として扱う。

### エラー分類: timeout / rate limit / スキーマ不正 / 部分成功・認識不能

`domain/ocr.py`に`OCRProviderError`とそのサブクラス
（`OCRTimeoutError`・`OCRRateLimitedError`・`OCRServerError`・
`OCRResponseSchemaError`）を追加した。これらは「providerが結果を一切返せな
かった」ことを表し、`RecognitionJobProcessor`が以下へ分類する
（`auto_scoring.domain.models.ErrorCategory`、Issue #18で確定済みの4値を
再利用 — 新しい値は追加しない）:

| 例外                       | `ErrorCategory` | retry対象 |
| -------------------------- | --------------- | --------- |
| `OCRTimeoutError`          | `TIMEOUT`       | される    |
| `OCRRateLimitedError`      | `RATE_LIMITED`  | される    |
| `OCRServerError`           | `SERVER_ERROR`  | される    |
| `OCRResponseSchemaError`   | `PERMANENT`     | されない  |
| その他の`OCRProviderError` | `PERMANENT`     | されない  |

「部分成功」「認識不能」はこの表に**含まれない** — これらはprovider呼び出し
自体は成功しており（`OcrResult`が返る）、上記手順5〜6の低Confidence経路で
`needs_review`として扱う。`error_message`にはprovider例外の生メッセージを
含めない（request/response本文を含み得るため、AGENTS.md「Security」）。

未知の例外（上記のいずれでもない）は意図的に捕捉せず、`jobs/queue.py`の
既存の catch-all（`_run_claimed`が`ErrorCategory.PERMANENT`として処理する）
に委ねる。二重に同じフォールバックを実装しない。

### Confidence閾値: 設定値のまま、既定 0.80 を運用しながら調整する

業務ルール決定書 §3 (C)は Issue #81 で「**固定値を決めず、設定値のまま運用しながら
都度調整する**」ことに確定し、既定 0.80 は据え置かれた。§3.1 C の
「閾値ハードコードで判定を分岐させない、閾値は設定の単一箇所から読む」と
「閾値に基づく自動確定（人間レビューのスキップ）は実装しない」は確定後も残る制約である。
`auto_scoring.jobs.recognition_settings.RecognitionSettings`（`QueueSettings`と同じ素の
`dataclass`、新しい設定フレームワークは追加しない）が`confidence_threshold: float = 0.80`
を持ち、`create_app(recognition_settings=...)`で差し替えられる。

### Bounding Box: providerの正規化座標をdomainの`NormalizedRect`へ変換する

`domain.ocr.BoundingBox`（provider契約側、微小なepsilon許容）と
`domain.models.BoundingBox`/`NormalizedRect`（永続化側、epsilon無し）は別の
値オブジェクト。`RecognitionJobProcessor`内の変換でクランプする
（`x + width`が浮動小数の丸めで1.0をわずかに超える場合に備える）— 実際の
providerがこの誤差を出すことは稀だが、ページ端の1トークンのせいでJob全体が
例外で落ちるのは避ける。

### 手動文字入力API（Issue #19受入条件「OCR失敗時も…手動文字入力へ進める」）

Issue #18が`POST /submissions/{submission_id}/questions/{question_id}/resume`
を「将来のレビューAPIが最終的に呼ぶだけでよい」暫定エンドポイントとして追加した
のと同じ考え方で、`auto_scoring.api.recognitions_router`に最小限のエンドポイント
を追加した。完全なレビューUI・レビューAPIは引き続き後続Issueの対象。

- `GET /submissions/{submission_id}/questions/{question_id}/answer-image` --
  人間が確認する切り出し画像（PNGバイト列）。
- `GET /submissions/{submission_id}/questions/{question_id}/recognitions` --
  これまでの`RecognitionResult`履歴（AI提案・人間修正を含む、`created_at`昇順）。
- `POST /submissions/{submission_id}/questions/{question_id}/recognitions` --
  人間が手入力したテキストを`source=human`・`confidence=1.0`の
  `RecognitionResult`として保存する。

  **Issue #20以降、`JobQueueService.mark_question_usable`は呼ばない**
  （コードレビュー指摘）: Issue #20が`GradingJobProcessor`を導入し、1つの
  `Job`が文字認識とAI採点の両方を担うようになったため、この設問の`Job`は
  既に（訂正前のテキストに対する）`GradeResult`を持っている。ここで
  `mark_usable`を呼ぶと、その古い・未レビューのgradeを根拠に前提待ちの
  後続設問を解放してしまう -- Issue #19時点（`Job`がOCRのみを表していた頃）
  の設計を踏襲したままだと成立しなくなった。手入力したテキスト自体は追記型
  履歴として残るが、後続設問の解放には`POST .../resume`
  （`jobs_router`、人間が明示的にgradeを承認する経路）か、将来の再採点
  Issueが必要。

`recognition_results.text`にも`submissions.student_label`/
`original_filename`（Issue #17 review）と同じ理由で長さ上限
（`MAX_RECOGNIZED_TEXT_LENGTH = 10000`）を設けた
（`migrations/versions/0010_recognition_text_length.py`）。API直叩きで無制限の
文字列を送り込めないようにする境界入力検証（AGENTS.md「Security」）。

## API

`auto_scoring.api.recognitions_router`（上記3エンドポイント）。既存の
`jobs_router`と同じ`Authorization: Bearer <token>`保護下にマウントする
（`create_app`）。

## 検証

- `backend/tests/test_ocr.py` / `test_ocr_provider_contract.py`:
  `overall_confidence`・新しい例外階層・`NullOCRProvider`のcontract test
  （実providerと同じ契約を満たすことを確認）。
- `backend/tests/test_recognition_processor.py`: `RecognitionJobProcessor`を
  スクリプト可能なfake `OCRProvider`＋実SQLite＋実`LocalFileStore`で検証
  （高/低Confidence、`NEEDS_REVIEW`画像でproviderを呼ばないこと、
  timeout/rate limit/schema不正/その他例外の分類、境界値Bounding Boxの
  クランプ）。
- `backend/tests/test_recognitions_api.py`: 上記APIを`TestClient`経由で検証
  （実SQLite、`FakeJobProcessor`）。
- 実OCRサービスを使うテストはこのIssueには存在しない（`NullOCRProvider`が
  唯一の同梱アダプタで、ネットワークに一切アクセスしないため）。実アダプタを
  追加する後続Issueが、そのアダプタ専用のlive probe commandを
  `docs/poc-1-japanese-handwriting-ocr.md`の方針に従って追加する。
