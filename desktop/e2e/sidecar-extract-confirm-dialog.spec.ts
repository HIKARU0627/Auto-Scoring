import { test, expect } from "@playwright/test";

import { closeElectronApp, launchElectronApp } from "./electron-launch";
import {
  ANSWER_SHEET_PDF,
  createDraftTest,
  E2E_EXTRACT_STUB_ENV,
  expectExtractDialogActionsInViewport,
  openDraftTestSettings,
  openExtractConfirmDialog,
  resizeContent,
  waitForHomeReady,
} from "./registration-helpers";

const VIEWPORTS = [
  { width: 700, height: 720, label: "700x720" },
  { width: 1280, height: 762, label: "1280x762" },
] as const;

/** Issue #380 acceptance sizes: the wide desktop and the narrow window. */
const READABILITY_VIEWPORTS = [
  { width: 1536, height: 1024, label: "1536x1024" },
  { width: 700, height: 900, label: "700x900" },
] as const;

for (const viewport of VIEWPORTS) {
  /**
   * Issue #293 acceptance: the extract cost dialog keeps cancel/confirm inside
   * the viewport and clickable at narrow and default Electron sizes. Extraction
   * itself is stubbed — only the dialog interaction is under test.
   */
  test(`extract confirm dialog actions stay in viewport at ${viewport.label}`, async () => {
    test.setTimeout(180_000);

    const app = await launchElectronApp({
      env: { AUTO_SCORING_E2E_PDF: ANSWER_SHEET_PDF, ...E2E_EXTRACT_STUB_ENV },
    });

    try {
      const page = await app.firstWindow();
      await resizeContent(app, page, viewport.width, viewport.height);
      await waitForHomeReady(page);

      const testId = await createDraftTest(page);
      await openDraftTestSettings(page, testId);
      await openExtractConfirmDialog(page);
      await expectExtractDialogActionsInViewport(page);

      await page.getByTestId("extract-confirm-button").click();
      await expect(page.getByTestId("extract-confirm-dialog")).toHaveCount(0);
      await expect(page.getByTestId("criteria-number-0")).toHaveValue("問1");
    } finally {
      await closeElectronApp(app);
    }
  });

  test(`extract cancel closes the dialog at ${viewport.label}`, async () => {
    test.setTimeout(180_000);

    const app = await launchElectronApp({
      env: { AUTO_SCORING_E2E_PDF: ANSWER_SHEET_PDF, ...E2E_EXTRACT_STUB_ENV },
    });

    try {
      const page = await app.firstWindow();
      await resizeContent(app, page, viewport.width, viewport.height);
      await waitForHomeReady(page);

      const testId = await createDraftTest(page);
      await openDraftTestSettings(page, testId);
      await openExtractConfirmDialog(page);
      await expectExtractDialogActionsInViewport(page);

      await page.getByTestId("extract-cancel-button").click();
      await expect(page.getByTestId("extract-confirm-dialog")).toHaveCount(0);
      await expect(page.getByTestId("extract-criteria-button")).toBeEnabled();
    } finally {
      await closeElectronApp(app);
    }
  });
}

for (const viewport of READABILITY_VIEWPORTS) {
  /**
   * Issue #380: `max-w-md` resolved to `--spacing-md` (12px) because the custom
   * spacing scale shadows Tailwind's container scale, collapsing the panel into
   * a 12px bar. Assert the real rendered width, not a jsdom claim.
   */
  test(`extract dialog keeps a readable width at ${viewport.label}`, async () => {
    test.setTimeout(180_000);

    const app = await launchElectronApp({
      env: { AUTO_SCORING_E2E_PDF: ANSWER_SHEET_PDF, ...E2E_EXTRACT_STUB_ENV },
    });

    try {
      const page = await app.firstWindow();
      await page.setViewportSize({
        width: viewport.width,
        height: viewport.height,
      });
      await waitForHomeReady(page);

      const testId = await createDraftTest(page);
      await openDraftTestSettings(page, testId);
      await openExtractConfirmDialog(page);

      const panel = page.locator(
        '[data-testid="extract-confirm-dialog"] > div > div',
      );
      const box = await panel.boundingBox();
      expect(box, "dialog panel box").not.toBeNull();
      expect(box!.width, "dialog panel width").toBeGreaterThanOrEqual(360);
      expect(box!.width, "dialog panel width").toBeLessThanOrEqual(
        viewport.width - 32,
      );
      expect(box!.height, "dialog panel height").toBeLessThanOrEqual(
        viewport.height,
      );

      await expect(page.getByTestId("extract-page-count")).toBeVisible();
      await expect(page.getByTestId("extract-cost")).toBeVisible();
      await expect(page.getByTestId("extract-cancel-button")).toBeVisible();
      await expect(page.getByTestId("extract-confirm-button")).toBeVisible();

      await expect(page.getByTestId("extract-cancel-button")).toBeFocused();

      const focused: (string | null)[] = [];
      for (let i = 0; i < 4; i += 1) {
        await page.keyboard.press("Tab");
        focused.push(
          await page.evaluate(
            () => document.activeElement?.getAttribute("data-testid") ?? null,
          ),
        );
      }
      expect(new Set(focused)).toEqual(
        new Set(["extract-cancel-button", "extract-confirm-button"]),
      );

      await page.keyboard.press("Escape");
      await expect(page.getByTestId("extract-confirm-dialog")).toHaveCount(0);
      await expect(page.getByTestId("extract-criteria-button")).toBeEnabled();
    } finally {
      await closeElectronApp(app);
    }
  });
}
