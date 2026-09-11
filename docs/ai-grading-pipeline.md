# 本番AI採点パイプライン

GitHub Issue [#20](https://github.com/HIKARU0627/Auto-Scoring/issues/20)（親
[#3](https://github.com/HIKARU0627/Auto-Scoring/issues/3)）。問題文・設問画像・
OCR結果・模範解答・rubric・配点から構造化された採点候補を生成し、人間確認前の
提案として保存する本番パイプラインを実装する。

> **⚠ 採点の入力はIssue #95 決定10で変わった。** **回答欄を切り出した画像が主入力**であり、
> OCR結果は得られていれば添える補助情報になった（模範解答も必須ではない）。
> **ページ全体の画像は採点に渡さない**（ヘッダを含むため。業務ルール §2 (2)、簡易設計書 §26.1.1）。
> ページ全体を送るのは**回答欄の検出**（Issue #105）だけである。
> 現在の仕様は [`simplified-design-specification.md`](./simplified-design-specification.md)
> §8.1・§9.1 が正。本書は実装当時の記録として残してある。

依存: [#26](https://github.com/HIKARU0627/Auto-Scoring/issues/26)（設問依存関係
DAG。`auto_scoring.domain.dependency_graph`）、[#16](https://github.com/HIKARU0627/Auto-Scoring/issues/16)
（テスト登録・プロファイル）、[#19](https://github.com/HIKARU0627/Auto-Scoring/issues/19)
（OCR認識パイプライン。`RecognitionJobProcessor`）、[#14 PoC 2](https://github.com/HIKARU0627/Auto-Scoring/issues/14)
（`AIProvider`契約・構造化出力スキーマ・メトリクスパイプライン。
`domain/ai_grading.py`・`domain/ai_provider.py`・`domain/ai_grading_metrics.py`）。

対象外: 人間レビュー操作（承認/修正/却下UI・API）とPDF描画は後続Issueで扱う。

## 決定事項

### AIモデル: 優先度つきフォールバック（業務ルール §3 (B)、Issue #81 で確定）

Issue #20 の実装時点では §3 (B) は未確定で、既定の`AIProvider`を
`NullAIProvider`（当時の`adapters/ai/null_provider.py`）に置いた。この既定は
Issue #97 で無くなっている（下記「アプリ本体への接続」）。
[Issue #81](https://github.com/HIKARU0627/Auto-Scoring/issues/81)で
プロジェクトオーナーが確定した内容は**単一モデルの選択ではない**:

| 優先度 | provider                             | 現状のアダプタ                                            |
| ------ | ------------------------------------ | --------------------------------------------------------- |
| 1      | Gemini API（Vertex AI + ADC）        | `adapters/ai_grading/vertex_gemini_provider.py`（#35）    |
| 2      | Codex App Server                     | `adapters/ai_grading/codex_app_server_provider.py`（#44） |
| 3      | OpenRouter（オープンウェイトモデル） | `adapters/ai_grading/openrouter_provider.py`（#44）       |
| 4      | OpenAI API                           | `adapters/ai_grading/openai_provider.py`（#35）           |

上から順に試し、失敗したら次へ落とす。本Issue（#81）はこの層をどこに置くかの設計を
記録するところまでだった。**設計どおりの実装は Issue #35 で完了している**:
合成アダプタ `adapters/ai_grading/fallback_provider.py` の `FallbackAIProvider` と、
`AUTO_SCORING_AI_GRADING_TRANSPORT` をカンマ区切りの優先度リストとして読む
`create_ai_provider()`。4 経路すべての live 疎通は
[`poc-2-ai-grading.md`](./poc-2-ai-grading.md) §7.4 に記録した。

なお ① は **Vertex AI 経由**である。Gemini の **API キーは組織ポリシーで禁止**されて
いるため、認証は Application Default Credentials（ADC）に限られる。GCP プロジェクト ID
は ADC から実行時に読むので、リポジトリには一切保存しない
（`adapters/ai_grading/_google_adc.py`）。

#### 層の置き場所: `AIProvider`ポートの内側の合成アダプタ

フォールバックは**`AIProvider`を実装する合成アダプタ**（順序つきの子アダプタ列を持ち、
`grade()`で順に試す）として`adapters/ai_grading/`に置く。`GradingJobProcessor`にも
`domain/ai_provider.py`のポート定義にも、キューにも手を入れない。理由:

- `GradingJobProcessor`側に置くと、「1回のprovider呼び出し」という前提で書かれている
  手順6〜8（`asyncio.to_thread`、DBトランザクションを保持しない、応答検証）に
  provider選択のループが混ざり、processorが採点手順とprovider運用の両方を持つことになる。
- キューのretry層に置くと、フォールバックのたびにJobの`attempt`を消費し、
  「同じproviderへのbackoff付きretry」と「別providerへの切り替え」が区別できなくなる。
  この2つは意味が違う（前者はレート制限の回復待ち、後者は回復を待たない切り替え）。
- 合成アダプタなら`AIProviderContract`（`backend/tests/test_ai_provider_contract.py`）を
  そのまま満たす1つのサブクラスとしてテストでき、`create_app(ai_provider=...)`の
  注入経路も既存のまま使える。

`create_ai_provider()`（`adapters/ai_grading/factory.py`）は
`AUTO_SCORING_AI_GRADING_TRANSPORT`を**カンマ区切りの優先度リスト**として受け取り
（既定の並びは `gemini,codex_app_server,openrouter,openai`）、**認証情報が揃っている
ものだけをチェーンに組む**（揃っていないproviderで失敗を1段消費しない。#35 で実装）。
1つも揃っていなければ空のチェーンを作らず`AIProviderConfigError`で落とす
（「設定済みに見えるのに1問も採点しない」状態を作らないため）。値が1つだけのときは
チェーンを作らずそのアダプタ自体を返すので、既存の呼び出し・`.env.local`はそのまま
動く。認証情報の持ち方は既存方針どおり`.env.example` / `backend/.env.local`で、
実キーはコミットしない（Gemini は鍵ではなく ADC）。

#### どの失敗で次へ落とすか

`GradingJobProcessor`が既に分類している例外（後述「エラー分類」）を、そのまま
フォールバックの判断にも使う。新しい例外型は追加しない。

| 失敗                                                          | 次のproviderへ落とす | 理由                                                                                                                                                                          |
| ------------------------------------------------------------- | -------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ProviderRateLimitedError`（429）                             | 落とす               | そのproviderの枠が空くのを待つより、別providerで進む方が速い                                                                                                                  |
| `ProviderServerError`（5xx）                                  | 落とす               | provider側の障害。同じ相手へのretryは同じ結果になりやすい                                                                                                                     |
| `ProviderTimeoutError`                                        | 落とす               | 同上。ただし1 provider内でのretryは行わず、1回で次へ落とす                                                                                                                    |
| `SchemaViolation`（構造化出力に従わない）                     | 落とす               | モデル固有の能力差。同じモデルへ再送しても直らないが、別モデルなら通りうる                                                                                                    |
| 認証情報不足・設定不正（`AIProviderConfigError`）             | チェーン構築時に除外 | 実行時ではなく組み立て時に落とす（上記）。Codex App Server は鍵を持たないが、`codex` 実行ファイルが無いホストでは同じく構築時に除外する（無ければ確実に失敗する段を残さない） |
| 素の`ProviderUnavailable`（実行時の401/4xx・transport error） | 落とす               | 表に無い経路。構築時には有効だった認証情報が呼び出し時に拒否される場合であり、チェーンが存在する理由そのもの                                                                  |
| 応答の対応不一致（手順7、rubricへ写せない応答）               | 落とさない           | ポートの外（processor）で判定するため合成アダプタからは見えない。現状どおり`PERMANENT`                                                                                        |

**上表に無い例外はチェーンを止める。** 上表はポート（`domain/ai_provider.py`）が
宣言している例外がすべてなので、それ以外はアダプタの不具合であって provider の
障害ではない。不具合を迂回すると、同じ壊れ方が毎回同じアダプタで起き続けるのに
誰も気づかないまま第2候補で動き続けることになる。落とす判断は1か所（合成アダプタの
`except`）に固定し、**任意のリモート応答を宣言済みの2例外へ変換する責任はアダプタ
境界に置く**（各アダプタの contract test にある malformed envelope のテスト）。

チェーンを全部使い切ったときは、**最後に観測した例外をそのまま送出する**
（クラス・メッセージ・traceback ともそのまま。試した段の記録 `ProviderAttempt` だけを
`attempts` に付けて渡す。後述「失敗の診断は、濾すのではなく組み立てる」）。
`ProviderRateLimitedError` / `ProviderServerError` / `ProviderTimeoutError` は
既存のマッピングどおりretry対象の`ErrorCategory`になるので、全provider不調のときは
Jobがbackoffして再投入される（並列数の既定4に対するレート制限の受け皿は
business-rules-and-evaluation-data.md §3.1 E のとおり引き続き必要）。全providerが
`SchemaViolation`なら`PERMANENT`となり、人手に回る。

#### どのproviderで採点したかを残す

`GradeResult.provider` / `model` / `prompt_version`（Issue #20で追加済み、
`domain/models.py`）が既にこの記録である。合成アダプタは**成功した子アダプタの
`ProviderDescriptor`をそのまま返す**（合成アダプタ自身の名前で上書きしない） --
再現性と、後からの一致率比較（provider別集計、`domain/ai_grading_metrics.py`）が
provider単位で成立するのはこの1点にかかっている。スキーマ変更は不要。

#### アプリ本体への接続（Issue #97 で完了）

Issue #20 は本番**パイプライン**（境界・schema検証・永続化・分類・Confidence運用・
前提設問contextの受け渡し）を実装し、`create_app()`の`job_processor`既定値を
`RecognitionJobProcessor`（Issue #19）から`GradingJobProcessor`（後述、
`RecognitionJobProcessor`を内部で合成する）へ置き換えた。ただし、その
`GradingJobProcessor`が呼ぶ`ai_provider`の既定値は`NullAIProvider`のままで、
`create_ai_provider()`（Issue #35 で完成）には**呼び出し側が存在しなかった**。
Issue #80 で取込のあと採点ジョブが起票されるようになっても、そのジョブは
何もしなかった。Issue #97 がこれを繋いだ。

**どこで環境を読むか: `create_app()` ではなく composition root（`api/sidecar.py`
の `run()`）。** `create_app()` の中で`os.environ`を読むと、アプリを組み立てる
テスト全部が「そのマシンにたまたま入っている設定」を引き継ぐ -- `gcloud` ログイン
のある開発機と無い CI runner で結果が変わる。これは Issue #35 で実際に CI を
落とした失敗そのものであり、`docs/quality-gates.md`「ホストを見る判定はテストへ
注入する」が禁じている形である。`run()` が
`api.app.build_ai_provider(os.environ)` を呼び、結果を
`create_app(ai_provider=...)` へ渡す。実環境は1つしか無い場所で1回読む。

**認証情報が1つも無いホスト: 起動する。ただし黙らない。**
`create_ai_provider()`は`AIProviderConfigError`で落ちるが、`build_ai_provider()`
はそれを**状態**へ変換する -- 採点以外（取込・レビュー・PDF出力）はプロバイダを
必要としないのに、鍵が無いという理由でその3つまで失うのは、採点できないことより
はるかに悪い失敗であるため。

| 決めたこと                                       | そうした理由                                                                                                                                                                                                               |
| ------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `NullAIProvider`を`UnconfiguredAIProvider`へ置換 | `NullAIProvider`は score 0・confidence 0.0 の`GradeResult`を**永続化する**。レビュー画面では「実プロバイダが答案を読んで0点を付けた」と見分けがつかない。これがこの Issue の消したかった「AIが採点したが空だった」そのもの |
| `grade()`で`ProviderUnavailable`を送出           | `GradingJobProcessor`が既に`PERMANENT`へ分類する。設問のJobはFAILEDで終わり、retryもされず（retryしても鍵は増えない）、`GradeResult`行は1つも書かれない                                                                    |
| 理由はJobではなくアプリ全体で1回言う             | 理由はどの設問でも同じ1文であり、`Job.last_error`にはprovider例外文言を入れない規約（AGENTS.md「Security」）がある。`GET /grading/availability`が`{available, reason}`を返し、アプリはそれを**全画面の上の帯**として出す   |
| 帯は消せない／`reason`をそのまま出す             | 閉じられる帯は「消したまま採点されない」状態を作れてしまう。`reason`は英語だが、設定変数名とホスト前提条件だけを含み（値は含まない）、実際に直せる人が読む唯一の手がかり                                                   |
| 応答が無いときは帯を**出さない**                 | 「サイドカーが応えなかった」と「採点が使えない」は別の事実。前者を後者と断定すると、一度の通信失敗が設定不備の告知になる（`app/lib/core/widgets/grading_unavailable_banner.dart`）                                         |

`reason`に**設定値**を入れないことは2重に担保する: `create_ai_provider()`の
`AIProviderConfigError`は変数**名**しか含まない（規約は`factory.py`のモジュール
docstring）、それ以外の想定外例外は**例外型名だけ**を残して本文を捨てる
（`_google_adc`が google-auth のメッセージに対して既に採っている規律と同じ）。

**この規約は後から必要になったものである（レビュー1回目 P2）。** `factory.py`の
メッセージ群は「ログにしか出ない」前提で書かれており、
`AUTO_SCORING_AI_GRADING_TEMPERATURE`の読めなかった値・未知の transport 名・
`AUTO_SCORING_CODEX_EXECUTABLE`の設定値をそのまま含んでいた。本Issueが
**公開経路を新設した**ことで、設定先を間違えて鍵を貼った操作者に、その鍵が画面と
ログから読み返される状態になっていた。3か所とも値を落とし、規約を
`factory.py`側（値を書く側）へ置いた。`backend/tests/test_grading_availability.py`
は、`create_ai_provider()`が読む**全変数**に順に偽の鍵を入れ、`reason`にも
HTTP応答本文にも出ないことを確認する（既知の悪いメッセージの一覧ではなく変数の
一覧にしてあるのは、将来また値を書き始めたメッセージを捕まえるため）。

**同じ事故がもう1つの経路でも起きた（レビュー2回目 P2）。** Vertex アダプタは
`AUTO_SCORING_VERTEX_PROJECT` / `AUTO_SCORING_GEMINI_MODEL` をリクエスト URL へ
組み込み、httpx がそれを INFO でログに出す。サイドカーは root を INFO にして回転
ファイルログへ書くので、404 応答だけで設定値が永続ログに残っていた。**この経路は
本Issueが作った**（実providerに繋いだからこそ URL が組み立てられる）。

経路を数え上げるのをやめ、**外へ出る場所にゲートを置いた**:
`api/secret_redaction.py` が「設定値とは何か」を1か所で定義し
（`AUTO_SCORING_` 名前空間の、12文字以上の値と資格情報系の変数。`v1`・`0.0`・
`global` のような短い構造的な値は伏せない -- 伏せるとログが読めなくなる）、
テキストがプロセスを出る2か所がこれを適用する: `install_log_redaction`
（このプロセスがログを設定する唯一の場所。uvicorn は `log_config=None` で起動する
ので uvicorn のロガーも root のハンドラを通る）と `build_ai_provider`
（reason を作る唯一の場所）。

**ただしマスクだけでは足りない（レビュー3回目 P2）。** httpx は URL のホスト名を
小文字化するため、`AUTO_SCORING_VERTEX_LOCATION` に大文字を含む値を入れると完全一致の
置換をすり抜けた（パスは `***` になるのにホスト名には残る）。値の表現形を決めるのは
ライブラリ側なので、照合を足し続ける勝負にはならない。**リクエストURLのログを消すのを
やめ、出さないことにした**: `api/sidecar.py` の `_VERBOSE_LOGGERS` が INFO を許すのは
`auto_scoring` / `uvicorn` / `alembic` だけで、root は WARNING。httpx も httpcore も、
まだ足していない将来の依存も、既定で INFO を出せない。

#### 失敗の診断は、濾すのではなく組み立てる（レビュー4回目）

URL のログを止めた時点の説明「必要な情報は `GradeResult` と `Job.last_error` にある」は
**採点が成功したときにしか成り立たなかった**。チェーンが 401/403/404 で全滅すると
`GradeResult` は作られず、`GradingJobProcessor` は `ProviderUnavailable` を一律
`"call failed"` に畳み、`FallbackAIProvider` は最後の例外だけを再送出していた。
初回起動でこれを踏んだ操作者は、ADC のログインをやり直すのか(401)・プロジェクトで
aiplatform を有効化するのか(403)・`AUTO_SCORING_GEMINI_MODEL` の綴りが違うのか(404) を
区別できない。

`domain/ai_provider.py` に `ProviderAttempt` を足した。持てるのは次の 4 つだけ
（3 つ目までが Issue #97、4 つ目は Issue #121 で足した）:

| 記録するもの      | 何を使うか                                                                                                  |
| ----------------- | ----------------------------------------------------------------------------------------------------------- |
| provider の識別子 | アダプタの `name` **リテラル**（`describe().model` は設定なので不可）                                       |
| 失敗の種類        | このポートの**例外クラス名**（`ErrorCategory` と1:1）                                                       |
| HTTP ステータス   | **数値**。応答が無い場合（timeout/transport）は `None`                                                      |
| schema 違反の詳細 | このリポジトリの schema 定義由来の**フィールドパス**と pydantic の**種別コード**（Issue #121 で追加。後掲） |

例外メッセージ・レスポンスボディ・URL・ヘッダは入れない。**濾すのではなく組み立てる**
ので、アダプタのメッセージが将来また設定値を含んでも `Job.last_error` へは出ない。
4 つ目も同じ規律の適用であって例外ではない -- 組み立てる部品が全部リテラルであることを
`describe_schema_violation` 側で保証している。

出口は3つ。`Job.last_error`（jobs API が返し、画面へ出せる。答案1件・設問1件の粒度で
再起動をまたいで残る）、`FallbackAIProvider` の WARNING 1行（**フォールスルーした段
ごと**に出す。全滅時の途中の段 — 「Vertex が 403 で OpenRouter が 401」 — は最後の例外
だけでは表せず、成功して落ちたとき、つまり例外が誰にも渡らないときにも残る必要がある）、
そして `GradingJobProcessor._failed` の WARNING 1行（Issue #121 で追加。
**チェーンを組まない単一プロバイダ構成**では前者が一度も出ないため）。

**「全部のケースを診断できる」とは主張しない。** 主張できるのはこの4つを記録することまで。

詳細と教訓は `docs/quality-gates.md`
「新しい公開経路を作ったら、そこへ流れ込むものを全部見直す」。

実キーでの疎通・schema 検証は Issue #35 で 4 経路すべて実施済み
（[`poc-2-ai-grading.md`](./poc-2-ai-grading.md) §7.4。合成フィクスチャのみを送信）。

**OCR 側は Issue #114 で接続した。** 本Issue（#97）の時点では `NullOCRProvider`
のままで、`GradingJobProcessor` が採点へ渡す OCR テキストは常に空だった。ただし
**採点自体はそれでも動いていた** — 多モーダルの provider が回答欄の切り出し画像を
直接読むためである（簡易設計書 §8.1.1）。止まっていたのは採点ではなく
**設問の連鎖**のほうで、経緯と決着は
[`ocr-recognition-pipeline.md`](./ocr-recognition-pipeline.md) §8 にある。

### 上限を超えた注釈コメントは切り詰める。採点結果は捨てない（Issue #121）

2026-09-09 の実機検証（実データ × 実 Vertex AI）で、AI 採点が恒久失敗した 6 件のうち
**5 件がこれ**だった。

```
loc: ('annotations', 0, 'comment')   type: string_too_long
     String should have at most 120 characters
```

性質を先に押さえる。**`finishReason` は `STOP`** で、応答は完全な JSON。**点数も
採点基準 ID も設問 ID も正しい。** 落ちた理由は注釈コメントが 147 字／157 字
あったこと**だけ**である。Gemini の structured output は schema の形は守るが
`maxLength` は強制しないので（`poc-2-ai-grading.md` §7.4）、上限は手元でしか効かない。
そして**記述量の多い設問ほど落ちる**。

**上限を上げても同じことが起きる。** 上限がある限り超える応答は来る。直したのは
上限の値ではなく、**上限の役割**である。

- `MAX_COMMENT_CHARS`(120、業務ルール §2 (6)) は据え置き。DB の CHECK 制約
  (`0012` / `0013`) でもあるので、値を動かすのは移行を伴う別の判断になる。
- `domain/ai_grading.py` の 2 つの `comment` フィールドは、上限超過を**拒否**する
  代わりに `domain.models.truncate_comment` で**切り詰める**。切った印として
  末尾に `…` を付ける（PDF 描画側が既に使っている打ち切り記号と同じ文字。
  `adapters/pdf/pdfium_pypdf_engine.py` の `_ELLIPSIS`）。
- 切り詰めの対象は**コメントだけ**。点数・基準 ID・設問 ID・`rationale`・
  `recognition` は 1 文字も触らない。

**これは Issue #97 / PR #100 の「崩れた応答は保存しない」規律の例外ではない。**
あの規律が捨てるのは**信用できない応答**である。ここで起きていたのは、
**信用できる応答の付随部分が長い**だけで、応答の信用に関わる項目
（点数・基準 ID・設問 ID）はすべて正しかった。schema のうち
「その採点を信じてよいか」を語る項目は今までどおり違反で捨てる。
コメントの長さが語るのは「コメントが何文字入るか」だけなので、譲るのはコメントの側になる。

プロンプト（`adapters/ai_grading/_prompt.py`）にも上限は書いてあるが、
**プロンプトだけには頼らない。** 実機はまさにその指示を守らなかった。
文面は「超えた分は切り捨てられる」に直してある（以前の「reject される」は、
この変更で嘘になるため）。

### どのフィールドがなぜ落ちたかを残す（Issue #121）

同じ実機検証で、**サイドカーのログに恒久失敗が 1 行も記録されず**、
`Job.last_error` も `[gemini SchemaViolation]` までしか言わなかった。原因の特定には
プロバイダ応答を自前で捕まえる必要があった。

`ProviderAttempt` の「濾すのではなく組み立てる」規律（前掲）は、この情報を**禁じていない**。
フィールドパスはこのリポジトリ自身の schema 定義のリテラルであり、
`string_too_long` のような種別コードは pydantic 自身のリテラルである。**値だけが危ない。**

- `domain/ai_grading.py` の `describe_schema_violation` が `loc` と `type` だけから
  `annotations.0.comment: string_too_long` を組み立てる。`error["input"]` は読まない。
  `extra_forbidden` の `loc` 末尾は**プロバイダが送ってきたキーそのもの**なので、
  そこだけ固定のプレースホルダに置き換える。
  （この処理は PoC 2 のレポータが既に持っていたものを domain へ移して共有した。
  同じ判断を 2 箇所で維持しない。）
- `ProviderAttempt` に `detail` を足し、3 つのアダプタが
  `SchemaViolation(..., detail=describe_schema_violation(exc))` を投げる。
  `Job.last_error` は
  `gemini AI provider returned a malformed response [gemini SchemaViolation annotations.0.comment: string_too_long]`
  になる。
- **schema 検証を通ったあとの失敗にも同じ規律を適用する。** Issue #117 が足した
  「rubric の位置が範囲外」は pydantic の `ValidationError` ではないので
  `describe_schema_violation` を通らない。`grading_response_from_result` が
  `detail="criteria.<位置>.index: out_of_range"` を直接付ける（前掲
  「モデルに識別子を転記させない」）。
- `GradingJobProcessor._failed` が、同じ文字列を WARNING で 1 行出す。
  `FallbackAIProvider` の WARNING は**チェーンを組んだときしか出ない**が、
  実機はプロバイダ 1 本の構成だった（鍵の無い openrouter / openai は
  `factory` が除外する）。ログが 1 行も無かったのはそれが理由で、
  恒久失敗の記録をチェーンの有無に依存させない。

### 解答でない画像から作った点数を、点数として確定させない（Issue #136）

2026-09-09 の実機再検証（8教科・実データ・実 AI）で、**採点結果が作られた 14 件のうち
7 件（50%）が確信度 1.00 の誤った 0 点**だった。画面には「0 / N 点・採点信頼度 100%
（高）」としか出ず、**正しい 0 点と見分けが付かない。**

原因は採点 AI の精度ではない。**答案でないものを渡していた。** 切り出し 14 件のうち
正しかったのは 4 件で、残りは枠がずれた・半分だけ乗った・罫線だけの空欄・別設問を
切っている、のいずれかだった。

#### インク量の閾値では分離できない（測ってある）

切り出し 14 件のインク比率を、正しい切り出しか誤りかを付けて並べると:

```
0.0148正  0.0170誤  0.0216正  0.0225正  0.0235誤  0.0252誤  0.0285誤
0.0372誤  0.0541正  0.1420誤
```

**正誤が完全に交互になっている。** 誤りの 0.0372 を拾う閾値にすると、正しい切り出し
（0.0148 / 0.0216 / 0.0225）を全部弾く。理由は 2 つで、(1) 空欄にも印刷罫線があり
インクとして数えられる、(2) **正しい切り出しでも、余白の多い計算欄は 0.015 前後しか
ない**（#122 が閾値を決めたときの実測 3 枚には (2) の形が入っていなかった）。

したがって `NEARLY_BLANK_INK_COVERAGE`（`domain/submission_intake.py`）を動かしても
この問題は解けない。**吸着（#122）でも救えない**——17 領域すべて「最大 0.000 動かしました」で、
モデルは最初から罫線上の値を返しており、**間違った罫線に静かに乗っているものが 14 件中 5 件**
あった。座標からも注記からも正しい枠と区別が付かない。

#### 採った方向: AI が既に書いていた判断を、捨てずに受け取る

7 件の根拠テキストを読み直すと、**AI 自身が気づいている件があった。**

| 根拠に書かれていたこと                                            | 件数 |
| ----------------------------------------------------------------- | ---: |
| A: 渡された画像はこの設問の解答ではない、と明確に書いている       |    2 |
| B: 示唆はあるが断定していない                                     |    1 |
| C: 疑いを示さず採点しているが「解答が空白である」とは明示している |    4 |

A の 2 件は、**画像に何が写っていたかを描写したうえで**「これは解答ではない」と
断定している（一方は生徒 ID 欄と提出期限だけが写っていた、もう一方は別設問のラベルが
写っていた）。それでも出口が「確信度 1.00 の 0 点」しかなかった。

そこで、**採点応答に「渡された画像は何だったか」を報告する経路**を足した
（`answerImage`、`domain.models.AnswerImageFinding`）。新しい推定は増やしていない。
既に得られている判断を捨てないだけである。

#### 「解答ではない」と「解答が空白」を、1 つの信号に潰さない

これが設計上いちばん重要な点である。値は 3 つ + `null`:

| 値               | 意味                                                    | いま何が起きるか                        |
| ---------------- | ------------------------------------------------------- | --------------------------------------- |
| `answer`         | この設問の解答欄で、記入がある                          | 通常どおり採点                          |
| `blank`          | この設問の解答欄で、記入が無い                          | **通常どおり採点し、値を記録する**      |
| `not_the_answer` | この設問の解答欄ではない（別設問・見出し・ID 欄・余白） | 点数を作らず人へ回す                    |
| `null`           | プロバイダが何も報告しなかった                          | 通常どおり採点（この Issue 以前と同じ） |

boolean 1 本にすると C の 4 件が同じ旗を立て、**本当に無記入の答案にも同じ旗が立つ。**
無記入は生徒が実際にすることであり、その 0 点は正しいかもしれない。**分けてあれば、
まず A+B だけを人に回して副作用ゼロで 7 件中 3 件を救い、無記入の頻度を実測してから
C の扱いを決められる。**

**`null` を `answer` として読まない。** 記録済みの PoC データセットはこのフィールドを
持たないし、指示を無視するプロバイダもありうる。「誰も見ていない切り出しを、
見て問題なしと言ったことにする」のは、この Issue が止めた捏造そのものである。

#### 受け口: 採点の応答を見てから、切り出し側の契約に落とす

既存の理由（`no_answer_area_defined` / `answer_area_zero_area` / `crop_nearly_blank` /
`reading_order_conflict`）は**採点の前**に決まるが、`crop_not_the_answer` は
**採点の応答を見て初めて分かる**。それでも置き場所は
同じにした（`jobs/grading_processor.py::_crop_is_not_the_answer`）:

- **`AnswerImage` を `NEEDS_REVIEW` + 理由 `crop_not_the_answer` にする。** 切り出しに
  ついての恒久的な事実であって、それを見つけた試行の性質ではない。こうすると
  **再判定でプロバイダを呼ばない**（`recognition_processor` / `grading_processor` は
  どちらも `NEEDS_REVIEW` で止まる。同じ画像は同じ答えしか返さない）。また
  「検出が何回まちがった枠を渡したか」を後から数えられる。
- **`GradeResult` を作らない。** 画面で正しい 0 点と見分けが付かなくしているのは
  **点数の行そのもの**なので、作らないことが直し方になる。結果、Issue #118 が作った
  「AI が採点しなかった設問を人が引き取る」経路にそのまま合流する。
- **Job は `PERMANENT` で失敗させる。** 同じ切り出しを同じモデルへ送り直しても
  同じ答えが返るので、再試行に意味がない。「人が材料を直すまで AI は進めない」という点で、
  rubric や模範解答が無いときの既存の `PERMANENT` と同じ意味である。`Job.last_error`
  に理由語（`crop_not_the_answer`）が入り、画面はそれを見て**何を直すべきか**を言う
  （[pdf-review-overlay.md](./pdf-review-overlay.md) §2.13.2）。

**矛盾した応答（`not_the_answer` なのに点数が 0 より大きい）も人へ回す。** 実機では
起きていないが、契約として決めておかないと実装の偶然で決まる。解答でない画像から
出た点数は、5/5 でも 0/5 でも同じだけ根拠が無い。`GradeResult.__post_init__` と
DB のトリガ（`db/orm.py`・migration `0017`）の両方で、`not_the_answer` を持つ
採点行は**保存できない**ようにしてある。

**CHECK 制約ではなくトリガなのは、測って決めた。** SQLite は既存テーブルに CHECK を
足せないので、CHECK にすると migration が `grade_results` を作り直すことになる。
作り直すとそのテーブルが sqlite_master の末尾へ移り、**SQLite がカスケードを適用する
順番が変わる**。すると `reviews.ai_grade_result_id` の `ON DELETE SET NULL` が、
その review 行自身が消える前に走り、`approved` の review が採点結果を失って
`ck_reviews_confirmed_requires_ai_grade`（Issue #118）で削除ごと落ちる——テストの削除が
できなくなる。列を足すだけなら作り直しは要らないので、規則はトリガで表現している。

なお **`approved` の review が指す採点行を単体で削除すると、この作り直しと関係なく
同じ制約に当たる**（実測）。テスト削除がふだん通るのは、review 行のほうが先に
カスケードで消えるからで、スキーマの並び順に依存している。これは main にもある
既存の脆さで、`reviews` 側の変更になるため別の Issue とする。

#### `blank` は分岐させないが、記録する

C（4 件）を拾うかどうかは、**無記入がどれくらいの頻度で来るか**で決まる。実データでは
0 件だったが、40 枚規模では出るはずで、その頻度は今回（各教科 1 答案）測れていない。

分岐は足していない。ただし `grade_results.answer_image_finding` に値を残す。記録しないと、
頻度を知るために実データでの再検証を丸ごともう一度回すことになる（1 時間半かかる）。
残しておけば、次に誰かが実データを流したときに `SELECT` 1 本で数えられる:

```sql
SELECT answer_image_finding, COUNT(*) FROM grade_results GROUP BY answer_image_finding;
```

**未決事項**: この数字が出たら、`blank` も人へ回すかを決める。分岐を 1 つ足すだけで
拾える形にしてある。

> **更新（Issue #156）: 分岐は今も足していないが、画面には出す。**
> `GradeResultResponse.answer_image_finding` として API に載せ、添削レビュー画面が
> `blank` のときだけ本文で伝える（[pdf-review-overlay.md](./pdf-review-overlay.md)
> §2.3.2）。実機再検証 #4 で `blank` と記録された 3 件は**3 件とも切り出しの誤り**で、
> 本当の無記入は 0 件、しかも採点信頼度は 1.00 だった。**採点の分岐を変えずに、
> AI が既に言っていたことを人へ渡すだけ**なので、上の「頻度を測ってから決める」は
> そのまま生きている——`blank` を人へ回すかどうかは、まだ決めていない。

#### この変更が持ち込むリスク

**モデルが正しい切り出しに対して `not_the_answer` と言い始めると、本当に採点できた
はずのものが人に回る。** 今回の実データでは正しい切り出しが 4 件あった。プロンプト
（`adapters/ai_grading/_prompt.py`）は、根拠なく言えない書き方にしてある——値の定義を
「解答がどう見えるか」ではなく**「解答の代わりに何が写っているかを言えるか」**に置き、
唯一まぎらわしい「空欄」には別の値を与えて名指しで除外している。実際にどうなるかは
実データを流さないと分からないので、マージ後の実機検証で**その 4 件が採点されたまま
かを確認する**。

### 自然文の出力言語は日本語固定（Issue #140）

8教科の実機再検証で、`rationale`/`comment` が**教科によって英語で返ってきた**
（日本史・化学・英語は英語、古漢・現代文・生物は日本語）。モデルは渡した資料や
設問の言語に引きずられていて、どちらを使うかを一度も指示していなかった。同じ
実機検証で、採点基準抽出（[criteria-extraction.md](./criteria-extraction.md)）の
モデル自身の申し送り `note` も英語で返り、そのまま画面に出ていた。

この画面を読むのは日本の塾講師で、読む対象は生徒に返す添削コメントの下書きである。
**出力言語は日本語固定**とし、設定で切り替えられるようにはしない（利用者が日本の
塾講師以外に増える見込みが無い）。

#### 1か所に定義し、3アダプタが参照する

`domain.ai_response_language` に `RESPONSE_LANGUAGE_INSTRUCTION`（プロンプト本文に
足す1文）と `FIELD_LANGUAGE_NOTE`（スキーマの `description` に足す1句）を追加し、
`adapters/ai_grading/_prompt.py` ・ `adapters/criteria_extraction/_prompt.py` ・
`adapters/answer_area_detection/_prompt.py` の3アダプタがそれを import して使う。
3アダプタがそれぞれ自分の文言で「日本語で」と書く形にはしていない -- それこそが
今回のばらつきの原因（教科ごとに違う資料言語へ、指示が無いまま引きずられた）と
同じ失敗を、指示の書き方の水準で繰り返すことになるため。#125（3アダプタ共通部分の
一本化）とは別で、ここで共通化したのは**言語指定だけ**である。

**両方の経路に置く必要がある。** 構造化出力のバックエンドが実際に強制するのは
スキーマ側（各フィールドの `description` を含む）で、プロンプト本文は信頼できる
指示チャネルとして別に送られる -- スキーマ駆動のデコーダがプロンプト本文をどこまで
重く見るかは保証されていない。どちらか片方にしか書かないと、もう片方しか読まれない
フィールドで資料の言語へ戻る。これが実際に起きていた失敗そのものなので、
プロンプト本文（`GRADING_SYSTEM_INSTRUCTIONS` 等）とスキーマの `description`
（`comment` / `rationale` / 採点基準ごとの `rationale` / 注釈の `comment` /
抽出・検出側の `note`）の両方に足した。

**引用は対象外。** 生徒の解答・模範解答・OCR結果を逐語引用する
`AnnotationCandidate.target` や、採点基準文書からの転記である
`ExtractedCriterionOutput.description` / `model_answer` は、原文の言語のまま
でよい。ここへ日本語化の指示を足すと、英語科の答案そのものを日本語へ訳して返す
方向にモデルを押しかねず、答案の実際の文字列と一致しなくなる
（`target` は OCR の word box と照合して打点位置を決めるため、逐語性が壊れると
機能しない）。

`ai_classification`（採点基準PDF/答案の自動振り分け、Issue #101）は対象外にした。
`role`/`candidate_id` は enum、`confidence` は数値のみで、モデル自身の自由文を
一切返さない -- 訳す対象になる自然文フィールドがそもそも無い。
`backend/tests/test_ai_response_language.py` の
`test_classification_schemas_have_no_free_text_field` がこの前提を固定していて、
将来ここに自由文フィールドが増えたら赤くなる。

#### 定義を1か所に保つことをテストで固定する

`backend/tests/test_ai_response_language.py` は、3アダプタのプロンプト本文が
共有定数をそのまま含むこと、対応するスキーマフィールドの `description` に
`FIELD_LANGUAGE_NOTE` が含まれること、逐語引用・転記系フィールドには含まれない
ことを検査する。**定義を消す（`RESPONSE_LANGUAGE_INSTRUCTION` を削除・改名する）
と、3アダプタすべてが import エラーで即座に落ちる**ことを実際に確かめた
-- 3アダプタの `_prompt.py` はどれもこの名前を直接 import しているため、
定義側を壊すと参照側全部が壊れる形になっている。個別のプロンプト・スキーマから
指示文だけを取り除く変異でも、対応する1本だけが赤くなることを確認した
（全部が緑のままにはならない）。

### 画像を運ぶ AI 呼び出しを1本にする（Issue #125）

採点基準の抽出（#103）・回答欄の検出（#105）・資料の分類（#101）は、どれも
**「ページ画像と strict JSON Schema を image-capable transport へ1回投げ、
壊れた応答は `SchemaViolation` にする」**という同じ処理をしていた。#105 の
実装時にその重複は申告されていて、「マージ後に1本化する」follow-up として
#125 が起票された。

**目的は行数削減ではない。「1箇所直せば3つとも直る」ようにすること。**
#121（注釈コメントが上限を超えると採点結果ごと破棄する）は採点側で見つかったが、
**「strict schema に合わない応答は丸ごと捨てる」という構造は4アダプタで共通**で、
3つに分かれている限り、同型の欠陥を直すたびに「同じ処理をしている別の場所」を
探す作業が発生する。

#### 何を1本にし、何を分けたまま残したか

| 何                                                      | どこ                                                     |
| ------------------------------------------------------- | -------------------------------------------------------- |
| transport の選択（`AUTO_SCORING_AI_GRADING_TRANSPORT`） | `adapters/ai/image_transport.py`（1本）                  |
| vendor ごとの認証情報・base URL・保持オプトアウト       | 同上（1本）                                              |
| ページ画像の載せ方（base64 / data URL / `inlineData`）  | `adapters/ai/image_call.py`（1本）                       |
| strict schema の送信と応答エンベロープの取り出し        | 同上（1本）                                              |
| 応答を丸ごと捨てる判断（`discard_response`）            | 同上（**1本**。#121 と同型の欠陥はここに集まる）         |
| プロンプト本文                                          | 各アダプタの `_prompt.py` / `classifier.py`（3本のまま） |
| 応答スキーマ                                            | 同上（3本のまま）                                        |
| パーサと妥当性検査                                      | 各アダプタの `domain` モジュール（3本のまま）            |
| 「この端末では使えない」の言い方                        | 各 factory（3本のまま。後述）                            |

プロンプトとスキーマを共通化しないのは #125 が明示した「やらないこと」である
——3つは目的が違い、共通化すれば片方の都合でもう片方の文言が動く。

**新しい抽象は足していない。** 共通化した `ImageJsonCall` は、#101 が
`adapters/ai_classification/_calls.py` に既に持っていた `StructuredJsonCall`
（「system 指示・テキスト・画像・スキーマを送り、JSON テキストを返す」）を
画像1枚から複数枚へ広げて上へ移したものである。「将来のための基底クラス」も
「差し替え可能なインターフェース」も足していない。

#### `Unconfigured*` は3本のまま残した

#125 は「この端末では使えない」の表現も1本化の対象に挙げているが、実際には
1本にできなかった。`UnconfiguredCriteriaExtractor` は adapters 側、
`UnconfiguredAnswerAreaDetector` は domain 側にあり、資料の分類はクラスではなく
例外（`ClassifierUnavailable`）で表す。3つは**別のポートを実装していて**、
`api/sidecar.py` はそれぞれを `isinstance` で見分けて別の availability を返す。
1つのクラスにまとめるとその区別が消え、`api/` の書き換えを伴う——#125 の
「共通化であって層を足すことではない」からも、担当範囲からも外れる。
共通化したのは、その reason を作る側（transport 選択の失敗理由）である。

#### 3本とも同じ扱いになることをテストで固定する

`backend/tests/test_ai_response_overflow.py` は、3アダプタそれぞれに
**「完全な応答で、載っている値も正しく、1つの文字列だけが長すぎる」**という
#121 と同型の入力を与え、3本とも同じ答え（応答ごと `SchemaViolation`、値は
引用しない、例外を連鎖させない）になることを検査する。#140 の
`test_ai_response_language.py` と同じ形で、**共有部分を1か所変えると3本ぶんが
同時に落ちる**。実際に変異させて確かめた:

- `discard_response` が `SchemaViolation` ではなく `ProviderUnavailable` を
  投げるようにすると、3アダプタのテストと新規テストで **37 件**が落ちる。
- `transport_priority_list` の区切り文字を変えると、3アダプタの factory
  テストが落ちる。
- アダプタ固有の部分（抽出の `images` 引数／検出の設問候補／分類の
  `_PROPOSABLE_ROLES`）を壊すと、**その1本だけ**が落ちる。

`ai_classification` は分類スキーマに自由文フィールドが1つも無い（#140 と同じ
理由）ので、「長すぎる文字列」に相当する入力は**モデルが返した role 文字列
そのものが長すぎる**場合になる。テストにその旨を書いてある。

`docs/job-queue.md`が決定した「1 Question = 1 Job（`JobKind.GRADING`）、
Job内部でOCR→採点をどう分けるかはJobProcessor実装側の自由」という設計を受け、
`auto_scoring.jobs.grading_processor.GradingJobProcessor`は
`RecognitionJobProcessor`（Issue #19、変更なし）を内部に持ち、その`process()`を
呼んだ後にAI採点を行う:

1. まず`RecognitionJobProcessor.process(job)`を呼ぶ。`FAILED`ならそのまま
   返し、採点は一切試みない。
2. `SUCCEEDED`でも、`RecognitionResult`が実際に永続化されているか
   （`recognition_result_id(job)`で参照）を確認する。無ければ
   （回答欄検出失敗で切り出し画像自体が信頼できず、providerを一切呼ばずに
   `usable=False`を返した場合）、採点する文字が無いため即座に同じ結果を返す。
3. 同じ`job.id`に対する`GradeResult`が既に存在すれば（クラッシュ後の再処理、
   `RecognitionJobProcessor`と同じ理由）providerを再度呼ばず、既存行から
   `usable`を再計算して返す。
4. `Question.model_answer`が未登録、または`Rubric`が無い（`criteria`が空）
   場合は、`RecognitionJobProcessor`の「回答欄画像が無い」場合と同じ扱いで
   `FAILED`(`PERMANENT`)にする -- 採点材料が無い設問をAIに推測させない
   （AGENTS.md「Verification」: 「読めない文字や判断不能を推測で補完しない」）。
   人間がmodel answer/rubricを登録するまで自動リトライしても無意味なため
   `PERMANENT`とする。
5. 確定済み`DependencyGraph`（Issue #26）から前提設問のcontextを組み立てる
   （後述）。
6. `AIProvider.grade()`を呼ぶ（`asyncio.to_thread`でイベントループをブロック
   しない。ネットワーク呼び出し中はDBトランザクションを保持しない --
   `jobs/queue.py`・`RecognitionJobProcessor`と同じ規約）。rubric_textは
   criterionを**番号付きの箇条書き**にし、設問の`scoring_method`（加算/減点）
   を含める。登録済みcriterion `id`はrubric_textには入れず、
   `GradingRequest.criterion_ids`として番号と同じ順で別に運ぶ
   （後述「provider requestで全rubric意味論を保持する」・
   「モデルに識別子を転記させない」）。
7. 応答の`max_score`が要求したものと一致しない場合、または応答の
   `criteria[].index`から解決したcriterion idの集合が登録済みrubricのcriterion
   id集合と完全一致しない場合（登録済みのidを省略している場合。範囲外の
   `index`はここへ来る前に`SchemaViolation`になる）は`FAILED`(`PERMANENT`)に
   する -- PoC 2のメトリクスハーネス
   （`ai_grading_metrics.evaluate_sample`）が「対応不一致」として実装している
   分類を、本番パイプラインでも同じ理由で採用・拡張する: rubricへ確実に
   マッピングできない応答をこの設問の採点として保存しない
   （コードレビュー指摘: schema上は妥当でもcriterion idが登録済みrubricと
   食い違う応答を、そのまま高confidenceで永続化・usableにしていた）。
   なお`question_id`の照合は無くなった（Issue #117）: 応答は識別子を持たず、
   `GradingResponse.question_id`は送ったrequestから埋めるため、比較しても
   常に一致する。
8. 成功応答は`GradeResult`（`source=ai`、常に）として永続化し、応答に含まれる
   `annotations[]`も`Annotation`（`source=ai`）として保存する
   （`target`を`anchor_text`へ、座標は一切持たない -- 簡易設計書 §12.1）。
   graderの認識結果（`response.recognition_text`/`recognition_confidence`）も
   別の`RecognitionResult`（後述）として保存する。
9. `Job.usable`は「OCR pipeline自身のRecognition Confidence、AI grader自身の
   Recognition Confidence、Grading Confidenceの**3つすべて**が閾値以上」
   （後述、Issue #20受入条件）。

### エラー分類: timeout / rate limit / 5xx / スキーマ不正 / 対応不一致

`domain/ai_provider.py`の`ProviderUnavailable`に`ProviderTimeoutError`・
`ProviderRateLimitedError`・`ProviderServerError`の3サブクラスを追加した
（`domain/ocr.py`の`OCRProviderError`サブクラス群と同じパターン -- PoC 2時点の
`ProviderUnavailable`は無分類の単一例外だったが、Issue #20は「timeout、429/5xx
を分類しqueueのretry規則へ接続する」ことを求めるため、この粒度が必要）。
`GradingJobProcessor`は以下へ分類する（`ErrorCategory`、Issue #18で確定済みの
4値を再利用 -- 新しい値は追加しない）:

| 例外                          | `ErrorCategory` | retry対象 |
| ----------------------------- | --------------- | --------- |
| `ProviderTimeoutError`        | `TIMEOUT`       | される    |
| `ProviderRateLimitedError`    | `RATE_LIMITED`  | される    |
| `ProviderServerError`         | `SERVER_ERROR`  | される    |
| `SchemaViolation`             | `PERMANENT`     | されない  |
| 応答の対応不一致（上記手順7） | `PERMANENT`     | されない  |
| その他の`ProviderUnavailable` | `PERMANENT`     | されない  |

注釈コメントの長さ超過は**この表に現れない**。Issue #121 以降、上限超過は
`SchemaViolation` ではなく切り詰めになったため、そもそも失敗として分類されない
（前掲「上限を超えた注釈コメントは切り詰める」）。

「範囲外score」はこの表に現れない -- `ai_grading.GradingOutput`のPydantic
バリデーション（`score <= max_score`、両方とも`>= 0`）が構造化出力のパース時点
（provider adapter内部）で`SchemaViolation`として弾くため、`GradingJobProcessor`
が改めて数値レンジをチェックする必要が無い。`error_message`にはprovider例外の
生メッセージを含めない（request/response本文（答案本文を含み得る）を含み得る
ため、AGENTS.md「Security」）。schema 違反のときだけ、**フィールドパスと
pydantic の種別コード**（値ではない）が `describe_schema_violation` 経由で
`ProviderAttempt.detail` に載る（Issue #121。前掲）。

### 同期の回答欄検出は、その場で短く再試行する（Issue #304）

429 は一時的なレート制限であり、登録画面の「回答欄を自動検出」は利用者が押した
1回の操作でそれに当たると失敗表示になっていた。採点キュー側は Issue #153 で
`retry_policy.RetryPolicy` による backoff と `Retry-After` の尊重を決めていたが、
同期の検出だけがその外にあった。検出アダプタ
`adapters.answer_area_detection.detector` は同じ `RetryPolicy` を使い、
`ProviderRateLimitedError`（429）だけを再試行する。独自の backoff は作らない。

| 決めたこと         | 値                                   | 理由                                                                                                   |
| ------------------ | ------------------------------------ | ------------------------------------------------------------------------------------------------------ |
| 全体の試行回数     | 3（初回 + 最大2回）                  | 実測の検出は成功時13〜21秒。利用者を待たせ続けず、瞬間的な混雑を吸収するのに十分な回数。               |
| 合計待ち時間の上限 | 20秒                                 | 押した人が画面を見ている。待ちがこれを超えるなら、その場で待つより「待って押し直す」を伝える方がよい。 |
| 初回 backoff       | 4.0秒（等分割 jitter で実待ち2.0秒） | `RetryPolicy` の `rate_limited_*` スケジュール。以後 ×2・上限16秒（実待ち8.0秒）。                     |
| `Retry-After`      | あれば必ず尊重                       | Issue #153 と同じ決定。ただし上限を超える値は待たずに諦める。                                          |

待ち時間の上限は「名目のスケジュール」だけでなく**実際に待った合計**でも見る。
`Retry-After` は名目 delay を置き換えるので、複数回の `Retry-After` が積み上がると
名目の予算を超えうるためである。タイムアウト（`ProviderTimeoutError`）と5xxは
再試行しない: 検出は全ページを1回で運ぶ300秒の呼び出しで、タイムアウトを
やり直すと最悪ケースを二度払うことになる。

再試行を使い切った 429 は登録APIで 503 のまま返す。応答には解析済みの
`Retry-After` ヘッダと、本文の `retry_after_seconds` が載る（取れなければ
`null`。ヘッダも付けない）。画面はこの値だけを使い「約N秒待ってから
もう一度」と案内する。provider の英語文字列は表示しない
（単一ソースは `desktop/src/renderer/core/action-requirements.ts`）。

### provider requestで全rubric意味論を保持する

`GradingRequest.rubric_text`は当初、各criterionの`description`と
`max_points`のみを結合した文字列だった。登録済みcriterion `id`（応答の
`criteria[].id`をrubricへマッピングし直すために必須）と、設問の
`scoring_method`（`ScoringMethod.ADDITIVE`/`SUBTRACTIVE`。加算式と減点式を
providerが区別するために必須）のどちらも欠けていた -- 実providerが接続
された場合、outcomeをrubricへ確実にマッピングできず、減点式採点を加算式と
取り違えるおそれがあった（コードレビュー指摘）。

修正: `jobs.grading_processor.build_rubric_prompt`が「採点方式:
加算方式/減点方式」の1行と、criterionごとの1行を生成する。

> **2026-09-09 更新（Issue #117）**: この行は当初
> `- id=<criterion id>: <description>(配点<max_points>点)` だった。現在は
> `<番号>. <description>(配点<max_points>点)` であり、登録済み`id`は
> プロンプトに入れない。理由は次節。

### モデルに識別子を転記させない（Issue #117）

**実機（実データ × 実 Vertex AI）で採点が permanent 失敗した。** 期待した
criterion id `d4a534d8…` に対しモデルが返したのは `d4a4534d8…` で、「4」が
1つ多い。criterion idは`f"{test_id}:{number}:rubric:c{n}"`（`test_id`は
`uuid4().hex`の32文字）で**45文字**あり、それをモデルに書き写させていた。
計測は **45文字のid → 4/4で不一致、短いid → 0/4**。長さが直接の原因である。

**構造化出力では防げない。** JSON Schemaが強制できるのは応答の**形**であって、
「その形の中の文字列が入力の正確な転記であること」ではない。実際この
リポジトリは、Vertex AIの`responseJsonSchema`が形は守りながら`maxLength`を
無視した実測を既に記録している（`poc-2-ai-grading.md` §7.4）。

**「短いidにする」は採らない。** 短くしても転記は転記で、確率が下がるだけ。
決定は次の2つで、どちらも「転記させない」側に寄せてある:

1. **`questionId`をワイヤ形式から削除した。** 1回の呼び出しは1設問なので、
   エコーバックは呼び出し側が既に知っていること以上を何も証明しない。
   `GradingResponse.question_id`は送った`GradingRequest`から埋める。
   これで34文字の転記要求も消えた（Issueの報告はcriterion idだけだったが、
   同じ欠陥が`questionId`にもあった）。
2. **`criteria[].id`（自由文字列）を`criteria[].index`（1始まりの整数）に
   置き換えた。** プロンプトのrubricは`1. <description>(配点N点)`と番号だけを
   出し、`index`→登録済みidの対応は
   `domain.ai_provider.grading_response_from_result`が
   `GradingRequest.criterion_ids`（rubric_textと同じ順・同じ関数が生成）で
   解決する。さらに`adapters.ai_grading._schema.strict_ai_grading_result_schema`
   はリクエストごとにスキーマを組み、`index`に`enum: [1..N]`、`criteria`に
   `minItems`/`maxItems` = N を入れる -- 自由回答ではなく**選択問題として
   問う**（Issue #101の帰属判定と同じ手）。ただしこれは多重防御であって
   本体ではない。本体は「小さい整数は何かの転記ではない」ことのほうである。

**`index`ではなく配列の位置そのもの（idもindexも持たない）にはしなかった。**
欠落や並べ替えを静かに取り違えるため。`index`があれば手順7の集合一致判定が
欠落・重複を必ず捕まえ、「誤った採点結果を保存しない」（Issue #97）が保たれる。
範囲外の`index`は`grading_response_from_result`が`SchemaViolation`にする。

**この新しい失敗経路も診断できる**（Issue #121 の決定「どのフィールドがなぜ落ちたかを
残す」を、後から足した経路に適用し忘れない）。範囲外`index`の`SchemaViolation`は
`detail="criteria.<位置>.index: out_of_range"`を持つので、`Job.last_error`は
`[gemini SchemaViolation criteria.0.index: out_of_range]`になる。
フィールドパスはこのリポジトリ自身のリテラル、位置は整数で、provider が書いた値は
1つも混ざらない。`describe_schema_violation`（pydantic の`ValidationError`が対象）は
この経路を通らないため、`detail`を明示的に付けている。

**副次的な効果**: providerへ送るペイロードから`test_id`が消えた。
`mvp-acceptance.md`は従来「設問idとrubric criterion idが構造上`testId`を
含むため送信は不可避」と書いていたが、もう不可避ではない
（`test_no_student_identifying_data_reaches_either_provider`が禁止語に
`test_id`を追加して実測している）。

この性質は`backend/tests/test_ai_grading_identifier_echo.py`が外側から固定する
（「45文字級のidがプロンプトに現れない」を、文字数の閾値ではなく**不在**として
書いてある）。

### Confidence閾値: 3つの確信度すべてが閾値以上のときだけusable

Issue #20受入条件「Recognition ConfidenceとGrading Confidenceのどちらかが
閾値未満ならneeds_reviewにする」を実装する。`Job.usable`は次の**3つすべて**が
閾値以上のときだけ`True`になる（コードレビュー指摘: 当初の実装はrecognition
confidenceを`RecognitionSettings`の閾値ではなく`GradingSettings`の閾値と
比較しており、2つの設定値が異なる場合に誤って`usable`と判定しうる不具合が
あった）:

1. OCR pipeline自身のRecognition Confidence
   （`recognition_outcome.usable`、`RecognitionJobProcessor`が自身の
   `RecognitionSettings.confidence_threshold`で既に判定済みの値をそのまま
   再利用する -- `GradingJobProcessor`が独自に`RecognitionResult.confidence`
   を読み直して別の閾値と比較することはしない）。
2. AI grader自身のRecognition Confidence（`response.recognition_confidence`。
   後述のとおりOCRテキストを訂正した場合の、grader自身の読み取りに対する
   確信度）。`RecognitionJobProcessor.confidence_threshold`
   （新設の公開プロパティ、`RecognitionSettings`と単一の情報源を共有する）
   と比較する -- `GradingSettings`の閾値と比較しない。
3. Grading Confidence（`response.grading_confidence`、
   `GradingSettings.confidence_threshold`と比較）。

回答欄画像が丸ごと信頼できない場合（`AnswerImageStatus.NEEDS_REVIEW`）は、
`RecognitionJobProcessor`の既存の振る舞いどおり文字認識自体を試みず、採点する
文字が無いため`GradingJobProcessor`も採点を一切試みない。それ以外は
Recognition Confidenceが低くても採点そのものは試みる -- 2つ目・3つ目の数値が
実際に存在して初めて比較が意味を持つため。

閾値は`auto_scoring.jobs.grading_settings.GradingSettings`
（`RecognitionSettings`と同じ素の`dataclass`）が持つ。Recognition Confidenceと
Grading Confidenceを混同しない（簡易設計書 §10）という方針に合わせ、
`RecognitionSettings.confidence_threshold`とは別の設定値として独立させた
（同じ値を共有する保証はない -- 将来どちらかだけ調整できるようにするため）。
`0.80`は業務ルール決定書 §3 (C)の**既定値**である。Issue #81 で「固定値は決めず、
設定値のまま運用しながら都度調整する」ことが確定し、既定 0.80 は据え置かれた。
閾値がいくつであれ**閾値に基づく自動確定（人間レビューのスキップ）は実装しない**
（§3.1 C）-- `Job.usable`が制御するのは「この設問を人間が見なくてよいか」ではなく
「後続の依存設問へ進んでよいか」である。

> **この最後の一文を、画面は長らく逆に読んでいた（Issue #156）。**
> 添削レビュー画面は `succeeded` かつ `usable == false` を無条件に「要確認」
> （人を呼ぶ強調色）として描いており、実機再検証 #4 では**AI採点12件のうち11件**に
> それが立った。同じ実行の**依存エッジは0本**なので、その11件は1つも下流を
> 止めていない。**この節の契約は正しく、読み方が誤っていた。**
>
> 直したのは画面側だけで、**ここに書かれた3つの閾値判定は変えていない**
> （依存の解放条件としては正しく働いている）。画面側の規則は
> [dependency-dag-progress-view.md](./dependency-dag-progress-view.md) §1.3。
>
> なお、この11件を作っていたのはほぼ OCR 側の項（1.）である。
> `domain.ocr.overall_confidence` は**全トークンの最小値**なので、実測15件を
> トークン数順に並べると **5トークン以下は4件すべてが閾値超え、9トークン以上は
> 9件すべてが閾値未満**と、答案の長さできれいに分かれた（正誤では分かれていない）。
> **`usable` の判定そのものを見直すかどうかは、この Issue の範囲外**として
> 別途起票する。依存エッジが実際に引かれる教材が出てくるまで、この値が
> 誰かを止めることは無い。

### AI graderが訂正した認識結果を保持する

`AIProviderContract`（PoC 2）は、マルチモーダルなproviderが与えられたOCR
テキストを訂正して返すことを明示的に許容する
（`test_grade_preserves_the_recognized_text`）。当初の実装はこれを
`GradingRequest`構築後に一切参照せず、`response.recognition_text`/
`response.recognition_confidence`を破棄していた -- レビュー担当者はAIが
実際に採点した文字列を確認できず、graderが低いRecognition Confidenceを
報告している場合でも（元のOCR結果が高Confidenceであれば）`usable`になり
得た（コードレビュー指摘）。

修正: 採点成功時に、graderの読み取り結果を2つ目の`RecognitionResult`
（`source=ai`、id `grading-recognition:<job.id>`。OCR pipeline自身の結果
`recognition:<job.id>`とは別行）として永続化し、その`confidence`を上記の
usable判定へ組み込む。簡易設計書 §16.5の「AI認識文字」がレビューUI上
2つの独立した項目（OCR結果とAI採点結果）になり得ることに対応する。

前提設問context（後述）の`recognized_text`は、履歴の中で最も新しいAI行
（`_latest_preferring_human`。人間確定行があればそちらを優先）を採用するため、
前提設問が採点済みであればgraderが訂正した読み取りが渡る -- 実際に採点で
使われた文字列の方が、採点前の生OCR結果より前提として正確なため。

### `prompt_text`のプレースホルダ（未解決事項の記録）

`GradingRequest.prompt_text`（設問文）は非空白文字列必須だが（PoC 2時点の
`__post_init__`不変条件）、MVPの`Question`ドメインモデル（Issue #11）は
問題文抽出パイプラインをまだ持たない -- `docs/dependency-graph.md`の
`QuestionInfo.prompt_text`が同じ理由で空文字既定値になっているのと同じ未解決
事項である（「PDFからの問題文抽出パイプラインが実装され次第、そちらを既定入力
に差し替え」）。

本Issueはこれを解決しない（別Issueのスコープ）。代わりに、設問文を捏造せず、
`prompt_text`を「設問「{number}」の解答を、模範解答と採点基準に基づいて採点
してください。」という設問番号のみを含む正直な指示文に留める
（`jobs.grading_processor._prompt_text_for`）。実際の採点材料
（`model_answer`・`rubric_text`）は省略せずそのままproviderへ渡る。将来、
問題文抽出/入力の仕組み（Issue #26の`overrides`と同種の仕組み、または新しい
永続フィールド）が実装されたら、その値に差し替える。

### 前提設問context: 業務ルール §4.3 が許可する情報だけを渡す

業務ルール決定書 §4.3は依存元設問から依存先設問の採点へ引き継いでよい情報を
次に限定する: 確定した（人間承認済み、または高Confidenceの）OCRテキスト、
criterion結果と最終得点。禁止する情報: 依存元の答案画像そのもの、依存元のAI
コメント文・自由文の判定根拠、生徒識別情報、確定DAGに無い設問の情報。

`auto_scoring.domain.grading_context`（新規、純粋domain関数のみ）が
`DependencyGraph`（Issue #26）のedgeと、呼び出し側が解決済みの前提結果
（`PrerequisiteSource`）から、`ai_provider.PrerequisiteAnswer`のタプルを
組み立てる。`PrerequisiteAnswer`は`recognized_text`/`score`+`max_score`/
`criteria`（`domain.models.CriterionResult`、rationaleを持たない --
§4.3が除外する「自由文の判定根拠」を構造的に持ち込めない）のみを持ち、
画像・コメント・生徒識別情報のフィールドは存在しない。`graph.edges`に
無い設問はそもそも走査対象にならないため、確定DAGに無い設問の情報が
混入することは構造的に無い。

`provides`が要求するデータを呼び出し側の`sources`が持たない場合は
`MissingPrerequisiteContextError`を送出し、値を捏造しない
（AGENTS.md「Verification」）。DAGスケジューリング（Issue #18/#26）が
前提未usableな依存先Questionの`Job`を`BLOCKED`のまま留めるため
（`domain.job_scheduling.evaluate_readiness`）、この例外は通常経路では
発生しない -- `GradingJobProcessor`はこれを`FAILED`(`PERMANENT`)として扱う。

**未対応の項目（記録）**: §4.3は「条件分岐型のとき、分岐の結果として選択された
依存先の採点基準・模範解答の枝」と「依存元設問の模範解答（テストプロファイル
由来）」も渡してよいとするが、Issue #26が確定した
`DependencyProvision`（`recognized_text`/`score`/`criterion_result`のみ）には
対応する値が無い。本Issueは「#26のedge定義に従う」よう指示されているため、
`DependencyProvision`の拡張（新しい値の追加とDBトリガーの更新、
`migrations/versions/0003_dependency_graph.py`の`_KNOWN_DEPENDENCY_PROVISIONS_SQL`
参照）は本Issueのスコープ外とし、将来Issue #26の後続作業として記録するに
留める。

前提未完了（依存元Questionの`Job`が`usable`に達していない）の間は、依存先
Questionの`Job`自体が`BLOCKED`のまま`JobQueueService`のワーカーに一度も
ディスパッチされないため、`AIProvider.grade()`は呼ばれない -- Issue #20
追加受入条件「前提未完了では依存QuestionのAIProviderが呼ばれない」は
Issue #18/#26が既に実装したDAGスケジューリングでそのまま満たされる
（`backend/tests/test_grading_processor.py`の
`test_dependent_question_job_is_blocked_until_prerequisite_is_usable`で確認）。

### 添削資料の誤答カタログを採点プロンプトの文脈に載せる（Issue #106）

添削資料（Excel）は、採点基準 PDF が持たない情報 -- **誤答パターン → 減点量 → 赤入れ案** --
を持つ唯一の登録資料である（`grading-material-structure.md` §5.3）。効くのは点数ではなく
**コメント生成**であり、Issue #103 はこれを意図的に読まずに閉じた。本 Issue が読む側を作った。

**渡し方は「文脈」であって「規則」ではない。** 読み取ったカタログは
`GradingRequest.error_catalog` に載り、`adapters.ai_grading._prompt` が
`ERROR_CATALOG_HEADING` の下に並べる。見出しは 3 つのことを明示する:

1. **rubric が上位である。** カタログの行は上書きしない
2. 行は**別の設問・別の回**のものでありうる（各行は自分の 問題番号 / 回数 を持つ）
3. **ここに書かれた減点量は、この答案の点数を決めない**

これは飾りではない。カタログは人が人に向けて書いた散文であり、「適宜減点」「部分点10点なし」と
いった行を素の材料として渡せば、モデルにはそれを規則として適用する理由がある。
**AI の出力をカタログで機械的に上書きすることはしない**（確定は人の仕事・簡易設計書 §25.2）。

**設問で絞り込まない。** 実測でカタログは 1 ファイル 2〜6 行・全 7 教科で 27 行しかない。
一方カタログの 問題番号 は「問1」「大問1-問1(1)」「5」と表記が揃わず、登録済み設問番号との
文字列照合は**綴りのずれで黙って 0 件に落ちる**。プロンプトが少し長くなるほうが安い。
全文を送ってよいことは業務ルール §2 (2) の「資料側は文書全体を送ってよい」による。

**空のときは節ごと出さない。** 添削資料を持たないテストのほうが多く、そのすべてが
「無い資料」を宣言するプロンプトを送ることになってはならない。
`build_grading_user_content` はカタログが空なら**本 Issue 以前と 1 バイトも変わらない**文字列を
返す（`tests/test_error_catalog_prompt.py`)。この分岐は同ファイルで**変異させて赤くなることを
確認済み**（守りを外す／条件を反転する／見出しを空にする、の 3 通り）。

**読めなかったことは空の結果にしない。** 列構成が想定と違うファイルは
`ErrorCatalogUnreadable` になり、`adapters.excel_error_catalog.annotation_resource_catalog`
が理由付きで WARNING を出して採点は続く（添削資料は任意入力・業務ルール §2 (18)）。
区別されるのは (a) 未登録 (b) Word しか無い (c) 登録済みだが列を解釈できない、の 3 状態で、
**(c) を (a) と同じ見た目にしない**ことが本 Issue の主眼である。
**画面へ出すのは Issue #209**（現状は WARNING ログのみ）。

**永続化していない。** 採点のたびに Excel を読み直す。人が直した内容が残る形は Issue #209。

読み取り側の実測（7 教科 / 27 行 / 減点量は 4 教科・17 行にしか無い）と、Word を対象外に
した代償（**Word のみを持つ 4 教科ではカタログが 1 件も得られない**、Issue #208）は
`grading-material-structure.md` §5.4 に記録した。

### GradeResultのAI追跡情報とcontextの記録

`GradeResult`（`domain/models.py`）に以下を追加した
（`migrations/versions/0012_grade_result_ai_metadata.py`）:

- `comment`: AIの総評コメント（簡易設計書 §16.5「コメント」）。
- `provider`/`model`/`prompt_version`: AI再現性の3つ組（Issue #20受入条件
  「provider/model/prompt versionが追跡でき」）。3つ together か、3つとも
  `NULL`かのどちらかのみ許容する -- 人間確定行はこの3つを持たない。
- `dependency_graph_version`: 採点時点で有効だった確定`DependencyGraph`の
  バージョン（`JobRow.dependency_graph_version`と同じ理由、Issue #26）。
- `context`: どの前提`RecognitionResult`/`GradeResult`行を実際に読んで
  この採点を行ったか（`question_id`/`recognition_result_id`/
  `grade_result_id`のJSON配列）。

Issue #20追加受入条件「使用したgraph versionと前提result versionをGradeResult
へ記録し、前提が更新された場合は古い下流結果を再利用しない」は、
`GradeResult`（`RecognitionResult`と同じく追記のみ）の性質と`Job.SUCCEEDED`が
終端状態であること（`domain.models._JOB_TRANSITIONS`）から成立する: 前提が
人間レビュー等で更新された後の再採点は、必ず**新しいJob**（新しい`job.id`）を
必要とし、その新しいJobの`GradingJobProcessor.process()`は前提の**最新**の
結果を読んで新しい`GradeResult`行（新しい`id`、異なる`context`/
`dependency_graph_version`を持ちうる）を作る -- 古い行は書き換えられず、
2つの行は`context`を見比べれば区別できる。「前提が更新された後に自動で
再採点する」トリガー機構自体（人間レビューAPIからの`Job`再発行）は、本Issueが
対象外とする人間レビュー操作の一部であり、後続Issueで扱う。

### セキュリティ

- providerへ送る`GradingRequest`は当該設問1問分の情報のみ（プロンプト文・
  設問1問分の答案画像・OCRテキスト・模範解答・rubric・配点・前提設問context）
  で構成し、生徒識別情報（`student_label`等）やテスト全体・他設問の答案は
  一切含めない（業務ルール §2 (2)、§4.3）。
- 前提設問contextは§4.3が許可する範囲に構造的に限定される（前節）。
- APIキー・画像バイト列・答案本文・provider生応答はログに出さない
  （`error_message`はカテゴリ名のみを含む固定文言、`RecognitionJobProcessor`
  と同じパターン）。

## 検証

- `backend/tests/test_ai_grading_identifier_echo.py`: providerへ送るテキストに
  `question_id`もcriterion idも現れないこと、応答スキーマの`index`が
  `enum: [1..N]`で`criteria`が丁度N件であること（Issue #117）。実際に失敗した
  34/45文字のidをそのまま組み立てて確かめる。
- `backend/tests/test_ai_provider_contract.py`: `ProviderTimeoutError`等の
  新しい例外階層、`PrerequisiteAnswer`のバリデーション（provides要求データの
  必須化、空白ocr_textの許容）、`UnconfiguredAIProvider`のcontract相当テスト。
- `backend/tests/test_grading_context.py`: `build_prerequisite_context`/
  `build_context_entries`のunit test（各provisionの受け渡し、確定DAGに無い
  設問が混入しないこと、不足時に捏造せず例外を送出すること）。
- `backend/tests/test_grading_processor.py`: `GradingJobProcessor`を
  スクリプト可能なfake `OCRProvider`/`AIProvider`＋実SQLite＋実
  `LocalFileStore`で検証 -- 正常系（GradeResult/Annotation永続化・
  再現性メタデータ）、schema不正、対応不一致、timeout/rate limit/5xx分類、
  rubricの番号付けとcriterion idが別々に運ばれること（Issue #117）、
  低Recognition/低Grading Confidenceそれぞれのneeds_review化、model
  answer/rubric未登録時の`PERMANENT`失敗、クラッシュ後の再処理で二重に
  providerを呼ばないこと、前提設問contextの実際の組み立てと`GradeResult.
context`への記録、依存先Jobが前提未完了の間`BLOCKED`のままであること。
- `backend/tests/test_domain_models.py`: `GradeResult`の新フィールド
  （comment長さ上限、AI再現性3つ組の全部/無しのみ許容、
  `dependency_graph_version`の正値制約、`GradeResultContextEntry`の
  重複question_id拒否）のunit test。
- `backend/tests/test_migrations.py`（既存ファイルの一部）:
  `0012_grade_result_ai_metadata`のhead revision反映確認。
- `backend/tests/test_grading_availability.py`（Issue #97）: `build_ai_provider`
  の2つの失敗経路（設定不足・想定外例外）と、そのどちらでも資格情報の値が
  `reason`へ出ないこと、`GET /grading/availability`の応答と認証要求。ホストの
  `codex`/ADC の有無は両方とも注入する。
- `backend/tests/test_sidecar.py`（Issue #97）: 認証情報の無いホストでも
  `run()`が起動し、環境を読む場所が composition root であること。
- 実AIサービスを呼ぶテストはこのリポジトリに1つも無い。Issue #20 時点では
  同梱アダプタが`NullAIProvider`だけだったためで、実アダプタが揃った今も
  同じである -- 各アダプタの contract test は`httpx.MockTransport`と偽の
  資格情報で書き、live 疎通は`docs/poc-2-ai-grading.md`の probe command で
  手元から行う（結果は §7.4）。
