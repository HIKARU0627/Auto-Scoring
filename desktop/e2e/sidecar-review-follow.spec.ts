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

async function fetchJson(page: Page, urlPath: string): Promise<unknown> {
  return page.evaluate(async (path) => {
    const response = await window.autoScoring.sidecarFetch({
      method: "GET",
      urlPath: path,
    });
    const binary = atob(response.bodyBase64);
    const bytes = Uint8Array.from(binary, (character) =>
      character.charCodeAt(0),
    );
    return JSON.parse(new TextDecoder().decode(bytes)) as unknown;
  }, urlPath);
}

/** The one registered test's id, read from the API rather than the DOM. */
async function firstTestId(page: Page): Promise<string> {
  const tests = (await fetchJson(page, "/test-registrations")) as {
    id: string;
  }[];
  const first = tests[0];
  if (first === undefined) {
    throw new Error("no registered test found");
  }
  return first.id;
}

/**
 * Issue #319 acceptance: entering the review screen *before* grading finishes
 * must still end with 承認 available, with no user action.
 *
 * The app is the real Electron shell, the real Python sidecar, the real
 * SQLite database and the real answer PDF. Only the external AI calls are
 * stubbed (`AUTO_SCORING_E2E_STUB_CRITERIA_EXTRACT`,
 * `AUTO_SCORING_E2E_STUB_GRADING_JOBS`): the job list is served as "running"
 * for a moment and then "succeeded", so the screen's own polling is what the
 * spec exercises.
 */
test("採点が終わる前にレビュー画面へ入り、操作せずに承認できるようになる", async () => {
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

    // 登録を完了させて ready にする。
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

    // 採点が終わる前に入る。スタブは最初の数回を「実行中」で返す。
    await goHome(page);
    const testId = await firstTestId(page);
    await page.getByTestId(`home-resume-review-${testId}`).click();

    const approve = page.getByTestId("review-approve-button");
    await expect(approve).toBeVisible({ timeout: 30_000 });
    // 再読み込みの手段 (受入条件) が画面にある。
    await expect(page.getByTestId("review-refresh-button")).toBeVisible();
    await expect(approve).toBeDisabled();
    await expect(page.getByTestId("review-approve-reason")).toContainText(
      "AIが採点中",
    );

    // 何も操作しない。画面自身の追従だけで承認できるようになる。
    await expect(approve).toBeEnabled({ timeout: 60_000 });
  } finally {
    await closeElectronApp(app);
  }
});
