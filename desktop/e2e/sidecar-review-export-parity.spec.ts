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

/**
 * Issue #406 acceptance: the review screen draws the confirmed score where the
 * exported PDF draws it, and says where the comments go -- so a reviewer
 * approves the paper the export will actually produce.
 *
 * Only the real Electron window can show this (jsdom has no layout). A question
 * registered by detection has no `score_area` (Issue #103/#159), so this is the
 * *margin* case: the score is drawn in the page's left strip as `a/m 問N`, the
 * same line `domain.pdf_export._fallback_score_text` writes, and the comments
 * are declared to go to the trailing note page (Issue #161).
 *
 * The screenshot pairs the screen with the exported page rendered from the
 * same answer sheet; see docs/pdf-review-overlay.md §2.18.
 */

const SCREENSHOT_PATH = path.join(
  "..",
  "docs",
  "pdf-review",
  "export-parity-screen-1536x1024.png",
);

const SEEDED_ANNOTATIONS = [
  { kind: "circle", x: 0.1, y: 0.1, width: 0.1, height: 0.05, comment: null },
  {
    kind: "cross",
    x: 0.3,
    y: 0.1,
    width: 0.1,
    height: 0.05,
    comment: "時制に注意",
  },
  {
    kind: "comment",
    x: 0.3,
    y: 0.4,
    width: 0.3,
    height: 0.05,
    comment: "記述が不完全です",
  },
] as const;

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

async function seedAnnotatedGrade(page: Page, testId: string): Promise<void> {
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
      annotations: SEEDED_ANNOTATIONS,
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

test("点数とコメントの出力先が、レビュー画面で出力紙面と一致する (Issue #406)", async () => {
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
    await seedAnnotatedGrade(page, testId);

    await page.getByTestId(`home-resume-review-${testId}`).click();
    await expect(page.getByTestId("review-page-surface")).toBeVisible({
      timeout: 30_000,
    });

    const cdp = await page.context().newCDPSession(page);
    await cdp.send("Emulation.setDeviceMetricsOverride", {
      width: 1536,
      height: 1024,
      deviceScaleFactor: 1,
      mobile: false,
    });

    // The confirmed score is drawn on the page, in the margin strip the export
    // uses because the question has no score_area of its own.
    const overlay = page.getByTestId("review-score-overlay");
    await expect(overlay).toBeVisible({ timeout: 30_000 });
    await expect(overlay).toHaveAttribute("data-placement", "margin");
    await expect(overlay).toContainText("/");
    // Same red pen as the export (design-tokens §3.4).
    await expect(overlay).toHaveClass(/text-annotation-mark/);

    // And the comments are declared to leave the answer for the note page,
    // not overlaid on it (Issue #161).
    await expect(page.getByTestId("review-comment-destination")).toContainText(
      "末尾の注釈ページ",
    );

    const parent = path.dirname(SCREENSHOT_PATH);
    fs.mkdirSync(parent, { recursive: true });
    await page.screenshot({ path: SCREENSHOT_PATH, fullPage: false });
  } finally {
    await closeElectronApp(app);
  }
});
