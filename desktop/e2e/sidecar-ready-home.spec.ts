import { test, expect, _electron as electron } from "@playwright/test";

import {
  electronLaunchArgs,
  isolatedSidecarLaunchEnv,
} from "./electron-launch";

/**
 * Issue #264 acceptance: the sidecar is ready, API data loads on the home
 * screen, and the bearer token never reaches the renderer.
 */
test("sidecar becomes ready and home dashboard loads real API data", async () => {
  test.setTimeout(120_000);

  const app = await electron.launch({
    args: electronLaunchArgs(),
    env: isolatedSidecarLaunchEnv(),
  });

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

    const sidecarStatus = await page.evaluate(async () => {
      return window.autoScoring.getSidecarStatus();
    });

    expect(sidecarStatus).toMatchObject({
      kind: "ready",
      connection: { host: "127.0.0.1" },
    });
    expect(sidecarStatus).not.toHaveProperty("token");
    if (sidecarStatus.kind === "ready") {
      expect(sidecarStatus.connection).not.toHaveProperty("token");
    }

    await expect(page.locator('[data-testid="home-open-intake"]')).toBeVisible({
      timeout: 10_000,
    });

    await expect(page.locator('[data-testid="home-error"]')).toHaveCount(0, {
      timeout: 30_000,
    });

    await expect(page.locator('[data-testid="home-next-up"]')).toBeVisible({
      timeout: 30_000,
    });

    const bodyText = await page.locator("body").innerText();
    expect(bodyText).not.toMatch(/Bearer\s+\S+/i);
    expect(bodyText).not.toContain("test-token");
  } finally {
    await app.close();
  }
});
