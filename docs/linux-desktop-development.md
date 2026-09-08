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
./scripts/screenshot-linux-app.sh -r /tests -t dark -w 700x720  # 画面・テーマ・幅（§4.4）
```

スクリプトは 1 コマンドで、ビルド → 起動 → 目的の画面が出るまで待機 → 撮影 →
後片付け までを通しでやる。ビルドは差分ビルドなので最新なら素通りする。

待ち方は固定 sleep ではなく、次の 3 つが観測できるまでのポーリングにしてある。
遅いマシンで**黙ってスプラッシュ画面を撮ってしまう**のが一番困る失敗だからである。

1. `auto_scoring_app` という名前の X ウィンドウが **viewable になる**。ウィンドウは
   Flutter の first frame で初めて表示されるので（`app/linux/runner/my_application.cc`）、
   これ自体がエンジンの起動待ちを兼ねる。名前が引けるだけでは足りない。mutter が
   map するまでの一瞬は `Map State: IsUnMapped` で、そこでは `import` はまだ読めない。
2. **そのウィンドウが画面に出ていて、スプラッシュから目的の画面へ実際に入れ替わる**
   （§4.2）。ここを通らないと、撮れる画像が「今の画面」である保証が無い。
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

**1. 画面から消えていないか、直接聞く。** mutter が描画を止める理由のうち、X とセッション
バスに聞けば即答が返るものが 3 つある。

| 何を             | どう聞くか                                 |
| ---------------- | ------------------------------------------ |
| ロック／ブランク | `org.gnome.ScreenSaver.GetActive`          |
| 最小化           | `_NET_WM_STATE` に `_NET_WM_STATE_HIDDEN`  |
| 別ワークスペース | `_NET_WM_DESKTOP` ≠ `_NET_CURRENT_DESKTOP` |

起動前・起動待ちの間・**シャッターの直前と直後**に聞く。とくに直前・直後の 2 回が要で、
起動を見張り終えてからシャッターを切るまでの数秒は他に見張るものが無く、そこで消えると
「読み込み途中のホーム画面」が撮れて信じられてしまう。答えが返らない環境（GNOME がバスに
居ない、まだウィンドウが無い）は「画面に出ている」と読む。ここは早い・正確な診断であって、
保証そのものは 2. が担う。

**2. スプラッシュがホーム画面へ入れ替わるのを見届ける。** アプリが起動オーバーレイを外すのは
サイドカーが `/healthz` に答えてからなので、**サイドカーが上がったのと同じかそれより後に
動いた画面**は、今も描かれている画面である。`/healthz` のポーリングとウィンドウの撮影を
同じループで回し、それぞれが起きた時刻を突き合わせる。

意図的にやらないことが 2 つある。

- **「1 つ前のフレームと違う」では受理しない。** スプラッシュの途中で固まったウィンドウも、
  固まるまでに何度も絵が変わっており、その変化はどれも本物である。できないのは
  「バックエンドが上がった後にもう一度変わる」ことだけで、見るべきはそこである。
- **動きを目撃することも要求しない。** 最初のサンプルを撮る時点でサイドカーが既に答えて
  いれば、ホーム画面はもう出ていて静止しており、健全な起動でも見せるものが残っていない。
  「最後に動いたのがサイドカーより後」なら、その動きを見ていなくても受理する。

許容差は 120 ms 取ってある。`serving_ms` は**こちらが**サイドカーの応答を見た時刻で、
アプリは同じエンドポイントを自分のペースで叩いており、こちらが記録するより 1 ポーリング分
早く動けるためである。**アプリのポーリング間隔ではなく、こちらの検出遅れだけを覆えばよい**
ので、`/healthz` はフレーム撮影よりずっと短い間隔で叩き、許容差を小さく保っている。

**3. 絵が止まってから撮る。** ホーム画面は出た直後に `backend: checking...` を出すので、
固定 sleep ではなく「`-s` 秒のあいだ絵が変わらなくなるまで」待つ。30 秒待っても止まらない
場合は、その旨を出したうえで撮る（動き続ける画面も「今の画面」ではあるため）。

どれかが通らなければ、画像を書かずに落ちる。1. なら消えている理由をそのまま言う。2. が
時間切れになったとき（＝理由は名指しできないが描かれていない）はこう出る。

```text
the window stopped redrawing before the home screen could appear, so `import`
can only return the frame the compositor kept from before it stopped. mutter
stops presenting a window that is not on screen: unlock the session and wake the
display, and make sure the window is neither minimised nor on another workspace.
See docs/linux-desktop-development.md 4.2.
```

#### 残る穴

- 1. が名指しできない理由で描画が止まり、しかもそれが**ホーム画面へ切り替わる前後 0.2 秒
     ほど**に入り込んだ場合は、2. の許容差を通り抜けうる。ウィンドウ全体が他のウィンドウに
     完全に隠れている場合がこれに当たる（未実測）。
- 撮った後にアプリ自身が固まった場合は、それが最後に描いた画面なので古くはない。
- **同じ静止画面を撮り続けて md5 が変わらないこと自体は異常ではない。** ホーム画面は静止画
  なので当然一致する。md5 の一致が問題になるのは、動いているはずの画面が動いていないときだけ。

#### 実測（Issue #73）

| 状況                   | `import -window auto_scoring_app`                                                               | `import -window root`                                 | スクリプト                                                        |
| ---------------------- | ----------------------------------------------------------------------------------------------- | ----------------------------------------------------- | ----------------------------------------------------------------- |
| ロック／ブランク       | **成功するが古いフレームを返す**（0.3 秒間隔 38 枚中 37 枚が一致）                              | `unable to read X window image 'root'` で**失敗する** | 起動前にロックを検出して即座に失敗。画像は書かない                |
| 最小化                 | **成功して固まったフレームを返す。**しかも最後に見えていた画面ですらない（最小化の途中の 1 枚） | 成功する（写るのは今表示中の画面）                    | `_NET_WM_STATE_HIDDEN` を見て失敗。画像は書かない                 |
| 別ワークスペースに退避 | **成功して、最後に見えていたフレームを返し続ける**                                              | 成功する（写るのは今表示中の画面）                    | `_NET_WM_DESKTOP` の違いで失敗。画像は書かない                    |
| 描画が生きている       | 毎回変わる                                                                                      | 成功                                                  | ホーム画面が撮れる（スプラッシュ→ホーム→別画面で md5 が全部違う） |

**`xwininfo` の `Map State` はこの判定には使えない。** 最小化中も別ワークスペースでも
`IsViewable` のままで、`import` も成功する。この事象が黙って通ってしまうのは、
「撮れたかどうか」と「見えているかどうか」が X の上で別物だからである。見えているかどうかは
`Map State` ではなく EWMH のプロパティ（`_NET_WM_STATE` / `_NET_WM_DESKTOP`）に出る。

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

### 4.4 画面・テーマ・幅を指定して撮る（Issue #71）

ホーム画面以外を撮るには、**どの画面をどのテーマ・どの幅で出すかをアプリ側へ
渡す**必要がある。スクリプトはクリックができないので、起動先の画面を指定できな
ければホーム画面しか撮れない。

```bash
./scripts/screenshot-linux-app.sh -r /tests -t dark -w 700x720 -o /tmp/list.png
```

| オプション | 渡し方                                            | 読む側                                        |
| ---------- | ------------------------------------------------- | --------------------------------------------- |
| `-r ROUTE` | 環境変数 `AUTO_SCORING_INITIAL_ROUTE`             | `app/lib/main.dart`（**デバッグビルドのみ**） |
| `-t THEME` | 環境変数 `AUTO_SCORING_THEME`（`light` / `dark`） | 同上。既定は `ThemeMode.system`               |
| `-w WxH`   | 環境変数 `AUTO_SCORING_WINDOW_SIZE`               | `app/linux/runner/my_application.cc`          |

- **route はアプリの経路そのもの**（`app/lib/core/app_routes.dart`）。
  `/tests/<test-id>/submissions/<submission-id>/review` のように id を含む経路も
  そのまま渡せる。
- **テーマをアプリ側で固定するのは、デスクトップの配色設定に触らないため。**
  Flutter Linux は GNOME の `color-scheme` に従うので、外から切り替えるには
  ユーザーのデスクトップ設定を書き換えるしかない。作業中に画面全体が暗転し、
  実行が途中で落ちればそのまま戻らない。§4.2 と同じ理由で、ユーザーのマシンの
  設定はエージェントが触らない。
- **route とテーマは `kDebugMode` の中だけで読む。** 配布ビルドの起動画面や配色が
  環境変数で変わってよい理由はない。§2 が作るのは `--debug` なので、必要な場所で
  だけ有効になる。
  **未確認: release ビルドでこの分岐が実際に消えることは実測していない。**
  `kDebugMode` はコンパイル時定数なので release では `false` に畳まれる、という
  Flutter の一般的な挙動に依っているだけである。Windows の release ビルドは
  この開発機では作れない（§0、共通の実行環境制約）ので、確かめるなら CI か
  Windows 機で行う。コード上 `kDebugMode` で囲まれていることは確認済み。
- **ウィンドウ幅を C++ 側で読むのは、外から窓を広げる道具が無いため。** `xdotool` /
  `wmctrl` は §1 の前提パッケージに無く、root 無しでは入れられない。`app/linux/` は
  §0 のとおり配布物ではないので、ここに開発用の口を開けても製品には出ない。

#### 画面に出すデータを用意する

空のデータベースで撮った画面は、情報密度も優先順位も狭幅の破綻も評価できない。
一方で、テスト登録も答案取込も OCR と AI を通るので、資格情報の無い開発機では
**手で作れない**。

```bash
uv run --project backend python scripts/seed-demo-app-data.py
```

`app-data/` へ**全部が作り物のデータ**を書く（テスト2件・答案3件・確定済み依存
グラフ・認識結果・採点結果・レビュー履歴）。`--app-data-dir` を省くとアプリが
使うのと同じ既定の場所（§5.2）へ書く。
**アプリを終了させてから実行すること**（起動中はロックを持っている、§5.1）。

**このスクリプトは書く前に対象の `app-data/` をリセットする。** テストを全件削除し、
その下の答案・採点・注釈・レビューが CASCADE で一緒に消える。だから書き込みの前に、
**スキーマの `ON DELETE CASCADE` を辿って**その削除が届く全テーブルを読み、
**行の主キーの文字列カラムが1つでも `demo-` で始まらなければ実行ごと拒否する**。

読むテーブルを**手で列挙しない**のは、2回続けて穴が開いたからである（Issue #71 の
レビュー1回目・2回目）。1回目は `tests` しか見ておらず、デモのテストに実答案を足すと
通過した。2回目は12テーブルを並べたうえで `dependency_edges` を「端点は `questions` で
覆われる」として除外していたが、**端点は外部キーではなく単なる文字列カラム**で、
`questions` に存在しない id を書ける。列挙は、スキーマが動くたびに人が数え直さなければ
古くなり、古くなっても何も落ちない。

主キーを見るのは、それが行を識別しているものだからである。`dependency_edges` のような
リンク表では主キーがグラフと**両端点**を含むので、上の穴はこの規則で自動的に塞がる。

判定は id の接頭辞であって、所有権の証明ではない。**デモのテストに実答案を1枚でも
取り込んだ `app-data/` は、そのままでは二度とシードできない**（拒否される）。
安全側に倒してあるので、そのときは別のディレクトリを `--app-data-dir` に渡すこと。
これらは `backend/tests/test_seed_demo_app_data.py` が固定している。CASCADE で消える
テーブルの集合そのものも突き合わせているので、**スキーマが増えたときはテストが落ちる**。

`queued` / `running` のジョブは置けない。サイドカーは起動と同時にキューを回すため、
終端でないジョブは数秒で終端へ動く。撮れるのは「そのあと」の画面であって、置いた
はずの状態ではない。実行中ノードの動き自体も静止画には写らないので、そこは
`app/test/dependency_dag_panel_test.dart` が検査している
（[dependency-dag-progress-view.md](./dependency-dag-progress-view.md) §5.2）。

#### 一式を撮る

1画面につき1回起動する。評価用の一式はこのスクリプトのループである。

```bash
for theme in light dark; do
  for geom in 1280x720 700x720; do
    ./scripts/screenshot-linux-app.sh -r / -t "$theme" -w "$geom" \
      -o "$OUT/home-$theme-$geom.png"
  done
done
```

**スクロールできない**ことは頭に入れておくこと。テスト設定画面のように縦に長い
画面は、1枚に写るのは最初の画面ぶんだけである。

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
