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
