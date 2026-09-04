# エージェント開発環境（ADE）セットアップ・運用ガイド

GitHub Issueを起点に隔離worktreeで実装し、同じ品質gateでPRへ届けるための再現手順。
設定値の正本は、共通規約が [`AGENTS.md`](../AGENTS.md)、タスクエントリーポイントが
[`package.json`](../package.json) の `scripts`、CIが
[`.github/workflows/ci.yml`](../.github/workflows/ci.yml)。

## 責務

| 層                 | 責務                                                          | 追跡場所                                        |
| ------------------ | ------------------------------------------------------------- | ----------------------------------------------- |
| Agent instructions | 仕様の正本、依存方向、security、Task境界、完了条件            | `AGENTS.md`                                     |
| Repository Skills  | 反復し判断が複雑な専門作業とレビュー準備                      | `.agents/skills/`（`.claude/skills/` はミラー） |
| Setup hook         | worktreeごとの依存導入、Git hooks登録、（任意）GitHub App帰属 | `orca.yaml`、`scripts/bootstrap-worktree.ps1`   |
| Git hooks          | commit前の高速検査、push前のlint・typecheck・test             | `.githooks/`                                    |
| GitHub Actions     | hooksを迂回しても必ず実行する品質gate                         | `.github/workflows/ci.yml`                      |
| main ruleset       | PR経由、required checks、branch削除・force-push禁止           | GitHub repository settings（手動設定）          |

Git hooksは高速・決定的・非破壊な検査だけを行う。重い検証（build、integration、
e2e）はCIを必須gateとし、ローカルではレビュー準備時に実行する。

## 初回構築

### 1. 必要環境

- Git
- Node.js（`.node-version` に固定）
- Corepack / pnpm（`package.json` の `packageManager` に固定）
- PowerShell 7（`pwsh`）— `bootstrap` と GitHub App 帰属スクリプトで使用
- Orca（隔離worktreeのオーケストレーター。前提とする。別ツールや素の branch 運用でも `pnpm run bootstrap` は動く）
- （任意）専用GitHub AppのInstallationとローカルだけに保存した秘密鍵

```bash
pnpm install && pnpm run bootstrap
```

`pnpm run bootstrap` は依存を導入し、`.githooks/` を現在のworktreeへ有効化し、
GitHub App帰属が設定済みならそれも適用する。

### 2. リポジトリ設定（GitHub）

個人開発でもmainへ直接pushせず、変更の根拠とCI結果をPRへ残す。

- merge方式: squash mergeのみ / merge後branch自動削除: 有効
- main ruleset: branch削除禁止、force-push禁止、PR必須、会話解決必須。承認レビューは不要
- required checks: `Quality`（`.github/workflows/ci.yml` の job 名）
- エージェントは `AGENTS.md` に従い、明示依頼がある場合だけ squash merge する

check名を変更するときは workflow、ruleset、[quality-gates.md](./quality-gates.md)
を同じ変更で更新する。

### 3. Orca リポジトリ設定

OrcaのSettings → Repositoryで対象リポジトリを選び、次を設定する。

| 設定             | 値                                                     |
| ---------------- | ------------------------------------------------------ |
| Base ref         | `origin/main`                                          |
| Setup hook       | `pwsh -NoProfile -File scripts/bootstrap-worktree.ps1` |
| Setup run policy | デフォルトで実行                                       |
| Agent startup    | setup完了まで待つ                                      |

setup hook（`orca.yaml` に宣言済み）は現在のworktreeへ依存導入・Git hooks有効化・
（設定済みなら）GitHub App帰属を行う。secret、token、個人環境の絶対pathは
`orca.yaml` へ書かない。Orca以外のツールや素の branch 運用では、同じことを
`pnpm install && pnpm run bootstrap` で各自実行すればよい。

## 日常のTaskフロー

1. 1つのGitHub IssueまたはSub-issueを1つの作業単位にし、目的・対象外・受入条件・
   参照仕様を本文で確認する。
2. `origin/main` を基点に隔離worktree（またはブランチ）を作成する。linked issue、
   worktree、branch、PRを同じTaskへ対応付ける。
3. setup完了後、エージェントは `AGENTS.md` と該当するrepository Skillを読む。
4. 変更に近いtestから実装し、必要な仕様書・運用文書を同じPRで更新する。
5. `pnpm run check` を実行し、`.agents/skills/review-ready/SKILL.md` に従って可読性
   確認 → Atomic Commit → push → Change Summary同期まで行う。
6. PR本文に `Closes #<Issue番号>` を記載する。Sub-issueなら親Issueも参照する。
7. CIが成功したらreview-readyとして人間へ引き渡す。エージェントは明示的な依頼が
   ある場合だけsquash mergeする。
8. レビュー指摘は同じworktreeで修正し、同じ検証とChange Summary同期を繰り返す。

## Repository Skillの最小セット

入口Skillは、頻繁に反復し一般的なagent能力だけでは判断を誤りやすい作業に限定する。

| Trigger                    | 入力                                   | 出力                                               |
| -------------------------- | -------------------------------------- | -------------------------------------------------- |
| 実装完了後: `review-ready` | `origin/main...HEAD` の変更、関連Issue | 可読なdiff、Atomic Commit、push、PR Change Summary |

`atomic-commit-splitter`、`change-explainer`、`code-simplification`、
`git-workflow-and-versioning`、`ponytail` 群は `review-ready` を支える補助Skill。
構成と同期は [review-ready-skills.md](./review-ready-skills.md) を参照。

## 復旧

### setupが失敗する

1. Node.js、`pwsh`、Git がPATHにあることを確認する。
2. `pnpm install` の失敗なら Node / pnpm version と lockfile 差分を確認する。
   lockfileを無断更新しない。
3. GitHub App帰属を使う場合は [ai-agent-git-attribution.md](./ai-agent-git-attribution.md)
   の初回設定を既存checkoutで行い、`pnpm run bootstrap` を再実行する。
4. `git config --get core.hooksPath` が `.githooks` であることを確認する。

### hookまたはCIが失敗する

表示された最初の失敗コマンドを単独で再実行する。`--no-verify` は原因調査中の一時
確認に限定し、CIが成功するまでmergeしない。CI環境だけの失敗はNode / pnpm、環境
変数、OS差分を確認し、検査自体を削除して通さない。
