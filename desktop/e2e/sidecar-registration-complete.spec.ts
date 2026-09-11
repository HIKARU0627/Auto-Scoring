import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

import { test, expect, _electron as electron } from "@playwright/test";

import { electronLaunchArgs, PACKAGE_ROOT } from "./electron-launch";

const FIXTURE_ROOT = path.join(
  PACKAGE_ROOT,
  "e2e/fixtures/registration-intake",
);
const CRITERIA_PDF = path.join(FIXTURE_ROOT, "subject-a/02_criteria.pdf");
const ANSWER_SHEET_PDF = path.join(
  PACKAGE_ROOT,
  "e2e/fixtures/answer-sheet.pdf",
);

type ElectronPage = Awaited<
  ReturnType<Awaited<ReturnType<typeof electron.launch>>["firstWindow"]>
>;

async function waitForSidecarReady(page: ElectronPage): Promise<void> {
  await expect
    .poll(async () => {
      const sidecarStatus = await page.evaluate(async () => {
        return window.autoScoring.getSidecarStatus();
      });
      return sidecarStatus.kind;
    })
    .toBe("ready");
}

async function waitForHomeReady(page: ElectronPage): Promise<void> {
  await waitForSidecarReady(page);
  await expect(page.getByTestId("home-open-intake")).toBeVisible({
    timeout: 15_000,
  });
  await expect(page.getByTestId("home-next-up")).toBeVisible({
    timeout: 60_000,
  });
  await expect(page.getByTestId("home-error")).toHaveCount(0);
}

function e2eLaunchEnv(): Record<string, string> {
  const appDataDir = fs.mkdtempSync(
    path.join(os.tmpdir(), "auto-scoring-e2e-app-data-"),
  );
  return {
    ...Object.fromEntries(
      Object.entries(process.env).filter(
        (entry): entry is [string, string] => entry[1] !== undefined,
      ),
    ),
    AUTO_SCORING_E2E_APP_DATA: appDataDir,
    AUTO_SCORING_E2E_PDF: ANSWER_SHEET_PDF,
  };
}

async function createDraftTest(page: ElectronPage): Promise<string> {
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

async function openDraftTestSettings(
  page: ElectronPage,
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

async function completeRegistrationFromTestSettings(
  page: ElectronPage,
): Promise<void> {
  await expect(page.getByTestId("criteria-section")).toBeVisible({
    timeout: 15_000,
  });

  await page.getByTestId("add-criteria-question-button").click();
  await page.getByTestId("criteria-number-0").fill("問1");
  await page.getByTestId("criteria-points-0").fill("10");
  await page.getByTestId("criteria-model-answer-0").fill("模範解答");
  await page.getByTestId("confirm-criteria-button").click();
  await expect(page.getByTestId("criteria-section")).toContainText("確認済み");

  await page.getByTestId("upload-answer-layout-button").click();
  await expect(page.getByTestId("add-region-button")).toBeEnabled({
    timeout: 30_000,
  });
  await expect(page.getByTestId("answer-area-editor")).toBeVisible({
    timeout: 15_000,
  });
  await page.getByTestId("add-region-button").click();
  await page.getByTestId("confirm-profile-button").click();
  await expect(page.getByTestId("profile-section")).toContainText("確認済み", {
    timeout: 15_000,
  });

  await page.getByTestId("analyze-dependency-graph-button").click();
  await expect(page.getByTestId("dependency-graph-empty")).toBeVisible({
    timeout: 15_000,
  });
  await page.getByTestId("confirm-dependency-graph-button").click();
  await expect(page.getByTestId("dependency-graph-section")).toContainText(
    "確認済み",
    { timeout: 15_000 },
  );

  await page.getByTestId("complete-registration-button").click();
  await expect(page.getByTestId("test-status-label")).toHaveText(
    "テスト状態: 登録完了",
    { timeout: 15_000 },
  );
}

/**
 * Issue #255 acceptance: home → test settings → registration complete on the real
 * sidecar path (no mock API client). A draft test is created through the same
 * multipart upload bridge production code uses for intake file bytes.
 */
test("registers a test through test settings on the real sidecar path", async () => {
  test.setTimeout(180_000);

  const app = await electron.launch({
    args: electronLaunchArgs(),
    env: e2eLaunchEnv(),
  });

  try {
    const page = await app.firstWindow();
    await waitForHomeReady(page);

    const testId = await createDraftTest(page);
    await openDraftTestSettings(page, testId);
    await completeRegistrationFromTestSettings(page);
  } finally {
    await app.close();
  }
});

/**
 * Guard test: without the confirm buttons the flow above must not reach ready.
 * Run the negative check by temporarily commenting out the confirm handlers in
 * `TestSettingsPage.tsx`, re-running this spec, then restoring the handlers.
 */
test("requires confirm buttons to reach ready", async () => {
  test.skip(
    process.env["AUTO_SCORING_E2E_NEGATIVE"] !== "1",
    "Set AUTO_SCORING_E2E_NEGATIVE=1 after temporarily removing confirm handlers",
  );
  test.setTimeout(180_000);

  const app = await electron.launch({
    args: electronLaunchArgs(),
    env: e2eLaunchEnv(),
  });

  try {
    const page = await app.firstWindow();
    await waitForHomeReady(page);
    const testId = await createDraftTest(page);
    await openDraftTestSettings(page, testId);

    await expect(
      page.getByTestId("complete-registration-button"),
    ).toBeDisabled();
    await expect(page.getByTestId("test-status-label")).toHaveText(
      "テスト状態: 下書き",
    );
  } finally {
    await app.close();
  }
});
