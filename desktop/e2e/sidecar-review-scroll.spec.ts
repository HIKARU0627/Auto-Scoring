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

/** Drives intake, registration, and intake again until the review is open. */
async function openFirstReview(page: Page): Promise<void> {
  await waitForHomeReady(page);

  await page.getByTestId("home-open-intake").click();
  await page.getByTestId("intake-choose-folder").click();
  await expect(page.getByTestId("intake-stage-notice-subject-a")).toBeVisible({
    timeout: 30_000,
  });
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
  await expect(page.getByTestId("review-page-region")).toBeVisible({
    timeout: 30_000,
  });
}

/** Sets the renderer viewport through CDP, as the acceptance screenshots do. */
async function setViewport(
  page: Page,
  width: number,
  height: number,
): Promise<void> {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Emulation.setDeviceMetricsOverride", {
    width,
    height,
    deviceScaleFactor: 1,
    mobile: false,
  });
  // Let the screen's ResizeObserver re-measure before reading geometry.
  await page.waitForTimeout(400);
}

interface Geometry {
  readonly innerHeight: number;
  readonly innerWidth: number;
  readonly docScrollHeight: number;
  readonly rail: { top: number; bottom: number };
  readonly inspector: { top: number; bottom: number };
  readonly region: {
    top: number;
    bottom: number;
    scrollHeight: number;
    clientHeight: number;
    scrollWidth: number;
    clientWidth: number;
  };
}

async function readGeometry(page: Page): Promise<Geometry> {
  return page.evaluate(() => {
    const box = (testId: string) => {
      const element = document.querySelector(`[data-testid="${testId}"]`);
      if (element === null) {
        throw new Error(`missing ${testId}`);
      }
      const rect = element.getBoundingClientRect();
      return { top: Math.round(rect.top), bottom: Math.round(rect.bottom) };
    };
    const region = document.querySelector(
      '[data-testid="review-page-region"]',
    ) as HTMLElement;
    return {
      innerHeight: window.innerHeight,
      innerWidth: window.innerWidth,
      docScrollHeight: document.documentElement.scrollHeight,
      rail: box("review-question-rail"),
      inspector: box("review-inspector"),
      region: {
        ...box("review-page-region"),
        scrollHeight: region.scrollHeight,
        clientHeight: region.clientHeight,
        scrollWidth: region.scrollWidth,
        clientWidth: region.clientWidth,
      },
    };
  });
}

async function zoomIn(page: Page, times: number): Promise<void> {
  for (let i = 0; i < times; i += 1) {
    await page.getByTestId("review-zoom-in").click();
  }
}

/**
 * Issue #401 acceptance: zooming the answer PDF must not grow the document or
 * move the 設問レール / 採点パネル; only the PDF region scrolls, on both axes.
 *
 * jsdom has no layout, so `desktop/test/renderer/pdf-review-scroll.test.tsx`
 * fixes the height arithmetic and the scroll-container contract. This spec
 * fixes the behaviour those pieces are for, against the real Electron window.
 */
test("拡大しても両サイドは固定で、PDF領域だけが縦横にスクロールする (Issue #401)", async () => {
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
    await openFirstReview(page);
    await setViewport(page, 1536, 1024);

    const before = await readGeometry(page);
    expect(before.innerWidth).toBe(1536);
    expect(before.innerHeight).toBe(1024);

    await zoomIn(page, 2);
    // Wait for the zoomed surface to land inside the region's scroll area.
    await expect
      .poll(() => readGeometry(page).then((g) => g.region.scrollHeight), {
        timeout: 10_000,
      })
      .toBeGreaterThan(before.region.clientHeight);

    const after = await readGeometry(page);

    // Only the PDF region scrolls: the document itself does not grow.
    expect(after.docScrollHeight).toBeLessThanOrEqual(after.innerHeight + 1);

    // Both bars stay exactly where they were and stay on screen.
    for (const key of ["rail", "inspector"] as const) {
      expect(
        Math.abs(after[key].top - before[key].top),
        key,
      ).toBeLessThanOrEqual(1);
      expect(after[key].top, key).toBeGreaterThanOrEqual(0);
      expect(after[key].bottom, key).toBeLessThanOrEqual(after.innerHeight + 1);
    }

    // The page region owns both scrollbars after the zoom.
    expect(after.region.scrollHeight).toBeGreaterThan(
      after.region.clientHeight,
    );
    expect(after.region.scrollWidth).toBeGreaterThan(after.region.clientWidth);

    // Acceptance screenshot at the exact 1536x1024 renderer size. CDP capture
    // honours the device-metrics override; `page.screenshot` would return the
    // smaller physical window on this host.
    const shotSession = await page.context().newCDPSession(page);
    await shotSession.send("Emulation.setDeviceMetricsOverride", {
      width: 1536,
      height: 1024,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await page.waitForTimeout(300);
    const shot = await shotSession.send("Page.captureScreenshot", {
      format: "png",
    });
    const dir = "/tmp/opencode/401-shots";
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(
      path.join(dir, "review-zoom-1536x1024.png"),
      Buffer.from(shot.data, "base64"),
    );
  } finally {
    await closeElectronApp(app);
  }
});

/**
 * The narrow acceptance: the panes stack, but the page region still owns the
 * zoom scroll (the document may still scroll around the stacked panes).
 */
test("狭い画面でもPDF領域が自前で縦横にスクロールする (Issue #401)", async () => {
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
    await openFirstReview(page);
    await setViewport(page, 700, 900);

    const before = await readGeometry(page);
    await zoomIn(page, 2);
    await expect
      .poll(() => readGeometry(page).then((g) => g.region.scrollHeight), {
        timeout: 10_000,
      })
      .toBeGreaterThan(before.region.clientHeight);

    const after = await readGeometry(page);
    expect(after.region.scrollHeight).toBeGreaterThan(
      after.region.clientHeight,
    );
    expect(after.region.scrollWidth).toBeGreaterThan(after.region.clientWidth);
  } finally {
    await closeElectronApp(app);
  }
});
