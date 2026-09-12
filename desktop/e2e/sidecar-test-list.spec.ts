import { test, expect } from "@playwright/test";

import { closeElectronApp, launchElectronApp } from "./electron-launch";
import {
  ANSWER_SHEET_PDF,
  createDraftTest,
  goHome,
  waitForHomeReady,
} from "./registration-helpers";

/**
 * Issue #379 acceptance on the real sidecar path: the owner's report was that
 * an imported test never reached 採点 because the テスト一覧 route was an empty
 * placeholder. This drives the screen the app actually ships -- a created draft
 * test seen through the sidebar and the home overflow link, then both row
 * destinations (テスト設定 and 答案キュー).
 */
test("lists an imported test and reaches settings and the answer queue", async () => {
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
    await page.getByTestId("home-refresh").click();
    await expect(page.getByTestId(`home-test-card-${testId}`)).toBeVisible({
      timeout: 60_000,
    });

    // Sidebar entry (acceptance item 1).
    await page.getByTestId("sidebar-nav-tests").click();
    await expect(page.getByTestId("page-title")).toHaveText("テスト一覧");
    await expect(page.getByTestId(`test-list-row-${testId}`)).toBeVisible();
    await expect(page.getByTestId(`test-list-status-${testId}`)).toHaveText(
      "準備中",
    );

    // テスト設定 row action (acceptance item 2).
    await page.getByTestId(`test-list-open-settings-${testId}`).click();
    await expect(page.getByTestId("criteria-section")).toBeVisible({
      timeout: 15_000,
    });

    // Home overflow entry (acceptance item 5).
    await goHome(page);
    await page.getByTestId("home-open-all-tests").click();
    await expect(page.getByTestId(`test-list-row-${testId}`)).toBeVisible();

    // 答案キュー row action: a draft test has no answers yet, so the queue is
    // empty rather than an error (acceptance item 2).
    await page.getByTestId(`test-list-open-queue-${testId}`).click();
    await expect(page.getByTestId("page-title")).toHaveText("答案キュー");
    await expect(page.getByTestId("queue-empty")).toBeVisible({
      timeout: 15_000,
    });
  } finally {
    await closeElectronApp(app);
  }
});
