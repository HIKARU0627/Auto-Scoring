import { test, expect } from "@playwright/test";

import { closeElectronApp, launchElectronApp } from "./electron-launch";
import {
  ANSWER_SHEET_PDF,
  createDraftTest,
  openDraftTestSettings,
  openExtractConfirmDialog,
  waitForHomeReady,
} from "./registration-helpers";

/**
 * Issue #404 acceptance on the real sidecar path: an answer area an operator
 * drew (the same path auto-detection fills) can be corrected by hand. The
 * owner's report was that manual correction "does not exist" and that mouse
 * area selection "is not intuitive". This drives the shipped screen and checks
 * the pointer capture fix (resize survives leaving the 14px handle), keyboard
 * correction, undo, and drawing a fresh area.
 */
test("an answer area can be corrected with the mouse and the keyboard", async () => {
  test.setTimeout(180_000);

  const app = await launchElectronApp({
    env: {
      AUTO_SCORING_E2E_PDF: ANSWER_SHEET_PDF,
      AUTO_SCORING_E2E_STUB_CRITERIA_EXTRACT: "1",
    },
  });

  try {
    const page = await app.firstWindow();
    await waitForHomeReady(page);

    const testId = await createDraftTest(page);
    await openDraftTestSettings(page, testId);
    await openExtractConfirmDialog(page);
    await page.getByTestId("extract-confirm-button").click();
    await page.getByTestId("confirm-criteria-button").click();
    await expect(page.getByTestId("criteria-section")).toContainText(
      "確認済み",
    );

    await page.getByTestId("upload-answer-layout-button").click();
    await expect(page.getByTestId("answer-area-editor")).toBeVisible({
      timeout: 30_000,
    });

    // The acceptance screenshot is the shipped window at 1536x1024.
    const cdp = await page.context().newCDPSession(page);
    await cdp.send("Emulation.setDeviceMetricsOverride", {
      width: 1536,
      height: 1024,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await page
      .getByTestId("answer-area-draw-surface-0")
      .scrollIntoViewIfNeeded();

    const surfaceBox = async (): Promise<{
      x: number;
      y: number;
      width: number;
      height: number;
    }> => {
      const box = await page
        .getByTestId("answer-area-draw-surface-0")
        .boundingBox();
      if (box === null) {
        throw new Error("answer sheet surface did not render");
      }
      return box;
    };
    const surface = await surfaceBox();

    // Draw a fresh area where the owner expects it: on an empty part of the
    // answer sheet, without pressing "領域を手動追加" first.
    await page.mouse.move(
      surface.x + surface.width * 0.2,
      surface.y + surface.height * 0.05,
    );
    await page.mouse.down();
    await page.mouse.move(
      surface.x + surface.width * 0.4,
      surface.y + surface.height * 0.2,
      { steps: 8 },
    );
    await page.mouse.up();

    const box = page.getByTestId("answer-area-box-0");
    await expect(box).toBeVisible();
    await page.getByTestId("answer-area-draw-target").scrollIntoViewIfNeeded();
    await page.screenshot({
      path: "test-results/issue-404-answer-area-before.png",
      fullPage: false,
    });

    // Correct the drawn area with the mouse. The drag runs well past the
    // 14px handle, which is exactly where the old code lost the pointer and
    // dragged the whole box instead.
    await box.click();
    const before = await box.boundingBox();
    const handle = await page.getByTestId("answer-area-resize-0").boundingBox();
    if (before === null || handle === null) {
      throw new Error("region or resize handle did not render");
    }
    await page.mouse.move(
      handle.x + handle.width / 2,
      handle.y + handle.height / 2,
    );
    await page.mouse.down();
    await page.mouse.move(
      handle.x + handle.width / 2 + 120,
      handle.y + handle.height / 2 + 80,
      { steps: 4 },
    );
    await page.mouse.up();

    const after = await box.boundingBox();
    if (after === null) {
      throw new Error("region disappeared after resize");
    }
    expect(after.width).toBeGreaterThan(before.width + 80);
    expect(after.height).toBeGreaterThan(before.height + 40);
    expect(Math.abs(after.x - before.x)).toBeLessThanOrEqual(2);
    expect(Math.abs(after.y - before.y)).toBeLessThanOrEqual(2);
    await page.getByTestId("answer-area-draw-target").scrollIntoViewIfNeeded();
    await page.screenshot({
      path: "test-results/issue-404-answer-area-after.png",
      fullPage: false,
    });

    // A wrong correction is recoverable.
    await page.getByTestId("answer-area-undo").click();
    const undone = await box.boundingBox();
    expect(undone?.width).toBeCloseTo(before.width, 0);
    expect(undone?.height).toBeCloseTo(before.height, 0);

    // The same correction works without a mouse.
    await box.focus();
    const beforeKey = await box.boundingBox();
    await page.keyboard.press("ArrowRight");
    const afterKey = await box.boundingBox();
    expect((afterKey?.x ?? 0) - (beforeKey?.x ?? 0)).toBeGreaterThan(0);
    await page.keyboard.press("Control+z");
    const undoneKey = await box.boundingBox();
    expect(
      Math.abs((undoneKey?.x ?? 0) - (beforeKey?.x ?? 0)),
    ).toBeLessThanOrEqual(1);

    // Drawing another fresh area still works next to the first one.
    await page
      .getByTestId("answer-area-draw-surface-0")
      .scrollIntoViewIfNeeded();
    const surface2 = await surfaceBox();
    const viewport = await page.evaluate(() => ({
      width: window.innerWidth,
      height: window.innerHeight,
    }));
    const startY = Math.max(surface2.y + surface2.height * 0.05, 10);
    const endY = Math.min(
      Math.max(surface2.y + surface2.height * 0.2, startY + 60),
      viewport.height - 20,
    );
    await page.mouse.move(surface2.x + surface2.width * 0.6, startY);
    await page.mouse.down();
    await page.mouse.move(surface2.x + surface2.width * 0.75, endY, {
      steps: 8,
    });
    await page.mouse.up();
    await expect(page.getByTestId("answer-area-box-1")).toBeVisible();
  } finally {
    await closeElectronApp(app);
  }
});
