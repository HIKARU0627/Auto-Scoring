# 技術スタック調査・決定書

## 0. このドキュメントの位置づけ

[`simplified-design-specification.md`](./simplified-design-specification.md)
（簡易設計書）で「暫定」「要判断」とされていた技術要素について調査し、実装着手前の
**最終技術スタック**を決定する（GitHub Issue #1）。

- 簡易設計書が仕様の正本。本書は簡易設計書 §32「技術スタック」と §33「未決定事項」を
  具体化するもので、両者が食い違う場合は本書を優先し、簡易設計書側も同じ PR で更新する。
- コード・雛形は本 Issue の対象外。プロジェクト構成の実装は後続 Issue で行う。
- 「PoC 後に判断」と簡易設計書が明記している項目（OCR サービス、AI モデル）は、本書でも
  最終確定せず **PoC の判断材料**と**抽象化の境界**だけを固める。

### 0.1 確定事項（変更不可）

| 項目              | 値                |
| ----------------- | ----------------- |
| UI フレームワーク | Flutter           |
| 言語（UI 側）     | Dart              |
| デザインシステム  | Material Design 3 |

### 0.2 調査時に確認済みの前提

| 論点                                                        | 現時点の方針                               | 出典             |
| ----------------------------------------------------------- | ------------------------------------------ | ---------------- |
| 答案データ（個人情報を含む）の外部 AI/OCR クラウド API 送信 | **可**。ただし送信データは必要最小限に絞る | ユーザー確認済み |
| 初期対象 OS                                                 | Windows。macOS / Linux は将来対応          | 簡易設計書 §3    |
| アプリ形態                                                  | ローカル完結のデスクトップアプリ           | 簡易設計書 §26   |

---

## 1. 全体アーキテクチャ

簡易設計書 §21 の「Flutter + Python（FastAPI）を localhost 通信」を踏襲する。役割分担を
明示すると次のとおり。

```text
┌─────────────────────────────┐        HTTP (localhost, 127.0.0.1:<port>)
│ Flutter Desktop (Dart)      │  ───────────────────────────────────────►  ┌──────────────────────────┐
│  - UI / Material 3          │                                            │ Python サイドカー         │
│  - PDF 表示 + Annotation     │  ◄───────────────────────────────────────  │  FastAPI + Uvicorn        │
│    Overlay                  │        JSON / 画像バイナリ                   │  - PDF 解析 / 生成 (§3.1)  │
│  - レビュー操作・キー操作     │                                            │  - 画像前処理 (OpenCV)     │
│  - ジョブ進捗表示            │        子プロセスとして起動・監視・終了       │  - OCRProvider            │
│  - API キーは保持しない      │  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ►  │  - AIProvider            │
└─────────────────────────────┘                                            │  - ジョブキュー / SQLite   │
                                                                           └──────────────────────────┘
```

### 1.1 決定事項

| 論点           | 決定                                                                                                      | 根拠                                                                                |
| -------------- | --------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| プロセス構成   | Flutter アプリが Python サイドカーを**子プロセスとして起動・監視・終了**する 1 ユーザー / 1 マシン構成    | ローカル完結（§26）。常駐サービス化・Docker は運用負荷が見合わない                  |
| 通信プロトコル | HTTP/1.1 + JSON（FastAPI 標準）。ページ画像など大きなバイナリは HTTP バイナリレスポンス                   | gRPC は Dart 側の生成・ビルド負荷が大きく、単一マシン内通信では利点が薄い           |
| ポート         | 起動時に空きポートを動的取得し、Flutter へ受け渡す（固定ポートの衝突回避）                                | 複数ユーザーが同一 PC を使う教室環境を想定                                          |
| 認証           | 起動時に生成したランダムトークンを `Authorization` ヘッダで必須化。`127.0.0.1` バインドのみ               | 同一 PC の他プロセスからの無認証アクセスを防ぐ                                      |
| API キーの所在 | **Python サイドカー側のみ**が OCR/AI の API キーを保持。Flutter は一切保持しない                          | 鍵の露出面を最小化（§26）。UI はビルド成果物として配布されるため鍵を置けない        |
| DB の所有者    | **Python 側**が SQLite を単独で所有・書き込みする。Flutter は API 経由でのみ参照                          | 採点・OCR・ジョブ状態の書き込みがすべて Python 側。二重書き込み・ロック競合を避ける |
| API 契約       | FastAPI が生成する OpenAPI schema を正本とし、Dart クライアント（DTO + API 呼び出し）を**コード生成**する | 手書き DTO の乖離を防ぐ。生成コードはリポジトリにコミットしレビュー対象にする       |

### 1.2 サイドカーのライフサイクル

- Flutter 起動時にバンドル済み Python 実行ファイルを起動 →
  `GET /healthz` が通るまで待機 → スプラッシュ表示。
- Flutter 終了・クラッシュ時に子プロセスを確実に kill する（Windows は Job Object、
  将来の macOS/Linux はプロセスグループ）。Linux では未実装で、開発起動時は
  強制終了するとサイドカーが残る（[`linux-desktop-development.md`](./linux-desktop-development.md) §5.1）。
- サイドカーが異常終了したら UI にエラーを出し、再起動ボタンを提供（簡易設計書 §24）。

> 認証・動的ポート・OpenAPI → Dart 生成・接続情報の受け渡し（ハンドシェイク）の
> 実装決定は [`sidecar-api.md`](./sidecar-api.md)（GitHub Issue #10）にまとめた。
> **子プロセスの起動・監視・kill、Job Object による orphan 防止、`app-data/` の
> 格納場所、二重起動の扱い、ログとアンインストール方針は
> [`windows-distribution.md`](./windows-distribution.md)（GitHub Issue #24）で
> 確定した**（実装: `app/lib/core/sidecar_supervisor.dart`）。

---

## 2. フロントエンド（Flutter / Dart）

| 要素              | 決定                                                                                                                             | 代替案と却下理由                                                                                                                                                                          |
| ----------------- | -------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Flutter チャネル  | stable、最新安定版。バージョンは `fvm` などで固定しリポジトリに記録                                                              | beta/master は不採用（デスクトップ安定性優先）                                                                                                                                            |
| 状態管理          | **Riverpod 3.x**（配置と差し替え方針は §2.2）                                                                                    | Bloc: 記述量が多い。Provider: 新規非推奨。GetX: 過度な多機能・暗黙的挙動。Riverpod は非同期状態・キャッシュ・コンパイル時安全性で 2026 年時点の推奨                                       |
| ルーティング      | **go_router**（ルート表の置き場所は §2.2）                                                                                       | 画面数が限られ（§16）、宣言的ルーティングで十分。自前 Navigator 管理は不要                                                                                                                |
| DTO / モデル      | **OpenAPI 生成コード**（`built_value`）。**freezed は採用しない**（§2.3）                                                        | 手書きの `fromJson` は乖離・記述漏れの温床。生成コードでその目的は達しており、freezed は二重のモデル層になる                                                                              |
| HTTP クライアント | **dio**（インターセプタでトークン付与・リトライ・タイムアウト）                                                                  | 標準 `http` はインターセプタ・キャンセルが弱い                                                                                                                                            |
| PDF 表示          | **pdfrx**（pdfium ベース、寛容ライセンス）                                                                                       | Syncfusion PDF Viewer は商用ライセンス要件あり。pdfrx は Widget Overlay / ページ単位オーバーレイ / パン・ズームを阻害しないタップ領域を提供でき、§13 の「PDF + Annotation Overlay」に合致 |
| Annotation 描画   | pdfrx のページオーバーレイ上に Flutter ウィジェット（○×△・コメント・下線）を配置。座標は 0〜1 正規化で受け取りページサイズへ変換 | AI/Python に PDF 座標を直接描かせない（§12・§35-3）                                                                                                                                       |
| キーボード操作    | `Shortcuts` / `Actions` / `Focus` で §17 のショートカットを実装                                                                  | 独自キーハンドラは競合しやすい                                                                                                                                                            |
| ローカル保存      | ウィンドウ位置・最近使ったテスト等の軽量設定のみ `shared_preferences`。業務データは持たない                                      | 業務データの正本は Python 側 SQLite                                                                                                                                                       |
| Lint / Format     | `flutter analyze`（`flutter_lints` もしくは `very_good_analysis`）＋ `dart format`                                               | —                                                                                                                                                                                         |
| テスト            | `flutter_test` + `mocktail`、主要導線は `integration_test`                                                                       | —                                                                                                                                                                                         |

### 2.1 PDF 表示方式の決定

編集中の表示は **Flutter 側が pdfium で直接レンダリング**し、その上に Annotation を
ウィジェットとして重ねる（案 A）。Python がページ画像を返す方式（案 B）は帯域とズーム
品質で不利なため、**確定 PDF 出力時のみ** Python がラスタライズ／描画を担当する（§14）。

- リスク: Flutter（pdfium）と Python 側 PDF エンジンで座標系・DPI 解釈がずれる可能性。
  → **PoC 3（Issue #12）で検証済み**。Python 側を `pypdfium2`（= pdfium）に揃えたこと
  もあり、回転・CropBox 込みで 0〜1 正規化座標の往復誤差は最大 0.0005・DPI 非依存。
  [`poc-3-pdf-coordinates.md`](./poc-3-pdf-coordinates.md)。

### 2.2 Riverpod / go_router の配置（Issue #66 で確定）

上表の「Riverpod 3.x」「go_router」を実装に落とすときの置き場所を確定する。依存方向
`features → core → api`（§5）を壊さないことが制約。

| 対象                      | 置き場所                                          | 理由                                                                                                                                         |
| ------------------------- | ------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| Provider の定義           | `app/lib/core/`（型のすぐ隣）                     | `core` は「テーマ・ルーティング・DI」の層（§5）。`features` は `core` を import してよいので、どの画面からも到達できる                       |
| `appDependenciesProvider` | `core/app_dependencies.dart`                      | 差し替える値（`AppDependencies`）と同じファイルに置き、既定値＝「未接続」構成であることを 1 か所で読めるようにする                           |
| ルートのパス              | `core/app_routes.dart`（`AppRoutes`）             | 画面へ遷移するのは `features`。パスだけなら feature を import しないので `core` に置ける                                                     |
| ルート表（`GoRouter`）    | `app/lib/app_router.dart`（コンポジションルート） | ルートを組むには画面クラスを名指しする必要があり、**`core` は `features` を import できない**。`main.dart` と同じ層に置くのが唯一の解        |
| 画面の状態                | 当面は各画面の `ConsumerState`（`setState`）      | Issue #66 の範囲は「バケツリレーの解消」まで。画面内状態の Notifier 化は、その状態を複数画面で共有する必要が出た時点で行う（下記「範囲外」） |

決定の要点:

- **画面は `AppDependencies` をコンストラクタで受け取らない。**
  `ref.read(appDependenciesProvider)` で解決する。go_router のルート表はパスから画面を
  組み立てるため、コンストラクタ経由の注入はそもそも成立しない。
- **画面は provider を `initState` で1回だけ読み、結果をフィールドに持つ。**
  呼び出しのたびに読み直してはいけない。`ref` は `ConsumerState` が dispose された後に
  `StateError` を投げるため、`await` を挟んで2回読むメソッド（`_loadShell` / `_loadAll`
  のような逐次ロード）は、ユーザーが読み込み中に画面を離れると**未処理の非同期エラー**に
  なる。`SidecarApiException` の `catch` では捕まらない（Issue #66 レビュー P2）。
  1つの値に固定するのは意味的にも正しい: ある接続に対して始まった要求はその接続で
  終わるべきで、接続が差し替わった時点でコンポジションルートは
  `AppRoutes.starting` へ遷移させている。
  `await` を挟まない `ConsumerWidget`（`HomePage`）が `build` で `watch` するのは問題ない。
- **ウィジェットテストの差し替えは `ProviderScope(overrides: ...)` で行う。**
  入口は `app/test/app_harness.dart` の `pumpAppAt()`。従来の
  `SomePage(dependencies: ...)` と同じ粒度（個別の関数だけ差し替える）を保ったまま、
  ネイティブファイルピッカー（`core/pdf_file_picker.dart` の `pickPdfFileProvider`）の
  ように**コンストラクタ引数では渡せなくなったもの**も同じ仕組みで差し替えられる。
  テストが実際のルート表を通るため、画面遷移そのものも検証対象になる。
- **サイドカー異常時の復帰 UI（Issue #24）は go_router 導入後も最前面のまま。**
  `SidecarStartupOverlay` は引き続き `MaterialApp.router` の `builder` で Router 全体に
  重なる。異常検知時に `popUntil((route) => route.isFirst)` でスタックを畳んでいた処理は
  `GoRouter.go(AppRoutes.starting)` に置き換えた（`AppRoutes.starting` は画面ではなく、
  オーバーレイが覆っている間の空ルート）。回帰テストは
  `app/test/startup_gate_test.dart`。

**この Issue の範囲外（意図的に手を付けていない）:**

- 画面内状態の `Notifier` / `AsyncNotifier` 化。`PdfReviewPage` などの `setState` は
  そのまま。1 画面に閉じた状態を Riverpod へ移しても現時点で得るものが無く、UI 改良
  （#67 / #68 / #64）で画面構成そのものが変わる前にやると二度手間になる。
- サイドカーのライフサイクル（`SidecarSupervisor`）の provider 化。コンポジションルート
  が `ValueListenable` で持つ現在の形で足りている。

### 2.3 freezed を採用しない判断（Issue #66 で確定）

上表の当初の決定は「freezed + json_serializable（または OpenAPI 生成コード）」だった。
実装が進んだ結果、**OpenAPI 生成コードを採用した時点で freezed の目的は達成済み**であり、
追加する理由が無くなったため**採用しない**。

- **JSON を持つ型はすべて生成物**。`app/lib/api/` の DTO は FastAPI の OpenAPI schema から
  `built_value` ベースで生成しており（§1.1「API 契約」）、不変・`==`/`hashCode`・
  `toString`・`rebuild()`（= `copyWith` 相当）・`fromJson`/`toJson` を既に備える。
  freezed を入れると、同じデータに対して**生成モデルが 2 層**になり、両者の変換コードが
  新たな乖離の温床になる。
- **手書きモデルは少なく、かつ freezed 向きではない**。
  - `SidecarState`（`core/sidecar_supervisor.dart`）は Dart 3 の `sealed class` +
    パターンマッチで網羅性検査まで効いている。freezed の union 型が解いていた問題は
    言語機能で解決済み。
  - `SidecarConnection` / `PickedPdfFile` はフィールド 2 個の `const` クラスで、
    `copyWith` も値等価も使っていない。
  - `QuestionReviewState`（`features/pdf_review/`）は**意図的に可変**な画面内キャッシュで、
    不変データクラス化は設計に反する。
- **コストが釣り合わない**。freezed は `build_runner` + `freezed_annotation` +
  `json_serializable` と、生成ファイルの生成・コミット・鮮度チェックを品質ゲート
  （[`quality-gates.md`](./quality-gates.md)）に足すことを意味する。上記の数クラスのために
  払う額ではない。

**再検討の条件**: サイドカーに無い（＝生成 DTO で表せない）ドメインモデルを Flutter 側に
持つ必要が出て、その型に `copyWith`・値等価・JSON 永続化のうち複数が必要になったとき。

---

## 3. バックエンド（Python）

| 要素                 | 決定                                                                 | 備考                                                                                        |
| -------------------- | -------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| Python バージョン    | **3.12 以上**（3.13 可）。`.python-version` で固定                   | 3.12+ は型・エラーメッセージ・パフォーマンスが安定                                          |
| パッケージ管理       | **uv**（`pyproject.toml` + `uv.lock`）                               | pip/venv/poetry を単一ツールで置換。CI もローカルも同一ロックファイル                       |
| Web フレームワーク   | **FastAPI**（`fastapi[standard]`）                                   | 簡易設計書 §21 の暫定を追認。OpenAPI 自動生成が Dart クライアント生成に直結                 |
| ASGI サーバー        | **Uvicorn**（サイドカーとして単一ワーカーで内部起動）                | Gunicorn は不要（単一ユーザー・単一プロセス）                                               |
| バリデーション / DTO | **Pydantic v2**                                                      | 簡易設計書 §32。AI 出力の構造化（§9.2）にもスキーマを流用                                   |
| 非同期処理           | `async` FastAPI + `httpx`（OCR/AI 通信）                             | 外部 API 待ちが支配的なので I/O 並行が効く                                                  |
| Lint / Format        | **Ruff**（lint + format）                                            | flake8 + isort + black を単一ツールで置換                                                   |
| 型チェック           | **mypy**（`strict`）                                                 | pyright でも可。CI で固定する                                                               |
| テスト               | **pytest** + `pytest-asyncio` + `httpx.AsyncClient`                  | —                                                                                           |
| 設定管理             | `pydantic-settings` で `.env` / 環境変数を読み込み                   | 例値は `.env.example`、実値は `app-data` 配下のローカル設定 or OS キーチェーン（`keyring`） |
| ログ                 | 構造化ログ（`structlog` もしくは標準 `logging` + JSON フォーマッタ） | §28。**生徒答案本文をログへ書かない**フィルタを実装                                         |

### 3.1 PDF 処理ライブラリ（PoC 3 で確定）

簡易設計書 §14・§22 は **PyMuPDF** を指定しているが、PyMuPDF は
**AGPL-3.0 と Artifex 商用ライセンスのデュアルライセンス**である。ソースを公開しない
クローズドな配布物にする場合、AGPL を満たせないため **Artifex の商用ライセンス購入が必要**。

| 選択肢                                  | ライセンス                                                                                    | 影響                                                                 |
| --------------------------------------- | --------------------------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| A. PyMuPDF を採用（要ライセンス費）     | AGPL or 商用                                                                                  | 実装が最短。塾向け非公開配布なら商用ライセンス費用が発生。要見積もり |
| **B. オープンソース構成に置換（採用）** | `pypdfium2`（Apache/BSD）でラスタライズ＋座標取得、`pypdf`（BSD）でオーバーレイ・スタンプ生成 | ライセンス費ゼロ。ただし注釈描画・座標 API を自前で組む工数が増える  |

PoC 検討時は A を第一候補とし、ライセンス未承認時は B を採用する方針だった。PDF 処理は
`PdfEngine` インターフェースで隔離する。

**PoC 3（Issue #12）の結果 — 選択肢 B を採用**:
ライセンス判断者による PyMuPDF 採用の承認記録が無いため、Issue #12 受入条件に従い
PyMuPDF は候補から外し、**`pypdfium2` + `pypdf`** を採用した。縦横・回転
（0/90/180/270）・ページサイズ差・非ゼロ原点 MediaBox・CropBox インセットを含む全
fixture で 0〜1 正規化
座標の往復誤差は最大 0.0005（許容 0.004）、render DPI/zoom 非依存。採用した座標変換と
`PdfEngine` 契約は `backend/src/auto_scoring/` へ昇格済み。詳細と repro command は
[`poc-3-pdf-coordinates.md`](./poc-3-pdf-coordinates.md)。承認が後日出た場合は同じ
`PdfEngine` 契約に `PyMuPDFEngine` を追加して差し替える。

**Issue #23（添削済みPDF出力）で `reportlab` を追加**: `pypdf`/`pypdfium2` には
テキストレイアウト・フォント埋め込みAPIが無く、添削コメントの日本語テキストを
PDFへ描画するには不十分だった。`reportlab`（BSD系ライセンス、PyMuPDFのような
AGPL/商用ライセンス問題は無い）を`PdfEngine`実装の内部でのみ使用する形で追加した。
詳細は[`pdf-export.md`](./pdf-export.md) §3。

### 3.2 画像処理

| 要素   | 決定                                     | 備考                                                           |
| ------ | ---------------------------------------- | -------------------------------------------------------------- |
| OpenCV | **opencv-python-headless**               | 簡易設計書 §7・§32。GUI 依存を含まない headless 版でサイズ削減 |
| 補助   | Pillow（画像 I/O）、NumPy（OpenCV 依存） | §7 の傾き・回転・ノイズ・コントラスト補正に使用                |

### 3.3 データベース

| 要素             | 決定                                                                                          | 備考                                                            |
| ---------------- | --------------------------------------------------------------------------------------------- | --------------------------------------------------------------- |
| DBMS             | **SQLite**（`app-data/database.sqlite`、WAL モード）                                          | 簡易設計書 §18・§32                                             |
| アクセス層       | **SQLAlchemy 2.x**（+ 任意で SQLModel）                                                       | 生 SQL 直書きは §18 のエンティティ数では保守しにくい            |
| マイグレーション | **Alembic**                                                                                   | スキーマ変更を PR で追跡（AGENTS.md「Data/schema changes」）    |
| 主なエンティティ | Test / Question / Rubric / Submission / RecognitionResult / GradeResult / Annotation / Review | 簡易設計書 §18。AI 結果と人間の最終結果を分離保持（§19・§35-5） |
| 制約             | 外部キー・NOT NULL・状態列の CHECK（§25 の状態遷移）を DB 制約で担保                          | AGENTS.md「invariants は UI ではなく実制約で」                  |

### 3.4 非同期ジョブキュー（簡易設計書 §29）

| 論点       | 決定                                                                                    |
| ---------- | --------------------------------------------------------------------------------------- |
| 実装       | **プロセス内 `asyncio.Queue` + `asyncio.Semaphore`** による並行数制限ワーカー           |
| 永続化     | ジョブ（対象 submission・状態・試行回数・エラー）を **SQLite に保存**し、再起動時に復旧 |
| 並行数     | 設定値（既定 2〜3）。外部 AI のレート制限に合わせて調整。§33-24 の最終値はユーザー判断  |
| 却下した案 | Celery / arq（Redis 常駐が必要でローカル単体アプリに不相応）、RQ（同上）                |

人間が答案 1 をレビュー中に答案 2・3・4 の AI 処理を進める（§29）要件は、この
1 プロセス内キューで満たせる。

### 3.5 OCR / AI プロバイダ抽象（簡易設計書 §8.3・§20・§32）

- `OCRProvider` と `AIProvider` を **Python 側のインターフェース**として定義し、実装を
  差し替え可能にする（§35-6）。Flutter からは「OCR する」「採点する」API しか見えない。
- **具体サービス・モデルは PoC 後に確定**（§33-2, §33-3）。本書では PoC の初期候補のみ示す。

#### OCR 初期候補（PoC 1 で比較）

| 候補                                                   | 位置づけ                                                                                                 |
| ------------------------------------------------------ | -------------------------------------------------------------------------------------------------------- |
| **Google Cloud Vision API（DOCUMENT_TEXT_DETECTION）** | 第一候補。日本語手書きの実績が比較的高く、単語単位の Bounding Box が取れる（§12.3 の注釈位置決定に必須） |
| Azure AI Vision / Document Intelligence                | 対抗候補。印刷文字・複雑レイアウトに強いが、手書き対応言語が限定的                                       |
| Vision 対応 LLM（下記 AIProvider と共用）              | OCR 単体としても評価。孤立手書きでは専用 OCR を上回る報告があるが、Bounding Box は弱い                   |
| ローカル OCR（PaddleOCR / Tesseract 日本語）           | クラウド不可時のフォールバック。精度は PoC で要確認                                                      |

設計方針（§8.1）どおり **OCR 結果と Vision AI を併用**し、低 Confidence は自動確定しない
（§8.2・§35-2）。

#### AIProvider 初期候補（PoC 2 で比較）

| 候補                            | 位置づけ                                                                   |
| ------------------------------- | -------------------------------------------------------------------------- |
| Google Gemini（Vision 対応）    | 大きめのコンテキスト・コスト効率。画像＋ルーブリック同時入力（§8.1）に向く |
| Anthropic Claude（Vision 対応） | 指示追従・構造化出力の安定性                                               |
| OpenAI GPT（Vision 対応）       | 構造化出力ツールが充実                                                     |
| ローカル LLM                    | 送信不可データ用のフォールバック（現時点はクラウド可のため優先度低）       |

- 出力は**必ず JSON スキーマで構造化**して受け取る（§9.2）。各プロバイダの
  「JSON スキーマ / structured output」機能を使い、Pydantic モデルで検証する。
- Recognition Confidence と Grading Confidence を分離して保持（§10・§35-5）。

---

## 4. 配布・パッケージング

| 論点                    | 決定                                                                                                                                             |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| Python サイドカーの同梱 | **PyInstaller の onedir** で「インタプリタ＋依存＋DLL」を 1 ディレクトリにまとめ、Flutter の実行ファイル群に同梱                                 |
| 却下した案              | Nuitka（起動・実行は速いがフックエコシステムが弱く、OpenCV/PyMuPDF 同梱で詰まりやすい）。PyInstaller onefile（一時展開が遅く AV 誤検知が増える） |
| Windows インストーラ    | **Inno Setup（Issue #24 で確定）**。第一候補だった MSIX は、署名必須でありながら証明書が未準備のため「unsigned test artifact」を作れず不適合     |
| 署名                    | Windows コード署名証明書が必要（SmartScreen 対策）。取得はユーザー側手配事項。CI は unsigned のみ、署名は人間だけが行う                          |
| 自動更新                | MVP では対象外（§31 後回し候補に準拠）。将来 `msix` + 配布サーバ or `auto_updater`                                                               |

配布物の構成・`app-data/` の場所・ライフサイクル・障害復旧・署名手順は
[`windows-distribution.md`](./windows-distribution.md)（GitHub Issue #24）が正本。
MSIX を採用しない判断の根拠は同 §2。

---

## 5. リポジトリ構成案（後続 Issue で実装）

単一リポジトリに UI と バックエンドを併置する。

```text
/
├─ app/                     # Flutter デスクトップアプリ
│   ├─ lib/
│   │   ├─ main.dart        # コンポジションルート（サイドカー監視・DI の上書き）
│   │   ├─ app_router.dart  # go_router のルート表（画面を名指しするので core には置けない: §2.2）
│   │   ├─ features/        # 画面・状態（home, test_registration, review, ...）
│   │   ├─ api/             # OpenAPI 生成クライアント（コミットする）
│   │   └─ core/            # テーマ(Material 3), ルートのパス, provider 定義（DI）
│   ├─ integration_test/
│   └─ pubspec.yaml
│
├─ backend/                 # Python サイドカー
│   ├─ src/auto_scoring/
│   │   ├─ api/             # FastAPI ルーター（薄く保つ）
│   │   ├─ domain/          # 採点・プロファイル・状態遷移のコア（フレームワーク非依存）
│   │   ├─ adapters/        # PdfEngine, OCRProvider, AIProvider, Repository 実装
│   │   ├─ jobs/            # asyncio キュー
│   │   └─ db/              # SQLAlchemy モデル + Alembic
│   ├─ tests/
│   └─ pyproject.toml
│
├─ docs/
└─ package.json             # pnpm run <script> を全体のタスク入口として使う
```

依存方向（AGENTS.md「Architecture」）:

```text
app: features → core → api            （api は生成物。features はここだけ経由で通信）
backend: api → domain ← adapters       （domain はフレームワーク・DB・外部 API を import しない）
```

### 5.1 品質ゲートへの割り当て（`package.json` scripts）

`docs/quality-gates.md` の各ゲートに実ツールを割り当てる。実配線は後続 Issue。

| script      | 実行内容（案）                                                            |
| ----------- | ------------------------------------------------------------------------- |
| `lint`      | `dart format --set-exit-if-changed` + `flutter analyze` かつ `ruff check` |
| `typecheck` | `dart analyze`（analyzer） かつ `mypy backend/src`                        |
| `test`      | `flutter test` かつ `uv run pytest`                                       |
| `build`     | `flutter build windows --release` かつ サイドカーの PyInstaller ビルド    |

`format` は現状どおり Prettier（テンプレート基盤）。Node ツールチェーンは維持し、
Flutter/Python は `pnpm run` から各ツールを呼び出すラッパーにする
（`docs/quality-gates.md`「Non-Node project」の方針）。CI（`.github/workflows/ci.yml`）
には Flutter SDK と `uv` のセットアップステップを追加する。

---

## 6. セキュリティ方針の反映（簡易設計書 §26）

- クラウド AI/OCR 送信は許可されたが、**送信は設問単位の必要最小限**（該当設問の答案画像・
  OCR テキスト・模範解答・採点基準のみ）。テスト全体・生徒識別情報は送らない。
- 元答案 PDF はローカル `app-data` 配下にのみ保存。クラウドストレージへ自動アップロードしない。
- API キーはサイドカー側で OS キーチェーン（`keyring`）または権限を絞ったローカル設定に保存。
  リポジトリ・ログ・Issue・スクリーンショットに含めない（AGENTS.md「Security」）。
- localhost バインド + 起動時トークンで同一 PC の他プロセスからのアクセスを遮断。
- デバッグログに答案本文を出さないログフィルタを実装（§28）。

---

## 7. 簡易設計書 §33「未決定事項」への反映状況

| #             | 項目                                                                     | 本調査での扱い                                                                       |
| ------------- | ------------------------------------------------------------------------ | ------------------------------------------------------------------------------------ |
| 1             | Windows 専用とするか                                                     | 初期 Windows のみ。抽象化でクロスプラットフォーム維持（macOS/Linux は将来）          |
| 2             | 使用する AI モデル                                                       | **PoC 2 後に確定**。`AIProvider` で隔離。初期候補: Gemini / Claude / GPT             |
| 3             | 使用する OCR                                                             | **PoC 1 後に確定**。`OCRProvider` で隔離。第一候補: Google Cloud Vision              |
| 4             | 外部 AI API へ答案送信可否                                               | **可**（確認済み）。ただし送信データ最小化を実装方針とする                           |
| 5             | 答案 PDF の実ファイル構造                                                | テストプロファイル（§5）で吸収。PoC 4 で複数形式を検証                               |
| 6             | 1 PDF あたりの生徒数                                                     | 取込画面（§16.4）で方式選択可能にする設計。値自体はユーザー運用の判断                |
| 7〜11, 20〜21 | 添削記号・コメント規則・点数位置・採点方式・部分点・出力形式・上書き可否 | 業務ルール。実装前にユーザー確定が必要（本書では技術的に対応可能な設計余地のみ確保） |
| 19            | 低 Confidence の基準値                                                   | 設定値化。既定値は PoC の分布を見て提案                                              |
| 22            | キーボードショートカット                                                 | §17 の候補で実装開始。最終割り当てはユーザー確認                                     |
| 23            | AI 自動コメント生成の許容範囲                                            | 業務ルール。ユーザー判断                                                             |
| 24            | 並列 AI 処理数                                                           | 設定値化（既定 2〜3）。レート制限に合わせて調整                                      |

> 上記のうち「業務ルール」に属する項目は本 Issue の技術調査の範囲外。
> [`business-rules-and-evaluation-data.md`](./business-rules-and-evaluation-data.md)
> （GitHub Issue #8）で確定した。

---

## 8. 実装前に PoC で潰すべき技術リスク（簡易設計書 §30 と対応）

| PoC | 検証内容                               | 本書として特に確認したい点                                                                                                                             |
| --- | -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1   | 手書き認識（綺麗／普通／汚い字）       | Google Cloud Vision の日本語手書き精度と Bounding Box の質。LLM 併用時の改善幅                                                                         |
| 2   | 採点（模範解答＋マニュアル＋答案）     | 各 AIProvider の構造化 JSON 出力の安定性、人間採点との一致率、Grading Confidence の較正                                                                |
| 3   | PDF 座標（○×・コメントの表示・出力）   | **完了（Issue #12）**: pdfium ↔ pypdfium2+pypdf で 0〜1 正規化座標が往復一致（誤差 ≤0.0005）。[`poc-3-pdf-coordinates.md`](./poc-3-pdf-coordinates.md) |
| 4   | レイアウト変更（複数形式のテスト投入） | テストプロファイル生成 → 人間修正 → 各答案適用 のフローが形式差を吸収できるか                                                                          |

---

## 9. 決定サマリ

| 層           | 最終決定                                                                                            |
| ------------ | --------------------------------------------------------------------------------------------------- |
| UI           | Flutter (stable) / Dart 3 / Material 3 / Riverpod 3 / go_router / dio / pdfrx / freezed             |
| バックエンド | Python 3.12+ / uv / FastAPI / Uvicorn / Pydantic v2 / Ruff / mypy / pytest                          |
| PDF          | **pypdfium2 + pypdf** を `PdfEngine` で隔離（PoC 3 で採用。PyMuPDF はライセンス未承認のため不採用） |
| 画像処理     | opencv-python-headless / Pillow / NumPy                                                             |
| DB           | SQLite (WAL) / SQLAlchemy 2 / Alembic、書き込みは Python 側のみ                                     |
| ジョブキュー | プロセス内 asyncio.Queue + Semaphore、状態は SQLite に永続化                                        |
| OCR          | `OCRProvider` 抽象。PoC 第一候補 Google Cloud Vision（クラウド不可時ローカル OCR）                  |
| AI           | `AIProvider` 抽象。PoC 候補 Gemini / Claude / GPT。出力は JSON スキーマで構造化                     |
| プロセス連携 | Flutter が Python サイドカーを子プロセス起動、localhost + 起動時トークン、動的ポート                |
| 配布         | PyInstaller onedir で Python 同梱、**Inno Setup**（MSIX は署名必須で不適合）、署名は人間の手作業    |
| API 契約     | FastAPI OpenAPI schema を正本に Dart クライアントをコード生成しコミット                             |

---

## 10. 参考資料

- PyMuPDF ライセンス（AGPL / Artifex 商用のデュアル）:
  <https://pymupdf.readthedocs.io/en/latest/about.html>,
  <https://github.com/pymupdf/PyMuPDF/discussions/971>
- Flutter + Python サイドカー同梱（PyInstaller / Nuitka）:
  <https://github.com/maxim-saplin/flutter_python_starter>,
  <https://dev.to/maximsaplin/integrating-flutter-all-6-platforms-and-python-a-comprehensive-guide-4ipo>
- Flutter 状態管理 2026（Riverpod 3 を新規既定に）:
  <https://softaims.com/blog/flutter-state-management-riverpod-bloc-2026>,
  <https://foresightmobile.com/blog/best-flutter-state-management>
- pdfrx（Widget Overlay / タップ領域）: <https://pub.dev/packages/pdfrx>,
  <https://github.com/espresso3389/pdfrx>
- クラウド OCR 比較（日本語・手書き）:
  <https://imagetotable.ai/blog/google-vs-aws-vs-azure-ocr-2026>,
  <https://aimultiple.com/ocr-accuracy>
- Vision LLM による手書き採点の研究:
  <https://arxiv.org/abs/2605.19043>, <https://arxiv.org/pdf/2606.11477>
- uv（Python パッケージ管理）: <https://astral.sh/blog/uv-unified-python-packaging>,
  <https://github.com/astral-sh/uv/blob/main/docs/guides/integration/fastapi.md>
- OpenAPI からの Dart クライアント生成:
  <https://github.com/OpenAPITools/openapi-generator/blob/master/docs/generators/dart-dio.md>
- Windows パッケージング（MSIX）: <https://docs.flutter.dev/platform-integration/windows/building>
- Python タスクキュー選定 2026: <https://aleksul.space/posts/choosing-python-task-queue-library/>
