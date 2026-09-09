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

| OCRの状態            | `RecognitionResult`                | `usable` への寄与                   | 依存先                 |
| -------------------- | ---------------------------------- | ----------------------------------- | ---------------------- |
| 読めた・閾値以上     | 保存する                           | 第1項 True                          | 流れる                 |
| **読めた・閾値未満** | 保存する（低Confidenceも必ず残す） | 第1項 **False**                     | **止まる（変更なし）** |
| **OCRが使えない**    | **保存しない**                     | **第1項が消える**（2項のANDになる） | **流れる（新）**       |

- 「読めた・閾値未満」は**据え置いた**。業務ルール §4.4 が想定していたのはこの場合で、
  実際に読んだ結果が信用できないなら人が見るべきである。**ここは緩めていない**
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
  （「本当に読めなかった」であって「読む道具が無い」ではないため）

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
  - **新規** `test_an_ocr_reading_it_could_not_trust_still_blocks_until_a_human_resumes_it`:
    OCRが読んだうえで低Confidenceだった場合は**従来どおり止まり、`resume` で初めて動く**。
    「この端末にOCRが無い」を緩めたことで「OCRが読めなかった」まで緩んでいないことを、
    2本を並べて走らせて示す
- **変異させて確認した**（値ではなく直した性質を固定できているかの検査）:
  `usable=True` を `False` に戻すと5件、`confidence=0.0` の行を書き戻すと2件、
  OCR項を常に外すと4件が落ちる
- **実 Document AI への疎通は未実施。** ADC と processor のある端末が要るため
  Issue #54 に残す。本Issueが足したのは録画形状での疎通までである
