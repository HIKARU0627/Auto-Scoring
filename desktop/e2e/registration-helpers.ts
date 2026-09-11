import * as path from "node:path";

import type { ElectronApplication, Page } from "@playwright/test";
import { expect } from "@playwright/test";

import { PACKAGE_ROOT, pollSidecarReady } from "./electron-launch";

export const FIXTURE_ROOT = path.join(
  PACKAGE_ROOT,
  "e2e/fixtures/registration-intake",
);
export const CRITERIA_PDF = path.join(
  FIXTURE_ROOT,
  "subject-a/02_criteria.pdf",
);
export const ANSWER_SHEET_PDF = path.join(
  PACKAGE_ROOT,
  "e2e/fixtures/answer-sheet.pdf",
);

export async function waitForHomeReady(page: Page): Promise<void> {
  await pollSidecarReady(page);
  await expect(page.getByTestId("home-open-intake")).toBeVisible({
    timeout: 15_000,
  });
  await expect(page.getByTestId("home-next-up")).toBeVisible({
    timeout: 60_000,
  });
  await expect(page.getByTestId("home-error")).toHaveCount(0);
}

export async function createDraftTest(page: Page): Promise<string> {
  return page.evaluate(
    async ({ criteriaPdf }) => {
      const status = await window.autoScoring.getSidecarStatus();
      if (status.kind !== "ready") {
        throw new Error("sidecar not ready");
      }
      const response = await window.autoScoring.sidecarMultipartUpload({
        method: "POST",
        urlPath: "/tests",
        fileFields: [{ fieldName: "criteria", filePath: criteriaPdf }],
        formFields: { name: "E2E 理科", subject: "理科" },
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
    { criteriaPdf: CRITERIA_PDF },
  );
}

export async function openDraftTestSettings(
  page: Page,
  testId: string,
): Promise<void> {
  await page.getByTestId("home-refresh").click();
  await expect(page.getByTestId(`home-test-card-${testId}`)).toBeVisible({
    timeout: 60_000,
  });
  await page.getByTestId(`home-resume-registration-${testId}`).click();
  await expect(page.getByTestId("criteria-section")).toBeVisible({
    timeout: 15_000,
  });
  await expect(page.getByTestId("test-status-label")).toHaveText(
    "テスト状態: 下書き",
  );
}

export async function resizeContent(
  app: ElectronApplication,
  page: Page,
  width: number,
  height: number,
): Promise<void> {
  const window = await app.browserWindow(page);
  await window.evaluate(
    (browserWindow, size) => {
      browserWindow.setContentSize(size.width, size.height);
    },
    { width, height },
  );
}

export const E2E_EXTRACT_STUB_ENV = {
  AUTO_SCORING_E2E_STUB_CRITERIA_EXTRACT: "1",
} as const;

export async function openExtractConfirmDialog(page: Page): Promise<void> {
  await page.getByTestId("extract-criteria-button").click();
  await expect(page.getByTestId("extract-confirm-dialog")).toBeVisible({
    timeout: 15_000,
  });
}

export async function expectExtractDialogActionsInViewport(
  page: Page,
): Promise<void> {
  const viewport = await page.evaluate(() => ({
    width: window.innerWidth,
    height: window.innerHeight,
  }));

  for (const testId of ["extract-cancel-button", "extract-confirm-button"]) {
    const box = await page.getByTestId(testId).boundingBox();
    expect(box, `${testId} bounding box`).not.toBeNull();
    expect(box!.y, `${testId} top`).toBeGreaterThanOrEqual(0);
    expect(box!.y + box!.height, `${testId} bottom`).toBeLessThanOrEqual(
      viewport.height,
    );
    expect(box!.width, `${testId} width`).toBeGreaterThan(48);
    expect(box!.height, `${testId} height`).toBeLessThan(80);
  }
}
