# @auto-scoring/desktop

Electron desktop shell for Auto-Scoring (Windows). Replaces `../app` (Flutter)
after cut-over — the plan and the cut-over conditions are in
[`../docs/frontend-migration.md`](../docs/frontend-migration.md).

Issue [#217](https://github.com/HIKARU0627/Auto-Scoring/issues/217) built the
skeleton and the test foundation. **There are no screens yet:** design tokens,
the OpenAPI-generated TypeScript client and the home screen are separate issues.

- Toolchain: Node (`../.node-version`) + pnpm. A workspace package of its own,
  listed in [`../pnpm-workspace.yaml`](../pnpm-workspace.yaml).
- Layers (dependency direction enforced by
  [`test/architecture.test.ts`](./test/architecture.test.ts)):
  - `src/main/` — the Electron main process. Owns the window and, later, the
    Python sidecar's lifecycle (PoC 7 / [#203](https://github.com/HIKARU0627/Auto-Scoring/issues/203)).
  - `src/preload/` — the only bridge. Publishes `window.autoScoring` through
    `contextBridge`; `ipcRenderer` itself is never handed to the renderer.
  - `src/shared/` — the boundary's types (`bridge.ts`). Imports nothing, because
    both sides read it.
  - `src/renderer/` — React UI. Runs with `contextIsolation: true`,
    `nodeIntegration: false`, `sandbox: true`: no Node, no Electron, no `require`.
- **The renderer never receives raw bytes.** The sidecar owns `app-data`
  ([#207](https://github.com/HIKARU0627/Auto-Scoring/issues/207) approval
  condition 3), so a PDF reaches the UI as an identifier, not a byte array.
  `test/architecture.test.ts` fails if a binary payload type appears in
  `src/shared/bridge.ts`.

## Running it

```sh
pnpm run dev     # Vite dev server + a live Electron window
pnpm run start   # build, then run what would ship
```

## Gates

Run them from the repo root — `pnpm run typecheck:desktop`,
`pnpm run test:desktop` (Vitest + React Testing Library, and the
dependency-direction test), `pnpm run test:desktop:e2e` (Playwright launches the
built app), `pnpm run build:desktop`. See
[`../docs/quality-gates.md`](../docs/quality-gates.md).
