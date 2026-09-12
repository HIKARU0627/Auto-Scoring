import { test, expect } from "@playwright/test";

import {
  closeElectronApp,
  launchElectronApp,
  pollSidecarReady,
} from "./electron-launch";

/**
 * Issue #398 acceptance: on a host with no AI-grading credentials the
 * 採点不可バナー is actually mounted and visible above the screen. Before this
 * change the component existed but no screen imported it, so the user could not
 * tell "this machine cannot grade" apart from "the AI could not read this
 * answer".
 *
 * The transport is pinned and its key cleared, so the run proves the banner on
 * a machine that happens to export credentials; the fresh per-test app-data
 * has no stored key either (`isolatedSidecarLaunchEnv`).
 */
test("shows the grading-unavailable banner above the home screen", async () => {
  test.setTimeout(120_000);

  const app = await launchElectronApp({
    env: {
      AUTO_SCORING_AI_GRADING_TRANSPORT: "openrouter",
      AUTO_SCORING_OPENROUTER_API_KEY: "",
    },
  });

  try {
    const page = await app.firstWindow();
    await pollSidecarReady(page);

    const banner = page.locator('[data-testid="grading-unavailable-banner"]');
    await expect(banner).toBeVisible({ timeout: 15_000 });
    await expect(
      page.locator('[data-testid="grading-unavailable-headline"]'),
    ).toHaveText("AI採点は使えません（この端末に設定がありません）");
    await expect(
      page.locator('[data-testid="grading-unavailable-reason"]'),
    ).toBeVisible();

    // The band stacks over the screen; it does not replace it.
    await expect(page.locator('[data-testid="home-open-intake"]')).toBeVisible({
      timeout: 10_000,
    });
  } finally {
    await closeElectronApp(app);
  }
});
