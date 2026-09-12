import { test, expect, type Page } from "@playwright/test";

import { closeElectronApp, launchElectronApp } from "./electron-launch";
import {
  ANSWER_SHEET_PDF,
  completeRegistrationFromTestSettings,
  CRITERIA_PDF,
  FIXTURE_ROOT,
  goHome,
  openDraftTestSettings,
  waitForHomeReady,
} from "./registration-helpers";

/**
 * Issue #414 acceptance on the real sidecar path: after registering a test the
 * next step -- adding that test's answers -- was reachable only by knowing the
 * intake route by heart. These drive the three shipped entries (テスト設定,
 * 答案キュー, テスト一覧) and check the intake screen lands with the test
 * already chosen, which is the part a bare "open intake" link would miss.
 *
 * The 1536x1024 shots are written to `test-results/`; the committed copies live
 * under `docs/`. Only synthetic fixtures appear (names like `subject-a`), never
 * real answer data. The test rows use a neutral name so no real subject is
 * visible either.
 */

/**
 * Creates a draft test with a neutral, non-subject name. `createDraftTest`
 * hard-codes a subject for the other specs; the acceptance screenshot must not
 * contain one.
 */
async function createNeutralTest(page: Page, name: string): Promise<string> {
  return page.evaluate(
    async ({ criteriaPdf, testName }) => {
      const status = await window.autoScoring.getSidecarStatus();
      if (status.kind !== "ready") {
        throw new Error("sidecar not ready");
      }
      const response = await window.autoScoring.sidecarMultipartUpload({
        method: "POST",
        urlPath: "/tests",
        fileFields: [{ fieldName: "criteria", filePath: criteriaPdf }],
        formFields: { name: testName },
      });
      if (response.status !== 201) {
        throw new Error(
          `create test failed: ${response.status} ${JSON.stringify(response.body)}`,
        );
      }
      const body = response.body as { id?: string };
      if (body.id === undefined) {
        throw new Error("create test response missing id");
      }
      return body.id;
    },
    { criteriaPdf: CRITERIA_PDF, testName: name },
  );
}

async function useAcceptanceViewport(page: Page): Promise<void> {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Emulation.setDeviceMetricsOverride", {
    width: 1536,
    height: 1024,
    deviceScaleFactor: 1,
    mobile: false,
  });
}

test("registers a test and reaches intake from settings, list, and queue (Issue #414)", async () => {
  test.setTimeout(180_000);

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

    const testId = await createNeutralTest(page, "E2E サンプルA");
    await openDraftTestSettings(page, testId);
    await completeRegistrationFromTestSettings(page);

    // 1. テスト設定: the next step is on the screen that just completed.
    await expect(page.getByTestId("answers-intake-section")).toBeVisible();
    await useAcceptanceViewport(page);
    await page.getByTestId("answers-intake-section").scrollIntoViewIfNeeded();
    await page.screenshot({
      path: "test-results/issue-414-test-settings-1536x1024.png",
      fullPage: false,
    });

    // The button opens intake with this test already chosen.
    await page.getByTestId("open-answers-intake-button").click();
    await expect(page.getByTestId("intake-target-summary")).toBeVisible({
      timeout: 30_000,
    });
    await page.getByTestId("intake-target-summary").scrollIntoViewIfNeeded();
    await page.screenshot({
      path: "test-results/issue-414-intake-target-1536x1024.png",
      fullPage: false,
    });

    // 2. テスト一覧: every row can start the same intake.
    await goHome(page);
    await page.getByTestId("sidebar-nav-tests").click();
    await expect(page.getByTestId(`test-list-row-${testId}`)).toBeVisible({
      timeout: 30_000,
    });
    await useAcceptanceViewport(page);
    await page
      .getByTestId(`test-list-add-answers-${testId}`)
      .scrollIntoViewIfNeeded();
    await page.screenshot({
      path: "test-results/issue-414-test-list-1536x1024.png",
      fullPage: false,
    });
    await page.getByTestId(`test-list-add-answers-${testId}`).click();
    await expect(page.getByTestId("intake-target-summary")).toBeVisible({
      timeout: 30_000,
    });

    // 3. 答案キュー: the empty queue is not a dead end either.
    await goHome(page);
    await page.getByTestId("sidebar-nav-tests").click();
    await expect(page.getByTestId(`test-list-row-${testId}`)).toBeVisible({
      timeout: 30_000,
    });
    await page.getByTestId(`test-list-open-queue-${testId}`).click();
    await expect(page.getByTestId("queue-empty")).toBeVisible({
      timeout: 30_000,
    });
    await useAcceptanceViewport(page);
    await page.getByTestId("queue-add-answers-empty").scrollIntoViewIfNeeded();
    await page.screenshot({
      path: "test-results/issue-414-review-queue-1536x1024.png",
      fullPage: false,
    });
    await page.getByTestId("queue-add-answers-empty").click();
    await expect(page.getByTestId("intake-target-summary")).toBeVisible({
      timeout: 30_000,
    });
  } finally {
    await closeElectronApp(app);
  }
});

test("shows why a draft cannot receive answers and asks before discarding a session (Issue #414)", async () => {
  test.setTimeout(180_000);

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

    const readyId = await createNeutralTest(page, "E2E サンプルA");
    await openDraftTestSettings(page, readyId);
    await completeRegistrationFromTestSettings(page);
    // A second, unfinished test: the destination the intake screen must explain
    // it cannot use yet.
    const draftId = await createNeutralTest(page, "E2E サンプルB");

    await goHome(page);
    await page.getByTestId("sidebar-nav-tests").click();
    await expect(page.getByTestId(`test-list-row-${draftId}`)).toBeVisible({
      timeout: 30_000,
    });

    await page.getByTestId(`test-list-add-answers-${draftId}`).click();
    await expect(page.getByTestId("intake-target-summary")).toBeVisible({
      timeout: 30_000,
    });
    await page.getByTestId("intake-choose-folder").click();
    await expect(page.getByTestId("intake-review-summary")).toBeVisible({
      timeout: 30_000,
    });
    await expect(
      page.getByTestId("intake-draft-reason-subject-a"),
    ).toBeVisible();
    await useAcceptanceViewport(page);
    await page
      .getByTestId("intake-draft-reason-subject-a")
      .scrollIntoViewIfNeeded();
    await page.screenshot({
      path: "test-results/issue-414-draft-not-ready-1536x1024.png",
      fullPage: false,
    });

    // Leaving intake keeps the session. Coming back for another test must not
    // silently throw it away: the screen asks first.
    await goHome(page);
    await page.getByTestId("sidebar-nav-tests").click();
    await expect(page.getByTestId(`test-list-row-${readyId}`)).toBeVisible({
      timeout: 30_000,
    });
    await page.getByTestId(`test-list-add-answers-${readyId}`).click();

    await expect(page.getByTestId("intake-target-conflict")).toBeVisible({
      timeout: 30_000,
    });
    await useAcceptanceViewport(page);
    await page.getByTestId("intake-target-conflict").scrollIntoViewIfNeeded();
    await page.screenshot({
      path: "test-results/issue-414-target-conflict-1536x1024.png",
      fullPage: false,
    });
  } finally {
    await closeElectronApp(app);
  }
});
