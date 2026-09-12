import { test, expect } from "@playwright/test";

import { closeElectronApp, launchElectronApp } from "./electron-launch";
import { waitForHomeReady } from "./registration-helpers";

/**
 * Issue #386 acceptance on the real sidecar path: the settings screen offers
 * every provider the owner asked for, hides the key box where there is no key
 * (Vertex AI authenticates with ADC, Codex with the CLI's own login), and lets
 * the use order be reordered and saved.
 *
 * The host this runs on (CI, a Linux development machine) has no OS credential
 * store, which is a supported configuration: the screen says so and still lists
 * every provider and the order. No key is ever typed, so nothing secret can be
 * in the screenshot.
 */
test("設定画面で提供元と使用順を確認でき、1536x1024でキーが写らない (Issue #386)", async () => {
  test.setTimeout(120_000);

  const app = await launchElectronApp();

  try {
    const page = await app.firstWindow();
    await waitForHomeReady(page);

    await page.getByTestId("sidebar-nav-settings").click();
    await page.getByTestId("settings-tab-api-key").click();

    // All four providers are listed.
    for (const slotId of [
      "openrouter",
      "openai",
      "gemini",
      "codex_app_server",
    ]) {
      await expect(
        page.getByTestId(`settings-api-key-status-${slotId}`),
      ).toBeVisible({
        timeout: 30_000,
      });
    }
    // The two key-bearing providers have a key box...
    await expect(
      page.getByTestId("settings-api-key-field-openrouter"),
    ).toBeVisible();
    await expect(
      page.getByTestId("settings-api-key-field-openai"),
    ).toBeVisible();
    // ...and the keyless ones do not, but do expose their readable settings.
    await expect(page.getByTestId("settings-api-key-field-gemini")).toHaveCount(
      0,
    );
    await expect(
      page.getByTestId("settings-api-key-field-codex_app_server"),
    ).toHaveCount(0);
    await expect(
      page.getByTestId(
        "settings-api-key-setting-gemini-AUTO_SCORING_VERTEX_PROJECT",
      ),
    ).toBeVisible();
    await expect(
      page.getByTestId(
        "settings-api-key-setting-gemini-AUTO_SCORING_VERTEX_LOCATION",
      ),
    ).toBeVisible();

    // The use order lists every transport and can be reordered.
    for (const transport of [
      "gemini",
      "codex_app_server",
      "openrouter",
      "openai",
    ]) {
      await expect(
        page.getByTestId(`settings-transport-order-item-${transport}`),
      ).toBeVisible();
    }
    await page.getByTestId("settings-transport-order-down-gemini").click();

    // No password box holds a value: the screenshot cannot contain a key.
    const passwordValues = await page
      .locator('input[type="password"]')
      .evaluateAll((inputs) =>
        inputs.map((input) => (input as HTMLInputElement).value),
      );
    expect(passwordValues.every((value) => value === "")).toBe(true);

    const cdp = await page.context().newCDPSession(page);
    await cdp.send("Emulation.setDeviceMetricsOverride", {
      width: 1536,
      height: 1024,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await expect(
      page.getByTestId("settings-transport-order-item-openai"),
    ).toBeVisible();

    await page.screenshot({
      path: "test-results/issue-386-settings-1536x1024.png",
      fullPage: false,
    });
  } finally {
    await closeElectronApp(app);
  }
});
