---
name: "Review ready workflow"
description: "AI実装後、人間がレビューしやすい状態まで整えるための共通フロー"
applyTo: "**"
---

# レビュー準備フロー

AIエージェントの実装が完了したら、「コードを書く」だけで止めず、**人間がGitHub上ですぐレビューできる状態**まで整える。
利用するエージェント（Cursor CLI / Codex / Claude Code / Antigravity / OpenCode / GitHub Copilot）を問わず同じフローにする。

1. オーケストレーターSkill [`.agents/skills/review-ready/SKILL.md`](../../.agents/skills/review-ready/SKILL.md) に従って一連の処理を実行する。
2. 可読性改善は [`.agents/skills/ponytail-review/SKILL.md`](../../.agents/skills/ponytail-review/SKILL.md) と [`.agents/skills/code-simplification/SKILL.md`](../../.agents/skills/code-simplification/SKILL.md)、変更の分割は [`.agents/skills/atomic-commit-splitter/SKILL.md`](../../.agents/skills/atomic-commit-splitter/SKILL.md) を使う。実装フェーズから [`.agents/skills/ponytail/SKILL.md`](../../.agents/skills/ponytail/SKILL.md) の YAGNI モードを有効にしておく。
3. PRの変更説明は [`.agents/skills/change-explainer/SKILL.md`](../../.agents/skills/change-explainer/SKILL.md) に従い、PRコメントを1つだけ維持する。
4. コミット規約は [`.agents/skills/git-workflow-and-versioning/SKILL.md`](../../.agents/skills/git-workflow-and-versioning/SKILL.md) に従う。

Git操作は標準Git、GitHub操作は `AGENTS.md` «GitHub App authentication» が指定する経路（GitHub App の `./scripts/invoke-github-app-api.ps1`、または `gh` などプロジェクト指定のツール）に統一する。エージェント固有のGitHub認証・GitHubツールを必須にしない。
