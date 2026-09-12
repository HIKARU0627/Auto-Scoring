import { test, expect } from "@playwright/test";

import { closeElectronApp, launchElectronApp } from "./electron-launch";
import {
  ANSWER_SHEET_PDF,
  FIXTURE_ROOT,
  goHome,
  waitForHomeReady,
} from "./registration-helpers";

/**
 * Issue #384 (3): leaving the intake screen and coming back must not force the
 * operator to choose the folder and route the answers again.
 *
 * The real reproduction is the two-stage flow: import, open テスト設定, press
 * back — the router unmounts `IntakePage`, so before this fix the review state
 * came back empty. This spec drives the built app and checks the folder, file
 * roles and targets survive a round trip through the sidebar, that the restore
 * is announced, and that やり直す drops it.
 */
test("資料の取込は別画面から戻っても選択を保つ", async () => {
  test.setTimeout(300_000);

  const app = await launchElectronApp({
    env: {
      AUTO_SCORING_E2E_PDF: ANSWER_SHEET_PDF,
      AUTO_SCORING_E2E_FOLDER: FIXTURE_ROOT,
      AUTO_SCORING_E2E_STUB_CRITERIA_EXTRACT: "1",
    },
  });

  try {
    const page = await app.firstWindow();
    await waitForHomeReady(page);

    await page.getByTestId("sidebar-nav-intake").click();
    await page.getByTestId("intake-choose-folder").click();
    await expect(page.getByTestId("intake-review-summary")).toBeVisible({
      timeout: 30_000,
    });

    // A role change and an exclusion stand in for "the operator selected things".
    await page
      .getByTestId("intake-role-subject-a/01_answers.pdf")
      .selectOption("reference");
    await page
      .getByTestId("intake-include-subject-a/02_criteria.pdf")
      .uncheck();

    await page.getByTestId("sidebar-nav-tests").click();
    await expect(page.getByTestId("page-title")).toHaveText("テスト一覧", {
      timeout: 15_000,
    });
    await page.getByTestId("sidebar-nav-intake").click();

    await expect(page.getByTestId("intake-restore-notice")).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.getByTestId("intake-review-summary")).toBeVisible();
    await expect(
      page.getByTestId("intake-role-subject-a/01_answers.pdf"),
    ).toHaveValue("reference");
    await expect(
      page.getByTestId("intake-include-subject-a/02_criteria.pdf"),
    ).not.toBeChecked();

    await page.getByTestId("intake-restore-discard").click();
    await expect(page.getByTestId("intake-choose-folder")).toBeVisible();
    await expect(page.getByTestId("intake-review-summary")).toHaveCount(0);

    await goHome(page);
  } finally {
    await closeElectronApp(app);
  }
});
