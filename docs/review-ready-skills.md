# レビュー準備Agent Skill群

AIエージェントが生成したコードを、人間が短時間かつ安全にレビューできるよう、
レビュー前の整理を自動化するAgent Skill群。

## 目的

「コードを書く」だけでなく、**人間がレビューしやすい状態まで整理する**ところまで
エージェントに担当させる。

```text
AI実装 → 可読性改善 → Lint / Typecheck / Test / Build → Atomic Commitへ整理 → Push → PRの変更内容を説明 → Human Review
```

レビュー担当者が「PRを開く → 最新のChange Summaryを読む → 影響範囲を把握 →
Atomic Commit単位で確認 → 必要なdiffだけ詳しく読む」でレビューできる状態を目指す。

## Skill一覧

| Skill                                                                                   | 役割                                                                                        | 種別                              |
| --------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- | --------------------------------- |
| [`review-ready`](../.agents/skills/review-ready/SKILL.md)                               | オーケストレーター。下記を順に実行し、結果をまとめて報告する                                | 本テンプレートで作成              |
| [`atomic-commit-splitter`](../.agents/skills/atomic-commit-splitter/SKILL.md)           | 混在した未コミット変更を、部分ステージングで複数のAtomic Commitへ分割する**手順**           | 本テンプレートで作成              |
| [`change-explainer`](../.agents/skills/change-explainer/SKILL.md)                       | PR全体の変更を解析し、Change SummaryをPRコメントとして同期する（常に最新の1コメントを維持） | 本テンプレートで作成              |
| [`code-simplification`](../.agents/skills/code-simplification/SKILL.md)                 | AI生成コードの不要な複雑性を、挙動を変えずに減らす                                          | 外部（`addyosmani/agent-skills`） |
| [`git-workflow-and-versioning`](../.agents/skills/git-workflow-and-versioning/SKILL.md) | コミット規約・粒度・ブランチ運用。最初からAtomic Commitを維持する「予防」側                 | 外部（`addyosmani/agent-skills`） |
| [`ponytail`](../.agents/skills/ponytail/SKILL.md) ほか                                  | YAGNI・標準ライブラリ優先で「そもそも書かない」を徹底するモードとコマンド                   | 外部（`DietrichGebert/ponytail`） |

`git-workflow-and-versioning`（予防）と `atomic-commit-splitter`（整理・修復）は
役割分担の関係にある。可読性改善は `ponytail-review`（過剰実装の洗い出し）と
`code-simplification`（構造整理）を併用する。

## Skillの配置と同期

- **Canonical Source: `.agents/skills/`**。Skill本体はここで一元管理する。
- **`.claude/skills/` はコピーミラー**。Claude Codeは`.claude/skills/`を探索するため、
  `.agents/skills/`の内容をそのままコピーする薄い互換レイヤーを置く。

```bash
pnpm run skills:sync     # .agents/skills/ を .claude/skills/ へ同期する
pnpm run skills:check     # 同期ずれがあれば非ゼロ終了（pnpm run check に含まれる）
```

- 外部Skillは `npx skills add <owner>/<repo> -s <skill> --copy` で取得し、
  `skills-lock.json` でバージョンを固定する。取得したSkillも `.agents/skills/`
  に入るため、以降は上記の同期対象になる。

## エージェント間の互換

| エージェント                        | Skillの参照経路                                                                                                                         |
| ----------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| Antigravity / OpenCode / Codex など | `.agents/skills/` を直接参照                                                                                                            |
| Claude Code                         | `.claude/skills/`（`.agents/skills/` のコピーミラー）                                                                                   |
| Cursor                              | [`.cursor/rules/review-ready.mdc`](../.cursor/rules/review-ready.mdc) が `.agents/skills/` を参照                                       |
| GitHub Copilot                      | [`.github/instructions/review-ready.instructions.md`](../.github/instructions/review-ready.instructions.md) が `.agents/skills/` を参照 |

いずれの経路でも本体は同一の `.agents/skills/**/SKILL.md`。

## GitとGitHubの責務分離

| 対象                                                                   | 手段                                                   |
| ---------------------------------------------------------------------- | ------------------------------------------------------ |
| ローカルRepository（`git status` / `diff` / `add` / `commit` / `log`） | 標準の `git`                                           |
| GitHub（PR取得・PRコメント取得・作成・編集）                           | `AGENTS.md` «GitHub App authentication» が指定する経路 |

GitHub App帰属を採用しているリポジトリでは `./scripts/invoke-github-app-api.ps1`、
採用していないリポジトリでは `gh` などプロジェクト指定のツールを使う。エージェント
ごとに独立したGitHub認証実装を持たせない。詳細は
[ai-agent-git-attribution.md](./ai-agent-git-attribution.md)。
