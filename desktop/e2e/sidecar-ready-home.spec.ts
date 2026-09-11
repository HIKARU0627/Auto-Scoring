import { test, expect, _electron as electron } from "@playwright/test";

import { electronLaunchArgs } from "./electron-launch";

/**
 * Issue #254 acceptance: the real main process starts the sidecar, the renderer
 * subscribes to lifecycle status, and the home screen appears without mocks.
 */
test("sidecar becomes ready and the home screen is shown", async () => {
  test.setTimeout(120_000);

  const app = await electron.launch({ args: electronLaunchArgs() });

  try {
    const page = await app.firstWindow();

    await expect
      .poll(async () => {
        const sidecarStatus = await page.evaluate(async () => {
          return window.autoScoring.getSidecarStatus();
        });
        return sidecarStatus.kind;
      })
      .toBe("ready");

    await expect(page.locator('[data-testid="home-open-intake"]')).toBeVisible({
      timeout: 10_000,
    });

    const bodyText = await page.locator("body").innerText();
    expect(bodyText).not.toMatch(/Bearer\s+\S+/i);
    expect(bodyText).not.toContain("test-token");
  } finally {
    await app.close();
  }
});
