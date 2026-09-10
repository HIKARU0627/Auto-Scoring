# PoC 7: Electron main プロセスにおける Python サイドカーのライフサイクル制御（Issue #203）

親 Issue: [#201](https://github.com/HIKARU0627/Auto-Scoring/issues/201)（Flutter → Electron 移行）  
関連 Issue: [#24](https://github.com/HIKARU0627/Auto-Scoring/issues/24)（Windows 配布・サイドカーライフサイクル）、[#57](https://github.com/HIKARU0627/Auto-Scoring/issues/57)（shutdown releases the port の flaky）、[#96](https://github.com/HIKARU0627/Auto-Scoring/issues/96)（API キー設定と再起動）  
本ドキュメントは `AGENTS.md` «Verification» の 5 点（再現コマンド・期待した結果・実際の結果・決定・撤去または昇格の条件）に基づく技術プローブ報告書である。

---

## 1. 結論（先に）

- **起動・handshake・動的ポート・再起動・通常終了は Electron main（Node.js ランタイム）から完全に制御可能。**
  - ポート 0 による OS 自動採番、`%TEMP%` 配下の一時 handshake ファイル経由のトークン受け渡し、`/healthz` 疎通、Bearer トークン認証付き API 呼び出し、トークン取得直後の handshake 一時ディレクトリ削除まで、すべて正常に動作した（起動所要時間: PyInstaller バンドルで中央値 1.7〜1.8 秒、venv スクリプトで中央値 1.2〜1.3 秒）。
  - 設定変更に伴うサイドカーの再起動（#96 の要件）も、旧プロセスの終了待機 → 同一 `app-data` への新プロセス起動 → 新ポート・新トークン発行のシーケンスが約 1.4〜1.6 秒で完結する。
- **異常系における孤児プロセスの挙動:**
  - **Linux 実測**: 親プロセス（Electron main）が `kill -9` や異常クラッシュで唐突に終了した場合、サイドカーは**孤児プロセスとして生存し続ける**（PPID が 1 / init へ付け替え）。
  - **残った孤児と次回起動**: 孤児プロセスが生きている間は `app-data/.lock` を排他保持し続けるため、次回起動した Electron main のサイドカーは `DataRootLockedError` により **exit code 3 (`ALREADY_RUNNING_EXIT_CODE`)** で即座に終了する。supervisor はこれを検知して `SidecarFailure.ALREADY_RUNNING`（「Auto-Scoring はすでに起動しています」画面）へ確実に遷移する。つまり、**同一 `app-data` に対する多重書き込みはカーネルレベルで確実に遮断される。**
- **Flutter 実装が持っている保証のうち、素の Electron 側で再現できない唯一の点:**
  - **Windows Job Object による強制終了時の自動プロセス回収（`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`）は、Node.js 標準の `child_process` では再現できない。**
  - Flutter は `app/lib/core/child_process_group.dart` で `dart:ffi` を使い `kernel32.dll` の Job Object API を直接呼んで子プロセスを登録している。これにより、Flutter アプリがタスクマネージャーから強制終了（End Task / `taskkill /F`）されたりクラッシュした場合でも、Windows カーネルがサイドカーを確実に道連れ終了させていた。
  - 素の Electron（Node.js `child_process`）にはこの機構がないため、Windows においてもタスクマネージャーからの強制終了時にサイドカーが孤児として残存し、次回起動で「すでに起動しています」画面が表示される状態になる。
  - **対策方針**: 本番移行時に (1) Node.js ネイティブアドオン / FFI（`node-addon-api` 等）で Win32 Job Object を呼ぶか、(2) Python サイドカー側に「親プロセス監視（親の生存確認・stdin 切断検知）」を追加して自律終了させることで完全解決可能。

---

## 2. 測定項目と実測結果（OS 別）

測定環境:

- **Linux (実測)**: Linux 7.0.0-31-generic x86_64, glibc 2.39, Node.js v24.14.0, Python 3.12.3, uv 0.12.10
- **Windows (未検証 / 理論解析)**: 本ホストは Linux のため、Windows 実機での実測は未検証。Win32 API および Node.js / Python の Windows 実装仕様に基づく差異を項目ごとに明記する。

### 測定結果マトリクス

| #     | 測定項目                                                                 | Linux 実測結果                                                                                                                                                                     | Windows（実機未検証 / 挙動解析）                                                                                                                                                                                                             |
| ----- | ------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **1** | **起動と handshake**<br>（ポート 0 自動採番、handshake 読取、認証）      | **成功**<br>・PyInstaller: 1,722ms〜1,836ms<br>・venv: 1,236ms〜1,340ms<br>・ポート 0 で空きポート割当<br>・トークン取得後即座にファイル削除<br>・`/healthz` 200, `/tests` 200/401 | **実機未検証**<br>・Windows 実機でも `--port 0` および `--handshake-file` のプロトコル自体は同一。<br>・初回起動時は Windows Defender による未署名バイナリのスキャンが入り、数十秒を要する既知の挙動あり（`windows-distribution.md` §5.1）。 |
| **2** | **通常終了**<br>（プロセス消滅、ポート解放、ロック解放）                 | **成功**<br>・所要時間: 151ms〜190ms (平均 170.7ms)<br>・PID 消滅確認: `kill(pid, 0)` で消滅<br>・ポート解放確認: TCP 接続拒否<br>・ロック解放: 直後の再起動成功                   | **実機未検証**<br>・Windows では Node.js の `child.kill()` は Win32 `TerminateProcess` を呼ぶ（Flutter と同一）。<br>・SQLite WAL と atomic write により即座終了可能。                                                                       |
| **3** | **異常系（強制終了と孤児）**<br>（親 kill -9 時の挙動、app-data ロック） | **孤児残存を確認**<br>・親 kill -9 後もサイドカー PID 生存<br>・次回起動時、サイドカーが exit code 3 で即座終了<br>・supervisor が `ALREADY_RUNNING` 画面へ遷移                    | **実機未検証（差異大）**<br>・素の Node.js では Windows でも孤児が残る。<br>・Flutter のような Job Object が無いため、タスクマネージャーからの強制終了時にプロセスが残存する。                                                               |
| **4** | **再起動**<br>（設定変更時のサイドカー入替）                             | **成功**<br>・所要時間: 1,430ms〜1,605ms<br>・旧プロセス停止 → 新プロセス起動<br>・新ポート・新トークンへ置換完了                                                                  | **実機未検証**<br>・同一 `app-data` を用いた逐次再起動は Windows でも同一ロジックで動作する見込み。                                                                                                                                          |
| **5** | **既知の弱点（#57 同等性）**<br>（shutdown 時のポート解放 flaky）        | **アノマリー 0 件**<br>・10 サイクル連続: 0 件<br>・50 サイクル連続: 0 件 (平均 170.7ms)                                                                                           | **実機未検証（潜在リスクあり）**<br>・Windows 開発/CI で venv スクリプトを起動する場合、孫プロセス構造に起因する終了遅延の可能性が残る。                                                                                                     |

---

## 3. 各項目の詳細測定結果

### 3.1 起動と handshake

- **再現コマンド**: `pnpm --dir desktop-poc/poc-7-sidecar-lifecycle run probe` (ステップ 1)
- **測定 OS**: Linux (x86_64) 実測。Windows は未検証。
- **実測結果**:
  - `auto-scoring-sidecar` を `--port 0 --handshake-file <temp-dir>/handshake.json --app-data-dir <temp-dir>` で起動。
  - OS により空きポート（例: 54915, 58129 等）が自動採番され、`127.0.0.1` のみにバインドされた。
  - 生成された JSON `{host: "127.0.0.1", port: <int>, token: "<urlsafe-32>"}` を Node.js 側でポーリング（100ms 間隔）し、正常にデコード。
  - 認証確認:
    - `GET http://127.0.0.1:<port>/healthz` → 200 OK
    - `GET http://127.0.0.1:<port>/tests`（`Authorization: Bearer <token>`）→ 200 OK (空の JSON 配列 `[]`)
    - `GET http://127.0.0.1:<port>/tests`（トークンなし）→ 401 Unauthorized
    - `GET http://127.0.0.1:<port>/tests`（誤トークン）→ 401 Unauthorized
  - トークン取得後、一時 handshake ディレクトリは直ちに削除され、ディスク上にトークンが残存しないことを確認。
  - 秘密情報保護: ログおよび出力にはトークン長（43文字）のみを記録し、トークン値自体は一切出力しない。

### 3.2 通常終了

- **再現コマンド**: `pnpm --dir desktop-poc/poc-7-sidecar-lifecycle run probe` (ステップ 2)
- **測定 OS**: Linux (x86_64) 実測。Windows は未検証。
- **実測結果**:
  - `supervisor.shutdown()` を呼び出し、`child.kill('SIGTERM')` を発行。
  - 151ms〜190ms（50 回平均 170.7ms）で子プロセスの exit イベントを受信。
  - 直後に `process.kill(pid, 0)` を呼び出し、プロセスが存在しない（`ESRCH`）ことを確認。
  - 直後に当該ポートへの TCP 接続を試行し、`ECONNREFUSED`（リッスン停止）を確認。
  - app-data の排他ロック解放確認: シャットダウン完了直後に、全く同じ `app-data` ディレクトリを指定して第 2 の supervisor を起動したところ、ロック競合を起こすことなく正常に READY 状態となった。

### 3.3 異常系（強制終了と孤児・二重起動ロック）

- **再現コマンド**: `pnpm --dir desktop-poc/poc-7-sidecar-lifecycle run probe:orphans`
- **測定 OS**: Linux (x86_64) 実測。Windows は未検証。
- **実測結果**:
  1. 親プロセス（模擬 Electron main）を立ち上げ、サイドカーを起動して READY 状態にした後、親プロセス自身を `SIGKILL`（`kill -9`）で強制終了。
  2. 親プロセスの死後、サイドカー（子プロセス）の状態を確認したところ、**プロセスは生存（孤児化）し、ポートもリッスン状態を維持**していた。
  3. この状態で、新しい第 2 の Electron main インスタンスが同一の `app-data` を指定して起動を試行。
  4. 新しいサイドカーは `app-data/.lock` の OS レベル排他ロック（POSIX では `fcntl.flock`、Windows では `msvcrt.locking`）の取得に失敗。
  5. `backend/src/auto_scoring/api/sidecar.py` の `DataRootLockedError` ハンドラが作動し、**exit code 3 (`ALREADY_RUNNING_EXIT_CODE`)** で即座に終了。
  6. supervisor 側は 100ms 以内に exit code 3 を検知し、`SidecarFailure.ALREADY_RUNNING` に状態遷移した。
- **孤児プロセスが残る条件**:
  - 親プロセスが `before-quit` や `didRequestAppExit` 等の終了ハンドラを実行できない形（`SIGKILL`、OS の強制タスクキル、クラッシュ）で突然死した場合。
  - Linux 環境では POSIX の標準動作として孤児化する。
  - Windows 環境でも、Node.js 単体では Job Object がないため同様に孤児化する。

### 3.4 再起動（設定変更の反映）

- **再現コマンド**: `pnpm --dir desktop-poc/poc-7-sidecar-lifecycle run probe` (ステップ 4)
- **測定 OS**: Linux (x86_64) 実測。Windows は未検証。
- **実測結果**:
  - Issue #96 では、設定画面で API キーを保存した後にサイドカーを再起動して設定を反映する仕様となっている。
  - `supervisor.start()` を再実行することで、既存の sidecar プロセスが停止（exit 待ち）され、同一 `app-data` 上で新しい sidecar プロセスが起動。
  - 新旧プロセス間で PID が変化（例: 487852 → 487907）、ポート番号が変化（例: 60485 → 52987）、トークンが新しく再生成された。
  - 再起動にかかる全所要時間は **約 1.4 秒〜1.6 秒** であり、UI 上の再起動ボタン押下からスプラッシュを経てホーム復帰するまでのユーザー体験として十分に実用的。

### 3.5 既知の弱点（#57 の類似点・相違点）

- **再現コマンド**: `pnpm --dir desktop-poc/poc-7-sidecar-lifecycle run probe:flake 50`
- **測定 OS**: Linux (x86_64) 実測。Windows は未検証。
- **実測結果**:
  - 連続 50 回の起動・即時シャットダウン・ポート解放確認サイクルを実施したところ、**アノマリー（プロセスの生存残り、ポートのリスニング残り、旧トークンの受容）は 0 件（発生率 0.0%）** であった。
  - 平均起動時間: 1,372.5ms、平均終了時間: 170.7ms。
- **Issue #57 との対照・分析**:
  - Issue #57 は Windows CI 上で `sidecar_supervisor_integration_test` の「shutdown releases the port」が flaky に失敗する問題。
  - **Linux 実測での所見**: Linux では `child.kill('SIGTERM')` により uvicorn のイベントループが数十〜百ミリ秒でソケットを閉じ、プロセスが終了する。TCP TIME_WAIT はクライアント側から閉じる場合などに生じるが、リスナーソケット自体はプロセス終了とともに即座に OS カーネルによって解放されるため、Flake は再現しなかった。
  - **Windows における潜在リスク**:
    1. テスト環境（`backend/.venv/Scripts/auto-scoring-sidecar.exe`）では、Windows の venv ランチャーが「トランポリン exe → venv python.exe → ベースインタプリタ」という階層構造を持ち、ソケットを掴んでいるのは孫プロセスである（`windows-distribution.md` §7.3）。親プロセスへの `TerminateProcess` だけでは孫プロセスの終了が非同期になり、ポート解放確認が一瞬 `true`（生存）と誤認されるリスクが Electron でも同様に存在する。
    2. 一方、配布物（PyInstaller onedir）は単一プロセス構成であるため、本番環境ではこの孫プロセスの問題は発生しない。

---

## 4. Flutter 実装が持つ保証と Electron 側での再現可否

現状の Flutter 実装（`app/lib/core/`）が提供している保証と、Electron 側への移植時の再現可否を以下に整理する。

| #   | 保証項目                                       | Flutter 実装（現状）                                                                                                                                         | Electron / Node.js 実装                                                           | 再現可否                                     | 差異と必要な対応                                                                                                                                                                                                   |
| --- | ---------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------- | -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1   | **強制終了時の孤児プロセス自動回収**           | `child_process_group.dart` で Win32 Job Object（`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`）を作成し、子プロセスを登録。親の死後、Windows カーネルが子を強制回収。 | 素の Node.js `child_process.spawn()` には Job Object 登録機構がない。             | **素の Electron では再現不可**<br>（未対応） | **再現手段**:<br>・案 A (推奨): `node-addon-api` や FFI を用いて Win32 `AssignProcessToJobObject` を呼ぶ。<br>・案 B: Python 側に親 PID の定期監視スレッド、または stdin パイプ close 検知を入れて自律終了させる。 |
| 2   | **通常終了時のプロセス・ポート解放**           | `StartupGate.didRequestAppExit` から `shutdown()` で kill 実行。                                                                                             | Electron の `app.on('before-quit')` や `window-all-closed` で `shutdown()` 実行。 | **完全再現可能**                             | 実測平均 170ms で確実に終了・解放されることを実証済み。                                                                                                                                                            |
| 3   | **二重起動時の排他ロックと画面遷移**           | Python 側 `app-data/.lock` 排他ロック。失敗時は exit code 3 を返し、supervisor が `alreadyRunning` 画面へ遷移。                                              | Node.js `child.on('exit')` で exit code 3 を検知し、Renderer へ通知。             | **完全再現可能**                             | 本 PoC で exit code 3 検知および状態遷移の完全一致を確認済み。                                                                                                                                                     |
| 4   | **動的ポート採番とトークン秘匿**               | `--port 0` で OS 自動採番。`%TEMP%` の一時ファイルで受け渡し、読み取り直後に削除。                                                                           | Node.js `fs.mkdtempSync` と `--handshake-file`。読取後直ちに `rmSync`。           | **完全再現可能**                             | 本 PoC で完全動作確認済み。                                                                                                                                                                                        |
| 5   | **非同期パイプドレイン（バッファ詰まり防止）** | 子プロセスの stdout/stderr を非同期ドレイン。ログは rotating file に書き出す。                                                                               | Node.js `child.stdout.on('data', () => {})` でドレイン。                          | **完全再現可能**                             | パイプ溢れによるデッドロック防止を実証済み。                                                                                                                                                                       |
| 6   | **無停止でのサイドカー再起動**                 | `SidecarSupervisor.start()` により旧プロセス kill → 新プロセス起動。                                                                                         | 同一ロジックを Node.js で実装。                                                   | **完全再現可能**                             | 約 1.5 秒で新トークン・新ポートへの入替完了を確認済み。                                                                                                                                                            |

---

## 5. `AGENTS.md` «Verification» の 5 点

### 5.1 再現コマンド

本プローブは `desktop-poc/poc-7-sidecar-lifecycle/` 配下のスクリプトで再現可能である（製品コードへの影響ゼロ、新規外部依存ゼロ）。

```bash
# 1. 全 5 項目の統合プローブ測定（起動・handshake・通常終了・孤児化・再起動・#57連続試行）
pnpm --dir desktop-poc/poc-7-sidecar-lifecycle run probe

# 2. 異常系（強制終了時の孤児化と次回起動時の exit code 3 ロック検出）の単体測定
pnpm --dir desktop-poc/poc-7-sidecar-lifecycle run probe:orphans

# 3. シャットダウン時ポート解放の連続ストレステスト（引数で反復回数指定、既定 50 回）
pnpm --dir desktop-poc/poc-7-sidecar-lifecycle run probe:flake 20

# 4. Supervisor 単体テスト
pnpm --dir desktop-poc/poc-7-sidecar-lifecycle run test
```

### 5.2 期待した結果

1. Electron main（Node.js）から PyInstaller 版サイドカーを `--port 0` で起動し、handshake ファイルからポートとトークンを取得して疎通できること。
2. アプリ終了時にサイドカーが確実に終了し、ポートと app-data ロックが解放されること。
3. アプリを強制終了した際にサイドカーが孤児化する条件と、その状態で次回起動した際に app-data ロック（exit code 3）が正しく機能することが実測できること。
4. 設定変更後のサイドカー再起動が Electron main から正常に行えること。
5. Flutter 実装が持つ保証のうち、Electron で再現できないものが明確に特定されること。

### 5.3 実際の結果

- 上記 1〜4 について Linux 上での実測値を記録し、すべての期待動作を確認した。
- 5 について、**「Windows Job Object による強制終了時の自動孤児回収」が素の Electron（Node.js `child_process`）では再現できない唯一の保証**であることを特定した。

### 5.4 決定

1. **ライフサイクル制御の基本設計**: Electron main プロセスにおけるサイドカーの起動・handshake・通常終了・再起動・二重起動防止は、Node.js 標準ライブラリのみで構成した `SidecarSupervisor` クラスで完全に代替可能である。
2. **Windows における強制終了時の孤児対策（要対応事項）**:
   - 素の Electron のままでは、タスクマネージャーからの強制終了やクラッシュ時にサイドカーが孤児化し、次回起動で exit code 3（「すでに起動しています」画面）となるリスクが残る。
   - 親 Issue #201 の本実装フェーズにおいて、以下のいずれかの対策を導入することを決定・推奨する:
     - **推奨案**: Python サイドカー側（`backend/src/auto_scoring/api/sidecar.py`）に親プロセス監視スレッドを追加する。親プロセスの死（stdin パイプの EOF、または Windows では `OpenProcess` による待機）を検知して自律終了させる。これにより、Node.js 側に C++ ネイティブアドオンを追加することなく、Windows/Linux/macOS の全プラットフォームで一貫した孤児防止が実現できる。

### 5.5 撤去または昇格の条件

- **撤去条件**: 親 Issue #201（Flutter → Electron 移行）の完了、または設計方針の変更により本プローブコードが不要となった段階で、`desktop-poc/poc-7-sidecar-lifecycle/` は削除する。
- **昇格条件**: Issue #201 の Electron main プロセス実装時に、`desktop-poc/poc-7-sidecar-lifecycle/src/sidecar_supervisor.mjs` の設計および状態遷移ロジックを本番の Electron main コード（TypeScript）へ昇格・移植する。
