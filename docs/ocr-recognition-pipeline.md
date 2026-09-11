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
> 採点対象になり、**OCRは採点の前提ではなくなった**
> （採点の入力は**回答欄を切り出した画像**。**ページ全体ではない** — 簡易設計書 §26.1.1）。
> OCRに残る役割は、**採点AIとは独立した比較材料**を与えること（**OCR結果は「採点AIが
> 何を読んだか」ではない**。別々のモデルが別々に読むため、OCR結果を確認しても採点AIの
> 読み違いは検出できない）と、**文字に紐づくAnnotationのBounding Boxを供給する**ことの2つである。
> 現在の仕様は [`simplified-design-specification.md`](./simplified-design-specification.md)
> §8.1 が正。本書は実装当時の記録として残してある。
>
> **見直しは Issue #114 で実施した（2026-09-09）。** 旧版はここに
> 「本書のうち『OCR失敗＝採点不可』を前提にした箇所は見直しが要る」とだけ書いて
> 放置しており、**コードもその前提のままだった**。決着は下記
> 「§8 実OCRアダプタと、OCRが無い端末（Issue #114）」にある。

## 決定事項

### OCRサービス: Google Document AI（業務ルール §3 (A)、Issue #81 で確定）

> **本節は Issue #19 実装当時（アダプタ未実装）の記録である。**
> 実アダプタは Issue #114 で追加し、`NullOCRProvider` は削除した。§8 を参照。

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

実OCRアダプタ（Google Document AI）の追加は別Issueで行う（**Issue #114 で実施済み**。
実 API キーでの疎通検証は #54）。Document AI のレスポンス形式・Bounding Box 座標系への
依存は`OCRProvider`実装の内側に閉じ、座標変換・後処理へ漏らさない（§3.1 A）。
`OCRProvider`のcontract test（`backend/tests/test_ocr_provider_contract.py`の
`OCRProviderContract`）へ新しいサブクラスを追加するだけで済むよう、`domain/ocr.py`の
ポート定義は変更していない — **この見込みは当たった**。Issue #114 が足したのは
`OCRUnavailable` 1つだけで、`recognize()` の形は変わっていない。

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

> **手順5〜6の Confidence の扱いは Issue #158 で変わった（§9）。** 最小値は
> 「読めたか」ではなく「答案がどれくらい長いか」を測っていた。以下は Issue #19
> 実装当時の記録である。関数名も `overall_confidence` →
> `lowest_token_confidence`（表示専用）へ変わっている。

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
  `overall_confidence`（**Issue #158 で `lowest_token_confidence` へ改名**。
  §9.5）・新しい例外階層・`NullOCRProvider`のcontract test
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

---

## 8. 実OCRアダプタと、OCRが無い端末（Issue #114）

GitHub Issue [#114](https://github.com/HIKARU0627/Auto-Scoring/issues/114)。
本書冒頭が「見直しが要る」と書いたまま放置していた箇所の決着でもある。

### 8.1 何が起きていたか（実測）

`api/sidecar.py` は `create_app()` に `ocr_provider` を**一度も渡していなかった**。
したがって出荷されるすべての install が `NullOCRProvider` で動いていた。

| OCR                        | grading job | `usable`  | 点数 |
| -------------------------- | ----------- | --------- | ---- |
| scripted（テストの世界）   | succeeded   | **True**  | 出る |
| **注入なし＝出荷される姿** | succeeded   | **False** | 出る |

**点数と講評は出ていた** — 採点providerは多モーダルで、回答欄の切り出し画像を
直接読むため（簡易設計書 §8.1.1）。**だから長く気づかれなかった。**
出ていなかったのは認識テキストで、`confidence=0.0` が
`GradingJobProcessor` の3項ANDの第1項を常に落とし、結果として
**依存エッジのある設問は、人が `/resume` を1つずつ押すまで `BLOCKED` のまま**
だった。採点の自動化を掲げるアプリとして、これは機能していない状態である。

**テストがこれを見つけられなかった理由**: 既存テストはすべて `OCRProvider` を
注入する。「注入しない姿」を走らせるテストが1つも無かった。
`backend/tests/test_e2e_ocr_unavailable_chain.py` がその穴を塞ぐ。

> **「OCRが直れば全部流れる」という意味ではない。** 本Issueが言えるのは
> **OCRが無いことでは連鎖が止まらなくなった**ことだけである。実データでの試走では
> 別の理由で止まる設問が観測されている（採点providerの恒久失敗 —
> [#117](https://github.com/HIKARU0627/Auto-Scoring/issues/117) /
> [#121](https://github.com/HIKARU0627/Auto-Scoring/issues/121)、
> 回答欄の検出ずれで余白がAIへ渡る —
> [#122](https://github.com/HIKARU0627/Auto-Scoring/issues/122)）。
> それらは本Issueの範囲外である。

### 8.2 `usable` の意味を3状態にした

**これは新しい判断ではなく、Issue #95 決定10 の反映漏れの回収である。**
決定10 は簡易設計書 §24（「OCR失敗: **採点は止めない。**」）・§8.1.4
（「**読めていないものに数値を与えない**」）・§8.1.5（OCRは critical path から外れる）と
業務ルール §4.3 には反映されていたが、**業務ルール §4.4 と本書とコードには反映されていなかった。**

| OCRの状態            | `RecognitionResult`                | `usable` への寄与                   | 依存先                            |
| -------------------- | ---------------------------------- | ----------------------------------- | --------------------------------- |
| 読めた・閾値以上     | 保存する                           | 第1項 True                          | 流れる                            |
| **読めた・閾値未満** | 保存する（低Confidenceも必ず残す） | 第1項 **False**                     | **止まる（→ #158 で変更、§9.3）** |
| **OCRが使えない**    | **保存しない**                     | **第1項が消える**（2項のANDになる） | **流れる（新）**                  |

- 「読めた・閾値未満」は**据え置いた**。業務ルール §4.4 が想定していたのはこの場合で、
  実際に読んだ結果が信用できないなら人が見るべきである。**ここは緩めていない**
  — **この判断は Issue #158 で覆した（§9）。** 据え置いた「閾値未満」の中身が、
  読み取りの信用度ではなく**答案の長さ**だったため。
- 「OCRが使えない」は比較対象が存在しないので、比較して落とすことができない。
  `confidence=0.0` という**存在しない読み取りの数値を作らない**（§8.1.4）。
  残る2項 — **採点AI自身の読み取りConfidence**と**Grading Confidence** — が引き続き
  ゲートする。これは業務ルール §4.3 の「**OCR テキストとは限らない。**…
  採点 AI 自身の読み取りが引き継ぐ対象になる場合がある」そのものである

**「読めなかった」と「読む道具が無い」は `RecognitionResult` 行の有無で区別できる**
（Issue #114 受入条件 8）。行があって Confidence が低ければ前者、行が無ければ後者。

**検討して採らなかった案:**

- **`usable` に触らず `NullOCRProvider` の 0.0 を usable 扱いにする** — 0.0 を
  「問題なし」と読み替えることになり、受入条件 8 の区別ができず、§8.1.4 に反する
- **第1項を常に落とす（OCRは `usable` に一切関与しない）** — 業務ルール §4.4 の
  「依存元の OCR Confidence が閾値未満なら止める」を決定なしに捨てることになる。
  この案を実装すると既存テスト4件が落ちる（実際に変異させて確認した）

### 8.3 未設定端末の扱い — #97 と同じ規律

`NullOCRProvider` は**削除**した。#97 が `NullAIProvider`（0点・confidence 0.0 を
返すプレースホルダ）を `UnconfiguredAIProvider` に置き換えたのと同じ理由である:
**答えられないなら答えず、「答えられない」と言う。**

- `adapters/ocr/unconfigured_provider.py` の `UnconfiguredOCRProvider` は
  `domain.ocr.OCRUnavailable` を投げる。ネットワークに触らない
- `RecognitionJobProcessor` はこれだけを他の `OCRProviderError` より**先に**捕まえ、
  `SUCCEEDED` かつ `RecognitionResult` 無しで返す（＝ OCR項なし）
- `GET /ocr/availability` が `{available, reason}` を返す
  （`GET /grading/availability` と同型）。`reason` は**変数名だけを言い、値は言わない**
- サイドカー起動時に WARNING を1行出す。**起動失敗にはしない** — §24 が
  「採点は止めない」と言っている以上、OCRが無いことは起動を拒む理由にならない

`OCRUnavailable` は `OCRProviderError` の subclass だが、**この階層で唯一
「呼び出しが失敗した」を意味しない**メンバーである。ADCの期限切れも同じ扱いにする
（retry しても資格情報は入らない）。

### 8.4 Document AI アダプタ

`adapters/ocr/document_ai_provider.py`。

- **SDK を足さない。** 認証は既存の `adapters/ai_grading/_google_adc.AdcTokenSource`
  （ADC。**オーナーの組織ポリシーが API キーを禁じている**）で解決済みで、
  `:process` は JSON body 1つの POST である。`vertex_gemini_provider.py` が
  Vertex AI に対してすでに採った判断と同じ（AGENTS.md「Architecture」）
- サイドカーは `shared_adc_token_source` を**4つ目の利用者として再利用**する。
  Document AI は Vertex AI とは別サービスだが同じ `cloud-platform` スコープの
  ADC トークンで通るため、起動時の ~300ms を4回払わない
- **送るのは回答欄の切り出しのみ**（簡易設計書 §26.1.1「答案の内容を採点する」行）。
  このアダプタはページ画像に触れる経路を持たず、
  `test_document_ai_provider.py` が「渡されたバイト列をそのまま送る」ことを固定する
- `skipHumanReview: true` — Document AI 側のレビューキューに切り出しの複製を
  残さない（§26.2）
- 正規化座標（`normalizedVertices`）はすでに 0..1 で、送ったのは切り出し画像なので
  ページ寸法によるスケーリングは不要。回転トークンは外接矩形にする
- **ログ・例外に、画像・認識テキスト・processor リソース名・アクセストークンを
  一切出さない。** 例外に載るのは HTTP ステータス番号と例外クラス名だけ（PR #100 の規律）

#### 設定

**変数は1つ。** `AUTO_SCORING_DOCUMENT_AI_PROCESSOR` に Cloud Console が表示する
完全リソース名 `projects/<p>/locations/<l>/processors/<id>` をそのまま入れる。
project / location / processor id は互いに整合していなければならない（processor は
作成したlocationにしか存在しない）ので、3変数に分けると**食い違わせる方法を作るだけ**である。
`AUTO_SCORING_` 接頭辞であることには意味がある — `api.secret_redaction` が
この名前空間の値を自動で伏せる。

未設定は**壊れた設定ではなく、サポートされた設定**である。

### 8.5 まだ決めていないこと

- **`RecognitionResult.boxes` の座標系。** `domain.models.NormalizedRect` の
  docstring は「page-normalized」と書いているが、`OCRProvider` に渡すのは
  **回答欄の切り出し画像**なので、実際に入るのは**切り出し正規化**である。
  実アダプタが無く box が常に空だったため、これまで露見していなかった。
  §12.3 の文字紐づけAnnotationの配置に効くので、**本Issueでは値をそのまま保存し、
  食い違いは別Issueとして記録する**
- **`processOptions.ocrConfig.hints.languageHints` が実際に効くか。**
  ポートの `language` 引数を素直に渡しているだけで、**日本語手書きの精度が上がるという
  実測は無い**。processor の種類によっては `processOptions` 自体を受け付けない可能性も
  あり、どちらも live 疎通（Issue #54）でしか確かめられない
- **非テキスト領域（数式・図）を判定して OCR 呼び出しを省く**かどうか。
  簡易設計書 §8.1.5 が「その判定を確実に行えるかは検証していない」と書いており、
  §33.2 の未決事項のまま。Document AI が読めずに 0 トークンを返した設問は、
  本Issueでは「読めた・text 空・低Confidence」＝**止まる**に据え置いた
  （「本当に読めなかった」であって「読む道具が無い」ではないため）。
  **0トークンは Issue #158 のあとも止まる**（読めた語が1つも無いため。§9.3）

### 8.6 検証

- `test_document_ai_provider.py`: 送信ペイロード（切り出しのみ・`skipHumanReview`・
  language hint・regional host）、失敗分類（429/5xx/4xx/timeout/transport/非JSON）、
  応答パース（複数トークンのテキスト切り出し・回転矩形・欠損polygon・範囲外座標の
  クランプ）、**例外にレスポンス本文もリソース名も出ないこと**
- `test_ocr_provider_contract.py`: `DocumentAiOCRProvider` を `OCRProviderContract`
  のサブクラスとして追加（`httpx.MockTransport`。ネットワークにも資格情報にも触らない）
- `test_ocr_availability.py`: factory・`build_ocr_provider`・`GET /ocr/availability`、
  および**leak matrix**（各設定変数に番兵値を入れ、`reason` にもHTTP応答にも出ないこと）
- `test_e2e_ocr_unavailable_chain.py`: **出荷される合成**（OCR未注入＋scripted AI）で
  依存エッジのあるDAGを流し、**`/resume` を一度も呼ばずに**全設問が succeeded / usable に
  なること、OCR側の `RecognitionResult` が1行も書かれないこと
- `test_e2e_intake_to_export.py`（Issue #116 が書いたもの）の該当2本を新しい現実へ
  書き換え、**失われる被覆を3本目として足した**。#116 は「いまこうなる」を正しく
  写しており、変えたのは本Issueのほうである:
  - `..._every_question_still_reaches_export_by_hand`: `usable` の期待を False → **True**
  - `..._stays_blocked_until_a_human_resumes_it` →
    `..._a_dependent_question_still_runs_without_a_human`（**名前が事実と逆になるため改名**）
  - **新規** `test_an_ocr_reading_it_could_not_trust_still_blocks_until_a_human_resumes_it`
    （**Issue #158 で `test_an_ocr_that_read_nothing_still_blocks_until_a_human_resumes_it`
    へ改名**。止まる条件が「低Confidence」から「読めた語が1つも無い」に変わり、
    名前が事実と合わなくなったため。§9.4）:
    OCRが読んだうえで低Confidenceだった場合は**従来どおり止まり、`resume` で初めて動く**。
    「この端末にOCRが無い」を緩めたことで「OCRが読めなかった」まで緩んでいないことを、
    2本を並べて走らせて示す
- **変異させて確認した**（値ではなく直した性質を固定できているかの検査）:
  `usable=True` を `False` に戻すと5件、`confidence=0.0` の行を書き戻すと2件、
  OCR項を常に外すと4件が落ちる
- **実 Document AI への疎通は未実施。** ADC と processor のある端末が要るため
  Issue #54 に残す。本Issueが足したのは録画形状での疎通までである

---

## 9. `usable` 判定から「答案の長さ」を外す（Issue #158）

GitHub Issue [#158](https://github.com/HIKARU0627/Auto-Scoring/issues/158)。
§8.2 の表で「読めた・閾値未満 → 止まる（変更なし）」と据え置いた第1項が、
**読めたかどうかではなく答案の長さを測っていた**ことの決着である。

### 9.1 何が起きていたか（実測と、その分母）

`domain.ocr.overall_confidence` は**全トークンの最小値**だった。
`RecognitionJobProcessor` はこれを閾値と比べて `usable` を決めていたので、
**トークンが1つ増えるたびに「最も自信のないトークン」を引く機会が増える**。
同じ手書き・同じ読み取り品質でも、**長い解答ほど確実に閾値を割る**。

記録済みの実測（実機再検証 #4、2026-09-09、8教科・実データ・実 AI。
[ai-grading-pipeline.md](./ai-grading-pipeline.md)「Confidence閾値」の
Issue #156 追記が出どころ）:

| 実測（OCR読み取り15件） |                             |
| ----------------------- | --------------------------- |
| 5トークン以下           | **4件すべてが閾値超え**     |
| 9トークン以上           | **9件すべてが閾値未満**     |
| 6〜8トークン            | 記録に無い（15 − 13 = 2件） |

| 例               | overall_confidence |
| ---------------- | -----------------: |
| **正しい** 6/6点 |          **0.422** |
| **誤った** 0点   |          **0.726** |

**長さできれいに分かれ、正誤では分かれていない。** 同じ実行で `usable == false` は
AI採点12件中11件に立っており、その11件を作っていたのはほぼこの第1項だった。

#### 分母（自分で確かめた範囲と、確かめられなかった範囲）

- Issue #158 本文は「#4 の15件は**7教科ぶん**」と書いている。**この数字は
  リポジトリの記録では裏が取れない。** docs が実機再検証 #4 について記録している
  教科数は **8教科**である（[dependency-dag-progress-view.md](./dependency-dag-progress-view.md)
  §1.3 の実測表「実機再検証 #4、8教科」、[ai-grading-pipeline.md](./ai-grading-pipeline.md)
  「解答でない画像から作った点数を…」の「2026-09-09 の実機再検証（8教科・実データ・実 AI）」）。
- 同じ実行の件数も docs 内で3通りある: **AI採点12件**（#156 追記）、
  **採点結果14件・切り出し14件**（#136 節）、**OCR読み取り15件**（#158 の出どころ）。
  設問数・切り出し数・採点数・読み取り数のどれを数えたものかが節ごとに違う。
- **15件の教科別内訳はリポジトリのどこにも記録が無く、当該実行の app-data も
  この端末に残っていない**（`~/.local/share/auto-scoring/app-data` にあるのは
  `scripts/seed-demo-app-data.py` の合成データ10行で、`demo-sub-*` の id を持つ）。
  実データはリポジトリ外にしか無く、公開物には出せない。
- したがって**「7教科ぶん」は確かめられなかった**。確かめられたのは
  **「実行そのものは8教科であり、1教科ぶんではない」**ところまでである。
  以下の判断は教科別の傾向に依存させていない。

### 9.2 決めたこと: 単一の閾値を持たず、「読めなかった語の数と位置」を持つ

**長さに単調な統計を、ゲートの入力に使わない。** 最小値はその典型だが、
**「読めなかったトークンの数」も同じ欠陥を持つ** — 長く書けば個数も増える。
どちらも「閾値を1つ足す」形では直らない。

採った形:

- `domain.ocr.unreadable_spans(result, minimum_confidence=...)` が
  **閾値未満だったトークンの位置**（`UnreadableSpans.indices`）を返す。
  閾値は `RecognitionSettings.confidence_threshold` を渡す —
  業務ルール §3.1 (C)「閾値は設定の単一箇所から読む」は保つ。**変えたのは
  「何と比べるか」で、比べる値の出どころではない**（読み取り全体の集約値ではなく、
  トークン1つずつと比べる）。
- 数と位置は **`RecognitionResult.boxes` の各 box に `unreadable` として永続化する**。
  位置は box そのものなので、行に個数を1つ足すのではなく box に印を付ける。
- **ゲートに使うのは `nothing_readable`（＝読めた語が1つも無い）だけ。**
  これは長さに対して単調ではない: 同じ品質の語をいくら足しても、読めた語が
  1つある読み取りは読めたままだし、1つも無い読み取りは長くなっても増えない。

**新しい閾値は作らなかった。** 理由は3つで、いずれも実測に基づく:

1. **記録済みの15件からは、どんな閾値も較正できない。** 残っているのは
   バケット集計（4件/9件）と最小値2つだけで、**トークンごとの生値が無い**。
   §9.1 のとおり app-data も残っていない。数字の無い閾値を置けば、
   Issue 本文が言う「**全件が片側に寄る閾値**」を別の場所に作り直すだけである。
2. **率（読めなかった語 ÷ 全語）は長さに不変で有力だが、15件では旧判定と区別が
   付かない。** 下の «割合で15件を見るとどう分かれるか» が実測。
3. 個数の閾値は 9.2 冒頭のとおり、直そうとしている欠陥そのものである。

#### 割合で15件を見るとどう分かれるか（＝分かれない）

「読めなかった語の割合」は長さに不変なので、最小値の代わりに置く候補としては
正しい形である。**そこで記録済みの15件に当ててみた。記録から確定するのは
次の2つだけだった:**

| 記録された群     | 割合について記録から確定すること                                                        |
| ---------------- | --------------------------------------------------------------------------------------- |
| 5語以下の**4件** | 全語が閾値以上 → **割合はちょうど 0.0**                                                 |
| 9語以上の**9件** | 最小値が閾値未満 → **割合は 1/n 以上**（n≥9 なので下限は 0.111 以下）。**真の値は不明** |

したがって切り位置 `c` を動かすと:

- **`c` が十分小さいとき**（各件の 1/n より下）— 4件通過・9件不通過。
  **旧判定とまったく同じ分かれ方**になる。つまり長さで分かれたときの分かれ方を
  そのまま再現する。
- **`c` がそれより上のとき** — **9件がどちらへ行くかが記録から決まらない**。

**どの `c` を選んでも、記録済みの15件から「旧判定と違う分かれ方」を観測できない。**
割合が分けたのではなく、**分けられるだけの情報が残っていない**（トークンごとの
生値が無い以上、割合は最小値から復元できない）。

**採ったのはこの族の端である。** `nothing_readable` は「割合 = 1.0」、すなわち
**較正できない切り位置を発明せず、記録が支持する唯一の点に置いた**という意味である
（割合を使わないことにしたのではない）。トークンごとの生値が取れたら —
実データを流し、`RecognitionResult.boxes` の `unreadable` を数えれば取れる —
`c` を 1.0 より下に動かすことはこの形のまま可能である。**その材料を作るのが
`unreadable` の永続化でもある。**

#### 新しい判定を、記録済みの15件に当てるとどうなるか

**15件すべてが `usable` 側に寄る可能性が高く、少なくとも「長さで分かれる」形には
ならない。** 内訳:

- 旧判定が落とした9件について記録に残っているのは「**最小値が閾値未満**」まで。
  「全トークンが閾値未満だったか」は**記録からは判定できない**。
- 新判定は旧判定より**厳しくなることが構造的に無い**
  （`nothing_readable` ⇒ 最小値 < 閾値）。よって新判定で止まる件数は
  **旧判定の9件以下**であり、旧判定で通った4件は必ず通る。
- トークンごとに閾値を割る確率を `p`（長さと独立）と置くと、
  旧判定が止める確率は `1 − (1 − p)^n` で **n について単調増加**、
  新判定が止める確率は `p^n` で **単調減少**する。**向きが逆になる**というのが
  この変更の全部である。記録された分かれ方（n≤5 で4件通過 / n≥9 で9件不通過）に
  最尤で当てはめると `p ≈ 0.16` で、そのとき `n = 9` の `p^9 ≈ 9 × 10⁻⁸`。
  ただし**この当てはめ自体、短い4件が全部通ったこと（同じ `p` の下で確率 0.028）を
  うまく説明できていない** — トークン数と1語あたりの品質は独立ではないらしい。
  **だから根拠に使っているのは当てはめた数値ではなく、単調性の向きのほうである。**

**「新しい判定でも全件が片側に寄るなら、それも閾値として働いていないのでは」**
—— そのとおりで、**`nothing_readable` は閾値ではない**。「下流へ渡せる文字が
1つも無い」という構造的な事実であり、§8.5 が「読めずに0トークンを返した設問は
止める」と決めた場合を保つためだけにある。**分けるための数値ではなく、
分けないことを選んだ結果**である。人へ渡す粒度は数値ではなく
「どこが読めなかったか」が受け持つ（§9.5）。

#### 何を保証し、何を保証しないか

- **保証する**: 下流へ渡せる読み取りが1語も無い前提設問は、依存先を解放しない。
  そして**答案が長いというだけでは止まらない**（§9.7 の性質テスト）。
- **保証しない**: 「読めた語が1つある」読み取りの**質**は、この項は保証しない。
  ほとんど読めなかった答案でも、1語読めていれば第1項は通る。
- **それでよい理由**: OCRの項が守る下限は、#114 の時点ですでに
  **「読み取りが1つも無くても依存先は流す」**（OCR未設定端末）になっている。
  1語読めた読み取りが、読み取りゼロより下流に危険ということはない。残る2項
  （**採点AI自身の読み取り確信度**と**Grading Confidence**）は変えておらず、
  引き続き止める。そして `usable` が制御するのは
  「人が見なくてよいか」ではなく「後続へ進んでよいか」である
  （[ai-grading-pipeline.md](./ai-grading-pipeline.md)「Confidence閾値」）。
  **確定は最後まで人の仕事**（簡易設計書 §25.2）。
- **代わりに人へ渡すもの**: どこが読めなかったか。**永続化しただけで誰も見ないなら
  捨てたのと同じ**なので、画面へ届ける follow-up を
  [#185](https://github.com/HIKARU0627/Auto-Scoring/issues/185) として起票した（§9.6）。

### 9.3 `usable` の意味（§8.2 の表の更新）

| OCRの状態                         | `RecognitionResult` | `usable` への寄与      | 依存先             |
| --------------------------------- | ------------------- | ---------------------- | ------------------ |
| 読めた                            | 保存する            | 第1項 True             | 流れる             |
| **読めた・一部の語が閾値未満**    | 保存する（印付き）  | 第1項 **True**（変更） | **流れる（変更）** |
| **1語も読めなかった / 0トークン** | 保存する            | 第1項 False            | 止まる（変更なし） |
| OCRが使えない（#114）             | 保存しない          | 第1項が消える          | 流れる（変更なし） |

2行目が今回変わったところで、それ以外は変えていない。**§8.2 が
「ここは緩めていない」と書いた行を、実測に基づいて緩めた**ことになる。
緩めた根拠は「低Confidenceでも人は見なくてよい」ではなく、
**あの数値が低いことは読み取りの質ではなく答案の長さを表していた**である。

`RecognitionResult` は従来どおり必ず保存される。「読めなかった」と
「読む道具が無い」を行の有無で見分ける #114 受入条件 8 も変わらない。

### 9.4 依存を持つ設問（`BLOCKED`）の挙動

この第1項が実際に人を止めるのは**依存エッジがあるときだけ**である
（#156 が「誰も待っていない設問に要確認を立てる」のをやめた。実機再検証 #3・#4 とも
エッジは0本で、確定済みグラフ21件・設問92件に1本も無かった）。したがって
**この変更が現に効くのは、依存エッジが引かれた教材が出てきたとき**である。
そこを実際に流して固定してある:

- 前提設問の読み取りに**読めない語が混じっている**（他は読めている）→
  **後続は `/resume` 無しで走る**（`test_a_partly_unreadable_prerequisite_no_longer_blocks_its_dependent`）。
  **これが変わったところ。** 従来はここで `blocked` になり、人が1件ずつ
  `/resume` を押すまで動かなかった。
- 前提設問の読み取りに**読める語が1つも無い** → **従来どおり `blocked`**、
  `blocked_on_question_id` は前提設問、採点もされず、`/resume` で初めて動く
  （`test_an_ocr_that_read_nothing_still_blocks_until_a_human_resumes_it`。
  #114 が書いた同じテストの改名で、**名前が事実と合わなくなったため**改名した）。

2本を並べて走らせているのは #114 と同じ理由である。**「長い解答で止まらない」ように
したことで「読めなかったときも止まらない」まで緩んでいない**ことは、
片方だけでは言えない。

### 9.5 `RecognitionResult.confidence` は残した（表示専用）

残したうえで、**ゲートに使わないと分かる形にした**:

- 関数名を `overall_confidence` → **`lowest_token_confidence`** に変えた。
  「overall（全体）」という名前こそが、**読み取り全体への評価として読む**ことを
  誘っていた。実体は最小値1つ、つまり**最も自信の無かった1語の点**である。
- 値は変えていない（最小値のまま）。**永続化済みの行の意味を後から書き換えない**
  ためで、レビュー画面の `OCR文字認識信頼度` は従来どおり比較可能である。
- 比較する箇所は無くなった。`RecognitionJobProcessor` は `usable` をこの値から
  決めず、crash 復帰時の再計算も**永続化された box の印**から行う
  （行の数値から読み直すと、同じ読み取りが初回と再試行で違う答えになる）。

**この数値は依然として「答案の長さ」に引きずられる。** 画面に出ている以上、
読み手が読み取り品質の総合点として読む余地は残っており、**そこを直すには
「どこが読めなかったか」を画面へ届ける必要がある**（次節）。

### 9.6 画面へは届けていない（別 Issue）

`unreadable` は **domain と永続化まで**で、API 応答には載せていない
（`api.recognitions_router.BoundingBoxResponse` は従来どおり text と矩形だけ）。
**載せると OpenAPI schema が変わり、生成物である `app/packages/auto_scoring_api/`
まで波及する**ため、本 Issue では止めて別 Issue として起票した
（[#185](https://github.com/HIKARU0627/Auto-Scoring/issues/185)）。
画面（`app/`）はこの Issue では一切触っていない。

`domain.ocr_metrics` の PoC 集計にも同じ形の指標があったので直した:
「低Confidence率」（**低い語を1つでも含む答案の割合**＝長いほど上がる）を
「読めなかった語の割合」（**語単位の率**）に置き換えた。同じ合成フィクスチャで
messy バケットは 0.5 → 0.25 になる。こちらは**報告であってゲートではない**ので、
`ConfidenceBand.LOW`（表示用の帯）で数えている — 決定が読む閾値は
`RecognitionSettings.confidence_threshold` 1箇所のまま。

### 9.7 検証

- `test_ocr.py`: `unreadable_spans` の位置・件数・`nothing_readable`、および
  **性質のテスト** — 同じ品質の語を1〜40語まで増やしても
  `nothing_readable` が反転しないこと。同じテストの中で
  **`lowest_token_confidence` は3語目で閾値を割る**ことを併せて確かめている
  （「増やしても壊れない」が、そもそも壊れる材料になっていないせいで
  通っていることを防ぐ）。個数に閾値を置けない理由も、
  同じ品質の答案を1倍・2倍・5倍に伸ばすと個数が 1 → 2 → 5 になることで固定した。
- `test_recognition_processor.py`: 1語だけ読めない読み取りが `usable` かつ
  **どの box が読めなかったかを永続化する**こと、語数 1/2/3/8/20 で `usable` が
  変わらないこと、0トークンと全語不読が `usable=False` であること、
  crash 復帰の再計算が永続化された印から行われること。
- `test_e2e_intake_to_export.py`: §9.4 の2本（実 SQLite・実キュー・
  scripted provider）。
- `test_ocr_metrics.py`: 語単位の率。
- **変異させて確認した**（テストが本当に欠陥を捕まえるかの検査）:

  | 戻した内容                                            | 落ちたテスト |
  | ----------------------------------------------------- | -----------: |
  | ゲートを最小値（`lowest_token_confidence >= 閾値`）へ |      **6件** |
  | ゲートを「読めない語が0件」へ                         |      **7件** |
  | box に `unreadable` を書かない                        |      **2件** |
  | crash 復帰の再計算を行の `confidence` へ戻す          |      **1件** |

  1つ目は語数3/8/20の性質テストと e2e の解放テストを含む（語数1/2は
  **落ちない** — 混合の3語目で初めて閾値を割るため、性質が語数のどこで
  効くかまで一致している）。

- **実 Document AI は叩いていない**（課金が発生する。判断は記録済みの実測と
  合成データで足りている）。§8.6 と同じく、実疎通は Issue #54 に残る。

## 10. OCRトークン粒度の実測と検証（Issue #152）

出力PDFで注釈記号（「×」印等）が行全体を覆う問題（Issue #152）において、
「OCRプロバイダ（Document AI）がトークン単位ではなく行や語の粗い粒度でしか
Bounding Box を返していないのではないか」という仮説が検証対象となった。

実機再検証 #6 の実データ（11教科・23切り出し）で返された Document AI のトークン
**497個** を実測した結果、この前提は十分に成り立っていることが確認された:

| 指標                  | 実測値                 |
| :-------------------- | :--------------------- |
| トークン総数          | **497**                |
| 1トークンの平均文字数 | **1.93文字**           |
| 中央値                | **2文字**              |
| 最大文字数            | 9文字                  |
| 1文字のトークン       | 205 / 497（41.2%）     |
| 2文字のトークン       | 194 / 497（39.0%）     |
| 1〜2文字の合計        | **399 / 497（80.3%）** |

トークン文字数分布: `1: 205, 2: 194, 3: 59, 4: 24, 5: 6, 6: 4, 7: 3, 8: 1, 9: 1`。
1トークンが回答欄切り出しの横幅に占める割合は中央値 5.7%、縦方向で 12.8% であり、
行単位の粗いボックスではない。

したがって、記号が行全体を覆う現象の原因は OCR 側の座標粒度ではなく、
複数行にまたがるトークン列を 1 つの外接矩形に統合するドメインレイアウト処理
（`_shortest_box_run` / `_union`）にあることが特定された（`docs/pdf-export.md` §2.6）。
