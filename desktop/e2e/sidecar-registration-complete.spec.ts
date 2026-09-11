import { test, expect } from "@playwright/test";

import { closeElectronApp, launchElectronApp } from "./electron-launch";
import {
  ANSWER_SHEET_PDF,
  completeRegistrationFromTestSettings,
  createDraftTest,
  openDraftTestSettings,
  waitForHomeReady,
} from "./registration-helpers";

/**
 * Issue #255 acceptance: home → test settings → registration complete on the real
 * sidecar path (no mock API client). A draft test is created through the same
 * multipart upload bridge production code uses for intake file bytes.
 */
test("registers a test through test settings on the real sidecar path", async () => {
  test.setTimeout(180_000);

  const app = await launchElectronApp({
    env: {
      AUTO_SCORING_E2E_PDF: ANSWER_SHEET_PDF,
      AUTO_SCORING_E2E_STUB_CRITERIA_EXTRACT: "1",
    },
  });

  try {
    const page = await app.firstWindow();
    await waitForHomeReady(page);

    const testId = await createDraftTest(page);
    await openDraftTestSettings(page, testId);
    await completeRegistrationFromTestSettings(page);
  } finally {
    await closeElectronApp(app);
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

  const app = await launchElectronApp({
    env: {
      AUTO_SCORING_E2E_PDF: ANSWER_SHEET_PDF,
      AUTO_SCORING_E2E_STUB_CRITERIA_EXTRACT: "1",
    },
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
    await closeElectronApp(app);
  }
});
