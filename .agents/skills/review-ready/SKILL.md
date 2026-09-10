---
name: review-ready
description: AIエージェントによる実装完了後、人間がレビューしやすい状態まで整えるオーケストレーターSkill。コード可読性の改善、Test/Lint/Typecheck/Build、Atomic Commitへの整理、Push、PRのChange Summary同期を一連で実行する。「レビュー準備をして」「PRを出せる状態にして」「review-ready」と言われたときに使用する。Cursor CLI / Codex / Claude Code / Antigravity / OpenCode のどれでも同じフローになる。
---

# Review Ready

## 目的

実装が終わったコードを、レビュー担当者が

```text
PRを開く → 最新のChange Summaryを読む → 変更概要と影響範囲を把握 → Atomic Commit単位で確認 → 必要なdiffだけ詳しくレビュー
```

の流れでレビューできる状態まで整える。どのAIエージェントを使っていても同じレビュー準備フローになることを目指す。

## 全体フロー

```text
Implementation Complete
        ↓
Step 1  ponytail-review + code-simplification（可読性改善）
        ↓
Step 2  Verification（Test / Lint / Typecheck / Build）
        ↓
Step 3  atomic-commit-splitter（Atomic Commitへ整理）
        ↓
Step 4  Push
        ↓
Step 5  PR（open PR が無ければ作成する）
        ↓
Step 6  change-explainer（PR Change Summary を GitHub App 経由で同期）
        ↓
人間へ引き渡し（マージしない）
```

各Stepは対応するSkillに委譲する。本Skillは順序・前提確認・最終報告のとりまとめを担う。
GitHubの承認レビューは不要。PRのマージ・auto-mergeは、人間がそのPRを明示的に
依頼したときだけ行う（`AGENTS.md` «Git workflow»）。

## 前提確認（開始前に必ず実施）

1. `git status` で未コミット変更の有無と範囲を確認する。
2. このリポジトリの `AGENTS.md` の «GitHub App authentication» に従う。GitHub App帰属を採用しているリポジトリでは、worktree単位の設定を行う。

   ```powershell
   ./scripts/configure-github-app-git-attribution.ps1
   git var GIT_AUTHOR_IDENT
   git var GIT_COMMITTER_IDENT
   git remote get-url origin
   git remote get-url --push origin
   ```

   Author/Committer が設定済み GitHub App bot（`<app-slug>[bot]`）、fetch/push URL がこのリポジトリの HTTPS URL であることを確認する。個人アカウントや SSH URL が残っていれば中止して人間へ報告する。GitHub App 帰属を採用していないリポジトリでは、`AGENTS.md` が指定する Author と push 認証を使う。
3. 現在のブランチが `main` でないことを確認する。`main` 上なら作業用ブランチを切る。

## Step 1: 可読性改善（Code Simplification / Ponytail Review）

**今回変更された範囲**を中心に、レビューしやすさを上げる。

1. `ponytail-review` Skill を使い、diffの中の過剰実装（標準ライブラリ・ネイティブ機能の再発明、不要な依存、投機的な抽象化、使われない拡張性）を洗い出す。
2. `code-simplification` Skill を使い、深いネスト・長い関数・曖昧な命名・不要な抽象化を整理する。
3. 1・2 で挙がった中から、**挙動を変えない**変更だけを適用する。

- 実装フェーズから `ponytail` モードを有効にしておくと、そもそも整理対象を作らずに済む。
- 今回の変更と無関係なコードを大規模にリファクタリングしない。
- 変更が生じた場合、簡素化のコミットは後続の `atomic-commit-splitter` で機能変更と分けて扱えるよう、未コミットのままにしておく（または `refactor:` として独立コミットにする）。
- 既にコードが十分読みやすい場合は何もしない。

## Step 2: Verification

プロジェクトで利用可能な検証を実行する。実行方法は `package.json` / `pyproject.toml` / `Cargo.toml` / `README` / CI設定から判断する。

このテンプレートでの標準エントリーポイント（`pnpm run <script>`）:

```bash
pnpm run check        # skills:check → format:check → lint → typecheck → test → build をまとめて実行
# 個別に実行する場合:
pnpm run lint
pnpm run typecheck
pnpm run test
pnpm run build
```

- まず速い検証（`pnpm run skills:check` / `pnpm run format:check` / `pnpm run lint` / `pnpm run typecheck`）を実行し、失敗を先に潰す。
- 重い検証（E2E、integration など）はプロジェクトが定義していれば実行する。時間が許すとき、または変更が関係するときに実行する。
- `lint` / `typecheck` / `test` / `build` がそのプロジェクトで未設定（"not configured" と表示）の場合は、その旨を最終報告に書く。
- 失敗したもの・実行しなかったもの（理由付き）は**最終報告に必ず含める**。失敗があっても後続Stepは続行してよいが、報告で明示する。

## Step 3: Atomic Commit

未コミット変更に複数の変更目的が混在している場合、`atomic-commit-splitter` Skill を実行してAtomic Commitへ整理する。

- すでに適切なAtomic Commitになっている場合は、意味のない履歴書き換えをしない。
- 変更目的が1つだけなら、`git-workflow-and-versioning` の規約に沿って単一コミットで確定する。
- コミットメッセージの型・粒度は `git-workflow-and-versioning` に従う。

## Step 4: Push

整理したコミットをリモートへ反映する。

```powershell
$env:GIT_TERMINAL_PROMPT = '0'
git push origin HEAD
Remove-Item Env:GIT_TERMINAL_PROMPT
```

- push認証はworktree設定のGitHub App credential helperが処理する。個人認証・`gh` へフォールバックしない。
- 失敗した場合は中止し、原因（権限・conflict・非fast-forward）を報告する。

## Step 5: PR

push しただけでは、Change Summary の同期先も、人間がレビューする場所も存在しない。
**`change-explainer` は PR を作成しない**ので、無ければここで作る。

```powershell
# 1. 対応する open PR を探す（あれば作らない。二重に作らないこと）
$owner = '<owner>'
$branch = (git rev-parse --abbrev-ref HEAD)
./scripts/invoke-github-app-api.ps1 -Method Get `
  -Endpoint "/repos/<owner>/<repo>/pulls?state=open&head=$owner`:$branch"

# 2. 無ければ作成する。本文はファイルへ書いて -BodyPath で渡す
#    ({ "title": ..., "head": ..., "base": "main", "body": ... } の JSON)
./scripts/invoke-github-app-api.ps1 -Method Post `
  -Endpoint "/repos/<owner>/<repo>/pulls" -BodyPath ./pr-body.json
```

- 本文は [`.github/pull_request_template.md`](../../../.github/pull_request_template.md)
  の構成に沿う。`Closes #<Issue番号>` を必ず入れる（Sub-issue なら親Issueも参照）。
- 本文をコマンドラインへ直接埋め込まない。改行・バッククォート・日本語で壊れるため、
  JSON ファイルに書いて `-BodyPath` で渡し、渡し終えたら消す。
- `base` は `main`。draft にしない（CI を回して人間へ渡すため）。
- 既に open PR があれば作らず、その番号を Step 6 へ渡す。
- **マージ・auto-merge はしない**（`AGENTS.md` «Git workflow»）。
- GitHub App に PR 作成権限が無い場合は中止し、不足している権限を人間へ報告する。
  個人アカウントや `gh` へフォールバックしない。

## Step 6: Change Summary

Step 5 の PR に対して `change-explainer` Skill を実行する。

- 最新のPR全体（`origin/main...HEAD`）を解析する。
- GitHub App経由で、対応するopen PRの `change-explainer` コメントを **なければ作成 / あれば編集** する。
- ここで `change-explainer` が「PR未作成」と報告したら、Step 5 が済んでいない。Step 5 に戻って PR を作り、`change-explainer` を再実行する。人間の手を待たない。
- GitHub App に権限が無くて Step 5 を完了できなかった場合だけ、Summary本文と不足権限を報告して終える。

## 最終報告

次を1つのまとめとして報告する。

```text
review-ready 実行結果

Step 1 可読性改善           : ponytail-review / code-simplification 実施 / 変更なし（対象と結果の要約）
Step 2 Verification        : lint ✓ / typecheck ✓ / build ✓ / e2e 未実行(理由) / ...
Step 3 atomic-commit       : N コミットへ整理 / 単一コミット / 変更なし
Step 4 Push                : origin/<branch> へ push 済み（commit範囲）
Step 5 PR                  : PR #<番号> を作成（URL） / 既存PR #<番号> を利用
Step 6 change-explainer    : PR #<番号> のコメントを 作成/編集（URL）

未解決・要注意:
- （検証失敗、スキップした処理、レビューで重点的に見てほしい点）
```

## 監督下で動いている場合の引き渡し

プロンプトに Task ID / Dispatch ID を含む preamble が注入されている（オーケストレーターに
dispatch された）場合、最終報告を人間へ書くだけで終わらせない。preamble の指示に従い、
その Dispatch につきちょうど1回 `worker_done` を送る。

- 成功・失敗のどちらでも送る。失敗を文章だけで匂わせない。
- Task ID と Dispatch ID の両方、明示的な outcome、上記の最終報告を圧縮した要約を含める。
- **実行できなかった検証（プラットフォーム制約による build など）は理由付きで必ず書く。**
  「全部通した」と書かない。
- 送ったらそのターンを終えて待機する。自分から次の作業を取りに行かない。

マージは Worker の仕事ではない（`AGENTS.md` «Git workflow»）。

## 冪等性

同じブランチで再実行しても安全であること。

- Step 1: 既に簡素なら変更を出さない。
- Step 3: 既にAtomic Commitなら履歴を書き換えない。
- Step 5: 既に open PR があれば作らず、それを使う。
- Step 6: 既存コメントを編集し、新規コメントを増やさない。

## 検証（このスキルの完了条件）

- [ ] `ponytail-review` と `code-simplification` を利用した（または不要と判断した理由がある）
- [ ] Test / Lint / Typecheck / Build を可能な範囲で実行した
- [ ] `atomic-commit-splitter` を利用した（または既にAtomic Commitである）
- [ ] 必要な変更をpushした
- [ ] 対応する open PR がある（既存を見つけたか、`Closes #<n>` 付きで作成した）
- [ ] `change-explainer` を利用してPR Change Summaryを同期した
- [ ] 各Stepの結果を最後にまとめて報告した
- [ ] 人間が当該PRのマージを明示依頼していない限り、マージしていない
- [ ] dispatch されている場合、`worker_done` を1回だけ送った（未実行の検証も明記した）
