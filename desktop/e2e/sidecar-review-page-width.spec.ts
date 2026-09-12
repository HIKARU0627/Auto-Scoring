import { test, expect } from "@playwright/test";
import type { Page } from "@playwright/test";

import { closeElectronApp, launchElectronApp } from "./electron-launch";
import {
  ANSWER_SHEET_PDF,
  FIXTURE_ROOT,
  completeRegistrationFromTestSettings,
  goHome,
  resizeContent,
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
 * Issue #354: the answer image must stay inside its own column of the two-column
 * review layout. It used to be drawn at a fixed 640px regardless of the column,
 * so at 1536/900/700 its box crossed the boundary into the inspector and, once
 * the page was scrolled, covered the 続きを表示 control.
 *
 * The assertion is the positive one: at every measured resolution the page
 * surface is contained by its scroll container. `surface` is the element that
 * is actually drawn and `scroller` is its column, so the test fails whenever the
 * page stops respecting the column, not just when a click happens to miss.
 */
test("答案画像はレビューの列からはみ出さない (Issue #354)", async () => {
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
    await page.getByTestId(`home-resume-review-${testId}`).click();
    await expect(page.getByTestId("review-page-surface")).toBeVisible({
      timeout: 30_000,
    });

    const gapsAt = () =>
      page.evaluate(() => {
        const surface = document.querySelector(
          '[data-testid="review-page-surface"]',
        );
        // Issue #401 made the page region scroll on both axes, so it is
        // located by its test id rather than the old `overflow-x-auto` class.
        const scroller =
          surface === null
            ? null
            : surface.closest('[data-testid="review-page-region"]');
        if (surface === null || scroller === null) {
          return null;
        }
        const inner = surface.getBoundingClientRect();
        const column = scroller.getBoundingClientRect();
        return {
          leftGap: inner.left - column.left,
          rightGap: column.right - inner.right,
          width: inner.width,
          columnWidth: column.width,
        };
      });

    for (const [width, height] of [
      [1536, 1024],
      [900, 800],
      [700, 720],
    ] as const) {
      await resizeContent(app, page, width, height);
      // The renderer re-measures through a ResizeObserver after the window
      // resizes; give that callback a turn before reading the geometry.
      await page.waitForTimeout(400);
      const gaps = await gapsAt();
      expect(gaps, `${width}x${height} page surface`).not.toBeNull();
      expect(gaps!.width).toBeLessThanOrEqual(gaps!.columnWidth + 1);
      // A 1px slack absorbs sub-pixel rounding; the old fixed 640px page
      // overflowed by tens of pixels at every one of these widths.
      expect(gaps!.leftGap, `${width}x${height} left`).toBeGreaterThanOrEqual(
        -1,
      );
      expect(gaps!.rightGap, `${width}x${height} right`).toBeGreaterThanOrEqual(
        -1,
      );
    }
  } finally {
    await closeElectronApp(app);
  }
});
