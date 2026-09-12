import * as fs from "node:fs";
import * as os from "node:os";
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

async function postJson(
  page: Page,
  urlPath: string,
  body: unknown,
): Promise<number> {
  return page.evaluate(
    async ({ path, payload }) => {
      const response = await window.autoScoring.sidecarFetch({
        method: "POST",
        urlPath: path,
        headers: { "content-type": "application/json" },
        bodyBase64: btoa(JSON.stringify(payload)),
      });
      return response.status;
    },
    { path: urlPath, payload: body },
  );
}

function exportedPdfCount(directory: string): number {
  return fs
    .readdirSync(directory)
    .filter((name) => name.toLowerCase().endsWith(".pdf")).length;
}

/**
 * Issue #345 acceptance: the last step of the product -- choosing a folder and
 * writing the exported PDFs -- runs end to end under `launchElectronApp()`.
 *
 * The destination comes from the same `chooseFolder` bridge the real click
 * uses, driven by `AUTO_SCORING_E2E_FOLDER`; the test does not stub
 * `window.showDirectoryPicker`. Only the external AI is replaced (the criteria
 * extractor), and the grading gap is closed the way Issue #118 designed for a
 * human: a manual grade. The assertion is on the file count, never the
 * contents.
 */
test("一括PDF出力が保存先を選び、実ファイルを書き出す", async () => {
  test.setTimeout(300_000);

  const root = fs.mkdtempSync(path.join(os.tmpdir(), "bulk-export-e2e-"));
  const intakeFolder = path.join(root, "intake");
  fs.cpSync(FIXTURE_ROOT, intakeFolder, { recursive: true });
  const exportFolder = intakeFolder;

  const app = await launchElectronApp({
    env: {
      AUTO_SCORING_E2E_PDF: ANSWER_SHEET_PDF,
      AUTO_SCORING_E2E_FOLDER: intakeFolder,
      AUTO_SCORING_E2E_STUB_CRITERIA_EXTRACT: "1",
      AUTO_SCORING_E2E_STUB_GRADING_JOBS: "1",
      AUTO_SCORING_E2E_STUB_BULK_EXPORT: "1",
    },
  });

  try {
    const page = await app.firstWindow();
    await waitForHomeReady(page);

    // 資料を取り込み、テストを登録する。答案はまだ上げない。
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

    // 登録済みテストへ答案を取り込む。
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

    // 登録ID・答案ID・設問IDをAPIから取る。
    const tests = (await fetchJson(page, "/test-registrations")) as {
      id: string;
    }[];
    const testId = tests[0]?.id;
    expect(testId).toBeTruthy();
    const submissions = (await fetchJson(
      page,
      `/tests/${testId}/submissions`,
    )) as { id: string }[];
    const submissionId = submissions[0]?.id;
    expect(submissionId).toBeTruthy();
    const questions = (await fetchJson(page, `/tests/${testId}/questions`)) as {
      id: string;
      points: number;
    }[];
    const question = questions[0];
    expect(question).toBeTruthy();

    // AI の代わりに人が採点する (Issue #118)。これで答案は確定状態になる。
    const gradeStatus = await postJson(
      page,
      `/submissions/${submissionId}/questions/${question!.id}/review/grade`,
      {
        expected_version: 0,
        score_awarded: 5,
        score_maximum: question!.points,
      },
    );
    expect(gradeStatus).toBe(201);

    // キューから一括出力を開く。
    await goHome(page);
    await page.getByTestId("home-refresh").click();
    await page.getByTestId(`home-open-queue-${testId}`).click({
      timeout: 30_000,
    });
    await expect(page.getByTestId("queue-bulk-export-button")).toBeVisible({
      timeout: 30_000,
    });
    await page.getByTestId("queue-bulk-export-button").click();
    await expect(page.getByTestId("bulk-export-start-button")).toBeVisible({
      timeout: 15_000,
    });

    // Issue #380: `max-w-lg` used to resolve to `--spacing-lg` (16px) and
    // collapse the panel, so assert the real rendered width before starting.
    const bulkPanel = await page
      .locator('[role="dialog"] > div')
      .first()
      .boundingBox();
    expect(bulkPanel, "bulk export panel box").not.toBeNull();
    expect(bulkPanel!.width, "bulk export panel width").toBeGreaterThanOrEqual(
      360,
    );

    const before = exportedPdfCount(exportFolder);
    await page.getByTestId("bulk-export-start-button").click();
    await expect(page.getByTestId("bulk-export-result")).toBeVisible({
      timeout: 120_000,
    });
    await expect(page.getByTestId("bulk-export-result")).toContainText(
      "1 / 1 件を出力しました。",
      { timeout: 120_000 },
    );

    // 実際にファイルが1件書き出されたこと（中身は見ない）。
    expect(exportedPdfCount(exportFolder)).toBe(before + 1);
  } finally {
    await closeElectronApp(app);
    fs.rmSync(root, { recursive: true, force: true });
  }
});
