# AIエージェントのGitHub帰属設定（任意）

Codex / Claude Code / Cursor CLI / Antigravity CLI などが行うGit操作とGitHub API
操作を、個人アカウントではなく専用GitHub Appのbotによる作業として記録するための
手順。採用は任意。採用しない場合は `AGENTS.md` の «GitHub App authentication»
節を削除し、エージェントが使うidentityとpush認証を代わりに明記する。

## 採用方式

- GitのAuthorとCommitterにGitHub Appのbot identityを使う。
- pushにGitHub App Installation access tokenを使う。
- PR、Issue、コメント、ラベルなどのGitHub API操作にもInstallation access token
  を使い、`gh` は使用しない。
- Appはこのリポジトリだけにインストールし、必要最小限のRepository permissions
  だけを付与する。
- Installation access tokenはHTTPS Git認証が必要になるたびに発行し、ファイル、
  Git設定、OSの資格情報ストアには保存しない。
- GitHub App秘密鍵はリポジトリ外に保存する。

GitHub Appを作成しただけではローカルコミットのAuthorは変わらない。またremoteに
SSH URLが残っていると個人のSSH鍵が使われる可能性がある。Author、Committer、
fetch認証、push認証のすべてを **worktree単位** で設定する。

複数のCLIは同じworktreeのGit設定を共有するため、CLIごとの認証設定は不要。担当CLI
を区別したい場合はPR本文に `AI-Agent: Codex` のような監査情報を書く。

## GitHub Appの作成

GitHubの `Settings` → `Developer settings` → `GitHub Apps` → `New GitHub App`。

| 項目                                    | 設定値                  |
| --------------------------------------- | ----------------------- |
| GitHub App name                         | `<your-org>-agent` など |
| Homepage URL                            | リポジトリのURL         |
| Webhook                                 | `Active` をオフ         |
| Where can this GitHub App be installed? | `Only on this account`  |

Repository permissions（最小構成）:

| Permission    | Access                                                             |
| ------------- | ------------------------------------------------------------------ |
| Metadata      | Read-only（自動付与）                                              |
| Contents      | Read and write                                                     |
| Issues        | Read and write                                                     |
| Pull requests | Read and write                                                     |
| Workflows     | Read and write（`.github/workflows/` をGit経由で更新する期間だけ） |
| その他        | No access                                                          |

作成後、`Install App` → `Only select repositories` で対象リポジトリだけに
インストールする。

## 秘密鍵とID

App設定画面でPrivate keyを生成し、ダウンロードした `.pem` をリポジトリ外へ移動する。

```text
例: C:\Users\<you>\.config\github-apps\<app>.pem
```

秘密鍵の内容、Installation access token、JWTをチャット、Issue、PR、コミット、
環境変数ファイルへ記載しない。秘密鍵ファイルへのシンボリックリンクもリポジトリ
内に作らない。

控える値:

- App ID: App設定画面の数値
- App slug: `https://github.com/apps/<app-slug>` の末尾
- Installation ID: App installationの設定URLに含まれる数値
- Private key path: `.pem` のローカル絶対パス
- Repository: `owner/repo`

## worktreeごとの設定

対象worktreeのルートで実行する（PowerShell 7 / `pwsh` が必要）。

```powershell
./scripts/configure-github-app-git-attribution.ps1 `
  -AppId "<App ID>" `
  -InstallationId "<Installation ID>" `
  -AppSlug "<App slug>" `
  -PrivateKeyPath "C:\path\to\<app>.pem" `
  -Repository "<owner>/<repo>"
```

このスクリプトは次を行う。

1. Appのbot account IDをGitHub APIから取得する。
2. 現在のworktreeだけにbotのAuthorとCommitterを設定する。
3. worktree単位のURL書き換えでfetch/pushの実効URLをHTTPSへ切り替える（共有remote
   は変更しない）。
4. Git credential helperを現在のworktreeだけに設定する。
5. helperがfetch/pull/push時に有効期間1時間のInstallation access tokenを発行する。
6. 公開ID・秘密鍵パス・repositoryを共有Git config（`aiagent.githubApp.*`）へ保存し、
   同じリポジトリの次回以降のworktree設定で再利用する。

秘密鍵の内容と発行トークンはGit設定へ保存しない。記録されるのは秘密鍵のローカル
パス、App ID、Installation ID、App slug、repository名。

初回設定後、新しいworktreeでは引数なしで実行できる。

```powershell
./scripts/configure-github-app-git-attribution.ps1
```

`orca.yaml` の setup hook（`bootstrap-worktree.ps1`）が新しいworktree作成時にこれを
自動実行する。setup hookにApp ID・Installation ID・秘密鍵パスは書かない。別PC・
別cloneでは共有Git configが無いため、最初のworktreeを作る前に既存checkoutで一度
だけ全引数を指定して初期設定する。

## GitHub API操作

```powershell
$body = @{
  title = 'PR title'
  head = 'feature-branch'
  base = 'main'
  body = 'PR body'
} | ConvertTo-Json

./scripts/invoke-github-app-api.ps1 `
  -Method Post `
  -Endpoint '/repos/<owner>/<repo>/pulls' `
  -BodyJson $body
```

このスクリプトは共有Git configのApp設定から有効期間1時間のInstallation access
tokenを発行し、`aiagent.githubApp.repository` 配下のREST APIだけを呼ぶ。トークンは
標準出力、ファイル、Git設定、環境変数へ保存しない。

権限が足りない場合は操作を停止する。個人アカウントのPAT、SSH鍵、`gh auth` へ
フォールバックしない。新しい種類の操作が必要になったら、Appへ最小権限だけを追加し、
インストール側で承認してから再実行する。

## コミット・push前の必須確認

```powershell
git var GIT_AUTHOR_IDENT
git var GIT_COMMITTER_IDENT
git remote get-url origin
git remote get-url --push origin
$env:GIT_TERMINAL_PROMPT = '0'
git fetch --dry-run origin
git push --dry-run origin HEAD
Remove-Item Env:GIT_TERMINAL_PROMPT
```

期待値:

- Author / Committer が `<app-slug>[bot]` と `users.noreply.github.com` の組み合わせ。
- fetch / push URL が `https://github.com/<owner>/<repo>.git`。
- `git fetch --dry-run` / `git push --dry-run` が対話入力なしで成功し、ref は変わらない。
- Installation access token が Git 設定やファイルに出力されていない。

空コミットによる検証は行わない。実際の変更コミットをfeature branchへpushし、
GitHub上でAuthorとpush主体がAppへ帰属していることを確認する。

## 人間との共同作業

人間が変更内容の作成に実質的に関与した場合だけ、コミット本文へ共同作者を記録する。

```text
Co-authored-by: NAME <ID+username@users.noreply.github.com>
```

レビューまたは承認だけの場合は共同作者にせず、PRのReview / Approvalとして残す。

## 既存コミットの扱い

この設定は新しいコミットにだけ適用される。共有・マージ済みコミットのAuthorを
変えるには履歴書き換えとforce pushが必要になるため、通常は過去履歴を書き換えない。

## 参考資料

- [Registering a GitHub App](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app)
- [Installing your own GitHub App](https://docs.github.com/en/apps/using-github-apps/installing-your-own-github-app)
- [Authenticating as a GitHub App installation](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/authenticating-as-a-github-app-installation)
- [Choosing permissions for a GitHub App](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/choosing-permissions-for-a-github-app)
