# Project instructions

> Template note: this file is the contract every AI agent (Claude Code, Cursor,
> Codex, Antigravity, OpenCode, GitHub Copilot, …) reads first. Adapt the
> bracketed parts to your project, delete what does not apply, and keep it short.
> Anything an agent must always do belongs here; multi-step specialised
> procedures belong in `.agents/skills/`.

## Source of truth and scope

- Requirements and acceptance criteria live in GitHub Issues (parent Issue #3
  tracks the MVP 0.2 base). Architecture and technology decisions live in
  `docs/` — `docs/simplified-design-specification.md` and
  `docs/technology-stack.md`. Implementation decisions and operational
  procedures live in `docs/`.
- One GitHub Issue is one change of purpose. Do not mix unrelated changes; split
  anything out of scope into its own Issue. How that maps onto worktrees,
  branches, and PRs is «Roles and work units» below.
- If a spec is missing, do not decide it in code alone. Record the decision or
  the open question in the relevant doc first. When behaviour, configuration, or
  operations change, update the related docs in the same PR.

## Roles and work units

Settle your role before anything else. Getting it wrong means either taking over
someone else's task or waiting on work nobody is doing.

| Situation                                                                     | Role       | Do this                                                                    |
| ----------------------------------------------------------------------------- | ---------- | -------------------------------------------------------------------------- |
| Your prompt carries an injected preamble with Task and Dispatch IDs           | Worker     | The preamble is authoritative, plus «Worker rules» below                   |
| A human asked you to run several Issues in parallel, supervise, or coordinate | Commander  | `docs/agent-orchestration.md` §3                                           |
| A human handed you one Issue directly — no preamble, no request to supervise  | Solo agent | Work that Issue. Create no Run/Task/Dispatch and send no lifecycle message |

```text
1 GitHub Issue = 1 Orca Task = 1 active Dispatch = 1 worktree = 1 branch = 1 PR
```

Ownership and completion live in Orca's orchestration state, not in a
conversation. An agent going idle is not a completed task, and a `worker_done`
is a claim to be verified, not a verdict. Orca's CLI flags change with the app:
run `orca skills get orchestration --full` before mutating orchestration state
instead of writing commands from memory. Repository-specific policy — which
files actually collide here, how to pick an agent, what a task spec must
contain, how to recover — is in
[`docs/agent-orchestration.md`](./docs/agent-orchestration.md).

### Worker rules

- Do only the assigned task. Carve anything out of scope into its own Issue.
- Ask a blocking question through the preamble's `ask` command. A local prompt
  the coordinator cannot see stalls the whole run.
- Tell the Commander before changing anything shared across tasks — the OpenAPI
  schema, `app/lib/core/`, or a spec document under `docs/`.
- Send `worker_done` exactly once per dispatch, on failure as well as success,
  carrying both IDs, an explicit outcome, a short summary, and any gate you could
  not run with the reason. Never leave a failure implied by prose alone.
- After `worker_done`, end the turn and idle. Do not pick up new work yourself.

## Architecture

- Keep a single, explicit dependency direction and do not create reverse
  references:
  - `app/` (Flutter): `features → core → api`. `api` is the backend client
    (generated later from the OpenAPI schema) and imports neither `core` nor
    `features`; `core` never imports `features`.
  - `backend/` (Python): `api → domain ← adapters`. `domain` must not import
    FastAPI, SQLAlchemy, HTTP clients, or any external-service SDK, nor the
    `api` / `adapters` layers.
  - Both directions are enforced by tests (`app/test/architecture_test.dart`,
    `backend/tests/test_architecture.py`). Full picture:
    `docs/technology-stack.md` §5.
- Keep entry points (route handlers, CLI commands, UI event handlers) thin:
  input validation, auth, calling into the core, and transport translation only.
  Business rules live in the core.
- Inject boundaries (DB, clock, randomness, network, filesystem) from outside the
  core. Guarantee important invariants with real constraints (DB constraints,
  transactions, types), not with UI state.
- Add a new dependency, service, or abstraction only when existing code, the
  standard library, and already-present dependencies cannot meet the requirement.
- Fix cross-cutting layout, naming, and placement conventions in `docs/` and
  follow them; do not let each change invent its own structure.

## Verification

- Run the test closest to your change first. Before handing off for review, run
  `pnpm run check`.
- `pnpm run check` runs: agent-skill mirror check, Prettier, then per stack —
  Dart `format`/`analyze`, `flutter test`, `flutter build windows --debug`, and
  Ruff (lint + format), `mypy --strict`, `pytest`, backend package import. It
  needs the Flutter SDK (`app/.fvmrc`) and `uv` on PATH; restore deps with
  `pnpm run bootstrap` (or `flutter pub get` in `app/` and `uv sync --locked`
  in `backend/`). See `docs/quality-gates.md`.
- `build:app` is `flutter build windows --debug` and cannot pass on Linux
  (`docs/orca-remote-environment.md` §8). Run every gate you can, and report the
  ones you could not run with the reason rather than claiming a full green.
- UI changes: check desktop and mobile, keyboard, focus, and non-colour-dependent
  states. Data/schema changes: include migration, constraints, indexes, a
  recovery procedure, and integration tests in the same PR.
- Distinguish a technical probe from a production feature. A probe is done only
  when its repro command, expected result, actual result, decision, and
  removal-or-promotion condition are all recorded.

## Security

- Validate every input that crosses a trust boundary. Handle authorization, CSRF,
  rate limiting, auditing, and secret masking together with the feature they
  protect, not later.
- Never put secrets, tokens, cookies, full connection strings, real personal
  data, or database dumps into commits, Issues, logs, fixtures, or screenshots.
  Example values go in `.env.example`; real values go in local `.env.local` or
  the hosting provider's environment settings.
- Confirm scope, backup/recovery, and blast radius before destructive data
  operations or production configuration changes.

## Agent Skills

- The canonical source for every skill is `.agents/skills/`. Do not maintain the
  same skill separately per agent.
- `.claude/skills/` is a copy mirror of `.agents/skills/` for agents (Claude
  Code) that search that path. After editing `.agents/skills/`, run
  `pnpm run skills:sync`. `pnpm run check` runs `skills:check` and fails on drift.
- Get external skills with `npx skills add <owner>/<repo> -s <skill> --copy` and
  track them in `skills-lock.json`.
- Only make something a repository skill if it is a repeated, judgement-heavy
  procedure. Do not duplicate one-off steps or plain conventions that this file
  already covers.
- After implementation, do not stop at "the code is written". Follow
  `.agents/skills/review-ready/SKILL.md` to get the change to a state a human can
  review quickly (readability pass → verify → atomic commits → push → PR change
  summary). Related skills: `atomic-commit-splitter`, `change-explainer`,
  `code-simplification`, `ponytail` (`ponytail-review` and friends),
  `git-workflow-and-versioning`.

## Git workflow

- Use short-lived branches off `origin/main`; never push to `main` directly. Keep
  each commit to one purpose — no generated files, formatting-only noise, or
  unrelated refactors mixed in.
- Opening the PR is the agent's step, not the human's: `change-explainer` only
  syncs the summary comment onto a PR that already exists. Look for an open PR
  for your branch and create one through the GitHub App helper when there is
  none (`review-ready` Step 5).
- Put `Closes #<number>` in the PR body. For a sub-issue, reference the parent
  Issue too, and keep the worktree's linked issue consistent.
- The tracked git hooks in `.githooks/` are canonical; `pnpm run bootstrap`
  points the current worktree at them. Hooks can be bypassed, so the same
  required checks run in GitHub Actions and the `main` branch ruleset.
- A Worker or solo agent must not merge a PR, enable auto-merge, or bypass
  merge rules; `review-ready` stops at push + PR + change summary. Merging is
  the Commander's or a human's step.
- The Commander may squash-merge without asking a human each time. The owner
  delegated the merge _decision_ — not verification — on 2026-09-10, but only
  when, before merging, all of these hold: required checks are green, the
  Issue's acceptance criteria are met, the branch carries no change outside
  that Issue's scope, and no unresolved Critical/High review finding remains.
  Green checks alone are not a reason to merge — a red, incomplete, or
  acceptance-unmet PR is stopped regardless of check status. The delegation
  excludes force-push, any destructive operation other than deleting the
  merged branch, and production configuration changes. Full procedure and
  provenance: `docs/agent-orchestration.md` §6.

## GitHub App authentication

> Adopt this section if you want agent commits and pushes attributed to a
> dedicated GitHub App bot instead of a personal account. Otherwise delete it and
> state which identity and push credential agents should use.

- Agents must not use a personal account's credentials for Git or GitHub API
  operations, and must not use the `gh` CLI.
- Before committing, run `./scripts/configure-github-app-git-attribution.ps1` to
  set the GitHub App bot as Author, Committer, and fetch/push credential for the
  current worktree only. After the first run (which takes all parameters), later
  worktrees reuse the values from the shared Git config.
- Verify `git var GIT_AUTHOR_IDENT`, `git var GIT_COMMITTER_IDENT`,
  `git remote get-url origin`, and `git remote get-url --push origin`. If any
  personal-account info or an SSH URL remains, stop fetching, committing, and
  pushing.
- Use `./scripts/invoke-github-app-api.ps1` for GitHub API operations (PRs,
  Issues, comments, labels). If the App lacks a permission, stop and ask a human
  to add the minimal permission — do not fall back to personal auth.
- Do not change `git config --global`. Never store installation access tokens,
  the GitHub App private key, or a symlink to it inside the repository.
- Full procedure: `docs/ai-agent-git-attribution.md`.
