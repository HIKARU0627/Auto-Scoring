# Template setup checklist

Work through this once after creating a repository from `agent-dev-template`.
Delete this file when you're done.

## 1. Identity

- [ ] `package.json` — set `name`, `description`; keep or bump `engines.node`
      and `.node-version` together.
- [ ] `README.md` — replace with your project's README (keep a pointer to
      `docs/` and `AGENTS.md`).

## 2. Agent contract — `AGENTS.md`

- [ ] Fill in **Source of truth and scope** (where specs live).
- [ ] Fill in **Architecture** with your real dependency direction and layer
      names.
- [ ] Keep or delete the **GitHub App authentication** section (see step 6).
- [ ] Delete guidance that doesn't apply; keep it short.

## 3. Quality gates

- [ ] Replace the four no-op `scripts` in `package.json` — `lint`, `typecheck`,
      `test`, `build` — with real commands. Non-Node projects point them at their
      own tools (e.g. `"test": "cargo test"`) and keep `package.json` as a task
      runner; `skills:sync` and `format` stay on Node.
- [ ] `pnpm run check` should pass (or fail for real reasons).
- [ ] `.github/workflows/ci.yml` — pin actions to commit SHAs; add
      integration / e2e jobs if you have them.
- [ ] After the first real run, make `Quality` and `Agent review` **required**
      in the `main` branch ruleset. Do not require a native approving-review
      count of 1 (authors cannot approve their own PRs). Agent PRs are gated
      by `.github/workflows/agent-review.yml`.

## 4. MCP servers

- [ ] Add your servers to `.mcp.json`, `.cursor/mcp.json`, and
      `.agents/mcp_config.json` (all three — see `docs/mcp.md`). No secrets.

## 5. Skills

- [ ] Keep the `review-ready` cluster. Add project-specific skills only for
      repeated, judgement-heavy procedures.
- [ ] Add external skills with
      `npx skills add <owner>/<repo> -s <skill> --copy`, then `pnpm run skills:sync`.
      They're tracked in `skills-lock.json`.
- [ ] Remove any skill you won't use, then `pnpm run skills:sync`.

## 6. GitHub App attribution (optional)

- [ ] **Using it?** Follow `docs/ai-agent-git-attribution.md`: create the App,
      run `./scripts/configure-github-app-git-attribution.ps1` once with all
      parameters (including `-Repository <owner>/<repo>`).
- [ ] **Not using it?** Delete the **GitHub App authentication** section from
      `AGENTS.md`, delete `scripts/configure-github-app-git-attribution.ps1`,
      `scripts/github-app-git-credential.ps1`,
      `scripts/invoke-github-app-api.ps1`, and `docs/ai-agent-git-attribution.md`.
      State which identity and push credential agents should use instead. In
      `.agents/skills/change-explainer/SKILL.md` and
      `.agents/skills/review-ready/SKILL.md`, the GitHub-App examples then read as
      "use `gh api` / `gh`".

## 7. Worktree orchestrator (Orca)

- [ ] Orca is the assumed orchestrator. In Settings → Repository, set the base
      ref to `origin/main`. `orca.yaml` already declares the setup hook
      (`pwsh -NoProfile -File scripts/bootstrap-worktree.ps1`).
- [ ] Not using Orca? `orca.yaml` is harmless to leave; run
      `pnpm install && pnpm run bootstrap` yourself per checkout / branch.

## 8. Issue / PR templates

- [ ] Tailor `.github/ISSUE_TEMPLATE/*.yml` and
      `.github/pull_request_template.md` to your workflow and language.
