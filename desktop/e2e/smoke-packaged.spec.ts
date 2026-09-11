import { test, expect, _electron as electron } from "@playwright/test";
import * as path from "node:path";

const packagedAppPath = process.env["PACKAGED_APP_PATH"];

test.describe("Packaged Electron app smoke test (Issue #265)", () => {
  test.skip(
    !packagedAppPath,
    "PACKAGED_APP_PATH not set; skipping packaged app smoke test",
  );

  test("sidecar becomes ready and real data is rendered without home-error", async () => {
    test.setTimeout(120_000);

    const exePath = path.resolve(packagedAppPath!);
    const app = await electron.launch({
      executablePath: exePath,
      cwd: path.dirname(exePath),
      args: [
        "--no-sandbox",
        ...(process.platform === "linux" ? ["--ozone-platform=x11"] : []),
      ],
    });

    try {
      const page = await app.firstWindow();

      // 1. Wait for sidecar status to become "ready"
      await expect
        .poll(
          async () => {
            const sidecarStatus = await page.evaluate(async () => {
              return window.autoScoring?.getSidecarStatus();
            });
            return sidecarStatus?.kind;
          },
          { timeout: 60_000 },
        )
        .toBe("ready");

      // 2. Acceptance Criterion 3: No home-error shown
      await expect(
        page.locator('[data-testid="home-error"]'),
      ).not.toBeVisible();

      // 3. Acceptance Criterion 3: Real data element derived from API response is visible
      await expect(page.locator('[data-testid="home-next-up"]')).toBeVisible({
        timeout: 15_000,
      });

      // 4. Secret redaction invariant
      const bodyText = await page.locator("body").innerText();
      expect(bodyText).not.toMatch(/Bearer\s+\S+/i);
      expect(bodyText).not.toContain("test-token");
    } finally {
      await app.close();
    }
  });
});
