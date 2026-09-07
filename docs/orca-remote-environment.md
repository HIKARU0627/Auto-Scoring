# Orca リモート開発環境（Ubuntu ランタイム）

Windows 上の Orca クライアントから、別 PC（Ubuntu）で動く Orca ランタイムへ接続して
開発するための構築・運用手順。Windows 側のメモリ消費を下げることが目的で、
Auto-Scoring アプリの機能とは独立したインフラ設定である（GitHub Issue #47）。

Orca 自体の運用フロー（Issue → worktree → PR）は [ade-setup.md](./ade-setup.md)、
品質 gate は [quality-gates.md](./quality-gates.md) が正本。本書はその実行場所を
リモートへ移すための追加手順だけを扱う。

## 構成

| 役割            | ホスト                        | 内容                                                    |
| --------------- | ----------------------------- | ------------------------------------------------------- |
| クライアント    | Windows（`zeropro`）          | Orca アプリ / `orca` CLI。worktree・terminal を操作する |
| ランタイム      | Ubuntu 24.04（`shijima`）     | `orca serve` が worktree・terminal・エージェントを実行  |
| 経路            | Tailscale（`100.125.134.49`） | WebSocket `ws://<tailscale-ip>:6768`                    |
| 管理用 SSH      | `ssh ubuntu`（鍵認証）        | ランタイムの起動・ログ確認・トラブルシューティング      |
| Orca バージョン | 両側 1.4.197                  | クライアントとランタイムで一致させる                    |

クライアント⇔ランタイムの本経路は Tailscale 上の WebSocket であり、SSH ではない。
SSH は本書の手順を流すための管理経路にすぎず、接続確立後は SSH を切っても
リモート worktree の操作は継続できる。

## 前提

### Windows 側

- Orca がインストール済みで `orca --version` が通る。
- Tailscale が動作し、`shijima` が同一 tailnet に見えている。
- `~/.ssh/config` に `ubuntu`（`HostName 100.125.134.49` / `User hikaru`）が定義済み。

### Ubuntu 側

- Orca は **AppImage** で導入されている。実体は
  `~/.cache/orca/appimage/launcher/orca-ide`（`~/Downloads/orca-linux.AppImage` から展開）。
- ログインシェルの `orca` は `~/.local/bin/orca`（Orca CLI 1.4.197）。
- Claude Code / Codex / Cursor Agent の CLI が `~/.local/bin` に導入済み。

> **注意: `/usr/bin/orca` は Orca ではない。** Ubuntu の `/usr/bin/orca` は GNOME の
> スクリーンリーダー（`orca` パッケージ、バージョン 46.1）で、名前が衝突している。
> `ssh ubuntu "orca ..."` のような**非ログインシェル**では `~/.local/bin` が PATH に
> 入らないため、スクリーンリーダーが起動してしまう。SSH 経由では
> `ssh ubuntu 'bash -lc "orca ..."'` を使うか、
> `~/.cache/orca/appimage/launcher/orca-ide` を絶対パスで呼ぶ。

## 1. Ubuntu 側で `orca serve` を常駐させる

`orca serve` はヘッドレスの Orca ランタイムサーバーで、フォアグラウンドで動き
pairing code を stdout に出す。再起動・切断からの自動復旧のため systemd の
user service にする。

### 1.1 表示サーバーの制約

Orca は Electron アプリで、`serve` でも表示サーバーを要求する。表示先が無いと
次のエラーで終了する。

```
Orca needs a usable display server, but the selected X11 or Wayland endpoint is unavailable.
```

対処は 2 通りある。本環境では **(b)** を採用した（(a) は `sudo` が必要で、
パスワード入力を伴うため未実施）。

| 方式                                 | 前提                     | 安定性                                     |
| ------------------------------------ | ------------------------ | ------------------------------------------ |
| (a) `xvfb-run` で仮想ディスプレイ    | `sudo apt install xvfb`  | 高。デスクトップへのログイン不要           |
| (b) デスクトップの Xwayland に相乗り | GNOME セッションが起動中 | 中。ログイン中のみ動作する（本環境の現状） |

(b) では `XDG_RUNTIME_DIR`、`DISPLAY=:0`、および mutter が発行する
`$XDG_RUNTIME_DIR/.mutter-Xwaylandauth.*` を `XAUTHORITY` に指定する必要がある。
このファイル名はセッションごとに変わるため、起動スクリプト側で解決する。

### 1.2 起動スクリプト

`~/.local/bin/orca-serve-runner` を次の内容で作成し、実行権限を付ける。
`xvfb-run` が入っていればそちらを優先し、無ければデスクトップセッションへ
フォールバックする。

```bash
#!/usr/bin/env bash
# Start the Orca headless runtime server for the systemd user service.
# Prefers a private Xvfb display; falls back to the desktop session Xwayland.
set -euo pipefail

export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export NO_COLOR=1 TERM=dumb
ORCA_BIN="$HOME/.cache/orca/appimage/launcher/orca-ide"
PAIRING_ADDRESS="${ORCA_PAIRING_ADDRESS:-$(tailscale ip -4 2>/dev/null | head -1)}"

if [ -z "$PAIRING_ADDRESS" ]; then
  echo "orca-serve-runner: cannot resolve pairing address (set ORCA_PAIRING_ADDRESS)" >&2
  exit 1
fi

# Run under a pty: Electron block-buffers stdout on a pipe, which would keep the
# pairing code out of the journal until the process exits.
run() {
  local cmd
  cmd="$(printf "%q " "$@")"
  exec script -qefc "$cmd" /dev/null
}

if command -v xvfb-run >/dev/null 2>&1; then
  run xvfb-run -a "$ORCA_BIN" serve --json --pairing-address "$PAIRING_ADDRESS"
fi

# No Xvfb: wait for the local GNOME session to publish its Xwayland auth file.
auth=""
for _ in $(seq 1 60); do
  auth="$(ls -1t "$XDG_RUNTIME_DIR"/.mutter-Xwaylandauth.* 2>/dev/null | head -1 || true)"
  [ -n "$auth" ] && break
  sleep 2
done
if [ -z "$auth" ]; then
  echo "orca-serve-runner: no display available (install xvfb or log in to the desktop)" >&2
  exit 1
fi
export DISPLAY="${ORCA_DISPLAY:-:0}"
export XAUTHORITY="$auth"
run "$ORCA_BIN" serve --json --pairing-address "$PAIRING_ADDRESS"
```

`script -qefc` で pty を挟んでいるのは、Electron が **パイプ出力を block buffering
する**ため。これが無いと `orca_server_ready`（pairing code を含む）が journal に
出ず、ペアリングができない。

### 1.3 systemd user service

`~/.config/systemd/user/orca-serve.service`:

```ini
[Unit]
Description=Orca headless runtime server
# Keep restarting even after repeated early failures (e.g. display not ready yet).
StartLimitIntervalSec=0
After=graphical-session.target network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=%h/.local/bin/orca-serve-runner
Restart=always
RestartSec=10
TimeoutStopSec=30
Environment=ORCA_DISPLAY=:0

[Install]
WantedBy=default.target
```

`StartLimitIntervalSec` は `[Unit]` に置く。`[Service]` に書くと
`Unknown key name 'StartLimitIntervalSec' in section 'Service', ignoring.` となり
再起動回数の上限が効いたままになる。

有効化する。`enable-linger` はログアウト後もユーザーマネージャーを動かすため。

```bash
ssh ubuntu 'systemctl --user daemon-reload \
  && systemctl --user enable --now orca-serve.service \
  && loginctl enable-linger hikaru'
```

状態とログ:

```bash
ssh ubuntu 'systemctl --user status orca-serve.service --no-pager'
ssh ubuntu 'journalctl --user -u orca-serve.service -n 50 --no-pager'
```

## 2. Windows 側からペアリングする

pairing code は `orca serve` 起動時の `orca_server_ready` 行に含まれる
`orca://pair?code=...` である。**これは接続用の device token を含む秘匿値**なので、
docs・Issue・PR・スクリーンショットに残さない。変数経由で受け渡す。

```powershell
$code = ssh ubuntu "journalctl --user -u orca-serve.service --since '-10 min' --no-pager -o cat | tr -d '\r' | grep -o 'orca://pair?code=[A-Za-z0-9+/=]*' | tail -1"
orca environment add --name shijima-runtime --pairing-code $code --json
```

登録後は名前で参照できる。

```powershell
orca environment list --json
orca environment show --environment shijima-runtime --json
orca status --environment shijima-runtime --json
```

pairing code はサーバー再起動をまたいで有効。`orca serve` を落として上げ直しても
`orca environment add` のやり直しは不要で、`runtimeId` だけが変わる（§5.4）。
再ペアリングが要るのは、ランタイム側の設定（`~/.config/orca`）を作り直したときだけ。

## 3. リモート環境で worktree と terminal を使う

### 3.1 リポジトリを登録する

リモートランタイムは自分のリポジトリ一覧を持つ。Windows 側の登録は引き継がれない。

```powershell
orca repo list --environment shijima-runtime --json
orca repo add --environment shijima-runtime --path /home/hikaru/development/<repo> --json
```

> **Git Bash から実行しない。** MSYS2 のパス変換が `/home/hikaru/...` を
> `C:/Program Files/Git/home/hikaru/...` に書き換え、
> `Project path must be an absolute path` で失敗する。PowerShell から実行するか、
> `MSYS_NO_PATHCONV=1` を付ける。

### 3.2 worktree を作る

```powershell
orca worktree create --environment shijima-runtime --repo id:<repo-id> --name <name> --json
```

`--host runtime:<environment-id>` は `--repo` と併用できず
`Choose either --repo or project target flags, not both.` になる。リモートに登録済みの
repo を使うときは `--environment <name>` + `--repo id:<repo-id>` を使う。
`--host runtime:<environment-id>` は `--project` / `--project-host-setup` と組み合わせる形。

### 3.3 terminal を動かす

```powershell
orca terminal create --environment shijima-runtime --worktree "worktree:<worktree-id>" --command "<command>" --json
orca terminal read --environment shijima-runtime --terminal <terminal-handle> --json
```

### 3.4 後片付け

worktree の削除は `id:` セレクタで指定する。`worktree:` セレクタは
`selector_not_found` になる。

```powershell
orca worktree list --environment shijima-runtime --json
orca worktree rm --environment shijima-runtime --worktree "id:<repo-id>::<abs-path>" --json
```

## 4. Tailscale と `--pairing-address`

`orca serve` は常に `0.0.0.0:6768` を bind する。`--pairing-address` は
**pairing code に埋め込んで相手へ広告するアドレスだけ**を変える（bind 先は変えない）。

- Tailscale IP を広告すると、保存される endpoint が `ws://<tailscale-ip>:6768` になる。
  Tailscale IP はノード固定なので、LAN 内でも外出先でも同じ環境定義で繋がる。
- 広告先を LAN IP にすると、ネットワークが変わるたび `orca environment add` のやり直しが要る。
  よって **Tailscale IP を広告する**（起動スクリプトは `tailscale ip -4` から自動取得する）。
- 同一 LAN にいる間、Tailscale は DERP 中継ではなく直結を選ぶ
  （`tailscale status` の該当行が `direct 192.168.x.x:41641`）。追加設定は不要。

`0.0.0.0` bind のため、**ポート 6768 は LAN からも到達する**。Tailscale 以外から
届く必要は無いので、ホストファイアウォールで `tailscale0` 以外からの 6768 を
落とすことが望ましい（`sudo` が必要なため未実施。§7）。

## 5. 検証記録（技術プローブ）

`AGENTS.md`「Verification」に従い、repro command・期待結果・実測結果・判断を残す。
実施日 2026-09-07、Orca 1.4.197（両側）、Ubuntu 24.04.4 / kernel 7.0.0-31-generic。

### 5.1 バージョン整合

| 項目  | 内容                                                                         |
| ----- | ---------------------------------------------------------------------------- |
| repro | Windows: `orca --version` / Ubuntu: `ssh ubuntu 'bash -lc "orca --version"'` |
| 期待  | 両側が同一バージョン                                                         |
| 実測  | 両側 `1.4.197`                                                               |
| 判断  | 整合。バージョン合わせの追加作業は不要                                       |

`ssh ubuntu "orca --version"`（非ログインシェル）は `46.1` を返す。これは GNOME
スクリーンリーダーのバージョンで、Orca ではない。

### 5.2 `orca serve` の起動

| 項目  | 内容                                                                                                      |
| ----- | --------------------------------------------------------------------------------------------------------- |
| repro | `ssh ubuntu 'systemctl --user restart orca-serve.service'` の後 `journalctl --user -u orca-serve.service` |
| 期待  | `orca_server_ready` が出て `0.0.0.0:6768` が LISTEN                                                       |
| 実測  | `advertisedEndpoint: ws://100.125.134.49:6768`、`ss -tln` に `0.0.0.0:6768` を確認                        |
| 判断  | 成立。ただし §1.1・§1.2 の表示サーバーと pty の対処が前提                                                 |

### 5.3 リモート worktree と terminal

| 項目  | 内容                                                                                                                                                                                                                 |
| ----- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| repro | `orca repo add` → `orca worktree create --environment shijima-runtime --repo id:<id> --name remote-probe-1` → `orca terminal create --command "uname -a && pwd && git branch --show-current"` → `orca terminal read` |
| 期待  | Ubuntu 上に worktree が作られ、terminal が Linux 上で実行される                                                                                                                                                      |
| 実測  | worktree `/home/hikaru/orca/workspaces/orca-remote-probe/remote-probe-1`（branch `remote-probe-1`）が生成。terminal 出力は `Linux shijima 7.0.0-31-generic ... x86_64` と当該パス                                    |
| 判断  | 成立。Windows クライアントからリモート実行が通ることを確認。テスト worktree は削除済み                                                                                                                               |

検証用に Ubuntu 上へ最小リポジトリ `/home/hikaru/development/orca-remote-probe` を作り、
Orca に登録した。以降の疎通確認にも使えるため残してある（Auto-Scoring 本体とは無関係）。
進行中の worktree（`issue-14`〜`issue-46` 等）には触れていない。

### 5.4 プロセス kill からの自動復旧

| 項目  | 内容                                                                            |
| ----- | ------------------------------------------------------------------------------- |
| repro | `ssh ubuntu 'pkill -9 -f "out/cli/index.js serve"'` → 状態と `NRestarts` を観測 |
| 期待  | systemd が 10 秒後に再起動し、再度 6768 を LISTEN                               |
| 実測  | 5 秒以内に `active`、`NRestarts=1`、新 PID で `0.0.0.0:6768` を LISTEN          |
| 判断  | 成立                                                                            |

> SSH 越しに `pkill -f` を使うと、パターン文字列が**自分の SSH コマンドライン自体**に
> 一致して接続ごと落ちる（`ssh` が exit 255 で終わる）。サーバーの再起動自体は成功する。

### 5.5 サービス停止中のクライアント挙動と再接続

| 項目  | 内容                                                                                                                                                               |
| ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| repro | `ssh ubuntu 'systemctl --user stop orca-serve.service'` → `orca status --environment shijima-runtime --json` → `start` → 再度 `orca status`                        |
| 期待  | 停止中は明示エラー、復帰後は再ペアリング無しで `connected`                                                                                                         |
| 実測  | 停止中は `{"ok": false, "error": {"code": "remote_runtime_unavailable"}}`（exit 1）。起動から 10 秒で LISTEN、その後 `state: ready` / `connectionState: connected` |
| 判断  | 成立。device token はサーバー再起動をまたいで有効。`orca environment add` の再実行は不要                                                                           |

### 5.6 削除・昇格条件

本書は恒久的な運用手順であり、プローブとして削除する対象ではない。
§7 の未了項目が解消された時点で、該当節を「実施済み」に更新する。

## 6. トラブルシューティング

| 症状                                                                | 原因と対処                                                                                              |
| ------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| `ssh ubuntu "orca ..."` がスクリーンリーダーのヘルプを出す          | 非ログインシェルで `/usr/bin/orca` が引かれている。`ssh ubuntu 'bash -lc "orca ..."'` を使う            |
| `Orca needs a usable display server`                                | `DISPLAY` / `XAUTHORITY` 未設定。§1.1。デスクトップ未ログインなら `xvfb` を入れる                       |
| `Missing X server or $DISPLAY` の直後に `SIGSEGV`                   | `DISPLAY=:0` だけ設定し `XAUTHORITY` を渡していない。`.mutter-Xwaylandauth.*` を指定する                |
| journal に pairing code が出ない                                    | Electron のパイプ出力バッファリング。`script -qefc` で pty を挟む（§1.2）                               |
| `Unknown key name 'StartLimitIntervalSec' in section 'Service'`     | `[Service]` ではなく `[Unit]` に置く（§1.3）                                                            |
| `Project path must be an absolute path`（パスは絶対パスなのに）     | Git Bash の MSYS パス変換。PowerShell から実行するか `MSYS_NO_PATHCONV=1`（§3.1）                       |
| `Choose either --repo or project target flags, not both.`           | `--host runtime:<id>` と `--repo` の併用。`--environment <name>` + `--repo id:<id>` にする（§3.2）      |
| `selector_not_found`（worktree 削除時）                             | `worktree:` ではなく `id:<repo-id>::<abs-path>` を使う（§3.4）                                          |
| `remote_runtime_unavailable`                                        | ランタイム停止・Tailscale 断。`systemctl --user status orca-serve.service` と `tailscale status` を確認 |
| `The OS keyring is unavailable, so secrets are stored unencrypted.` | gnome-keyring 未解錠。デスクトップにログインして解錠するか、keyring を導入する                          |

## 7. 未了項目（人手が必要）

いずれも `sudo` パスワードや秘匿情報の入力を伴うため、エージェントでは実施していない。

1. **`xvfb` の導入** — `sudo apt install xvfb`。導入すればデスクトップへのログイン無しに
   `orca serve` が動き、起動スクリプトは自動で `xvfb-run` 経路へ切り替わる（§1.2）。
   現状はデスクトップにログインしている間だけ動作する。
2. **ファイアウォール** — `tailscale0` 以外からの 6768 を落とす（§4）。
3. **Auto-Scoring リポジトリの clone と認証** — Ubuntu 側に GitHub 認証情報が無く
   （`ssh -T git@github.com` が `Permission denied (publickey)`）、private リポジトリを
   clone できない。デプロイキーまたは GitHub App 認証の配置が必要。
   秘密鍵はリポジトリに置かない（`AGENTS.md`「Security」、
   [ai-agent-git-attribution.md](./ai-agent-git-attribution.md)）。
4. **開発ツールチェーン** — Ubuntu 側に `pwsh` / `uv` / `flutter` / `pnpm` が無い。
   リモートで `pnpm run check` まで回すには [ade-setup.md](./ade-setup.md)「必要環境」の
   導入が必要。Node.js は v18.19.1 で、`package.json` の `engines.node >=24.14.0` に
   満たないため更新も要る。

3・4 が終わるまで、リモートランタイムで扱えるのは Auto-Scoring 以外のリポジトリに限る。
