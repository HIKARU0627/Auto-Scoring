import { test, expect } from "@playwright/test";

import { closeElectronApp, launchElectronApp } from "./electron-launch";

/**
 * Acceptance condition 1 of Issue #217: the Electron app starts and a window
 * appears. Drives the built output (`out/`), which is what `pnpm run test:e2e`
 * builds first, so this covers the real main -> preload -> renderer chain rather
 * than a bundler's idea of it.
 */
test("the app starts and shows a window", async () => {
  const app = await launchElectronApp();

  try {
    // Named `page`, not `window`: inside `evaluate` below, `window` has to mean
    // the renderer's DOM window, not Playwright's handle to it.
    const page = await app.firstWindow();
    await expect(page.getByTestId("sidecar-splash")).toBeVisible();
    await expect(
      page.getByTestId("sidecar-splash").getByRole("heading"),
    ).toHaveText("Auto-Scoring");

    // A window that exists but was never revealed is the failure mode worth
    // catching here: `src/main` creates it hidden and shows it on
    // `ready-to-show`, so an exception in that path would leave the user
    // staring at nothing while the process looks healthy.
    await expect
      .poll(() => page.evaluate(() => document.visibilityState))
      .toBe("visible");

    // The preload bridge is reachable and is the *only* thing reachable: no
    // `require`, no `process`. This is the runtime counterpart of the static
    // rules in test/architecture.test.ts.
    const reachable = await page.evaluate(() => ({
      hasBridge: typeof window.autoScoring?.getAppInfo === "function",
      hasRequire: "require" in globalThis,
      hasProcess: "process" in globalThis,
    }));
    expect(reachable).toEqual({
      hasBridge: true,
      hasRequire: false,
      hasProcess: false,
    });
  } finally {
    await closeElectronApp(app);
  }
});
