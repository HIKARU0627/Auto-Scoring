# サイドカーAPI基盤（認証・ポート・契約）

GitHub Issue #10（親: #3）で実装した、Flutter と Python サイドカー間のローカル
通信基盤の決定事項。簡易設計書 §21・技術スタック決定書 §1.1–§1.2 を具体化する。
食い違う場合は本書を優先し、上位ドキュメントも同じ PR で更新する。

## 1. 待受アドレスとポート

| 項目           | 決定                                                                                                         |
| -------------- | ------------------------------------------------------------------------------------------------------------ |
| バインド       | `127.0.0.1` 固定（`auto_scoring.api.sidecar.LOOPBACK`）。LAN インターフェースには出さない                    |
| ポート         | 既定は動的取得（`--port 0`）。`resolve_port` が空きポートを 1 つ選ぶ                                         |
| ポート競合時   | 要求ポートが bind できなければ、失敗させず空きポートへフォールバックする                                     |
| 競合の残余risk | `resolve_port` の bind 試行と uvicorn の bind の間に TOCTOU の隙間がある。単一利用者のローカル用途として許容 |

## 2. 認証（起動時トークン）

- 起動ごとに `secrets.token_urlsafe(32)`（256bit）でトークンを生成する。
  外部指定による固定トークンへの上書きは許可しない。
- `GET /healthz` 以外の全エンドポイントは `Authorization: Bearer <token>` を要求する
  （`auto_scoring.api.auth.require_token`）。一致比較は `hmac.compare_digest`。
- 不一致・欠落は `401` + `WWW-Authenticate: Bearer`。
- OpenAPI には `HTTPBearer` security scheme として出力され、生成クライアントにも反映される。

## 3. ハンドシェイク（接続情報の受け渡し）

親プロセス（Flutter の `SidecarSupervisor`。実装は Issue #24）へ `host` / `port` /
`token` を渡す方法:

- `--handshake-file <path>` で、指定ファイルへ `{"host","port","token"}` の JSON を 1 行書く。
- 書くのは **`create_app()` が成功したあと**。bind 直後に書いていた頃は、
  ロック失敗・マイグレーション失敗のたびに「誰も応答しない host:port」を書いた
  ファイルが残り、読む側が起動遅延と区別できなかった（Issue #24）。

トークンはハンドシェイク経路にのみ書き出す。アプリケーションログには
`_RedactingFilter` が `***` へ置換して出さず、標準出力にも書かない（`install_log_redaction`）。
uvicorn access ログはヘッダを出力しないため、通常経路でトークンが載ることはない。
フィルタは多層防御。

**確定（Issue #24）**: ファイル経由。fd 継承は不採用 — dart:io には Windows で
追加のハンドルを子へ継承させる公式手段がない。置き場所は `app-data` 配下ではなく
`%TEMP%` 配下の 1 起動ごとのランダム名ディレクトリで、Flutter がトークンを
読んだ直後に削除する。理由と検証は
[`windows-distribution.md`](./windows-distribution.md) §4。

読む側の成功条件は「ファイルが存在する」ではなく「JSON として parse でき
`host`/`port`/`token` が揃っている」こと。ファイルは Flutter が空で作り、
サイドカーがあとから書くため、その間は空・書きかけが読める（同 §4.1）。

### 3.1 親プロセス監視（`--parent-pid`、Issue #211）

ハンドシェイクの逆向き — 親が**死んだ**ことをサイドカーが知るための経路。

- `--parent-pid <PID>` を渡すと、サイドカーはその PID のプロセスが終わってから
  **5 秒以内に自分も終わる**（exit code 4）。AI 呼び出しでブロックしている最中でも
  終わる（監視は daemon スレッド、終了は `os._exit`）。
- **既定は無効。** 渡さなければ監視スレッドは 1 つも動かない。pytest と開発時の
  単独起動には親となる supervisor がおらず、既定オンにすると
  **pytest の実行器を親と見なして自殺する**。
- 渡すのは supervisor だけ。API ではないので OpenAPI schema には現れない。
- `0` 以下は POSIX のシグナル API ではプロセス**グループ**の指定になるため、
  引数の時点で拒否する。

生存判定は PID だけでは行わない（PID は再利用される）。PID とプロセス開始時刻の
組で見て、同じ PID を別プロセスが取った場合は「親は終わった」と判定する。判定に
必要な情報が OS から得られない場合は「生きている」と答える — 動いているサイドカーを
誤って殺す損失の方が大きく、孤児は `app-data` のロックが受け止めるため。

**このロックは最後の砦として残す**（[`windows-distribution.md`](./windows-distribution.md)
§5.3.1・§5.4）。監視はロックの置き換えではない。

## 4. API 契約（OpenAPI → Dart 生成）

- 正本は FastAPI が生成する OpenAPI schema。`backend/openapi/openapi.json` に
  決定的な整形（`sort_keys`・2 space・末尾改行）でコミットする。
- Dart クライアントは `openapi-generator` の `dart-dio` で生成し、
  `app/packages/auto_scoring_api/`（path 依存パッケージ）としてコミットする。
  built_value のシリアライザは `build_runner` で生成し `.g.dart` もコミットする。
- 生成物は手で編集しない。手書き DTO は置かない。
- **生成物を迂回して値を手で組む場所では、必ず生成クライアントのシリアライザを通す。**
  multipart の繰り返しフォーム項目（`POST /tests` の `material_roles`）のように、
  生成クライアントが `BuiltList<String>` としか型付けできない引数がある。そこへ Dart の
  列挙子名（`MaterialRole.annotationResource.name` = `annotationResource`）を入れると、
  wire 名（`annotation_resource`）を持つ `MaterialRole.serializer` を通らないまま送られる。
  型検査もリンタも通り、テストも全て緑のまま、実行時だけ 422 になる
  （Issue #139: 実資料の全教科に 添削資料 があるため、画面からどの教科も取り込めなかった）。
  対応表を手で書き足さず `standardSerializers.serializeWith(MaterialRole.serializer, role)`
  で生成クライアント側の対応表を使う。二重に持つと次に役割が増えたときまた割れる。
- Flutter 側の単一境界は `app/lib/api/sidecar_api_client.dart`（`SidecarApiClient`）。
  生成クライアントを包み、トークン付与（dio interceptor）・timeout・`CancelToken`・
  `DioException` → `SidecarApiException` 変換を担う。`core` / `features` はこの境界だけを使う。
- 接続先は `http://127.0.0.1:<port>` だけを許可し、トークンは保護 API にだけ付与する。
  公開例外は固定メッセージへ変換し、トークンや接続先を含めない。

### 生成コマンド

| コマンド                    | 内容                                                                                            |
| --------------------------- | ----------------------------------------------------------------------------------------------- |
| `pnpm run openapi:export`   | FastAPI から `backend/openapi/openapi.json` を書き出す                                          |
| `pnpm run openapi:generate` | export → `dart-dio` 生成 → `build_runner` → `dart format`                                       |
| `pnpm run openapi:check`    | `generate` 実行後、`backend/openapi` と `app/packages/auto_scoring_api` に git 差分があれば失敗 |

`openapi:check` は `pnpm run check` と CI（`.github/workflows/ci.yml` の "OpenAPI contract"
ステップ）で実行する。`uv` / `dart` / Java（openapi-generator 用）が PATH に必要なため、
高速な git hook（`check:pre-commit` / `check:pre-push`）には含めない
（`docs/quality-gates.md`「Adding heavier gates」）。

生成パッケージの `pubspec.lock` は、公開ライブラリではなくリポジトリ内のコード生成ツールとして
再現性を優先してコミットする。生成する JSON とマニフェストの改行も LF に固定する。
差分が出た場合は `pnpm run openapi:generate` で再生成してコミットする。

## 5. 設定エンドポイントと、資格情報の見える範囲（Issue #96）

`/settings/api-keys` は利用者自身の provider 設定を扱う。`GET` /
`PUT {slot_id}` / `DELETE {slot_id}` / `POST {slot_id}/verify` に加え、
利用順を保存・削除する `PUT` / `DELETE /settings/transport-order` がある
（Issue #386）。いずれも他の保護エンドポイントと同じく Bearer トークンを
要求する。

`PUT {slot_id}` の body は `{"values": {"<環境変数名>": "値"}}` で、キー
（OpenRouter / OpenAI）と、秘密でない設定（モデル・GCP プロジェクト・
リージョン）を同じ形で受ける。空文字または `null` はその設定の保存値を
消し、環境変数または既定に戻す。`{"value": "..."}` は Issue #96 の旧クライ
アント互換の省略形として残してある。

**どの応答にもキーは載らない。** 保存済みかどうか・どこから読んだか
（`credential_store` / `environment` / `none`）・どのモデルを使うか・
どこでキーを発行するかだけを返す。保存直後の応答にも載らない。画面が
表示できない値は、スクリーンショットからも問い合わせのやり取りからも
漏れない。**秘密でない設定は逆に必ず返す**: 現在のモデルや GCP プロジェ
クトを見せない画面は使えない。

Vertex AI（Gemini）は API キーを持たない。認証は ADC で、画面が持つのは
モデル・`AUTO_SCORING_VERTEX_PROJECT`・`AUTO_SCORING_VERTEX_LOCATION` の
3 つだけである（`AUTO_SCORING_GEMINI_API_KEY` の経路は存在しない）。
Codex app-server もキーを持たず、`codex` 実行ファイルの有無だけを出す。

**保存したキーは、その場でログ秘匿の対象に入る。** 起動時に組んだ
`configuration_secrets` はプロセス開始時の設定しか知らないので、あとから
入力されたキーは `api.secret_redaction.SecretRegistry` に足す。フィルタは
レコードごとに registry を読むので、追加は即座に効く。

### 5.1 実効 environment を重ねる場所

サイドカーは起動時に、資格情報ストアの値を `os.environ` の**コピー**へ
重ねた 1 つの dict を作り、4 つの provider ファクトリ（採点・配点抽出・
回答欄検出・OCR）と取込の役割判定へ渡す
（`adapters.credentials.api_keys.ApiKeySettings.effective_environment`）。

**`os.environ` 自体は書き換えない。** 書き換えると、このプロセスが起こす
子プロセスがそのキーを継承する。`codex app-server` transport は
`subprocess.Popen(..., env=_minimal_environment())` で最小限の環境を明示的に
組んで渡しており、そこへ OpenRouter のキーが混ざる理由は無い。コピーに
重ねる方式なら、この性質が実装の副作用ではなく設計として保たれる
（`test_sidecar.py::test_run_layers_a_stored_key_over_the_environment_without_writing_to_it`）。

重ねる規則は変数の種類で違う。API キーと読み書きできる設定（モデル・
GCP プロジェクト・リージョン）は資格情報ストアが勝ち、
`AUTO_SCORING_AI_GRADING_TRANSPORT` は画面で保存した順番が勝つ（無ければ
環境変数、次に保存済みキーから導出）。Issue #96 は開発機の Vertex 優先順を
守るために環境変数を最優先にしていたが、Issue #386 で画面から並べ替えられる
ようにしたためこの一段だけ改めた。画面の「保存した順番を削除（環境変数に
戻す）」で元の挙動に戻せる。理由と全体像は
[`windows-distribution.md`](./windows-distribution.md) §9.1。

## 6. テスト

| レイヤ  | テスト                                                                | 対象                                                                                                                                   |
| ------- | --------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| Python  | `backend/tests/test_api.py`                                           | `/healthz` は無認証 200、`/score` は無トークン/誤トークンで 401、正トークンで 200                                                      |
| Python  | `backend/tests/test_sidecar.py`                                       | ポート 0 → 空きポート、占有ポート → フォールバック、ログのトークン秘匿、ハンドシェイク、`run()` が loopback で bind                    |
| Python  | `backend/tests/test_openapi_schema.py`                                | コミット済み schema と生成結果の一致、security 設定                                                                                    |
| Python  | `backend/tests/test_page_image_api.py`                                | §7 のページ画像・ページ幾何。幾何が `PageGeometry` と同値、画素寸法 = 表示ページ × scale、許容外 scale の拒否、ETag のキーと無効化     |
| Flutter | `app/test/sidecar_api_client_test.dart`（tag: `sidecar`）             | 実サイドカーを起動し health check・保護 API（正トークン 200 / 誤トークン 401）・未起動時 `unavailable`・材料の役割が wire 名で渡ること |
| Flutter | `app/test/sidecar_supervisor_test.dart`                               | プロセス監督の状態遷移全部（`SidecarPlatform` を fake 化。時計も fake なので起動 timeout も一瞬で検証）                                |
| Flutter | `app/test/sidecar_supervisor_integration_test.dart`（tag: `sidecar`） | 実サイドカーに対して動的ポート・handshake 削除・通常終了・crash からの再起動・二重起動拒否                                             |

| Python | `backend/tests/test_credentials.py` | 資格情報ストアの読み書き、バックエンドが無い環境での縮退、実効 environment の重ね方、疎通確認の 5 通りの結果 |
| Python | `backend/tests/test_api_key_settings.py` | 設定エンドポイント。値を返さないこと、保存したキーがログから消えること（変異で確認）、キー未設定でも採点以外が動くこと |
| Flutter | `app/test/api_key_tab_test.dart` | 設定画面の「API キー」タブ。値を再表示しないこと、出どころの表示、疎通結果の出し分け、保存後の再起動導線 |

`flutter test -x sidecar` で実サイドカー起動テストを除外できる（`uv` 不要の環境向け）。

## 7. ページ画像とページ幾何（Issue #207、親 #201）

PoC 6（[`poc-6-pdf-coordinates.md`](./poc-6-pdf-coordinates.md)）が案 B を採った。
移行後の UI は**生の PDF を受け取って自分で描くのをやめ、サイドカーが pypdfium2 で
描いた画像を表示する**。採用理由は実測精度ではない（案 A も 45 測点すべて許容内）。
**同じ pdfium が raster 化と座標変換の両方を担うので、「表示するページ」の解釈が
2 つに割れる余地が構造的に無い**ことである。

| メソッド | パス                                                  | 返すもの                                             |
| -------- | ----------------------------------------------------- | ---------------------------------------------------- |
| `GET`    | `/submissions/{id}/pages`                             | `page_count` と各ページの `displayed_*` / `rotation` |
| `GET`    | `/submissions/{id}/pages/{n}/image`                   | `image/png`（`scale` 既定 2.0）                      |
| `GET`    | `/tests/{id}/answer-layout/pages`                     | 同上（回答欄エディタが描く答案用紙）                 |
| `GET`    | `/tests/{id}/answer-layout/pages/{n}/image`           | `image/png`（`scale` 既定 2.0）                      |
| `GET`    | `/tests/{id}/materials/{material_id}/pages`           | 同上（登録済み資料。PDF のみ。Word/Excel は 415）    |
| `GET`    | `/tests/{id}/materials/{material_id}/pages/{n}/image` | `image/png`（`scale` 既定 2.0）                      |

実装は `backend/src/auto_scoring/api/page_image_router.py`、
検査は `backend/tests/test_page_image_api.py`（fixture は合成 PDF 8 種）と
`backend/tests/test_material_page_api.py`。

### 7.1 正規化座標の基準は「返ってきた画像の画素寸法」ただ一つ

renderer が座標を作るときに割ってよいのは、**受け取った画像そのものの画素寸法**だけ。

```text
正規化X = クリック位置px ÷ 画像幅px
正規化Y = クリック位置py ÷ 画像高px
```

pdfium がその画素の中へ表示ページを描いた以上、この割り算がサイドカー側の座標変換と
食い違うことは定義上ありえない。

**幾何エンドポイントの値を座標計算に使わないこと。** 幾何の用途は次に限る。

| 用途       | 使う値                                 | 例                                       |
| ---------- | -------------------------------------- | ---------------------------------------- |
| レイアウト | `displayed_width` / `displayed_height` | 画像が届く前の枠取り（縦横比だけを使う） |
| ページ送り | `page_count`                           | 次ページ・前ページ、サムネイル一覧       |
| 回転の把握 | `rotation`                             | 回転済みであることの表示                 |

画像の画素寸法は `ceil(displayed_* × scale)` に**切り上げ**られる。座標を幾何から作り、
画像は別に丸められる、という形にすると、**案 B が消したはずの二重解釈を renderer 側で
作り直すことになる。** この区別は OpenAPI の description（4 本すべて）にも書いてある。

**画素寸法はどこにも重複して返さない。** Issue #207 はレスポンスヘッダか幾何側で画素
サイズも返すことを提案していたが、採らなかった。PNG は自分の寸法を持っており
（`naturalWidth` / `naturalHeight`）、renderer はそれを追加の要求なしに読める。同じ数を
2 か所に置けば、画像と食い違いうる値が 1 つ増える —— 上の規則が防ごうとしている形そのもの。
`ceil(displayed × scale)` という関係自体は
`test_page_image_api.py::test_image_pixel_size_is_the_displayed_page_times_scale` が
回転 0/90/180/270・非ゼロ原点 MediaBox・CropBox インセットで固定している。

### 7.2 幾何は座標変換と同じ `PageGeometry` から出す

router は寸法を自分で計算しない。`PdfEngine.page_geometry`（= 注釈書き出しが
`domain/pdf_geometry.py` へ渡すのと同じ値）をそのまま返す。別経路で計算した瞬間に
ずれる余地が生まれる。

`test_geometry_is_the_transforms_own_page_geometry` が同一性を固定し、
`test_the_fixture_set_can_tell_a_second_derivation_apart` が「fixture が第二の導出
（MediaBox を読む／`/Rotate` を無視する）と区別できること」自体を固定する。後者が無いと、
原点にある直立 A4 ばかりの fixture では**前者が真かつ空**になりうる。

### 7.3 `scale` はサーバ側で列挙し、黙って丸めない

許容値は **1.0 / 2.0 / 3.5**、既定 **2.0**（`ALLOWED_SCALES` / `DEFAULT_SCALE`）。
PoC 6 実測で 5.1 / 20.8 / 78.6 ms per page。任意の実数を受けると、大きな値でこの
プロセスのメモリと時間を焼ける。**許容外は 422 で拒否する。近い値へ丸めない** ——
黙って差し替えると、呼び出し側が枠取りに使った画素寸法と違う画像が返り、呼び出し側には
気づく手段が無い。

OpenAPI schema の `enum` と実際の検証は、どちらも `ALLOWED_SCALES` 1 つから作る。
なお `Literal[1.0, 2.0, 3.5]` は使えない。pydantic の literal 検証はクエリ文字列を
float へ寄せないので、`?scale=2.0` まで 422 になる（`_permitted_scale` の docstring）。

### 7.4 ETag のキーは `(文書の中身, ページ, scale)`

PoC 6 が測ったキーそのまま。文書は**バイト列の SHA-256** で識別する。パスや mtime では
ない —— `POST /tests/{id}/answer-layout` は答案用紙をその場で置き換えるので、同じ長さで
タイムスタンプ粒度内の差し替えが古いキャッシュのまま配られる。`scale` がキーに入るのは、
**scale が変われば別の画像**であって同じ画像の丸め直しではないから。
`If-None-Match` の一致は**描画の前**に判定する（304 の価値はそこにしか無い）。

### 7.5 renderer は生の PDF バイト列を受け取らない

**app-data の所有はサイドカーのまま。** 移行後の UI が受け取るのは、上のページ画像と
幾何だけである。

生の PDF を返す既存 2 本 —— `GET /submissions/{id}/source-pdf` と
`GET /tests/{id}/answer-layout/pdf` —— は**消していない**。cut-over まで Flutter アプリ
（添削レビュー画面・回答欄エディタ）が使っているためで、それが唯一の利用者である。
**cut-over 後に残る用途は無い**: 回答欄検出・配点抽出・PDF 出力はいずれも保存済み
ファイルを直接開いており、HTTP を経由しない。

**この 2 本を消すかは cut-over で判断する。追跡は Issue #201。** 専用の cut-over Issue が
切られたら、項目をそちらへ移し、両エンドポイントの description の参照先も更新すること。
後者の description には以前「Flutter が pdfrx で描くから PDF を返す」という採用理由が
書かれていたが、移行でその前提が消えた。**理由が古いまま残るのが、このリポジトリで
何度も踏んだ形である**（#111 → #138）。

### 7.6 資料の中身はページ画像で返す（Issue #415）

取り込んだ資料を別ウィンドウで見せる（`docs/test-registration.md`）ときも、**案 B の
ままページ画像を返す。** 追加したのは上の 2 本で、認証（`require_token`）・loopback
束縛・`LocalFileStore.resolve_stored_path` によるパス解決・ETag のキーは、答案ページと
**同じ実装を共有する**。新しい認証経路も公開の仕方も発明していない。

生のファイルを返さなかった理由:

- **CSP`default-src 'none'` では renderer が PDF をインライン表示できない。**
  ページ画像だけが「中身が見える」を満たす。
- **複数ページの送りが要件**（受入条件）。`PdfEngine` のページ数・ジオメトリをそのまま
  使えるページ画像が最短。
- **Word/Excel の資料は raster 化できない。** これはサーバ側で **415** を返し、renderer は
  「アプリ内でプレビューできない」と役割・ファイル名を添えて表示する（黙って空にしない）。
  生バイトを返すと、Issue #207 が消した「文書が renderer に渡る経路」を作り直すことになる。

資料の行は `GET /tests/{id}/materials`（メタ情報のみ、`api.test_registration_router`）で
引く。`{material_id}` は必ず**そのテストの行**として解決し、別テストの id を持ち込んでも
404 になる。ファイルが非 PDF のときは本文を読む前に 415 で止める。
