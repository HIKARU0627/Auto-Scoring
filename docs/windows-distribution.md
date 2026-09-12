# Windows 配布・サイドカーライフサイクル・障害復旧

GitHub Issue #24（親: #3）で実装した、Windows 向け配布物とサイドカーのプロセス
ライフサイクルの決定事項。簡易設計書 §21〜§28 と技術スタック決定書 §1.2・§4 を
具体化する。食い違う場合は本書を優先し、上位ドキュメントも同じ PR で更新する。

本 Issue で確定した未決事項:

| 未決だった点                       | どこに書かれていたか                     | 本書での決定 |
| ---------------------------------- | ---------------------------------------- | ------------ |
| `app-data/` の実際の格納場所       | `answer-intake-and-preprocessing.md` §10 | §3           |
| ハンドシェイクをファイルか fd か   | `sidecar-api.md` §3                      | §4           |
| MSIX か Inno Setup か              | `technology-stack.md` §4                 | §2           |
| 二重起動時の扱い                   | Issue #24 受入条件                       | §5.4         |
| uninstall 時にデータを残すか消すか | Issue #24 実施内容                       | §6           |

---

## 1. 配布物の構成

配布物は 1 つのインストーラー exe で、次の 2 つのビルド成果物を同梱する。

```text
<インストール先>/                       # 既定: %LOCALAPPDATA%\Programs\Auto-Scoring
├─ auto_scoring_app.exe                 # Flutter release ビルド
├─ flutter_windows.dll
├─ msvcp140.dll                         # MSVC ランタイム（§1.1）
├─ vcruntime140.dll
├─ vcruntime140_1.dll
├─ data/                                # Flutter の assets / AOT snapshot
├─ *.dll                                # Flutter プラグインの DLL（pdfrx 等）
└─ sidecar/                             # PyInstaller onedir の成果物
    ├─ auto-scoring-sidecar.exe
    └─ _internal/                       # Python インタプリタ・依存・ネイティブライブラリ
```

`sidecar/` の位置は `app/lib/core/sidecar_paths.dart` の `sidecarBundleDirectory`
と `installer/auto-scoring.iss` の `[Files]` の 2 か所で決まる。`app/test/sidecar_paths_test.dart`
が定数を固定している。

`data/` の中ではなく実行ファイルと同階層に置く理由: `data/` は Flutter 自身の
ものでビルドのたびに丸ごと書き換わるため、そこに置いたものは消える可能性があり、
ビルド生成物と区別もつかない。

### 1.1 MSVC ランタイムを同梱する（配布物に必須）

**素の Windows には Visual C++ 再頒布可能パッケージが入っていない。** その状態では
Flutter の実行ファイルが `msvcp140.dll` / `vcruntime140.dll` /
`vcruntime140_1.dll` を解決できず、**そもそも起動しない**。Flutter の Windows
テンプレートはこれらを同梱しないので、`app/windows/CMakeLists.txt` に
`InstallRequiredSystemLibraries` を追加し、実行ファイルと同じディレクトリへ
install するようにした。

- PyInstaller バンドルも自前のランタイム DLL を持っているが、それは `sidecar\`
  配下にあり**役に立たない**。Windows のローダーが見るのは起動する実行ファイルと
  同じディレクトリで、任意のサブディレクトリではない。
- **CI では絶対に再現しない**。`windows-latest` runner には Visual Studio が
  入っており、ランタイムが常にシステム側にある。clean VM で初めて出る種類の不具合で、
  §10 の手順に確認項目を入れてある。
- vcredist_x64.exe を installer から実行する案は採らない。**あれは管理者権限を
  要求する**が、この installer は既定で非昇格のユーザー単位インストール（§2.2）
  なので前提が崩れる。app-local 配置は Microsoft が認めている配布方法で、対象
  DLL は再頒布可能リストに含まれる。

### 1.2 ビルド手順（開発者・CI 共通）

```powershell
pnpm run package:sidecar          # backend/dist/auto-scoring-sidecar/ を作る
pnpm run package:sidecar:smoke    # 作った exe を実際に起動して検証（§7）
cd app; flutter build windows --release; cd ..
pnpm run package:installer        # installer/output/*.exe を作る（unsigned）
```

いずれも Windows 専用。Linux/macOS では PyInstaller がクロスコンパイルできず、
Flutter の Windows ビルドもできないため、**CI の `windows-latest` runner が
唯一の検証環境**（§7）。

### 1.3 Electron 配布物の構成とサイドカー配置・解決経路（Issue #265）

Electron 版配布物は `electron-builder` により Windows インストーラ（NSIS）および展開済みディレクトリ（`win-unpacked`）として出力される。

```text
<インストール先>/                       # 既定: %LOCALAPPDATA%\Programs\Auto-Scoring
├─ Auto-Scoring.exe                     # Electron 実行ファイル
├─ resources/                           # app.asar 等
├─ *.dll                                # Electron / Chromium ランタイム
└─ sidecar/                             # PyInstaller onedir の成果物（extraFiles で配置）
    ├─ auto-scoring-sidecar.exe
    └─ _internal/                       # Python インタプリタ・依存・ネイティブライブラリ
```

- **配置経路**: `desktop/electron-builder.json` の `extraFiles` 設定により、`pnpm run package:sidecar` が出力した `backend/dist/auto-scoring-sidecar` を `<appOutDir>\sidecar\` へ直接同梱する。
- **解決経路**: `desktop/src/main/sidecar-paths.ts` の `sidecarExecutableCandidates` は、実行時 `process.execPath` の親ディレクトリ（`<インストール先>`）直下の `sidecar\auto-scoring-sidecar.exe` を最優先候補として解決する。開発時は `workingDirectory`（リポジトリルート）からの `backend/.venv/` がフォールバックとして機能するが、パッケージ版では `extraFiles` による同梱サイドカーが確定的に選択される。

### 1.4 Electron ビルド・パッケージ手順

```powershell
pnpm run package:sidecar          # backend/dist/auto-scoring-sidecar/ を作る
pnpm run package:sidecar:smoke    # サイドカー単体 smoke test
pnpm run package:electron         # desktop/dist/win-unpacked と installer をビルド
pnpm run package:electron:smoke   # パッケージ版の実機 smoke test（§7.4）
```

---

## 2. インストーラー: MSIX ではなく Inno Setup

技術スタック決定書 §4 と Issue #24 は **MSIX を第一候補**とし、要件が合わなければ
理由を記録して Inno Setup に切り替えてよいとしていた。調査の結果 **Inno Setup を
採用**する。

### 2.1 MSIX を採用しない理由

| #   | 不適合                                                                                                                                                                                                                    | 影響                                                                                                                                                                                                                                    |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | **署名が必須**。MSIX パッケージは、対象マシンが信頼する証明書で署名されていないとインストール自体ができない（自己署名証明書を各マシンへ手で登録する運用を除く）                                                           | 受入条件「code signing 証明書が未準備の場合、unsigned test artifact と人間だけが行う署名手順を明確に分離する」を**満たせない**。unsigned MSIX は誰もインストールできず、clean VM smoke test にも使えない。証明書購入は Issue #24 対象外 |
| 2   | **`%LOCALAPPDATA%` がリダイレクトされる**。MSIX コンテナ内のアプリが書く `%LOCALAPPDATA%` は `%LOCALAPPDATA%\Packages\<PackageFamilyName>\LocalCache\Local\` へ転送され、**アンインストール時にパッケージごと削除される** | §6 の「アンインストールでは既定でデータを残す」方針と正面から衝突する。答案 PDF と採点結果が黙って消える                                                                                                                                |
| 3   | **子プロセスがコンテナ内で動く**。同梱した `auto-scoring-sidecar.exe` はパッケージのコンテナ内で実行され、ファイルシステム・レジストリの仮想化を受ける                                                                    | サイドカーは §3 の実パスへ書くことを前提にしている。動かないとは限らないが、Flutter 側と Python 側で「同じパス」の意味が変わる                                                                                                          |

1 が単独で決定的。2 と 3 は、証明書が用意できたあとに再検討する場合でも
設計変更が要る点として記録しておく。

### 2.2 Inno Setup を採用する結果

- unsigned の `.exe` は SmartScreen の警告こそ出るが**インストールできる**ので、
  CI が artifact を作り、人間が clean VM で smoke test できる。
- 既定は**ユーザー単位インストール**（`PrivilegesRequired=lowest`）。管理者昇格が
  不要で、インストール先が §3 のデータ配置と同じユーザープロファイル内に収まる。
  管理者権限があるユーザーはダイアログでマシン全体へも入れられる
  （`PrivilegesRequiredOverridesAllowed=dialog`）。アプリは自分のインストール
  ディレクトリへ一切書き込まないので、どちらでも動く。
- アンインストール時の挙動をこちらで書ける（§6）。

証明書が用意できたら MSIX への差し戻しは可能。`installer/auto-scoring.iss` の
先頭にこの判断を書いてある。

---

## 3. `app-data/`（データの場所と権限）

**決定**: サイドカーの `--app-data-dir` 既定値を OS のユーザー単位データ領域にする。
実装は `auto_scoring.api.sidecar.default_app_data_dir`（`backend/tests/test_sidecar.py`
が各 OS の解決を検証）。

| OS                | 既定パス                                                             |
| ----------------- | -------------------------------------------------------------------- |
| **Windows**       | `%LOCALAPPDATA%\Auto-Scoring\app-data\`                              |
| macOS（将来）     | `~/Library/Application Support/Auto-Scoring/app-data/`               |
| Linux（開発・CI） | `$XDG_DATA_HOME/auto-scoring/app-data/`（既定 `~/.local/share/...`） |

置かれるもの（簡易設計書 §23、`answer-intake-and-preprocessing.md` §8）:

```text
%LOCALAPPDATA%\Auto-Scoring\app-data\
├─ .lock                        # 排他ロック用（§5.4）。内容に意味はない
├─ database.sqlite (+ -wal, -shm)
├─ logs/sidecar.log             # §5.5
├─ tests/<test-id>/{model-answer.pdf, manual.pdf, profile.json}
├─ submissions/<submission-id>/{source.pdf, pages/, questions/}
└─ exports/<original-stem>_corrected[_N].pdf
```

**権限**: `%LOCALAPPDATA%` は Windows が作る時点でそのユーザーのみに ACL が
設定されている。アプリは追加の ACL 設定をしない（親から継承した既定が既に
「本人のみ」であり、独自に付け直すほうが間違えやすい）。教室で 1 台を複数人が
使う場合、Windows ユーザーを分ければデータも分かれる。

### 3.1 なぜ `cwd()/app-data` をやめたか

以前の既定値は「カレントディレクトリ配下の `app-data`」（暫定値と明記されていた）。
配布物では使えない:

- 起動方法（スタートメニュー、エクスプローラー、Flutter からの spawn）で
  カレントディレクトリが変わるため、**同じアプリが起動のたびに別のデータベースを
  見る**ことになる。
- `C:\Program Files` 配下にインストールした場合、そこは非管理者が書けない。

### 3.2 なぜ Flutter は `--app-data-dir` を渡さないか

`app/lib/main.dart` の supervisor は `--app-data-dir` を**渡さない**（テスト用の
上書きは可能）。パス解決は Python 側の 1 か所だけに置く。Dart 側でも
`%LOCALAPPDATA%` の解決を書けば、同じインストール物が 2 つの答えを持ち、片方だけ
直したときに黙って食い違う。

---

## 4. 起動シーケンスとハンドシェイク

```text
Flutter 起動
  └─ SidecarSupervisor.start()
       1. %TEMP% に per-attempt の一時ディレクトリを作り、空の handshake.json を作る
       2. sidecar.exe --port 0 --handshake-file <その中> を子プロセス起動
          （直後に Windows Job Object へ登録 → §5.3）
       3. 250ms 間隔で poll:
            - プロセスが終了していたら即座に失敗（timeout を待たない）
            - handshake.json が {host, port, token} として parse できたら接続情報確定
            - Authorization: Bearer <token> 付きで GET /healthz が 200 なら ready
       4. ready になった時点で handshake の一時ディレクトリごと削除
       5. timeout（60 秒）を超えたら子プロセスを kill して失敗
```

**決定（`sidecar-api.md` §3 の未決事項）**: 接続情報の受け渡しは
**ファイル経由**（fd 継承ではない）。`%TEMP%` 配下（Windows では
`%LOCALAPPDATA%\Temp`、既にそのユーザーのみの ACL）に **1 起動ごとの
ランダム名ディレクトリ**を作り、その中に置く。理由:

- dart:io には Windows で追加のハンドルを子へ継承させる公式手段がない。
- `app-data/` 配下ではなく `%TEMP%` にするのは、これが**生きたトークンを持つ
  ファイル**だから。再起動をまたいで残る前提のディレクトリに置くものではないし、
  サイドカー自身がファイルを配信するツリーの中でもない。
- **トークンを読んだ直後に削除する**（起動完了時、または失敗時）。ディスク上に
  トークンがある時間を最短にする。`app/test/sidecar_supervisor_integration_test.dart`
  が実際に消えていることを検証する。

### 4.1 ハンドシェイクの読み取り競合

ファイルは Flutter が空で作り、**別プロセスが**あとから書く。したがって
「ファイルが存在する」は成功条件にならない（空・書きかけが読める）。
成功条件は **JSON として parse でき、`host`/`port`/`token` が揃っていること**。
それ以外はすべて「まだ書かれていない」として再試行する
（`app/test/sidecar_supervisor_test.dart` の `handshake reading` グループが
空ファイル・空白のみ・途中まで・型違い・token 欠落/空を網羅）。

### 4.2 ハンドシェイクは `create_app` の後に書く

`auto_scoring.api.sidecar.run` は、ソケットを bind したあと **`create_app()` が
成功してから**ハンドシェイクを書く。以前は bind 直後に書いていたため、
データルートのロック失敗・マイグレーション失敗・DB 破損のいずれでも、
「誰も応答しない host:port」を書いたファイルが残った。読む側はそれを
「起動が遅いだけ」と区別できず、timeout いっぱい待つしかなかった。

---

## 5. ライフサイクルと障害復旧

状態機械は `app/lib/core/sidecar_supervisor.dart`、UI は
`app/lib/features/startup/startup_gate.dart`（簡易設計書 §24）。

| 状態              | UI                                                         |
| ----------------- | ---------------------------------------------------------- |
| `SidecarStarting` | スプラッシュ（「初回起動には時間がかかることがあります」） |
| `SidecarReady`    | ホーム画面                                                 |
| `SidecarFailed`   | エラー画面 + **再起動ボタン**                              |
| `SidecarStopped`  | 終了中                                                     |

スプラッシュとエラー画面は `MaterialApp.router` の `builder` で **Router（=
Navigator）全体の上に重ねる**。最下段のルートとして置いてはいけない: 答案取込や
添削レビューを開いている最中にサイドカーが落ちると、エラー画面と再起動ボタンが
push 済みのページの下に隠れ、ユーザーには「自分の画面が理由も示さず全リクエストに
失敗し続ける」ようにしか見えない。

サイドカーが使えなくなった時点で `GoRouter.go(AppRoutes.starting)` により push 済みの
ルートを畳む（go_router 導入前は `Navigator.popUntil(isFirst)`、
[`technology-stack.md`](./technology-stack.md) §2.2）。各画面は
`appDependenciesProvider` から `AppDependencies`（= その時の `SidecarApiClient`）を
解決しており、放置すると閉じたクライアントを呼び続け、再起動が新しい port と token を
発行しても届かないため。**作業中の画面は失われる**が、未送信の編集を持っていた
サイドカー自身が死んでいる以上どのみち失われており、エラー画面はそれを隠さない。

`SidecarFailed` の内訳と表示:

| `SidecarFailure`      | 起きたこと                              | 表示                                             |
| --------------------- | --------------------------------------- | ------------------------------------------------ |
| `executableMissing`   | どのパスにも sidecar が無い             | 「インストーラーから再インストールしてください」 |
| `alreadyRunning`      | サイドカーが exit code 3 で終了（§5.4） | 「Auto-Scoring はすでに起動しています」          |
| `exitedDuringStartup` | 起動途中で自分から終了                  | ログの場所を案内                                 |
| `startupTimedOut`     | 60 秒 `/healthz` に応答しなかった       | 同上                                             |
| `crashed`             | ready になったあとで終了                | 同上                                             |

エラー画面はトークンも例外文字列も出さない
（`app/test/startup_gate_test.dart` が検証）。

### 5.1 起動 timeout

`sidecarStartupTimeout = 60 秒`（`sidecar_supervisor.dart` の定数 1 か所）。
初回起動が遅いのは、新規データベースへ全マイグレーションを流すのと、
Windows Defender が初回実行の未署名実行ファイル群をスキャンするため
（`app/test/sidecar_api_client_test.dart` に GitHub hosted runner での実測が
記録されている）。

**プロセスが即座に異常終了した場合は timeout を待たない**。poll ループは毎回
まず子プロセスの終了を確認し、終了していればその場で失敗にする。

### 5.2 通常終了時の kill

`StartupGate.didRequestAppExit`（ウィンドウを閉じたとき Flutter が呼ぶ最後の
Dart コード）で `SidecarSupervisor.shutdown()` → 子プロセスを kill →
exit を待つ。

kill は Windows では常に `TerminateProcess`（graceful signal が無い）。
安全なのは、サイドカーの書き込みがすべてクラッシュ耐性を持つ設計だから:
SQLite は WAL、ファイルは `os.replace` による atomic write、起動時に
`sweep_temp` + `repair_incomplete_*` が中断分を回収する。

### 5.3 強制終了時の orphan 防止（Windows Job Object）

クラッシュ・タスクマネージャからの終了・`taskkill` では上の Dart コードは
一切走らない。残ったサイドカーは loopback ポートと `app-data/` の排他ロックを
握り続けるため、**次回起動が「すでに起動しています」で失敗し、しかもユーザーには
理由が分からない**。

対策は `app/lib/core/child_process_group.dart`: `dart:ffi` で `kernel32.dll` の
`CreateJobObjectW` / `SetInformationJobObject`（`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`）
/ `OpenProcess` / `AssignProcessToJobObject` を呼び、子プロセスを Job Object へ
登録する。Job のハンドルはアプリの生存中ずっと開いたままにする。プロセスが
どう死んでも OS がハンドルを閉じ、そのとき Job 内の全プロセスが終了する。

C++ プラグインを `windows/runner` に足すのではなく FFI にした理由: ビルド
システムに手を入れず、Flutter テンプレートと同期を取る必要もなく、境界全体が
1 つの Dart ファイルに収まって `flutter analyze` の対象になる。

非 Windows では no-op 実装に差し替わる（`ChildProcessGroup.forCurrentPlatform`）。
macOS/Linux 配布は本 Issue の対象外で、そこでの等価物（`setsid` プロセス
グループ）は配布を始めるときに実装する。

> Issue #62 で `app/linux/` を足したが、**あれは開発機で画面を見るための足場で
> あって配布対象ではない**。上の「macOS/Linux 配布は対象外」は変わっていない。
> no-op のままなので Linux では強制終了時にサイドカーが残る。
> [`linux-desktop-development.md`](./linux-desktop-development.md) §0・§5.1 を参照。

**残存リスク**: `Process.start` と Job への登録の間に数マイクロ秒の隙間がある
（Windows の完全解は `CREATE_SUSPENDED` + assign + resume だが dart:io は
これを公開していない）。その隙間で Flutter 側が死んだ場合のみ orphan が残る。

### 5.3.1 Electron ではその Job Object が無い（Issue #211）

上の保証は **Windows の Job Object を、親プロセス側から**かけている。Node.js の
`child_process` に相当する機構は無いため、素の Electron へ移行する（#201）と
この保証はそのまま消える。PoC 7（#203、[`poc-7-sidecar-lifecycle.md`](./poc-7-sidecar-lifecycle.md)
§4）が Linux で実測し、Electron 側で再現できない唯一の項目として特定した。

**決定（Issue #211）: 同じ保証を、親ではなくサイドカー自身に持たせる。**
ネイティブアドオンから Win32 Job Object を呼ぶ案は当面採らない。精度では
Job Object が上だが、**Windows でしか動かず Linux の CI で検査できない対策は、
「テストが無いまま実装だけが保証を持っている」という今回の状態を掘り直すことになる。**
Python 側なら `kill -9` で親を殺して子が終わることを CI で実際に走らせられる。

`backend/src/auto_scoring/adapters/parent_watchdog.py`:

| 項目           | 決定                                                                                                                                                       |
| -------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 有効化         | `--parent-pid <PID>` を渡したときだけ。**既定は無効**（[`sidecar-api.md`](./sidecar-api.md) §3.1）                                                         |
| 期限           | 親の死から 5 秒以内（`DETECTION_BUDGET_SECONDS`）。その 1/5 の間隔で監視する                                                                               |
| 生存判定       | PID そのものではなく **PID + プロセス開始時刻**。PID 再利用で別プロセスを親と誤認しない                                                                    |
| 判定不能のとき | 「生きている」と答える。動作中のサイドカーを誤って殺す方が、孤児を残すより高くつく（孤児は app-data のロックが受け止める）                                 |
| 終了の仕方     | daemon スレッドから `os._exit`。AI 呼び出しで数分ブロックしている最中でも期限を守るため                                                                    |
| Windows        | `ctypes` で `OpenProcess` + `GetProcessTimes`（依存の追加なし）。backend の CI は Windows Server 2025 で走るため、この分岐は CI で実際に動いている（下記） |

**app-data のロックは残す。** 監視は利用者の手間を減らすためのものであって、
正しさを担保しているのは §5.4 のロックの方である。監視が効かなかった場合
（判定不能、`--parent-pid` を渡さない起動、SIGKILL より早い異常）は、これまで
どおりロックが多重書き込みを止める。

**どこまで確かめたか（Issue #211）**:

- **監視そのものは Windows で動いている。** `Backend` ジョブは Windows Server 2025 の
  runner で走る（`.github/workflows/`）。`tests/test_parent_watchdog.py` の実プロセス検査は
  そこで実際に親を殺し、子が予算内に `exit code 4` で終わり `app-data` のロックを解放する
  ところまで通っている。`ctypes` の分岐（`OpenProcess` + `GetProcessTimes`）もそこで実行
  されている。Linux 側では `sys.platform` の分岐により mypy も pytest もこの分岐を通らない
  ので、**Windows 分岐の検証は CI の Windows ジョブが唯一の根拠**である。
- **製品としての経路は未検証。** 配布物（PyInstaller onedir）+ Electron main +
  タスクマネージャーからの End Task、という実際の並びを Windows 実機で通した人はいない。
  CI で確かめたのは `python.exe` の親子だけである。

**cut-over の条件（未達）**: 「強制終了しても次回の起動が失敗しないこと」を
**Windows 実機で、配布物と Electron supervisor の組み合わせで確認するまで移行しない**。
supervisor 側から `--parent-pid` を渡す配線自体がまだ無い（#201 Phase 2 以降）。

### 5.4 二重起動

**決定: 2 つ目のインスタンスは起動を明示的に拒否する。**

SQLite を 2 プロセスが同時に書くこと自体を防ぐ仕組みは既にある:
`auto_scoring.adapters.data_root_lock.acquire_data_root_lock` が `app-data/.lock`
に **OS レベルの排他ロック**（Windows は `msvcrt.locking`、POSIX は `fcntl.flock`）
を取り、`create_app` がその成否で起動を決める。ロックの所有者はカーネルなので、
プロセスが死ねば必ず解放される（stale lock の掃除は不要）。

本 Issue で足したのは、それを**ユーザーに説明できる形にする**部分だけ:

1. サイドカーは `DataRootLockedError` を捕まえて **exit code 3**
   （`ALREADY_RUNNING_EXIT_CODE`）で終了する。他の起動失敗（1）と区別できる。
2. supervisor はその exit code を `SidecarFailure.alreadyRunning` に写像し、
   「Auto-Scoring はすでに起動しています」と表示する。

named mutex による単一インスタンス化は**採用しない**。ロックの正本が
「データを実際に書くプロセス」の側にある方が正しく、Flutter 側にもう 1 つ
別の排他機構を置くと、2 つが食い違う状態（mutex は取れたがロックは取れない、
またはその逆）を新たに作ることになる。

副次的な結果として、`--app-data-dir` を明示的に分ければ 2 つ目のインスタンスは
安全に動く（それぞれ別の DB・別の動的ポート）。これは開発とテストのための
経路で、配布物の既定ではない。

### 5.5 ログ

| 項目           | 決定                                                         |
| -------------- | ------------------------------------------------------------ |
| 場所           | `%LOCALAPPDATA%\Auto-Scoring\app-data\logs\sidecar.log`      |
| ローテーション | 5 MiB ごと、3 世代保持（上限 20 MiB）。`RotatingFileHandler` |
| 出力先         | ファイル **と** stderr の両方                                |
| トークン       | `_RedactingFilter` が全ハンドラで `***` に置換               |
| 答案本文       | **書かない**（下記）                                         |

ファイルログが必要な理由: Flutter の supervisor は子プロセスの stdout/stderr を
drain する（読まないとパイプが詰まってサイドカーが書き込みでブロックする）。
配布物では stderr の行き先が無いので、ファイルが唯一の恒久的な記録になる。

サイズ基準（時間基準ではない）にしたのは、利用が集中的だから — 1 日で 1 クラス分、
その後 1 週間何もない、という使われ方をする。

**生徒答案本文をログに書かない（簡易設計書 §28）**: これは規律であって
フィルタで機械的に落とせるものではない（任意の日本語文字列を「答案本文」と
判定する手段が無い）。実際の運用は次のとおり:

- 現状 `backend/src/auto_scoring/` のログ出力は、ID・ファイルパス・状態・
  ジョブ結果のみで、認識テキストや答案本文を渡している箇所は無い。
  認識結果・採点結果の本文は DB にのみ保存する（§18・§19）。
- 例外は `codex_app_server_provider.py` の 1 か所で、一時ワークスペースの削除に
  失敗したとき「答案画像がディスクに残っているかもしれない」と**パスだけ**を
  記録する。中身は出さない。
- トークンは `_RedactingFilter` が多層防御として落とす。

新しくログを足すときは、ID とパスだけを渡す。

---

## 6. アンインストール時のデータ

**決定: 既定では残す。ただしアンインストーラーが削除するか尋ねる。**

`installer/auto-scoring.iss` の `CurUninstallStepChanged` が
`%LOCALAPPDATA%\Auto-Scoring` の削除確認ダイアログを出す（既定の選択は
**「いいえ」= 残す**）。サイレントアンインストールでは尋ねず、必ず残す。

理由:

- **既定が「残す」**: そのディレクトリには取り込んだ答案 PDF・採点結果・
  レビュー履歴の唯一のコピーが入っている（§23・§27）。アンインストール
  （バージョン更新時の in-place upgrade を含む）が 1 学期分の採点を消せる
  状態にはできない。
- **それでも尋ねる**: 同じデータは生徒の個人情報でもある（§26）。PC を
  手放すときに、`%LOCALAPPDATA%` を手でたどらせるのではなく、正規の手段で
  消せる必要がある。

インストール先ディレクトリ自体は通常どおり削除される。アプリは自分の
インストールディレクトリへ書き込まないので、消し残しは出ない。

---

## 7. 検証（CI）

Windows 成果物は Linux では作れないので（PyInstaller はクロスコンパイル
できず、`flutter build windows` も動かない）、**検証はすべて
`.github/workflows/ci.yml` の `Package (Windows)` job**（`windows-latest`）で行う。
既存の `Quality` job には手を入れていない。

| ステップ                          | 内容                                                               |
| --------------------------------- | ------------------------------------------------------------------ |
| `pnpm run package:sidecar`        | PyInstaller onedir バンドルを作る                                  |
| `pnpm run package:sidecar:smoke`  | **作った exe を実際に起動して検証**（下記）                        |
| `flutter build windows --release` | Flutter release ビルド                                             |
| `pnpm run package:installer`      | Inno Setup で unsigned インストーラーを作る                        |
| `upload-artifact`                 | `auto-scoring-installer-unsigned` と `auto-scoring-sidecar-bundle` |

### 7.1 smoke test が必要な理由

PyInstaller は **hidden import の漏れでビルドを失敗させられない**。
足りない module・data file・ネイティブライブラリは、Python の無いマシンで
**凍結された exe を実行したときにだけ**表面化する。
`scripts/smoke-test-sidecar.ps1` がその実行を担う:

1. `--self-test` — 遅延 import されるネイティブ依存（OpenCV / pdfium /
   reportlab）を明示的に import する。通常の起動と `/healthz` はこれらに
   一切触れないので、**バンドルが壊れていても起動と疎通は成功してしまう**。
   実際に壊れるのは、ユーザーが最初の答案 PDF を入れた瞬間になる。
2. 実起動 — `--port 0` で起動 → ハンドシェイクを parse → `/healthz` が 200 →
   トークン付きの `/score` が 200 → トークン無しの `/score` が 401 →
   `database.sqlite` が作られている（= マイグレーションがバンドル内で走った）→
   `logs/sidecar.log` にトークンが漏れていない → kill → **そのポートで
   もう何も応答しない**。

ローカルで同じことを走らせるには `pnpm run package:sidecar:smoke`（Windows）。

**push 前に Linux でも走らせること。** `pnpm run package:sidecar` は Linux でも
Linux バイナリを作れるので、同じ `.ps1` をそのまま流せる:

```bash
pwsh -NoProfile -File scripts/smoke-test-sidecar.ps1 \
  -SidecarPath backend/dist/auto-scoring-sidecar/auto-scoring-sidecar
```

上の 2 も含め全ステップが Linux でも走るので、**スクリプト自身のバグ**（構文、
strict mode 違反、PowerShell の読み取り専用自動変数との名前衝突）はここで潰れる。
実際 `$pid`（`$PID` は現在のプロセス ID を持つ読み取り専用の自動変数で、変数名は
大文字小文字を区別しない）への代入が CI まで到達し、**バンドル自体は全チェックを
通過したあとで** job を落とした。同じ手順を手で実行しても、スクリプト自身のバグは
絶対に見つからない。

Linux のリハーサルで covered できないのは `.exe` 拡張子と、初回実行時の Windows
Defender のスキャン（`-TimeoutSeconds` の既定値が大きい理由）だけ。

### 7.2 Dart 側のテスト

プロセス起動・FFI・ファイルシステム・時刻はすべて `SidecarPlatform` として
注入するので、**Windows 向けのライフサイクル全体が Linux の `flutter test` で
検証できる**:

| ファイル                                            | 対象                                                                                                                                                                               |
| --------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `app/test/sidecar_supervisor_test.dart`             | 状態遷移全部（起動 / handshake 競合 7 パターン / health poll / timeout / 即時終了 / already running / crash / 再起動 / shutdown）。時計は fake で進めるので 60 秒の timeout も一瞬 |
| `app/test/sidecar_paths_test.dart`                  | インストール後の Windows レイアウトと開発時 fallback のパス解決                                                                                                                    |
| `app/test/startup_gate_test.dart`                   | スプラッシュ / エラー画面 / 再起動ボタン / 終了時 kill / トークンを描画しないこと                                                                                                  |
| `app/test/sidecar_supervisor_integration_test.dart` | **実サイドカーに対して** dynamic port・process cleanup・crash recovery・二重起動拒否（tag: `sidecar`）                                                                             |

`flutter test -x sidecar` で実サイドカー起動テストを除外できる（`uv` の無い環境向け）。

### 7.3 Issue #57: 生存判定の緩さと、未確定の flaky（調査中）

`sidecar_supervisor_integration_test.dart` の
`shutdown releases the port and the app-data lock` が Windows CI で不定期に
`Expected: false / Actual: <true>` で落ちる（Issue
[#57](https://github.com/HIKARU0627/Auto-Scoring/issues/57)、PR #58）。
**真因は未確定のまま**である。誤った分析を 2 回積んだので、確定した事実と
未確定の事実を分けて記録する。

#### 実測で否定された仮説（どちらも誤り）

- **「並行実行中の別テストのサイドカーが解放直後のポートを掴んだ」** —
  判定をセッショントークン付きの保護されたエンドポイント（`GET /tests`）へ
  変えたあとも同じ形で落ちた。`/tests` は
  `protected = APIRouter(dependencies=[Depends(require_token)])` 配下で認証
  必須、トークンは `secrets.token_urlsafe(32)`（256bit）を
  `hmac.compare_digest` で比較する（`api/auth.py`）。**別インスタンスがこちらの
  トークンで 2xx を返すことはあり得ない。**
- **「venv ランチャーの孫プロセスが生き残って応答していた」** — テスト自身に
  計装を入れて Windows CI で 2 件再現させたところ、失敗した瞬間に、ポートを
  listen しているプロセスも、`python|auto-scoring` にマッチするプロセスも、
  このテストの app-data を CommandLine に持つプロセスも、**1 つも存在しなかった**。
  ただしこの観測はレポート収集時点のもので、レポートの最初の一手が返るまでに
  数百ミリ秒かかる。**「判定が走った瞬間に誰もいなかった」ことの証明ではない。**

#### 確定した事実: 旧判定には実在する緩さがあった

`test/sidecar_probe_test.dart` が自前サーバーに対して実測している:

| 相手の応答                                | 旧判定      | 現判定      |
| ----------------------------------------- | ----------- | ----------- |
| 200 + JSON 空配列（生きているサイドカー） | serving     | serving     |
| 200 + ボディ無し                          | **serving** | not serving |
| 204 No Content                            | **serving** | not serving |
| 200 だがボディが配列でない                | not serving | not serving |
| accept 直後に切断                         | not serving | not serving |
| ヘッダ途中で切断                          | not serving | not serving |
| ヘッダ完結・ボディ切り詰め                | not serving | not serving |
| 401（別インスタンス）                     | not serving | not serving |

旧判定は生成クライアントの `listTests()` が例外を投げるかどうかだけを見ていた。
dio の既定 `validateStatus` はあらゆる 2xx を通し、`listTests` はボディが無ければ
`const []` を返して例外を投げない。そのため **200 + 空ボディと 204 を
「サーブしている」と誤読していた**。判定は `test/sidecar_probe.dart` の
`sidecarStillServing` に切り出し、生の HTTP で
**「200 かつ JSON 配列のボディ」だけ**を serving と数えるようにした。

#### 未確定: CI で観測された `true` の真因

上の表のとおり、**プロセス終了中の socket が出す形は旧判定でも正しく
not serving と判定されていた**。したがって「切れかけた接続を成功と誤読した」
だけでは観測を説明できない。厳密化は実在した欠陥を潰したが、**CI で起きた
ことの原因だと断定する根拠は無い**。

厳密化後、flake-hunt（Windows 6 leg × 12 反復 = 72 サンプル）を 2 回走らせて
いずれも再現しなかったが、**これは根拠として弱い**。緩い判定のままでも直前の
90 サンプルで再現しておらず（再現したのはその前の 58 サンプル中 2 件）、
陰性が出ること自体に前科がある。計装を足した前後で再現率が落ちたことから、
**計装自体がリクエスト経路にイベントループのホップを足して窓をずらしている
（観測者効果）**疑いもあり、切り分けられていない。

#### 受入条件を直接守る assertion

ポート越しの応答では上記の曖昧さから逃れられないので、
**shutdown 前に listen socket を所有していたプロセスが、shutdown 後に消えて
いること**を、プロセスに直接聞く assertion を足した（`tasklist` / `ps`）。
原因が「短命な生存者」であっても、これは決定的に検出できる。あわせて、
判定が `true` を返した場合と、そのプロセスが生きていた場合に、証拠
（生のステータス・ヘッダ・ボディ長、ポートの所有 pid とその CommandLine、
この app-data を持つプロセス全部、サイドカーらしきプロセス全部）を CI ログへ
出す計装を残してある。**Issue #57 は open のままなので、次に再現したときに
証拠が残る。**

#### 参考: 実行ファイルの形が本番とテストで違う

Windows CI 上の実測（正常終了時、3 回ずつ）:

- `backend/.venv/Scripts/auto-scoring-sidecar.exe`（テストが起動する）は
  トランポリン → venv の `python.exe` → ベースインタプリタの 3 段で、
  **listen socket を所有するのは孫**。supervisor が `kill` して `exitCode` を
  待つのは先頭のプロセスだけ。
- `backend/dist/auto-scoring-sidecar/auto-scoring-sidecar.exe`（利用者が動かす、
  PyInstaller **onedir**）は**単一プロセス**で、spawn した pid 自身が socket を
  所有する。

どちらも `TerminateProcess` の 1ms 後には連鎖ごと消えていた。この違いは
「本番では `kill` + `exitCode` の待ちが完全な保証になるが、テストが起動する
形では孫のティアダウンが非同期で保証されない」ことを意味する。真因が未確定
なので、これが今回の flaky と関係するかどうかも未確定である。

#### 副次的に直した、同種の前提

- `sidecar_api_client_test.dart` の
  `a sidecar that is not running surfaces as unavailable` は、エフェメラル
  ポートを bind → close して「空いているポート」を得ていた。空いているのは
  誰かが取るまでで、`--port 0` のサイドカーに配られるのはまさにそのポート。
  どの OS のエフェメラル範囲より下で `--port 0` が絶対に当たらない固定ポート
  （1）に変えた。
- `leaves no handshake file holding the token on disk` は `%TEMP%` 全体を舐めて
  いた。`%TEMP%` はマシン全体で共有され、中断された過去の実行や実アプリの
  セッションが残したディレクトリまで拾う。テスト実行中に**増えた**分だけを
  見るようにした。

### 7.4 Electron パッケージの検証（CI と自動テスト、Issue #265）

Electron 版配布物の導入に伴い、CI の `Package (Windows)` ジョブおよびローカル自動テストに以下を追加した。

| ステップ                          | 内容                                                                                         |
| --------------------------------- | -------------------------------------------------------------------------------------------- |
| `pnpm install --frozen-lockfile`  | `--filter auto-scoring` を外し、workspace の `desktop/` と `electron-builder` も含めて復元   |
| `pnpm run package:electron`       | `desktop/` をビルドし、`electron-builder --win` でインストーラと `win-unpacked` を生成       |
| `pnpm run package:electron:smoke` | `scripts/smoke-test-electron-package.ps1` で実起動・データ描画・強制終了時孤児防止を自動検査 |
| `upload-artifact`                 | `auto-scoring-electron-installer-unsigned`（`desktop/dist/*-unsigned.exe`）                  |

`scripts/smoke-test-electron-package.ps1` が検証する 2 つの柱:

1. **実データ描画スモークテスト (`desktop/e2e/smoke-packaged.spec.ts`)**:
   Playwright 経由でパッケージ版 exe（`win-unpacked`）を起動し、ウィンドウの存在だけでなく以下を検査する:
   - サイドカーが正常起動し lifecycle status が `ready` になること
   - `[data-testid="home-error"]` が**表示されていないこと**（CSP や API 通信阻害の検出）
   - API 応答由来のダッシュボード要素（`[data-testid="home-next-up"]`）が**表示されること**
   - セッショントークン等の秘匿情報が画面テキストに漏洩していないこと
2. **強制終了時孤児防止テスト (UG-01/02, Issue #211)**:
   パッケージ版 exe をバックグラウンド起動し、`--parent-pid` 付きで起動されたサイドカープロセスと待受ポートを特定した上で、Electron 親プロセスをタスクマネージャ相当（`Stop-Process -Force` / `kill -9`）で強制終了する。親監視 watchdog が 15 秒以内にサイドカーを道連れ終了させ、ポートが解放されることを検査する。

**変異検査 (Mutation Testing)**:
同梱された `sidecar/` ディレクトリを一時的に改名または削除すると、Part 1 ではサイドカーが `executableMissing` で起動失敗して `ready` に達せず Playwright が失敗し、Part 2 でもサイドカー子プロセスが見つからず失敗する。これによりテストが実際に機能していることを確認できる。

---

## 8. コード署名（人間だけが行う手順）

**証明書は未準備**。Issue #24 の対象外（購入はユーザー側手配事項、
技術スタック決定書 §4）。したがって:

- **CI が作るのは unsigned の test artifact だけ**。ファイル名も
  `Auto-Scoring-Setup-<version>-unsigned.exe`（Flutter 版）および
  `Auto-Scoring-Electron-Setup-<version>-unsigned.exe`（Electron 版）と明示する。
- **リポジトリにも CI secrets にも、証明書・秘密鍵・パスワードを置かない。**
  `installer/auto-scoring.iss` に `SignTool=` ディレクティブは**書かない**
  （書けば CI が署名を試みることになる）。electron-builder 側でもコード署名は行わない。
- 署名は、CI が作った artifact に対して**人間が手元で**行う。

証明書が用意できたあとの手順（**人間のみ**、CI では実行しない）:

1. CI の `auto-scoring-installer-unsigned` artifact をダウンロードする。
2. 証明書（`.pfx`）を、リポジトリの外・共有されないローカルの場所に置く。
3. 署名する:

   ```powershell
   signtool sign /fd SHA256 /td SHA256 /tr http://timestamp.digicert.com `
     /f <証明書のパス>.pfx /p <パスワード> Auto-Scoring-Setup-<version>-unsigned.exe
   ```

   タイムスタンプ（`/tr`）は必須。無いと証明書の有効期限が切れた瞬間に
   既存の署名まで無効になる。

4. `signtool verify /pa /v <exe>` で検証し、署名済みの名前へ変更して配布する。

CI で署名するようにする場合は、`.pfx` を base64 で GitHub Secrets へ置くのが
一般的な手だが、**それは別 Issue での判断**とする（鍵の露出面が増えるため、
簡易設計書 §26 の観点で明示的な合意が要る）。

---

## 9. OCR / AI の API キー

技術スタック決定書 §1.1 の決定どおり、**API キーを持つのは Python サイドカー
だけ**で、Flutter は一切保持しない。UI はビルド成果物として配布されるため
鍵を置けない。

| 種別   | 置き場所                                                                               |
| ------ | -------------------------------------------------------------------------------------- |
| 例値   | リポジトリの `.env.example`（実値は絶対に入れない）                                    |
| 実値   | `backend/.env.local`（git-ignored）、または **OS の資格情報ストア**（`keyring`。§9.1） |
| 配布物 | **同梱しない**。インストーラーにも exe にも入らない                                    |
| ログ   | **出さない**（§5.5）。資格情報ストアから読んだキーも同じ扱い（`api.secret_redaction`） |

配布物に鍵が入らないことは構成上保証される: `packaging/auto-scoring-sidecar.spec`
の `datas` は `migrations/` と `alembic.ini` と各ライブラリの package data のみで、
`.env*` を一切拾わない。`installer/auto-scoring.iss` の `[Files]` も
`app/build/windows/.../Release` と `backend/dist/auto-scoring-sidecar` の
2 つのビルド出力だけを参照する。

### 9.1 インストール後にキーを設定する（Issue #96）

配布物には `.env.local` もシェルも無い。**設定画面の「API キー」タブ**で
利用者が自分のキーを入れ、サイドカーが OS の資格情報ストアから読み戻す。

| 項目                | 決定                                                                                                                                           |
| ------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| 方式                | **A（利用者が自分のキーを入れる）**。開発者がプロキシを運営する案 B は採らない                                                                 |
| 保存先              | OS の資格情報ストア。Windows は資格情報マネージャー（DPAPI 保護）。Python の `keyring` 経由                                                    |
| サービス名          | `Auto-Scoring`。エントリ名は環境変数名と同じ（`AUTO_SCORING_OPENROUTER_API_KEY`）                                                              |
| 既定の provider     | **OpenRouter**。鍵 1 本で複数モデルに届くので、利用者に作らせるアカウントが 1 つで済む                                                         |
| 設定できる provider | OpenRouter と OpenAI は API キー、Gemini は Vertex AI（ADC。キー欄は無い）、Codex はログインセッション（Issue #386）。利用順も画面で並べ替える |
| 既定のモデル        | `google/gemini-2.5-flash`（`.env.example` と一致することをテストで固定）                                                                       |
| 再表示              | **しない。** キーは保存済みかどうかと、どこから読んだかだけを出す。モデル・GCP プロジェクト・リージョンは秘密でないので表示する                |
| 未設定のとき        | **起動する。** 取込・手動添削・PDF 出力は動く。採点だけが「API キーが未設定です」で止まる                                                      |

**優先順位は変数の種類で違う。**

| 対象                                 | どちらが勝つか                                                       | 理由                                                                                                                                                                                          |
| ------------------------------------ | -------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| API キー                             | **資格情報ストア**                                                   | 画面で入れたキーが使われないと、入れた意味が無い                                                                                                                                              |
| `AUTO_SCORING_AI_GRADING_TRANSPORT`  | **画面で保存した順番**（無ければ環境変数、次に保存済みキーから導出） | Issue #386 で利用順も画面から設定できるようにした。押しても効かない設定を置かないため。画面に「保存した順番を削除（環境変数に戻す）」があり、#96 の「開発機は環境変数で決められる」保証は残る |
| モデル・GCP プロジェクト・リージョン | **資格情報ストア**（画面で保存した値）。無ければ環境変数、次に既定   | 秘密ではない設定は画面で編集でき、その値が使われる                                                                                                                                            |
| prompt version                       | **環境変数**                                                         | 開発者向けの固定値。画面には出さない                                                                                                                                                          |

画面はどの層の値が効いているかを「どこから読んだか」つきで表示する。開発機は
`.env.local` と資格情報ストアの両方を持ちうるので、「キーがある」だけでは
どちらが使われているか分からない。

**バックエンドが無い環境で落ちない。** Linux の開発機と CI には Windows
資格情報マネージャーが無く、Secret Service も無いことがある。読み取りは
「何も保存されていない」に縮退し、サイドカーは今までどおり環境変数だけで
起動する。**保存だけは失敗を返す**（HTTP 503）——「保存した」と言われた
キーが次の起動で消えているのが、この画面にとって最悪の結果だから。

**配布物では `keyring.backends` を hidden import に入れる。**
`keyring` はバックエンドを entry point 走査で見つけるので、PyInstaller の
静的解析では拾えない（`packaging/auto-scoring-sidecar.spec`）。抜けると、
**唯一これが必要なプラットフォームでだけ**保存が黙って効かなくなる。

**疎通確認。**「保存できた」は「使える」ではない。設定画面のボタンが
provider ごとの無課金の確認を 1 回行い、成功・認証失敗・ネットワーク不通・
provider エラー・残高切れ・**ホスト側の認証欠如**を別々に表示する（Issue #386）:
OpenRouter は `GET /api/v1/key`、OpenAI は `GET /models`、Gemini は ADC の
トークン解決、Codex は `codex` 実行ファイルの有無。

**保存しても、再起動するまで採点には効かない。** provider チェーンは
サイドカー起動時に 1 回だけ組む。画面はそれを説明する代わりに、
`SidecarSupervisor.start()`（§5 の再起動経路）を呼んで自分で再起動する。

費用の可視化（1 枚あたり・月間累計）は Issue #96 の範囲外。[Issue #187](https://github.com/HIKARU0627/Auto-Scoring/issues/187) で扱う。

---

## 10. clean VM smoke test（人間が行う受入確認）

CI が自動化できるのは §7 まで。受入条件「clean Windows VM で installer から
起動し、Python/Flutter SDK なしで登録から PDF 出力まで実行できる」は、
**Python も Flutter SDK も入っていない Windows VM** を用意して人間が確認する。

| #   | 手順                                                                                                                           | 期待結果                                                                                                                                                             |
| --- | ------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | clean な Windows 11 VM を用意（Python / Flutter / Visual Studio / **Visual C++ 再頒布可能パッケージ** いずれも未インストール） | 「アプリと機能」に `Microsoft Visual C++ ... Redistributable` が無いことを確認する（§1.1）                                                                           |
| 2   | CI の `auto-scoring-installer-unsigned` artifact を展開して実行                                                                | SmartScreen 警告 →「詳細情報」→「実行」でインストーラーが起動する（unsigned なので正常）                                                                             |
| 3   | 既定のまま完了                                                                                                                 | `%LOCALAPPDATA%\Programs\Auto-Scoring\` に展開され、`sidecar\` が存在する                                                                                            |
| 4   | スタートメニューから起動                                                                                                       | スプラッシュ →（初回はマイグレーションで数十秒）→ ホーム画面「backend: ok」。**`vcruntime140.dll が見つかりません` 等のダイアログが出ないこと**（§1.1）              |
| 5   | `%LOCALAPPDATA%\Auto-Scoring\app-data\` を確認                                                                                 | `database.sqlite` と `logs\sidecar.log` がある。ログにトークンが無い                                                                                                 |
| 6   | 設定 →「API キー」タブで OpenRouter のキーを入れて保存 → 「疎通を確認する」→ 「いま再起動して反映する」                        | 保存後に値が**再表示されないこと**。疎通が成功と出ること。再起動後、採点不可バナーが消えること。資格情報マネージャーに `Auto-Scoring` のエントリができること（§9.1） |
| 7   | テスト登録 → 答案取込 → レビュー → PDF 出力                                                                                    | `app-data\exports\` に添削済み PDF が出る                                                                                                                            |
| 8   | もう一度アプリを起動（二重起動）                                                                                               | 2 つ目は「Auto-Scoring はすでに起動しています」。サイドカーは 1 つのまま（§5.4）                                                                                     |
| 9   | タスクマネージャで `auto_scoring_app.exe` を強制終了                                                                           | `auto-scoring-sidecar.exe` も一緒に消える（§5.3）                                                                                                                    |
| 10  | もう一度起動 → ウィンドウを閉じる                                                                                              | `auto-scoring-sidecar.exe` が残らない。ポートも解放される（§5.2）                                                                                                    |
| 11  | テスト登録画面を開いた**まま**、タスクマネージャで `auto-scoring-sidecar.exe` だけを強制終了                                   | 開いていた画面の**上に**エラー画面 + 再起動ボタンが出る（下に隠れない）。押すとホーム画面へ復帰する（§5・簡易設計書 §24）                                            |
| 12  | アンインストール                                                                                                               | データ削除の確認が出る。「いいえ」で `%LOCALAPPDATA%\Auto-Scoring\` が残る（§6）                                                                                     |

実施したら、**実行したコマンド・実際の結果・使った artifact の CI run 番号**を
Issue #24 または本書に追記する。

---

## 11. 上位ドキュメントへの反映

| 文書                                     | 反映内容                                         |
| ---------------------------------------- | ------------------------------------------------ |
| `technology-stack.md` §1.2               | 子プロセスの起動・kill・バンドルの実装先を本書へ |
| `technology-stack.md` §4                 | MSIX ではなく Inno Setup を採用（理由は §2）     |
| `sidecar-api.md` §3                      | ハンドシェイクはファイル経由で確定（§4）         |
| `answer-intake-and-preprocessing.md` §10 | `app-data/` の格納場所が確定（§3）               |
