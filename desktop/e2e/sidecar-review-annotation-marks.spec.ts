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
 * Issue #403 acceptance: the review overlay draws every `AnnotationKind` as
 * its own mark -- `○`/`×`/`△`/underline/box as real strokes, score/comment as
 * text -- in `--color-annotation-mark`, instead of one red rectangle for all
 * seven kinds.
 *
 * This is only measurable against the real Electron window: jsdom has no
 * layout, so the unit tests pin the SVG/text the component produces while this
 * spec fixes that the marks are actually visible on screen at the acceptance
 * size and captures the screenshot from the real app.
 *
 * The annotations are seeded through the review API with synthetic text and
 * fixed rects (no real answer content), as the acceptance requires.
 */

const SCREENSHOT_PATH = path.join(
  "..",
  "docs",
  "pdf-review",
  "annotation-marks-1536x1024.png",
);

/** Seven synthetic marks, one per kind, spread over the page. */
const SEEDED_ANNOTATIONS = [
  { kind: "circle", x: 0.1, y: 0.1, width: 0.1, height: 0.05, comment: null },
  { kind: "cross", x: 0.3, y: 0.1, width: 0.1, height: 0.05, comment: null },
  {
    kind: "triangle",
    x: 0.5,
    y: 0.1,
    width: 0.1,
    height: 0.05,
    comment: null,
  },
  {
    kind: "underline",
    x: 0.1,
    y: 0.25,
    width: 0.25,
    height: 0.03,
    comment: null,
  },
  { kind: "box", x: 0.45, y: 0.25, width: 0.18, height: 0.07, comment: null },
  { kind: "score", x: 0.1, y: 0.4, width: 0.1, height: 0.05, comment: "3/5" },
  {
    kind: "comment",
    x: 0.3,
    y: 0.4,
    width: 0.3,
    height: 0.05,
    comment: "時制に注意",
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

/**
 * Records a human grade carrying all seven annotation kinds for the first
 * question, so the overlay has every kind to draw without a real AI call. The
 * rects are explicit, so placement does not depend on OCR anchor matching.
 */
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

test("添削記号が種類ごとの形と赤文字で答案上に描かれる (Issue #403)", async () => {
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

    // Every kind has its own mark on screen -- not one rectangle for all.
    for (const { kind } of SEEDED_ANNOTATIONS) {
      const mark = page.locator(`[data-kind="${kind}"]`).first();
      await expect(mark).toBeVisible({ timeout: 30_000 });
    }
    // The teacher's red pen, not the UI's error colour.
    await expect(
      page.locator('[data-kind="circle"] svg path').first(),
    ).toHaveAttribute("stroke", "currentColor");

    const parent = path.dirname(SCREENSHOT_PATH);
    fs.mkdirSync(parent, { recursive: true });
    await page.screenshot({ path: SCREENSHOT_PATH, fullPage: false });
  } finally {
    await closeElectronApp(app);
  }
});
