import * as fs from "node:fs";
import * as path from "node:path";

import { test, expect } from "@playwright/test";
import type { Page } from "@playwright/test";

import { closeElectronApp, launchElectronApp } from "./electron-launch";
import {
  ANSWER_SHEET_PDF,
  FIXTURE_ROOT,
  completeRegistrationFromTestSettings,
  goHome,
  waitForHomeReady,
} from "./registration-helpers";

/** The one registered test's id, read from the API rather than the DOM. */
async function firstTestId(page: Page): Promise<string> {
  const tests = (await page.evaluate(async () => {
    const response = await window.autoScoring.sidecarFetch({
      method: "GET",
      urlPath: "/test-registrations",
    });
    const binary = atob(response.bodyBase64);
    const bytes = Uint8Array.from(binary, (character) =>
      character.charCodeAt(0),
    );
    return JSON.parse(new TextDecoder().decode(bytes)) as { id: string }[];
  })) as { id: string }[];
  const first = tests[0];
  if (first === undefined) {
    throw new Error("no registered test found");
  }
  return first.id;
}

/** Puts a screenshot somewhere a human can look at it after the run. */
async function shoot(page: Page, name: string): Promise<void> {
  const dir = "/tmp/opencode/402-shots";
  fs.mkdirSync(dir, { recursive: true });
  await page.screenshot({ path: path.join(dir, name) });
}

/**
 * Issue #402 acceptance: pressing 再判定 must visibly say the request is being
 * carried out, and the rail must settle on its own once the replacement job
 * lands -- instead of sitting on 再判定待ち forever.
 *
 * Real Electron shell, real Python sidecar, real SQLite, real answer PDF. Only
 * the external AI calls are stubbed (`AUTO_SCORING_E2E_STUB_GRADING_JOBS`): the
 * job list is served as "running" for the first few reads and then "succeeded",
 * which is exactly the window this spec needs -- it enters review while grading
 * is in flight, so the regrade is pressed while the replacement job is still
 * reported as running.
 */
test("再判定を押すと再判定中と分かり、操作なしでレビュー待ちに戻る", async () => {
  test.setTimeout(300_000);

  const app = await launchElectronApp({
    env: {
      AUTO_SCORING_E2E_PDF: ANSWER_SHEET_PDF,
      AUTO_SCORING_E2E_FOLDER: FIXTURE_ROOT,
      AUTO_SCORING_E2E_STUB_CRITERIA_EXTRACT: "1",
      AUTO_SCORING_E2E_STUB_GRADING_JOBS: "1",
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
    await page.getByTestId("intake-import").click();
    await expect(page.getByTestId("intake-deferred-subject-a")).toBeVisible({
      timeout: 60_000,
    });

    await page.getByTestId("intake-open-test-settings-subject-a").click();
    await completeRegistrationFromTestSettings(page);

    // 第 2 段: 登録済みのテストへ答案を取り込み、採点を始める。
    await goHome(page);
    await page.getByTestId("home-next-up-action").click();
    await page.getByTestId("intake-choose-folder").click();
    await expect(page.getByTestId("intake-target-subject-a")).toBeVisible({
      timeout: 30_000,
    });
    await page.getByTestId("intake-import").click();
    await expect(
      page.getByTestId("intake-imported-submissions-subject-a"),
    ).toBeVisible({ timeout: 60_000 });
    await expect(page.getByText(/AI採点を開始しました/)).toBeVisible({
      timeout: 30_000,
    });

    // 採点が終わる前に入る。この時点ではまだ AI処理中。
    await goHome(page);
    const testId = await firstTestId(page);
    await page.getByTestId(`home-resume-review-${testId}`).click();

    const approve = page.getByTestId("review-approve-button");
    const rail = page.locator('[data-testid^="review-rail-"]').first();
    await expect(approve).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("review-approve-reason")).toContainText(
      "AIが採点中",
    );
    await expect(rail).toContainText("AI処理中");

    // 採点中に再判定を押す。
    await page.getByTestId("review-regrade-button").click();

    // 押した直後: 何も起きていないようには見えない。
    await expect(page.getByTestId("review-regrade-in-progress")).toBeVisible({
      timeout: 10_000,
    });
    await shoot(page, "regrade-in-progress.png");

    // 操作せずに、画面自身の追従だけでレビュー待ちへ戻る。
    await expect(approve).toBeEnabled({ timeout: 60_000 });
    await expect(page.getByTestId("review-regrade-in-progress")).toHaveCount(0);
    await expect(rail).not.toContainText("再判定待ち");
    await expect(rail).toContainText("レビュー待ち");
    await shoot(page, "regrade-done.png");
  } finally {
    await closeElectronApp(app);
  }
});
