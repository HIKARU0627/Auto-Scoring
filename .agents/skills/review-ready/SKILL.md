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
Step 5  change-explainer（PR Change Summary を GitHub App 経由で同期）
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

## Step 5: Change Summary

push後、`change-explainer` Skill を実行する。

- 最新のPR全体（`origin/main...HEAD`）を解析する。
- GitHub App経由で、対応するopen PRの `change-explainer` コメントを **なければ作成 / あれば編集** する。
- 対応するPRが存在しない場合、`change-explainer` はPRを作成しない。Change Summary本文を生成し「PR未作成」と報告する。この場合、必要ならPR作成は人間または明示指示に委ねる。

## 最終報告

次を1つのまとめとして報告する。

```text
review-ready 実行結果

Step 1 可読性改善           : ponytail-review / code-simplification 実施 / 変更なし（対象と結果の要約）
Step 2 Verification        : lint ✓ / typecheck ✓ / build ✓ / e2e 未実行(理由) / ...
Step 3 atomic-commit       : N コミットへ整理 / 単一コミット / 変更なし
Step 4 Push                : origin/<branch> へ push 済み（commit範囲）
Step 5 change-explainer    : PR #<番号> のコメントを 作成/編集（URL） / PR未作成のためSummaryのみ

未解決・要注意:
- （検証失敗、スキップした処理、レビューで重点的に見てほしい点）
```

## 冪等性

同じブランチで再実行しても安全であること。

- Step 1: 既に簡素なら変更を出さない。
- Step 3: 既にAtomic Commitなら履歴を書き換えない。
- Step 5: 既存コメントを編集し、新規コメントを増やさない。

## 検証（このスキルの完了条件）

- [ ] `ponytail-review` と `code-simplification` を利用した（または不要と判断した理由がある）
- [ ] Test / Lint / Typecheck / Build を可能な範囲で実行した
- [ ] `atomic-commit-splitter` を利用した（または既にAtomic Commitである）
- [ ] 必要な変更をpushした
- [ ] `change-explainer` を利用してPR Change Summaryを同期した（またはPR未作成を報告した）
- [ ] 各Stepの結果を最後にまとめて報告した
- [ ] 人間が当該PRのマージを明示依頼していない限り、マージしていない
