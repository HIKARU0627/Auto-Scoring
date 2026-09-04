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

親プロセス（将来の Flutter プロセス監視。本 Issue では**対象外**）へ `host` / `port` /
`token` を渡す方法:

- 必須の `--handshake-file <path>` で、指定ファイルへ `{"host","port","token"}` の JSON を 1 行書く。

トークンはハンドシェイク経路にのみ書き出す。アプリケーションログには
`_RedactingFilter` が `***` へ置換して出さず、標準出力にも書かない（`install_log_redaction`）。
uvicorn access ログはヘッダを出力しないため、通常経路でトークンが載ることはない。
フィルタは多層防御。

未決事項: プロセス監視実装時に、ファイル経由と fd 継承のどちらを本番採用するか。
`app-data` 配下の権限を絞った一時ファイルを第一候補とする。Windows 配布 Issue で確定。

## 4. API 契約（OpenAPI → Dart 生成）

- 正本は FastAPI が生成する OpenAPI schema。`backend/openapi/openapi.json` に
  決定的な整形（`sort_keys`・2 space・末尾改行）でコミットする。
- Dart クライアントは `openapi-generator` の `dart-dio` で生成し、
  `app/packages/auto_scoring_api/`（path 依存パッケージ）としてコミットする。
  built_value のシリアライザは `build_runner` で生成し `.g.dart` もコミットする。
- 生成物は手で編集しない。手書き DTO は置かない。
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

## 5. テスト

| レイヤ  | テスト                                                    | 対象                                                                                                                |
| ------- | --------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| Python  | `backend/tests/test_api.py`                               | `/healthz` は無認証 200、`/score` は無トークン/誤トークンで 401、正トークンで 200                                   |
| Python  | `backend/tests/test_sidecar.py`                           | ポート 0 → 空きポート、占有ポート → フォールバック、ログのトークン秘匿、ハンドシェイク、`run()` が loopback で bind |
| Python  | `backend/tests/test_openapi_schema.py`                    | コミット済み schema と生成結果の一致、security 設定                                                                 |
| Flutter | `app/test/sidecar_api_client_test.dart`（tag: `sidecar`） | 実サイドカーを起動し health check・保護 API（正トークン 200 / 誤トークン 401）・未起動時 `unavailable`              |

`flutter test -x sidecar` で実サイドカー起動テストを除外できる（`uv` 不要の環境向け）。
