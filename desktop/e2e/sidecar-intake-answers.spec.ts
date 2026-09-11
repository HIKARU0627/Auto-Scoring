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

/** Total submissions across every registered test, read from the API. */
async function countSubmissions(page: Page): Promise<number> {
  const tests = (await fetchJson(page, "/test-registrations")) as {
    id: string;
  }[];
  let total = 0;
  for (const test of tests) {
    const submissions = (await fetchJson(
      page,
      `/tests/${test.id}/submissions`,
    )) as unknown[];
    total += submissions.length;
  }
  return total;
}

/**
 * Issue #306 acceptance: 画面操作だけで、答案が 1 枚以上
 * `GET /tests/<id>/submissions` に現れ、採点が始まること。
 *
 * The folder fixture carries one grading-criteria PDF and one answer PDF. The
 * first import must create the draft test and hold the answer back; after the
 * test is registered, the home guidance must lead back to intake, which must
 * reuse the now-ready test and import the answer. No external AI is called.
 */
test("home から答案を取り込み、登録をはさんで採点を始める", async () => {
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
      {
        timeout: 30_000,
      },
    );
    await page.getByTestId("intake-import").click();
    await expect(page.getByTestId("intake-deferred-subject-a")).toBeVisible({
      timeout: 60_000,
    });
    await expect(
      page.getByTestId("intake-imported-submissions-subject-a"),
    ).toHaveCount(0);
    expect(await countSubmissions(page)).toBe(0);

    // 登録を完了させて ready にする。
    await page.getByTestId("intake-open-test-settings-subject-a").click();
    await completeRegistrationFromTestSettings(page);

    // ホームは「登録を続ける」ではなく、次の答案取込を案内する。
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
    const reusedTarget = await page
      .getByTestId("intake-target-subject-a")
      .inputValue();
    expect(reusedTarget).not.toBe("__new__");

    await page.getByTestId("intake-import").click();
    await expect(
      page.getByTestId("intake-imported-submissions-subject-a"),
    ).toBeVisible({ timeout: 60_000 });
    await expect(page.getByText(/AI採点を開始しました/)).toBeVisible({
      timeout: 30_000,
    });

    // 受入条件: `GET /tests/<id>/submissions` に 1 枚以上現れる。
    expect(await countSubmissions(page)).toBeGreaterThanOrEqual(1);
  } finally {
    await closeElectronApp(app);
  }
});
