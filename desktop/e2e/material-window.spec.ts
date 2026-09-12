import { test, expect } from "@playwright/test";

import { closeElectronApp, launchElectronApp } from "./electron-launch";
import {
  ANSWER_SHEET_PDF,
  createDraftTest,
  openDraftTestSettings,
  waitForHomeReady,
} from "./registration-helpers";

/**
 * The material window (Issue #415).
 *
 * This is the one test that proves the decision "the main process opens the
 * window, the renderer does not" actually holds at runtime: the click goes
 * through IPC, Electron creates a real second `BrowserWindow` with the same
 * preload and CSP, and Playwright sees it as a second `Page`. It also pins the
 * two window *lifetime* rules from the Issue: the window is reused rather than
 * multiplied, and closing it does not stop the work in the main window.
 */
test("a material opens in a reused second window and closes without stopping the main window (Issue #415)", async () => {
  test.setTimeout(300_000);

  const app = await launchElectronApp({
    env: { AUTO_SCORING_E2E_PDF: ANSWER_SHEET_PDF },
  });

  try {
    const mainWindow = await app.firstWindow();
    await waitForHomeReady(mainWindow);

    // Seed a draft test whose only material is the 採点基準 PDF; no registration
    // steps are needed to list or render a material.
    const testId = await createDraftTest(mainWindow);
    await openDraftTestSettings(mainWindow, testId);

    expect(app.windows()).toHaveLength(1);

    const openedWindow = app.waitForEvent("window", { timeout: 30_000 });
    await mainWindow.getByTestId("test-settings-open-materials-button").click();
    const materialWindow = await openedWindow;

    await expect(materialWindow.getByTestId("material-window")).toBeVisible({
      timeout: 60_000,
    });

    // Acceptance: the list carries the role, so "which file became the
    // 採点基準?" is answerable from the window.
    await expect(materialWindow.getByTestId("material-list")).toContainText(
      "採点基準",
      { timeout: 30_000 },
    );

    // Acceptance: the content is actually shown (the sidecar rasterized it).
    await expect(materialWindow.getByTestId("material-page-image")).toBeVisible(
      { timeout: 60_000 },
    );

    // Decision 3: opening again must re-focus the same window, not add one.
    await mainWindow.getByTestId("test-settings-open-materials-button").click();
    await mainWindow.waitForTimeout(1_000);
    expect(app.windows()).toHaveLength(2);

    // Decision 4: closing the material window leaves the main window working.
    await materialWindow.getByTestId("material-close-button").click();
    await expect
      .poll(() => materialWindow.isClosed(), { timeout: 15_000 })
      .toBe(true);
    expect(app.windows()).toHaveLength(1);
    await expect(mainWindow.getByTestId("test-settings-status")).toBeVisible();
  } finally {
    await closeElectronApp(app);
  }
});

test("closing the main window closes the material window too (Issue #415)", async () => {
  test.setTimeout(300_000);

  const app = await launchElectronApp({
    env: { AUTO_SCORING_E2E_PDF: ANSWER_SHEET_PDF },
  });

  try {
    const mainWindow = await app.firstWindow();
    await waitForHomeReady(mainWindow);

    const testId = await createDraftTest(mainWindow);
    await openDraftTestSettings(mainWindow, testId);

    const openedWindow = app.waitForEvent("window", { timeout: 30_000 });
    await mainWindow.getByTestId("test-settings-open-materials-button").click();
    const materialWindow = await openedWindow;
    await expect(materialWindow.getByTestId("material-window")).toBeVisible({
      timeout: 60_000,
    });

    // Decision 4's other half: the material window must not outlive the main
    // one. Without the handler in `main.ts`, it would keep the process alive.
    await mainWindow.close();
    await expect
      .poll(() => materialWindow.isClosed(), { timeout: 15_000 })
      .toBe(true);
  } finally {
    await closeElectronApp(app);
  }
});
