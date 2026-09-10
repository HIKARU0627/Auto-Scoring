import { defineConfig } from "@playwright/test";

/**
 * Electron flow tests. They drive the built app (`out/`), so `pnpm run build`
 * has to have run first -- `pnpm run test:e2e` chains the two.
 *
 * No `projects` and no browser download: `_electron.launch()` uses the Electron
 * binary from `node_modules`, so `playwright install` is not part of the setup.
 */
export default defineConfig({
  testDir: "e2e",
  // An Electron window that never appears should be reported as a failure in
  // well under a minute rather than hanging a CI job for the default timeout.
  timeout: 60_000,
  expect: { timeout: 10_000 },
  // A flaky launch test is a broken launch test; retrying would hide exactly
  // the intermittent orphan/lock problems this app has a history of.
  retries: 0,
  workers: 1,
  reporter:
    process.env["CI"] === undefined ? [["list"]] : [["list"], ["github"]],
});
