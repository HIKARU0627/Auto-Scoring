# Linux デスクトップでの開発起動とスクリーンショット

Linux 開発機でアプリを実際に描画し、画面を目で確認・スクリーンショット取得する
ための手順（GitHub Issue #62）。UI 改良フェーズの前提となる足場である。

## 0. これは配布対象ではない

**`app/linux/` は開発用の足場であって、Linux 版を製品として配布する意図はない。**

- **MVP の配布対象は Windows のみ。** macOS / Linux 配布は Issue #24 で明示的に
  対象外とされている（[`windows-distribution.md`](./windows-distribution.md)、
  [`technology-stack.md`](./technology-stack.md) §7-1）。この Issue はその決定を
  変更しない。
- `app/linux/` が存在することを「Linux 対応済み」と読まないこと。次のものは
  **一切用意していない**:
  - Linux 向けのパッケージング（PyInstaller のサイドカーバンドル、インストーラー、
    署名）。`installer/` と `scripts/build-windows-installer.ps1` は Windows 専用。
  - Linux でのサイドカー同梱。開発起動時は `backend/.venv` の console script を
    直接叩いている（§3）。配布物の `sidecar/` レイアウトは Linux には無い。
  - orphan プロセス防止。Windows の Job Object に相当する仕組みは非 Windows では
    no-op のまま（§5.1）。
- CI の配布ジョブ（`Package (Windows)`）にも Linux は入れていない。Linux ビルドを
  CI へ足すかは §6 に判断材料だけ置いてある。

配布対象を Linux へ広げるなら、それは本 Issue の続きではなく独立した Issue に
なる。上の 4 点がそのときの作業項目である。

## 1. 前提パッケージ

Ubuntu 24.04 での実測。`flutter doctor` の `[✓] Linux toolchain` はこれで通る。

```bash
sudo apt-get install -y \
  clang cmake ninja-build pkg-config libgtk-3-dev liblzma-dev \
  lld \
  imagemagick
```

| パッケージ                                                              | なぜ要るか                                                                                                                                                                                          |
| ----------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `clang` `cmake` `ninja-build` `pkg-config` `libgtk-3-dev` `liblzma-dev` | Flutter Linux desktop の公式必須ツールチェーン。前 4 つは `flutter doctor` が名指しで要求する                                                                                                       |
| `lld`                                                                   | **`flutter doctor` は要求しないが、無いとビルドが落ちる。** `pdfrx` → `pdfium_flutter` → `pdfium_dart` が native assets の build hook で `libpdfium.so` を取り込むため、Dart 側がリンカを探す（§2） |
| `imagemagick`                                                           | スクリーンショットの `import` コマンド。§4 でしか使わない                                                                                                                                           |

日本語フォントは `fonts-noto-cjk`（Ubuntu Desktop に既定で入る）が要る。無いと
UI の日本語が豆腐になり、スクリーンショットを見る意味が無くなる。

システムライブラリの追加が要らなかった依存も記録しておく:

- **`file_picker`** — Linux 実装（`file_picker_linux`）は XDG Desktop Portal を
  D-Bus 越しに呼ぶだけで、ネイティブプラグインを持たない。実際にダイアログを出す
  には `xdg-desktop-portal` とそのバックエンド（GNOME なら
  `xdg-desktop-portal-gnome`）が動いている必要がある。デスクトップセッションには
  既定で入っている。
- **`pdfrx`** — pdfium をシステムから探さず、ビルド時に `libpdfium.so` を
  ダウンロードして `bundle/lib/` に置く（§2）。開発機に pdfium を入れる必要は無い。

## 2. ビルド

```bash
cd app && flutter build linux --debug
```

成果物は `app/build/linux/x64/debug/bundle/`。`bundle/lib/libpdfium.so` が
できていれば pdfrx のネイティブ側も通っている。

**初回ビルドはネットワークを使う。** `pdfium_dart` の build hook が
`bblanchon/pdfium-binaries` の GitHub Release から `libpdfium.so` を取得する。
取得済みなら以降は再利用されるので、2 回目からはオフラインで通る。

`lld` が無いと、この取得の前段でこう落ちる:

```text
ERROR: Target dart_build failed: Error: Failed to find any of [ld.lld, ld] in LocalDirectory: '/usr/lib/llvm-18/bin'
```

`lld-18` が `/usr/lib/llvm-18/bin/ld.lld` を置くので解消する。`binutils` の
`/usr/bin/ld` では駄目で、clang のツールチェーンディレクトリの中を見に来る。

### 2.1 `app/windows/` との関係

`app/linux/` は `flutter create --platforms=linux --org com.autoscoring .` の
生成物そのままで、`app/windows/` には手を触れていない。とくに
`app/windows/CMakeLists.txt` の MSVC ランタイム同梱の install 規則
（[`windows-distribution.md`](./windows-distribution.md) §1.1、Issue #24）は
無傷である。

`flutter create` は `app/.metadata` の `migration.platforms` を**上書きして
`windows` の行を消す**ので、両方が並ぶよう戻してある。`app/linux/` を作り直す
ときは同じ確認をすること:

```bash
# windows/ が 1 バイトも変わっていないこと
git status --porcelain app/windows/
# .metadata に windows と linux の両方が残っていること
grep -A1 'platform: windows\|platform: linux' app/.metadata
```

## 3. 起動とサイドカーの結線

```bash
cd app && flutter run -d linux
```

サイドカーは `app/lib/core/sidecar_paths.dart` の
`sidecarExecutableCandidates()` が解決する。Linux では配布用の `sidecar/` が
無いので、開発用フォールバックである `backend/.venv/bin/auto-scoring-sidecar`
に落ちる。`app/` から `flutter run` すると 2 番目の候補（`<cwd>/../backend/...`）、
リポジトリルートからバンドルを直接起動すると 3 番目の候補（`<cwd>/backend/...`）
に当たる。どちらも同じ実行ファイルなので、`uv sync` が済んでいれば動く。

正常なら、スプラッシュ（「バックエンドを起動しています...」）を抜けて
`backend: ok` とテスト登録／テスト一覧／答案取込のボタンが出るホーム画面になる。

## 4. スクリーンショット

```bash
./scripts/screenshot-linux-app.sh                 # app/build/linux-screenshot.png へ
./scripts/screenshot-linux-app.sh -o /tmp/ui.png  # 出力先を指定
./scripts/screenshot-linux-app.sh -s 6            # 撮影前の待ち時間を延ばす
```

スクリプトは 1 コマンドで、ビルド → 起動 → ホーム画面が出るまで待機 → 撮影 →
後片付け までを通しでやる。ビルドは差分ビルドなので最新なら素通りする。

待ち方は固定 sleep ではなく、次の 3 つが観測できるまでのポーリングにしてある。
遅いマシンで**黙ってスプラッシュ画面を撮ってしまう**のが一番困る失敗だからである。

1. `auto_scoring_app` という名前の X ウィンドウが **viewable になる**。ウィンドウは
   Flutter の first frame で初めて表示されるので（`app/linux/runner/my_application.cc`）、
   これ自体がエンジンの起動待ちを兼ねる。名前が引けるだけでは足りない。mutter が
   map するまでの一瞬は `Map State: IsUnMapped` で、そこでは `import` はまだ読めない。
2. **そのウィンドウが再描画されている**（§4.2）。ここを通らないと、撮れる画像が
   「今の画面」である保証が無い。
3. サイドカーが `/healthz` に答える。`SidecarSupervisor` が
   `SidecarStarting` を抜ける条件と同じもの。ポートは `--port 0` で動的に決まる
   ので、サイドカーの pid から `ss` で引いている。
   **listen しているだけでは足りない**（uvicorn は起動処理の前に bind するため、
   そこで撮るとスプラッシュが写る）。

出力先の PNG は**すべてのチェックを通ったときにしか書かない**。実行の最初に前回の
PNG を消すので、撮影後にそのパスにあるのは「今回撮れた1枚」か「何も無い」かの
どちらかであり、失敗した実行が古い画像を残すことはない。

### 4.1 デスクトップセッションが要る

**`Xvfb` などの仮想ディスプレイでは動かない。** 実測した挙動は次のとおり:

- Xvfb 上ではウィンドウが 1 つも作られない。`eglSwapInterval` が
  `EGL_BAD_SURFACE` を返し続け、Flutter が first frame を出せないため、
  `my_application.cc` の「first frame でウィンドウを表示する」に到達しない。
- 画面の色深度（`-screen 0 1280x720x24` / `x30`）や
  `LIBGL_ALWAYS_SOFTWARE=1` を変えても解消しなかった。Xvfb は深度 32 の visual
  自体は持っているので、visual が無いことが原因ではない。
- したがって、[`orca-remote-environment.md`](./orca-remote-environment.md) §1.1
  が Orca 本体について採った (a) `xvfb-run` は、このアプリには使えない。同 §1.1
  の (b)（デスクトップの Xwayland に相乗り）だけが選択肢になる。

スクリプトは (b) を前提に、`DISPLAY=:0` と、mutter がセッションごとに乱数名で
発行する `$XDG_RUNTIME_DIR/.mutter-Xwaylandauth.*` を実行時に解決する。
`GDK_BACKEND=x11` を明示するのは、放っておくと GTK が Wayland バックエンドを選び、
X のウィンドウが存在しなくなって `import` からも `xwininfo` からも見えなくなる
ためである。

**ログイン中の GNOME セッションが要る。** 無いときはこう落ちる:

```text
cannot reach the X display :0 -- is a desktop session logged in?
```

なお、入れ子の X サーバである **`Xephyr` の上ではこのアプリは描画できた**。Issue #73 の
検証で、ロック中のセッションの下でも `Xephyr :7 -ac -screen 1280x800` を立て、その上で
アプリが起動し、スプラッシュのスピナーが動き、ホーム画面まで到達してスクリーンショット
も撮れることを実測している（EGL はソフトウェア実装に落ち、`DRI3 error: Could not get
DRI3 device` の警告が出るが動く）。Xvfb との違いは実測事実として残しておく。

ただし Xephyr にはウィンドウマネージャもコンポジタも無いので、**このスクリプトが想定
する環境ではない**。タイトルバーは写らず、§4.2 のロック・非表示の経路はそもそも再現
できない。ここを正式な足場にするかどうかは別 Issue の判断であり、現時点の手順は (b) の
ままである。

### 4.2 撮れた画像が「今の画面」であることの保証

`import` が返すのは、コンポジタがそのウィンドウについて**最後に保持したフレーム**で
ある。mutter はウィンドウが画面に出ていない間フレームコールバックを止めるので、
Flutter は `eglSwapBuffers` で待たされ、そこで描画を止める。この状態でも `import` は
**エラーにならず**、止まった1枚を何度でも返す。

Issue #73 はこれを踏んだものである。別プロセスとして 3 回、待ち時間も `-s 2` /
`-s 15` / `-s 25` と変えて撮ったのに、**3 枚ともバイト単位で同一のスプラッシュ画面**に
なった。スプラッシュの `CircularProgressIndicator`（回転するスピナー）の角度まで
一致していたのが決め手で、ライブキャプチャでは起こり得ない。

**原因はセッションのロックである。** 撮影を始めた時点で未ロックでも、途中でアイドル
ロックが掛かれば同じことが起きる。ロック以外の経路は確認されていない。

#### スクリプトが保証すること

1. **起動前と、シャッターの直前・直後**: セッションがロック／ブランクしていないかを
   `org.gnome.ScreenSaver.GetActive` に聞く。起動前に聞くのは、30 秒待たされてから
   「再描画されていない」と言われるより、一文で理由が出たほうが早いからである。
   シャッターを挟んで 2 回聞くのは、**作業中にアイドルロックが掛かる**のが Issue #73 の
   形そのものだからで、撮影の最後の数秒に入り込んだロックはこれで落ちる。答えが得られ
   ない環境（GNOME がバスに居ない）では「ロックされていない」と読む。ここは早期の
   診断であって、保証しているのは次の 2 つである。
2. **撮る前**: サイドカーを待つ前に、ウィンドウが再描画されていることを確かめる。
   スプラッシュのスピナーは必ず動くので、0.2 秒間隔で 3 枚撮り、**連続する 2 区間の
   両方で絵が変わること**を要求する。1 区間では足りない。起動直後に固まった
   ウィンドウでも「素のウィンドウ → 描けた 1 枚」の 1 回だけは変わるので、1 回の
   変化を「生きている」と読むと固まったウィンドウを通してしまう。
3. **撮った後**: 撮れた 1 枚が、起動中に採ったスプラッシュのフレームと一致しないこと
   を確かめる。スプラッシュ→ホームで絵は必ず変わるので、一致したならチェックの後に
   描画が止まったということになる。

どれかが通らなければ、画像を書かずに落ちる。2. なら次のメッセージが出る。

```text
timed out after 30s waiting for the window to be repainted
the window is not being repainted, so `import` can only return a stale frame.
mutter stops presenting a window that is not on screen: unlock the session and
wake the display, and make sure the window is neither minimised nor behind
another workspace. See docs/linux-desktop-development.md 4.2.

The other way to reach a screen that never moves is the "already running" error
screen, which replaces the splash when a leftover sidecar still holds app-data:
`pgrep -af auto-scoring-sidecar` (docs/linux-desktop-development.md 5.1).
```

後半の断りは、居残りサイドカーで起動に失敗したとき（§5.1）も画面が静止画になり、
同じチェックに引っ掛かるためである。

これで保証できるのは「撮影の直前まで描画が生きていた」ところまでである。チェックを
通ってから撮るまでの数秒の間に描画が止まった場合は 1. と 3. が拾うが、ホーム画面へ移った
直後に止まった場合までは切り分けられない。**同じ画面を撮り続けて md5 が変わらないこと
自体は異常ではない**（ホーム画面は静止画なので当然一致する）ことにも注意する。

#### 実測（Issue #73）

| 状況                   | `import -window auto_scoring_app`                                                               | `import -window root`                                 | スクリプト                                                        |
| ---------------------- | ----------------------------------------------------------------------------------------------- | ----------------------------------------------------- | ----------------------------------------------------------------- |
| ロック／ブランク       | **成功するが古いフレームを返す**（0.3 秒間隔 38 枚中 37 枚が一致）                              | `unable to read X window image 'root'` で**失敗する** | 起動前にロックを検出して即座に失敗。画像は書かない                |
| 最小化                 | **成功して固まったフレームを返す。**しかも最後に見えていた画面ですらない（最小化の途中の 1 枚） | 成功する（写るのは今表示中の画面）                    | 「not being repainted」で失敗。画像は書かない                     |
| 別ワークスペースに退避 | **成功して、最後に見えていたフレームを返し続ける**                                              | 成功する（写るのは今表示中の画面）                    | 「not being repainted」で失敗。画像は書かない                     |
| 描画が生きている       | 毎回変わる                                                                                      | 成功                                                  | ホーム画面が撮れる（スプラッシュ→ホーム→別画面で md5 が全部違う） |

**`xwininfo` の `Map State` はこの判定には使えない。** 最小化中も別ワークスペースでも
`IsViewable` のままで、`import` も成功する。見えていないことを X 側から知る手段が無い
のが、この事象が黙って通ってしまう理由である。だから「絵が動いているか」を直接見る。

ロック中かどうかはこれで判る。

```bash
loginctl show-session "$(loginctl list-sessions --no-legend | awk 'NR==1{print $1}')" -p Active -p LockedHint
gdbus call --session --dest org.gnome.ScreenSaver \
  --object-path /org/gnome/ScreenSaver --method org.gnome.ScreenSaver.GetActive
```

`LockedHint=yes` / `(true,)` ならロック中。`SetActive false` では解除できない
（パスワードが要る）ので、人がログインし直すしかない。

#### UI 作業中の運用

**UI 改良や UI/UX 評価の最中にセッションがロックされると、目視確認が静かに壊れる。**
スクリプトはエラーで止まるようになったが、`flutter run` で出しっぱなしにした画面を
そのまま見ている場合は気づけない。「変更が反映されていない」ように見えたときは、まず
ロックを疑うこと。

長い UI 作業に入る前に、画面ロック／ブランクまでの待ち時間を作業時間より長くしておくと
事故が減る（設定 → プライバシーとセキュリティ → 画面ロック）。**これはユーザーの
マシンの設定なので、エージェントが勝手に変更しないこと。** 必要なら人に依頼する。

### 4.3 公開リポジトリへの配慮

撮れるのはアプリのウィンドウ内だけで、ウィンドウタイトルは `auto_scoring_app`
固定なので、ローカルのユーザー名・ホスト名・ホームディレクトリのパスは写らない。
出力先の既定 `app/build/` は `.gitignore` 配下なので、うっかりコミットもしない。

**ファイル選択ダイアログや、パスを表示する画面を撮るときは中身を確認すること。**
リポジトリは公開されている。

## 5. Linux 固有の注意

### 5.1 サイドカーはアプリと一緒には死なない

`app/lib/core/child_process_group.dart` は **非 Windows では意図的に no-op**
である（Windows の Job Object 相当を用意していない）。アプリを `kill` で
落とすとサイドカーが生き残り、`app-data/` のロックを持ったままになる。
次の起動はスプラッシュを抜けられず、「Auto-Scoring はすでに起動しています。
終了コード: 3」のエラー画面になる。

ウィンドウを閉じて終了した場合は起きない。GTK の delete-event から
`didRequestAppExit` が走り、`SidecarSupervisor.shutdown()` がサイドカーを
明示的に kill するためである。

**`flutter run` の `q` では残る。** `q` はアプリのプロセスをそのまま停止させる
だけで、ウィンドウを閉じたときの経路を通らないので `didRequestAppExit` が
走らない。実測でも `q` で終了した後にサイドカーが 1 つ残った。`q` を使った
あとは次の起動の前に確認すること。

取り残しの確認と後片付け:

```bash
pgrep -af auto-scoring-sidecar
```

`scripts/screenshot-linux-app.sh` はアプリを専用のプロセスグループで起動し、
終了時にグループごと落として全員が消えるまで待つ。**他の worktree の
サイドカーまで巻き込む `pkill -f auto-scoring-sidecar` は使わないこと。**
並行して動いている別エージェントのテストを落とす。

### 5.2 app-data の場所

Linux では `$XDG_DATA_HOME/auto-scoring/app-data/`（既定
`~/.local/share/auto-scoring/app-data/`）。
[`windows-distribution.md`](./windows-distribution.md) §3 の表のとおり。
サイドカーのログは同ディレクトリの `logs/sidecar.log` にあり、結線がおかしい
ときはまずこれを見る。`/healthz` へのポーリングが数回で止まっていれば、
supervisor は `SidecarReady` に到達している。

### 5.3 無害なログ

起動時にこれらが出るが、いずれも動作に影響しない。

```text
Atk-CRITICAL **: atk_socket_embed: assertion 'plug_id != NULL' failed
Gdk-Message: Unable to load  from the cursor theme
```

`flutter doctor` の `Unable to access driver information using 'eglinfo'` も
同様で、`mesa-utils` が無いという情報表示にすぎない。ビルドにも実行にも要らない。

## 6. CI について（提案、未実施）

Linux ビルドの検証は CI に**入れていない**。判断材料だけ残す。

- 足すなら ubuntu runner（課金 1 倍）で `flutter build linux --debug` まで。
  既存の `Quality`（windows-latest）と `Package (Windows)` は触らない。
- 得られるのは「`app/linux/` の生成物が腐っていないこと」の検知だけ。
  §4.1 のとおり headless ではアプリを**描画できない**ので、起動確認・
  スクリーンショットまでは CI では取れない。
- 逆に、`app/linux/` は開発者が壊れたと気づいた時点で `flutter create` し直せば
  済むもので、壊れても配布物には影響しない（§0）。
- 判断が要るのは「ビルドの通りだけを守るために CI を 1 ジョブ増やすか」で、
  それはこの Issue の範囲を超える。必要になった時点で別 Issue にする。
