# Auto-Scoring

A Windows desktop app that helps a human grade handwritten answer sheets faster.
It takes in the PDFs a cram school provides — student answers, the model answer,
and the grading manual — reads the answers with OCR, proposes a score, marks
(○ / × / △), and comments with an AI model, and then lets a person review,
correct, and approve every proposal before exporting an annotated PDF.

It is deliberately **not** an auto-grader. The design is human-in-the-loop: the
AI produces candidates and its own confidence, and nothing is finalised without a
human decision. Low-confidence readings are never auto-confirmed.

Requirements and acceptance criteria live in
[GitHub Issues](https://github.com/HIKARU0627/Auto-Scoring/issues) (parent issue
[#3](https://github.com/HIKARU0627/Auto-Scoring/issues/3) tracks the MVP 0.2
base); the specification of record is
[`docs/simplified-design-specification.md`](./docs/simplified-design-specification.md).

## Status

The MVP 0.2 base is implemented: every item of the design specification's §31
is covered by an automated test or a recorded manual test — see
[`docs/mvp-acceptance.md`](./docs/mvp-acceptance.md).

Two things are intentionally still placeholders, because the project owner has
not chosen them yet
([`docs/business-rules-and-evaluation-data.md`](./docs/business-rules-and-evaluation-data.md)
§3):

- **OCR service** — the `OCRProvider` port and the review path around it are
  done; the default implementation reports every image as unrecognized, so each
  question routes to a human.
- **AI model** — `AIProvider` adapters exist for OpenRouter and the Codex
  app-server, but `create_app()` still defaults to the null provider.

Both are injected at the boundary, so adopting a real service is an adapter
change, not a rewrite. There is no auto-update, and installers built in CI are
unsigned.

## How it works

1. **Register a test** — upload the model answer, the grading manual, and a
   sample answer sheet. The layout differs per test, so instead of fixed
   coordinates the app builds a per-test _profile_: for each question, its page,
   the question and answer-area regions, and where marks may be placed. A human
   confirms the profile before it is used.
2. **Take in answers** — student answer PDFs are rendered, pre-processed with
   OpenCV, and cropped down to each answer area.
3. **Recognise and grade** — a job queue runs questions in parallel, respecting a
   dependency graph between questions. Recognition confidence and grading
   confidence are kept separate.
4. **Review** — the app shows the PDF with an annotation overlay: proposed score,
   marks, comment, rationale, and both confidences. The reviewer corrects,
   approves, or rejects; the edit history is append-only and undoable.
5. **Export** — once every question is confirmed, an annotated PDF is written.
   The original PDF is never modified.

## Architecture

A Flutter desktop app and a Python sidecar in one process tree, talking over
loopback HTTP:

```text
┌──────────────────────────────┐   HTTP/JSON over 127.0.0.1:<dynamic port>   ┌────────────────────────────┐
│ Flutter desktop (Dart)       │ ──────────────────────────────────────────► │ Python sidecar             │
│  · Material 3 UI             │ ◄────────────────────────────────────────── │  FastAPI + Uvicorn         │
│  · PDF view + annotation     │                                             │   · PDF parse / render     │
│    overlay (pdfrx / pdfium)  │        started, supervised and killed       │   · image pre-processing   │
│  · review and job progress   │        as a child process by the app        │   · OCRProvider            │
│  · holds no API keys         │ ──────────────────────────────────────────► │   · AIProvider             │
└──────────────────────────────┘                                             │   · job queue + SQLite     │
                                                                             └────────────────────────────┘
```

Decisions behind this, with the alternatives that were rejected, are in
[`docs/technology-stack.md`](./docs/technology-stack.md). The essentials:

- Everything runs locally on one machine. The sidecar binds `127.0.0.1` on a
  port picked at startup and requires a bearer token generated at the same time.
- **Only the sidecar holds OCR/AI credentials**, and it sends the minimum per
  question — the answer crop, the model answer, the rubric. No student
  identifying information leaves the machine.
- The sidecar owns the SQLite database; the app reads it only through the API.
- FastAPI's OpenAPI schema is the API contract, and the Dart client in
  `app/packages/auto_scoring_api/` is generated from it and committed.
  `pnpm run openapi:check` fails if the two drift.

Dependency direction is enforced by tests (`app/test/architecture_test.dart`,
`backend/tests/test_architecture.py`):

```text
app:     features → core → api
backend: api → domain ← adapters        (domain imports no framework, DB, or SDK)
```

## Repository layout

| Path              | What it is                                                                                     |
| ----------------- | ---------------------------------------------------------------------------------------------- |
| `app/`            | Flutter desktop app — see [`app/README.md`](./app/README.md)                                   |
| `backend/`        | Python sidecar — see [`backend/README.md`](./backend/README.md)                                |
| `docs/`           | Specification, technology decisions, PoC records, operations — see [`docs/`](./docs/README.md) |
| `scripts/`        | Bootstrap, packaging, OpenAPI, skill sync, GitHub App helpers                                  |
| `installer/`      | Inno Setup script for the Windows installer                                                    |
| `.agents/skills/` | Agent Skills (canonical source; `.claude/skills/` is a generated mirror)                       |
| `package.json`    | The single task entry point for both stacks — `pnpm run <script>`                              |

## Getting started

Needed on PATH: Git, Node.js (`.node-version`), Corepack/pnpm
(`packageManager` in `package.json`), the Flutter SDK (`app/.fvmrc`), and
[uv](https://docs.astral.sh/uv/) for Python (`backend/.python-version`).
PowerShell 7 (`pwsh`) is used by the bootstrap and packaging scripts, and
`pnpm run openapi:check` additionally needs Java (openapi-generator).

```bash
pnpm install && pnpm run bootstrap   # restore deps for both stacks, enable .githooks/
pnpm run check                       # every quality gate
```

Building the desktop app and the installer requires Windows.

## Commands

`pnpm run <script>` is the task interface for humans and agents alike. Each gate
fans out to an `:app` and a `:backend` half (`pnpm run test:backend`, …).

| Script                         | What it does                                            |
| ------------------------------ | ------------------------------------------------------- |
| `bootstrap`                    | Restore both toolchains, point git at `.githooks/`      |
| `format` / `format:check`      | Prettier over repo-level files                          |
| `lint`                         | `dart format` + `flutter analyze`; Ruff check + format  |
| `typecheck`                    | `flutter analyze`; `mypy --strict`                      |
| `test`                         | `flutter test`; `pytest`                                |
| `build`                        | `flutter build windows --debug`; sidecar package import |
| `openapi:export` / `check`     | Regenerate the schema and Dart client, fail on drift    |
| `package:sidecar`              | PyInstaller onedir build of the sidecar                 |
| `package:installer`            | Inno Setup installer (unsigned)                         |
| `skills:sync` / `skills:check` | Mirror `.agents/skills/` into `.claude/skills/`         |
| `check`                        | All of the above, in the order CI runs them             |

The same gates run as git hooks (`.githooks/`) and in GitHub Actions on
`windows-latest`. Details:
[`docs/quality-gates.md`](./docs/quality-gates.md).

## Docs

Specification and technology docs are written in Japanese; the operational docs
below are in English.

| Document                                                                        | Contents                                                   |
| ------------------------------------------------------------------------------- | ---------------------------------------------------------- |
| [simplified-design-specification.md](./docs/simplified-design-specification.md) | The specification of record (Japanese)                     |
| [technology-stack.md](./docs/technology-stack.md)                               | Technology decisions and rejected alternatives (Japanese)  |
| [sidecar-api.md](./docs/sidecar-api.md)                                         | Handshake, auth, OpenAPI → Dart generation                 |
| [data-model-and-local-storage.md](./docs/data-model-and-local-storage.md)       | Entities, SQLite, `app-data/` layout                       |
| [windows-distribution.md](./docs/windows-distribution.md)                       | Packaging, sidecar lifecycle, recovery, signing            |
| [mvp-acceptance.md](./docs/mvp-acceptance.md)                                   | §31 implementation items mapped to the tests proving them  |
| [quality-gates.md](./docs/quality-gates.md)                                     | Gates, git hooks, CI                                       |
| [agent-orchestration.md](./docs/agent-orchestration.md)                         | Running several agents in parallel: roles, units, recovery |

The full index, including the PoC records (Japanese handwriting OCR, AI grading,
PDF coordinates, multi-layout profiles), is [`docs/README.md`](./docs/README.md).

## Working with AI coding agents

This repository is built to be worked on by AI coding agents (Claude Code,
Cursor, Codex, Antigravity, OpenCode, GitHub Copilot) alongside humans, under
one shared contract:

- [`AGENTS.md`](./AGENTS.md) is the instruction file every agent reads first.
  `CLAUDE.md` mirrors it through an `@AGENTS.md` import.
- Skills live once in `.agents/skills/` and are mirrored into `.claude/skills/`
  by `pnpm run skills:sync`; CI fails on drift. External skills are tracked in
  `skills-lock.json`.
- The `review-ready` skill takes finished work to a reviewable state —
  readability pass → `pnpm run check` → atomic commits → push → PR change
  summary. Merging stays a human step.
- Work is coordinated through Orca Orchestration: one issue = one task = one
  active dispatch = one worktree = one branch = one PR, with ownership and
  completion held in orchestration state rather than in a conversation
  ([`docs/agent-orchestration.md`](./docs/agent-orchestration.md)).
- Agent commits and pushes are attributed to a dedicated GitHub App bot rather
  than a personal account
  ([`docs/ai-agent-git-attribution.md`](./docs/ai-agent-git-attribution.md)).

## License

[MIT](./LICENSE)
