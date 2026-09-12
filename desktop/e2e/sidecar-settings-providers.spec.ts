import * as fs from "node:fs";
import * as path from "node:path";

import { test, expect, type Page } from "@playwright/test";

import { closeElectronApp, launchElectronApp } from "./electron-launch";
import { waitForHomeReady } from "./registration-helpers";

/**
 * Issue #386 acceptance on the real sidecar path: the settings screen offers
 * every provider the owner asked for, hides the key box where there is no key
 * (Vertex AI authenticates with ADC, Codex with the CLI's own login), and lets
 * the use order be reordered and saved.
 *
 * Issue #448 adds two properties this spec pins down on the real app: the use
 * order can be dragged with a pointer **and** reordered with the keyboard
 * buttons that stay next to it, and the model box suggests ids while remaining
 * free text.
 *
 * The host this runs on (CI, a Linux development machine) has no OS credential
 * store, which is a supported configuration: the screen says so and still lists
 * every provider and the order. No key is ever typed, so nothing secret can be
 * in the screenshot.
 */
const SCREENSHOT_DIR = path.join("test-results", "issue-448");

async function setViewport(
  page: Page,
  width: number,
  height: number,
): Promise<void> {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Emulation.setDeviceMetricsOverride", {
    width,
    height,
    deviceScaleFactor: 1,
    mobile: false,
  });
  await page.waitForTimeout(400);
}

/** Mid-drag state has to be photographed before the drop, so it is dispatched
 * by hand rather than with `locator.dragTo` (which completes the drop). The
 * `dragstart` and the `dragover` go in separate round trips so React has
 * committed the "which row is in flight" state before the target is asked to
 * show itself. */
async function startDrag(
  page: Page,
  handleTransport: string,
  targetTransport: string,
): Promise<void> {
  await page.evaluate((handleTransport) => {
    const handle = document.querySelector(
      `[data-testid="settings-transport-order-handle-${handleTransport}"]`,
    );
    handle?.dispatchEvent(
      new DragEvent("dragstart", {
        bubbles: true,
        dataTransfer: new DataTransfer(),
      }),
    );
  }, handleTransport);
  await expect(
    page.getByTestId(`settings-transport-order-item-${handleTransport}`),
  ).toHaveAttribute("data-dragging", "true");

  await page.evaluate((targetTransport) => {
    const target = document.querySelector(
      `[data-testid="settings-transport-order-item-${targetTransport}"]`,
    );
    target?.dispatchEvent(
      new DragEvent("dragover", {
        bubbles: true,
        cancelable: true,
        dataTransfer: new DataTransfer(),
      }),
    );
  }, targetTransport);
}

async function finishDrag(page: Page, targetTransport: string): Promise<void> {
  await page.evaluate((targetTransport) => {
    const target = document.querySelector(
      `[data-testid="settings-transport-order-item-${targetTransport}"]`,
    );
    target?.dispatchEvent(
      new DragEvent("drop", {
        bubbles: true,
        cancelable: true,
        dataTransfer: new DataTransfer(),
      }),
    );
  }, targetTransport);
}

test("設定画面で提供元と使用順を確認でき、D&Dとキーボードで並べ替えられる (Issue #386, #448)", async () => {
  test.setTimeout(120_000);
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });

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

    // Issue #448: the model box is still free text, with suggestions attached.
    const modelInput = page.getByTestId("settings-api-key-model-openrouter");
    await expect(modelInput).toBeVisible();
    expect(await modelInput.getAttribute("list")).toBe(
      "api-key-model-options-openrouter",
    );
    expect(
      await page
        .getByTestId("settings-api-key-model-options-openrouter")
        .locator("option")
        .count(),
    ).toBeGreaterThan(1);

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

    // Keyboard-only reorder: the arrow buttons move Gemini down one place.
    await page.getByTestId("settings-transport-order-down-gemini").click();
    await expect(
      page.getByTestId("settings-api-key-transport-order"),
    ).toHaveText("codex_app_server → gemini → openrouter → openai");

    await setViewport(page, 1536, 1024);
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "order-keyboard-1536x1024.png"),
      fullPage: false,
    });

    // Drag-and-drop reorder, photographed mid-gesture.
    await startDrag(page, "openai", "codex_app_server");
    await expect(
      page.getByTestId("settings-transport-order-item-openai"),
    ).toHaveAttribute("data-dragging", "true");
    await expect(
      page.getByTestId("settings-transport-order-item-codex_app_server"),
    ).toHaveAttribute("data-drop-target", "true");
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "order-dragging-1536x1024.png"),
      fullPage: false,
    });

    await finishDrag(page, "codex_app_server");
    await expect(
      page.getByTestId("settings-api-key-transport-order"),
    ).toHaveText("openai → codex_app_server → gemini → openrouter");

    await setViewport(page, 700, 900);
    // At 700px the order card sits far below the provider list; bring it into
    // the shot rather than photographing whichever provider happens to be on
    // screen.
    await page
      .getByTestId("settings-transport-order-save")
      .scrollIntoViewIfNeeded();
    await page.waitForTimeout(200);
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "order-700x900.png"),
      fullPage: false,
    });

    // No password box holds a value: the screenshot cannot contain a key.
    const passwordValues = await page
      .locator('input[type="password"]')
      .evaluateAll((inputs) =>
        inputs.map((input) => (input as HTMLInputElement).value),
      );
    expect(passwordValues.every((value) => value === "")).toBe(true);
  } finally {
    await closeElectronApp(app);
  }
});
