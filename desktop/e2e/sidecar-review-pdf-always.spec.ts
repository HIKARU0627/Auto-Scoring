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
 * Gives the one question a human grade, so the review screen has a score
 * (配点) to show without a real AI call. The E2E grading stub only rewrites the
 * job list; it never writes a `GradeResult`, so a submission that went through
 * it has no AI score to display.
 */
async function seedManualGrade(page: Page, testId: string): Promise<void> {
  const submissions = (await fetchJson(
    page,
    `/tests/${testId}/submissions`,
  )) as { id: string }[];
  const questions = (await fetchJson(page, `/tests/${testId}/questions`)) as {
    id: string;
    points: number;
  }[];
  const submission = submissions[0];
  const question = questions[0];
  if (submission === undefined || question === undefined) {
    throw new Error("submission or question missing");
  }
  const bodyBase64 = Buffer.from(
    JSON.stringify({
      expected_version: 0,
      score_awarded: question.points,
      score_maximum: question.points,
      criteria: [],
    }),
    "utf8",
  ).toString("base64");
  const status = await page.evaluate(
    async ({ urlPath, encoded }) => {
      const response = await window.autoScoring.sidecarFetch({
        method: "POST",
        urlPath,
        headers: { "content-type": "application/json" },
        bodyBase64: encoded,
      });
      return response.status;
    },
    {
      urlPath: `/submissions/${submission.id}/questions/${question.id}/review/grade`,
      encoded: bodyBase64,
    },
  );
  expect(status).toBe(201);
}

/**
 * Issue #385 acceptance: the answer PDF viewer stays on the review screen and
 * the grading controls are visible at the same time at 1536x1024.
 *
 * This part is only measurable against the real Electron window: jsdom has no
 * layout, so vitest fixes the "no question selected" and page-flip logic while
 * this spec fixes that the two panes actually share the viewport.
 *
 * The host display is 1536x864, so a window 1024px tall is clamped by the
 * window manager. The renderer is therefore laid out at the acceptance size
 * through CDP device metrics, which is what the acceptance screenshot uses.
 */
test("答案PDFが常に表示され、1536x1024で採点操作と同時に見える (Issue #385)", async () => {
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

    await goHome(page);
    const testId = await firstTestId(page);
    await seedManualGrade(page, testId);

    await page.getByTestId(`home-resume-review-${testId}`).click();

    // The viewer is on screen as soon as the review screen is.
    await expect(page.getByTestId("review-page-region")).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.getByTestId("review-page-surface")).toBeVisible();
    await expect(page.getByTestId("review-page-indicator")).toHaveText(
      /^\d+ \/ \d+$/,
    );

    const cdp = await page.context().newCDPSession(page);
    await cdp.send("Emulation.setDeviceMetricsOverride", {
      width: 1536,
      height: 1024,
      deviceScaleFactor: 1,
      mobile: false,
    });

    // Wait for the score (配点) so the grading controls are fully on screen.
    await expect(page.getByTestId("review-score")).toBeVisible({
      timeout: 30_000,
    });

    // Every grading control and the PDF must share the 1536x1024 viewport.
    for (const control of [
      "review-page-surface",
      "review-page-indicator",
      "review-page-next",
      "review-score",
      "review-note-field",
      "review-approve-button",
      "review-reject-button",
    ]) {
      await expect(page.getByTestId(control)).toBeInViewport({ ratio: 0.1 });
    }

    await page.screenshot({
      path: "test-results/issue-385-review-1536x1024.png",
      fullPage: false,
    });
  } finally {
    await closeElectronApp(app);
  }
});
