# agent-dev-template

A reusable, framework-agnostic development environment for working with AI coding
agents (Claude Code, Cursor, Codex, Antigravity, OpenCode, GitHub Copilot). Use
it as a GitHub template for new projects.

## What you get

| Piece                               | Files                                                                                                                                                                |
| ----------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Agent contract**                  | `AGENTS.md` — the single instruction file every agent reads first; `CLAUDE.md` mirrors it via `@AGENTS.md` import                                                    |
| **Shared Agent Skills**             | `.agents/skills/` (canonical) → `.claude/skills/` (mirror), plus Cursor rules and Copilot instructions pointing at the same source                                   |
| **Skill sync + lockfile**           | `scripts/sync-agent-skills.mjs`, `skills-lock.json`                                                                                                                  |
| **Review-ready workflow**           | `review-ready` orchestrator + `atomic-commit-splitter`, `change-explainer`, `code-simplification`, `git-workflow-and-versioning`, `ponytail*`                        |
| **Task entrypoints**                | `package.json` scripts — `pnpm run <script>` (`check`, `bootstrap`, `skills:sync`, …)                                                                                |
| **Quality gates**                   | `.githooks/pre-commit`, `.githooks/pre-push`, `.github/workflows/ci.yml`                                                                                             |
| **Per-worktree bootstrap**          | `scripts/bootstrap-worktree.ps1`, `orca.yaml`                                                                                                                        |
| **Optional GitHub App attribution** | `scripts/configure-github-app-git-attribution.ps1`, `scripts/github-app-git-credential.ps1`, `scripts/invoke-github-app-api.ps1`, `docs/ai-agent-git-attribution.md` |
| **GitHub scaffolding**              | Issue templates, PR template, MCP config for 3 agent families                                                                                                        |

It ships **without** any application code or framework. `pnpm run <script>` is
the single task interface; a non-Node project keeps `package.json` purely as a
task runner and points the `lint` / `typecheck` / `test` / `build` scripts at its
own tools.

## Quick start (new project)

1. **Create from template**: on GitHub, "Use this template" → new repository.
   (Or `gh repo create <name> --template <owner>/agent-dev-template --private`.)
2. **Bootstrap**:
   ```bash
   pnpm install && pnpm run bootstrap
   ```
   Installs deps and points git at `.githooks/`.
3. **Wire up your project** — follow [`TEMPLATE_SETUP.md`](./TEMPLATE_SETUP.md):
   fill in `AGENTS.md`, set real `lint` / `typecheck` / `test` / `build`
   scripts, add your MCP servers, decide on GitHub App attribution.
4. **Verify**:
   ```bash
   pnpm run check
   ```

## Daily use

- Humans and agents both use `pnpm run <script>` — see `scripts` in
  `package.json` (`check`, `bootstrap`, `skills:sync`, `format`, …).
- Agents read `AGENTS.md`, then the relevant skill in `.agents/skills/`.
- After implementing, run the `review-ready` skill: readability pass →
  `pnpm run check` → atomic commits → push → PR change summary. Do not merge
  unless a human asked to merge that PR (`AGENTS.md`). GitHub does not require
  an approving review.
- Edit a skill in `.agents/skills/`, then `pnpm run skills:sync`. CI fails on
  drift.

## Requirements

- Git, Node.js (`.node-version`), Corepack/pnpm (`package.json` `packageManager`)
- PowerShell 7 (`pwsh`) — only for `bootstrap` and the GitHub App scripts

## Docs

- [`docs/ade-setup.md`](./docs/ade-setup.md) — Issue → worktree → PR operations
- [`docs/quality-gates.md`](./docs/quality-gates.md) — gates, hooks, CI
- [`docs/review-ready-skills.md`](./docs/review-ready-skills.md) — the skill cluster
- [`docs/ai-agent-git-attribution.md`](./docs/ai-agent-git-attribution.md) — GitHub App bot identity (optional)
- [`docs/mcp.md`](./docs/mcp.md) — MCP server config across agents
