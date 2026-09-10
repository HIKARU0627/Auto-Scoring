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

`/settings/api-keys` は利用者自身の API キーを扱う。`GET` / `PUT {slot_id}` /
`DELETE {slot_id}` / `POST {slot_id}/verify` の 4 本で、いずれも他の保護
エンドポイントと同じく Bearer トークンを要求する。

**どの応答にもキーは載らない。** 保存済みかどうか・どこから読んだか
（`credential_store` / `environment` / `none`）・どのモデルを使うか・
どこでキーを発行するかだけを返す。保存直後の応答にも載らない。画面が
表示できない値は、スクリーンショットからも問い合わせのやり取りからも
漏れない。

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

重ねる規則は環境ごとに優先順位が違う。API キーは資格情報ストアが勝ち、
`AUTO_SCORING_AI_GRADING_TRANSPORT` は環境変数が勝つ。理由と全体像は
[`windows-distribution.md`](./windows-distribution.md) §9.1。

## 6. テスト

| レイヤ  | テスト                                                                | 対象                                                                                                                                   |
| ------- | --------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| Python  | `backend/tests/test_api.py`                                           | `/healthz` は無認証 200、`/score` は無トークン/誤トークンで 401、正トークンで 200                                                      |
| Python  | `backend/tests/test_sidecar.py`                                       | ポート 0 → 空きポート、占有ポート → フォールバック、ログのトークン秘匿、ハンドシェイク、`run()` が loopback で bind                    |
| Python  | `backend/tests/test_openapi_schema.py`                                | コミット済み schema と生成結果の一致、security 設定                                                                                    |
| Flutter | `app/test/sidecar_api_client_test.dart`（tag: `sidecar`）             | 実サイドカーを起動し health check・保護 API（正トークン 200 / 誤トークン 401）・未起動時 `unavailable`・材料の役割が wire 名で渡ること |
| Flutter | `app/test/sidecar_supervisor_test.dart`                               | プロセス監督の状態遷移全部（`SidecarPlatform` を fake 化。時計も fake なので起動 timeout も一瞬で検証）                                |
| Flutter | `app/test/sidecar_supervisor_integration_test.dart`（tag: `sidecar`） | 実サイドカーに対して動的ポート・handshake 削除・通常終了・crash からの再起動・二重起動拒否                                             |

| Python | `backend/tests/test_credentials.py` | 資格情報ストアの読み書き、バックエンドが無い環境での縮退、実効 environment の重ね方、疎通確認の 5 通りの結果 |
| Python | `backend/tests/test_api_key_settings.py` | 設定エンドポイント。値を返さないこと、保存したキーがログから消えること（変異で確認）、キー未設定でも採点以外が動くこと |
| Flutter | `app/test/api_key_tab_test.dart` | 設定画面の「API キー」タブ。値を再表示しないこと、出どころの表示、疎通結果の出し分け、保存後の再起動導線 |

`flutter test -x sidecar` で実サイドカー起動テストを除外できる（`uv` 不要の環境向け）。
