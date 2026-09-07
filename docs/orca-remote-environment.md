# Orca リモート開発環境（Ubuntu ランタイム）

Windows 上の Orca クライアントから、別 PC（Ubuntu）で動く Orca ランタイムへ接続して
開発するための構築・運用手順。Windows 側のメモリ消費を下げることが目的で、
Auto-Scoring アプリの機能とは独立したインフラ設定である（GitHub Issue #47）。

Orca 自体の運用フロー（Issue → worktree → PR）は [ade-setup.md](./ade-setup.md)、
品質 gate は [quality-gates.md](./quality-gates.md) が正本。本書はその実行場所を
リモートへ移すための追加手順だけを扱う。

## 構成

> **本書のプレースホルダ表記。** ホスト名・ユーザー名・IP アドレス・Orca 環境名は実値では
> 書かない（`AGENTS.md`「Security」。pairing code と同じ扱い、§2）。読み替えは次の通り。
>
> | 表記             | 意味                                                      |
> | ---------------- | --------------------------------------------------------- |
> | `<windows-host>` | Windows クライアントのホスト名                            |
> | `<ubuntu-host>`  | Ubuntu ランタイムのホスト名                               |
> | `<user>`         | Ubuntu 側のログインユーザー名                             |
> | `<tailscale-ip>` | ランタイムの Tailscale IP（`tailscale ip -4` で得られる） |
> | `<runtime-env>`  | `orca environment add --name` で付ける Orca 環境名        |

| 役割            | ホスト                          | 内容                                                    |
| --------------- | ------------------------------- | ------------------------------------------------------- |
| クライアント    | Windows（`<windows-host>`）     | Orca アプリ / `orca` CLI。worktree・terminal を操作する |
| ランタイム      | Ubuntu 24.04（`<ubuntu-host>`） | `orca serve` が worktree・terminal・エージェントを実行  |
| 経路            | Tailscale（`<tailscale-ip>`）   | WebSocket `ws://<tailscale-ip>:6768`                    |
| 管理用 SSH      | `ssh ubuntu`（鍵認証）          | ランタイムの起動・ログ確認・トラブルシューティング      |
| Orca バージョン | 両側 1.4.197                    | クライアントとランタイムで一致させる                    |

クライアント⇔ランタイムの本経路は Tailscale 上の WebSocket であり、SSH ではない。
SSH は本書の手順を流すための管理経路にすぎず、接続確立後は SSH を切っても
リモート worktree の操作は継続できる。

## 前提

### Windows 側

- Orca がインストール済みで `orca --version` が通る。
- Tailscale が動作し、`<ubuntu-host>` が同一 tailnet に見えている。
- `~/.ssh/config` に `ubuntu`（`HostName <tailscale-ip>` / `User <user>`）が定義済み。

### Ubuntu 側

- Orca は **AppImage** で導入されている。実体は
  `~/.cache/orca/appimage/launcher/orca-ide`（`~/Downloads/orca-linux.AppImage` から展開）。
- ログインシェルの `orca` は `~/.local/bin/orca`（Orca CLI 1.4.197）。
- Claude Code / Codex / Cursor Agent の CLI が `~/.local/bin` に導入済み。
- **日本語フォントが導入済み** — `sudo apt install fonts-ipafont-gothic`。
  backend の PDF出力テストに必要（§8）。

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
umask 077

export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export NO_COLOR=1 TERM=dumb
ORCA_BIN="$HOME/.cache/orca/appimage/launcher/orca-ide"
PAIRING_ADDRESS="${ORCA_PAIRING_ADDRESS:-$(tailscale ip -4 2>/dev/null | head -1)}"
PAIRING_FILE="${ORCA_PAIRING_FILE:-${XDG_STATE_HOME:-$HOME/.local/state}/orca/pairing-code}"

if [ -z "$PAIRING_ADDRESS" ]; then
  echo "orca-serve-runner: cannot resolve pairing address (set ORCA_PAIRING_ADDRESS)" >&2
  exit 1
fi
mkdir -p "$(dirname "$PAIRING_FILE")"

# The ready line carries a reusable device token. Divert it to an owner-only
# file and keep it out of stdout, which systemd forwards to the journal.
emit_redacted() {
  local line
  while IFS= read -r line; do
    case "$line" in
      *"orca://pair?code="* | *"code%3D"*)
        printf "%s\n" "$line" >"$PAIRING_FILE"
        printf "orca-serve-runner: runtime ready; pairing code written to %s (kept out of the journal)\n" "$PAIRING_FILE"
        ;;
      *) printf "%s\n" "$line" ;;
    esac
  done
}

# Run under a pty: Electron block-buffers stdout on a pipe, so the ready line
# would otherwise not arrive until the process exits.
run() {
  local cmd
  cmd="$(printf "%q " "$@")"
  script -qefc "$cmd" /dev/null | emit_redacted
  exit "${PIPESTATUS[0]}"
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
する**ため。これが無いと `orca_server_ready` 行がプロセス終了までフラッシュされない。

### 1.2.1 pairing code を journal に残さない

`orca_server_ready` 行には**再利用可能な device token** が含まれる（§2）。素通しすると
systemd が journald へ転送し、journal とその export 先を読める者が誰でもランタイムの
認証情報を復元できてしまう。`AGENTS.md`「Security」がログへの token 混入を禁じている。

そのため `emit_redacted` が該当行を stdout から取り除き、`umask 077` の下で
`~/.local/state/orca/pairing-code`（`0600`、所有者のみ）へ書き出す。journal に残るのは
「書き出した」という 1 行だけ。ペアリング後はこのファイルを消してよい
（サービス再起動時に再生成される）。

```bash
ssh ubuntu 'rm -f ~/.local/state/orca/pairing-code'
```

**すでに journal へ出してしまった場合は、token を失効させる。** journald は
unit 単位の削除ができず、`--vacuum-*` は無関係なログまで消すため、ログを消すのではなく
ランタイム側の paired device store を作り直すのが確実（§5.6 で実証）。

```bash
ssh ubuntu 'systemctl --user stop orca-serve.service \
  && rm -f ~/.config/orca/orca-devices.json \
  && systemctl --user start orca-serve.service'
```

以後、旧 pairing code は `unauthorized` で拒否される。Windows 側は
`orca environment rm` してから §2 の手順で貼り直す。

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
  && loginctl enable-linger "$USER"'
```

状態とログ:

```bash
ssh ubuntu 'systemctl --user status orca-serve.service --no-pager'
ssh ubuntu 'journalctl --user -u orca-serve.service -n 50 --no-pager'
```

## 2. Windows 側からペアリングする

pairing code は `orca serve` 起動時の `orca_server_ready` 行に含まれる
`orca://pair?code=...` である。**これは再利用可能な device token を含む秘匿値**なので、
docs・Issue・PR・スクリーンショット・**ログ**に残さない。§1.2.1 の通り、起動スクリプトが
所有者のみ読める `~/.local/state/orca/pairing-code`（`0600`）へ書き出しているので、
journal ではなくそのファイルから変数経由で受け渡す。

```powershell
$code = ssh ubuntu "tr -d '\r' < ~/.local/state/orca/pairing-code | grep -o 'orca://pair?code=[A-Za-z0-9+/=]*' | tail -1"
orca environment add --name <runtime-env> --pairing-code $code --json
ssh ubuntu 'rm -f ~/.local/state/orca/pairing-code'
```

`$code` はシェル履歴・トランスクリプトにも残さない。値を確認したいときは
`$code.Length` のように長さだけ見る。

登録後は名前で参照できる。

```powershell
orca environment list --json
orca environment show --environment <runtime-env> --json
orca status --environment <runtime-env> --json
```

pairing code はサーバー再起動をまたいで有効。`orca serve` を落として上げ直しても
`orca environment add` のやり直しは不要で、`runtimeId` だけが変わる（§5.4）。
言い換えると **token は自然失効しない**ので、漏れたら §1.2.1 の手順で明示的に失効させる。
paired device の一覧はランタイム側の `~/.config/orca/orca-devices.json`（`0600`）にある。

## 3. リモート環境で worktree と terminal を使う

### 3.1 リポジトリを登録する

リモートランタイムは自分のリポジトリ一覧を持つ。Windows 側の登録は引き継がれない。

```powershell
orca repo list --environment <runtime-env> --json
orca repo add --environment <runtime-env> --path /home/<user>/development/<repo> --json
```

> **Git Bash から実行しない。** MSYS2 のパス変換が `/home/<user>/...` を
> `C:/Program Files/Git/home/<user>/...` に書き換え、
> `Project path must be an absolute path` で失敗する。PowerShell から実行するか、
> `MSYS_NO_PATHCONV=1` を付ける。

### 3.2 worktree を作る

```powershell
orca worktree create --environment <runtime-env> --repo id:<repo-id> --name <name> --json
```

`--host runtime:<environment-id>` は `--repo` と併用できず
`Choose either --repo or project target flags, not both.` になる。リモートに登録済みの
repo を使うときは `--environment <runtime-env>` + `--repo id:<repo-id>` を使う。
`--host runtime:<environment-id>` は `--project` / `--project-host-setup` と組み合わせる形。

### 3.3 terminal を動かす

```powershell
orca terminal create --environment <runtime-env> --worktree "worktree:<worktree-id>" --command "<command>" --json
orca terminal read --environment <runtime-env> --terminal <terminal-handle> --json
```

### 3.4 後片付け

worktree の削除は `id:` セレクタで指定する。`worktree:` セレクタは
`selector_not_found` になる。

```powershell
orca worktree list --environment <runtime-env> --json
orca worktree rm --environment <runtime-env> --worktree "id:<repo-id>::<abs-path>" --json
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

| 項目  | 内容                                                                                                                   |
| ----- | ---------------------------------------------------------------------------------------------------------------------- |
| repro | `ssh ubuntu 'systemctl --user restart orca-serve.service'` の後 `journalctl --user -u orca-serve.service` と `ss -tln` |
| 期待  | ランタイムが ready になり `0.0.0.0:6768` が LISTEN                                                                     |
| 実測  | 起動 10 秒で `0.0.0.0:6768` を LISTEN。`advertisedEndpoint: ws://<tailscale-ip>:6768`                                  |
| 判断  | 成立。ただし §1.1・§1.2 の表示サーバーと pty の対処が前提                                                              |

### 5.3 リモート worktree と terminal

| 項目  | 内容                                                                                                                                                                                                               |
| ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| repro | `orca repo add` → `orca worktree create --environment <runtime-env> --repo id:<id> --name remote-probe-1` → `orca terminal create --command "uname -a && pwd && git branch --show-current"` → `orca terminal read` |
| 期待  | Ubuntu 上に worktree が作られ、terminal が Linux 上で実行される                                                                                                                                                    |
| 実測  | worktree `/home/<user>/orca/workspaces/orca-remote-probe/remote-probe-1`（branch `remote-probe-1`）が生成。terminal 出力は `Linux <ubuntu-host> 7.0.0-31-generic ... x86_64` と当該パス                            |
| 判断  | 成立。Windows クライアントからリモート実行が通ることを確認。テスト worktree は削除済み                                                                                                                             |

検証用に Ubuntu 上へ最小リポジトリ `/home/<user>/development/orca-remote-probe` を作り、
Orca に登録した。以降の疎通確認にも使えるため残してある（Auto-Scoring 本体とは無関係）。
進行中の worktree（`issue-14`〜`issue-46` 等）には触れていない。

### 5.4 プロセス kill からの自動復旧

| 項目  | 内容                                                                              |
| ----- | --------------------------------------------------------------------------------- |
| repro | `ssh ubuntu 'pkill -9 -f "out/cli/inde[x].js serve"'` → 状態と `NRestarts` を観測 |
| 期待  | systemd が再起動し、再度 6768 を LISTEN                                           |
| 実測  | 10 秒以内に `active`、`NRestarts=1`、新 MainPID で `0.0.0.0:6768` を LISTEN       |
| 判断  | 成立                                                                              |

> `pkill -f` のパターンに `[x]` のような文字クラスを挟むのは、パターン文字列が
> **自分の SSH コマンドライン自体**に一致して接続ごと落ちるのを避けるため
> （素で書くと `ssh` が exit 255 で終わる。サーバーの再起動自体は成功する）。

MainPID は `orca-serve-runner` 自身（bash）で、`orca-ide` はその子。§1.2 の
`emit_redacted` へのパイプがあるため `exec` していない。`orca-ide` を落とすとパイプが
閉じて runner も終了し、systemd が unit ごと再起動する。

### 5.5 サービス停止中のクライアント挙動と再接続

| 項目  | 内容                                                                                                                                                               |
| ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| repro | `ssh ubuntu 'systemctl --user stop orca-serve.service'` → `orca status --environment <runtime-env> --json` → `start` → 再度 `orca status`                          |
| 期待  | 停止中は明示エラー、復帰後は再ペアリング無しで `connected`                                                                                                         |
| 実測  | 停止中は `{"ok": false, "error": {"code": "remote_runtime_unavailable"}}`（exit 1）。起動から 10 秒で LISTEN、その後 `state: ready` / `connectionState: connected` |
| 判断  | 成立。device token はサーバー再起動をまたいで有効。`orca environment add` の再実行は不要                                                                           |

### 5.6 pairing code の非ログ化と失効

| 項目  | 内容                                                                                                                                                                                  |
| ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| repro | §1.2 の `emit_redacted` を入れて再起動 → `journalctl --user -u orca-serve.service --since '-2 min' -o cat \| grep -c 'orca://pair?code='` と `ls -l ~/.local/state/orca/pairing-code` |
| 期待  | journal に code が 0 件、pairing ファイルが `0600` で生成される                                                                                                                       |
| 実測  | journal `0` 件。`-rw------- 1 <user> <user>` の `pairing-code` を 10 秒で生成。journal に残るのは「書き出した」旨の 1 行のみ                                                          |
| 判断  | 成立。以後 token は journal を経由しない                                                                                                                                              |

| 項目  | 内容                                                                                                                                     |
| ----- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| repro | `rm ~/.config/orca/orca-devices.json` + サービス再起動 → 旧 code で登録済みの環境に対し `orca status --environment <runtime-env> --json` |
| 期待  | 旧 token が拒否される                                                                                                                    |
| 実測  | `{"ok": false, "error": {"code": "unauthorized", "message": "Remote Orca runtime rejected the pairing token."}}`                         |
| 判断  | 成立。journal へ出てしまった 5 件の旧 code はこの手順で失効させ、§2 の経路で貼り直した                                                   |

### 5.7 削除・昇格条件

本書は恒久的な運用手順であり、プローブとして削除する対象ではない。
§7 の未了項目が解消された時点で、該当節を「実施済み」に更新する。

## 6. トラブルシューティング

| 症状                                                                | 原因と対処                                                                                                |
| ------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| `ssh ubuntu "orca ..."` がスクリーンリーダーのヘルプを出す          | 非ログインシェルで `/usr/bin/orca` が引かれている。`ssh ubuntu 'bash -lc "orca ..."'` を使う              |
| `Orca needs a usable display server`                                | `DISPLAY` / `XAUTHORITY` 未設定。§1.1。デスクトップ未ログインなら `xvfb` を入れる                         |
| `Missing X server or $DISPLAY` の直後に `SIGSEGV`                   | `DISPLAY=:0` だけ設定し `XAUTHORITY` を渡していない。`.mutter-Xwaylandauth.*` を指定する                  |
| `pairing-code` ファイルができない                                   | Electron のパイプ出力バッファリングで ready 行が届いていない。`script -qefc` で pty を挟む（§1.2）        |
| journal に pairing code が出てしまっている                          | `emit_redacted` 未適用。§1.2.1 で token を失効させ、redaction を入れてから貼り直す                        |
| `Unknown key name 'StartLimitIntervalSec' in section 'Service'`     | `[Service]` ではなく `[Unit]` に置く（§1.3）                                                              |
| `Project path must be an absolute path`（パスは絶対パスなのに）     | Git Bash の MSYS パス変換。PowerShell から実行するか `MSYS_NO_PATHCONV=1`（§3.1）                         |
| `Choose either --repo or project target flags, not both.`           | `--host runtime:<id>` と `--repo` の併用。`--environment <runtime-env>` + `--repo id:<id>` にする（§3.2） |
| `selector_not_found`（worktree 削除時）                             | `worktree:` ではなく `id:<repo-id>::<abs-path>` を使う（§3.4）                                            |
| `remote_runtime_unavailable`                                        | ランタイム停止・Tailscale 断。`systemctl --user status orca-serve.service` と `tailscale status` を確認   |
| `unauthorized` / `rejected the pairing token`                       | ランタイム側の device store が作り直されている。`orca environment rm` して §2 で貼り直す                  |
| `The OS keyring is unavailable, so secrets are stored unencrypted.` | gnome-keyring 未解錠。デスクトップにログインして解錠するか、keyring を導入する                            |

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
   [ade-setup.md](./ade-setup.md)「必要環境」の導入が必要。Node.js は v18.19.1 で、
   `package.json` の `engines.node >=24.14.0` に満たないため更新も要る。
   **ただしツールを揃えても `pnpm run check` は Ubuntu では完走しない**（§8）。
   3・4 が終わるまで、リモートランタイムで扱えるのは Auto-Scoring 以外のリポジトリに限る。

## 8. `pnpm run check` は Ubuntu で完走しない（プラットフォーム制約）

必須 gate `pnpm run check` は最後に `pnpm run build` を実行し、その `build:app` は
`package.json` で `flutter build windows --debug` に固定されている
（[quality-gates.md](./quality-gates.md)）。これは Windows ホストと Visual Studio を
要求するため、**ツールチェーンを何を入れても Linux では通らない**。ツールの不足は
§7.4 の問題だが、この build は環境整備で解決する種類の制約ではない。

リモート実行の可否は次の通り。

| gate                                       | Ubuntu   | 備考                                                       |
| ------------------------------------------ | -------- | ---------------------------------------------------------- |
| `skills:check` / `format:check`            | 可       | Node のみ                                                  |
| `openapi:check`                            | 要 Java  | `openapi-generator` が JRE を要求（`scripts/openapi.mjs`） |
| `lint` / `typecheck`（app・backend）       | 可       | `flutter analyze`・Ruff・mypy はクロスプラットフォーム     |
| `test`（`flutter test` / `pytest`）        | 可       | 同上。ただし日本語フォントが要る（下記）                   |
| `build:backend`                            | 可       | パッケージ import のみ                                     |
| **`build:app`（`flutter build windows`）** | **不可** | Windows ホストが必須                                       |

### 8.1 `pnpm run test:backend` に必要な日本語フォント

PDF出力の文字描画は Windows 同梱の日本語フォントを使う
（`pdfium_pypdf_engine._JAPANESE_FONT_CANDIDATES`。フォントを同梱・再配布しないための
決定で、[pdf-export.md](./pdf-export.md) §3.2）。それが無い環境では、テスト側が
**そのテストのassertionが必要とするグリフを実際に持つ**ローカルフォントを候補の末尾へ
追記して走る（`backend/tests/font_support.py`）。

ここで Ubuntu 標準のフォントは**日本語と Latin のどちらか片方しか持たない** ——
`DroidSansFallbackFull` は唯一の漢字対応 TrueType なのに数字を持たず、`DejaVuSans` は
その逆で、同梱の Noto CJK は CFF アウトラインなので reportlab が読めない。**同一ページに
点数（`4/5`）と日本語コメントの両方を描いて両方を検証するテストは、両方のグリフを持つ
1つのフォントを要求する**ため、素のイメージでは skip されてしまう。

そこで **`sudo apt install fonts-ipafont-gothic` を Ubuntu 側の必須パッケージとする**
（`fonts-vlgothic` / `fonts-takao-gothic` でも可）。IPAゴシックは日本語と Latin/数字の
両方を持ち、`font_support.py` の候補にも入っているため、導入すれば
**backend は skip 0 件**で完走する。入れない場合は該当2件が skip され、その分は Windows
CI でのみ検証されることになる（[mvp-acceptance.md](./mvp-acceptance.md) §4）。

したがって、リモート開発時の Windows build の検証は次のどちらかで担保する。

- **CI に任せる（推奨）** — `.github/workflows/ci.yml` の `Quality` job は
  `runs-on: windows-latest` で、PR ごとに Windows build まで実行する。これが
  main ruleset の required check であり、マージ前に必ず通る。
- **手元の Windows で確認する** — 手元で通したいときは、Windows 側の worktree で
  `pnpm run build:app` だけ実行する。リモートでは残りの gate を回す。

つまりリモート移行後も、Windows build の検証責任は CI（および必要に応じて Windows 機）
に残る。Ubuntu 側で `pnpm run check` を実行して失敗しても、それは移行の不備ではない。
`build:app` のターゲットを変えるのは本 Issue の範囲外で、変更するなら
`quality-gates.md` と CI を同じ変更で更新する。
