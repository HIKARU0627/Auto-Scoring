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

    // The renderer mounted one of its startup surfaces. Which one is not
    // deterministic: when the sidecar is already `ready`, it replaces the
    // transient `sidecar-splash` with the home screen before Playwright
    // attaches, so asserting the splash here races the sidecar (Issue #288).
    // The splash's own invariants (INV-030/032/036, UG-15) are pinned
    // deterministically in `test/renderer/App.test.tsx`; a slow first start is
    // covered by the 60s poll in `sidecar-ready-home.spec.ts`.
    await expect(
      page
        .getByTestId("sidecar-splash")
        .or(page.getByTestId("home-open-intake"))
        .or(page.getByTestId("sidecar-error")),
    ).toBeVisible();

    // A window that exists but was never revealed is the failure mode worth
    // catching here: `src/main` creates it hidden and shows it on
    // `ready-to-show`, so an exception in that path would leave the user
    // staring at nothing while the process looks healthy. Ask the native window
    // rather than the renderer: on Linux an unshown `BrowserWindow` still
    // reports `document.visibilityState === "visible"`, so the DOM check cannot
    // see this failure.
    const nativeWindow = await app.browserWindow(page);
    await expect
      .poll(() =>
        nativeWindow.evaluate((w) =>
          (w as { isVisible(): boolean }).isVisible(),
        ),
      )
      .toBe(true);

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
