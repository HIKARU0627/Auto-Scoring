import { test, expect, type Page } from "@playwright/test";

import { closeElectronApp, launchElectronApp } from "./electron-launch";
import {
  ANSWER_SHEET_PDF,
  completeRegistrationFromTestSettings,
  FIXTURE_ROOT,
  goHome,
  waitForHomeReady,
} from "./registration-helpers";

/**
 * Issue #450 acceptance on the real sidecar path: the owner could import
 * materials but not see where they were or what came next. The 1536x1024 shots
 * are written to `test-results/`; the committed copies live under
 * `docs/intake-and-settings/`. Only synthetic fixtures appear (subject-a and
 * neutral names), never real answer data.
 */

async function useAcceptanceViewport(page: Page): Promise<void> {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Emulation.setDeviceMetricsOverride", {
    width: 1536,
    height: 1024,
    deviceScaleFactor: 1,
    mobile: false,
  });
}

async function shoot(page: Page, name: string, anchor: string): Promise<void> {
  await useAcceptanceViewport(page);
  await page.getByTestId(anchor).scrollIntoViewIfNeeded();
  await page.screenshot({
    path: `test-results/${name}.png`,
    fullPage: false,
  });
}

test("資料の取込から採点の確認まで、次の一手が見える (Issue #450)", async () => {
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

    // 第 1 段: 資料を取り込み、テストを作る。答案はまだ上げない。
    await page.getByTestId("home-open-intake").click();
    await page.getByTestId("intake-choose-folder").click();
    await expect(page.getByTestId("intake-stage-notice-subject-a")).toBeVisible(
      { timeout: 30_000 },
    );
    await shoot(page, "issue-450-intake-review-1536x1024", "intake-import");

    await page.getByTestId("intake-import").click();
    await expect(page.getByTestId("intake-next-step-heading")).toHaveText(
      "次は、テスト設定で登録を完了します",
      { timeout: 60_000 },
    );
    await shoot(
      page,
      "issue-450-intake-done-register-1536x1024",
      "intake-next-step",
    );

    // 登録を完了させて ready にする。
    await page.getByTestId("intake-next-step-action").click();
    await completeRegistrationFromTestSettings(page);

    // ホームは次の答案取込を案内する。
    await goHome(page);
    await expect(page.getByTestId("home-next-up-action")).toHaveText(
      "答案を取り込む",
    );

    // 第 2 段: 同じフォルダを、登録済みのテストへ取り込む。
    await page.getByTestId("home-next-up-action").click();
    await page.getByTestId("intake-choose-folder").click();
    await expect(page.getByTestId("intake-target-subject-a")).toBeVisible({
      timeout: 30_000,
    });
    await page.getByTestId("intake-import").click();
    await expect(page.getByTestId("intake-next-step-heading")).toHaveText(
      "次は、答案キューで採点を確認します",
      { timeout: 60_000 },
    );
    await shoot(
      page,
      "issue-450-intake-done-review-1536x1024",
      "intake-next-step",
    );

    // 次へ: 答案キュー。順路のどこにいるかが見える。
    await page.getByTestId("intake-next-step-action").click();
    await expect(page.getByTestId("queue-journey")).toBeVisible({
      timeout: 30_000,
    });
    await shoot(page, "issue-450-queue-journey-1536x1024", "queue-journey");

    // テスト一覧は、行ごとに「次は何か」と次の一手を出す。
    await goHome(page);
    await page.getByTestId("sidebar-nav-tests").click();
    await expect(page.getByTestId("test-list-table")).toBeVisible({
      timeout: 30_000,
    });
    const nextRow = page.locator('[data-testid^="test-list-next-"]');
    await expect(nextRow.first()).toBeVisible();
    await shoot(page, "issue-450-test-list-next-1536x1024", "test-list-table");
  } finally {
    await closeElectronApp(app);
  }
});
