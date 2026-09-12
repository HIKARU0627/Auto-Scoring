import { test, expect } from "@playwright/test";
import type { Page } from "@playwright/test";

import {
  closeElectronApp,
  launchElectronApp,
  pollSidecarReady,
} from "./electron-launch";

/**
 * Issue #422 / Issue #375 item 4: the shell row has a definite height so the
 * Sidebar can stretch to it, but the body column must stay content-height.
 * A window taller than the content must not stretch the body (the band #375
 * removed), and `items-start` on the row is what keeps it that way. The band
 * changes the row's height, so both states are pinned.
 *
 * jsdom cannot measure this; `desktop/test/renderer/grading-unavailable-shell.test.tsx`
 * fixes the class contract and this spec fixes the pixels.
 */
const STATES = [
  {
    name: "バナーあり",
    env: {},
    bannerVisible: true,
  },
  {
    name: "バナーなし",
    env: {
      AUTO_SCORING_AI_GRADING_TRANSPORT: "openrouter",
      AUTO_SCORING_OPENROUTER_API_KEY: "dummy",
      AUTO_SCORING_OPENROUTER_MODEL: "google/gemini-2.5-flash",
    },
    bannerVisible: false,
  },
] as const;

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
  await page.waitForTimeout(400);
}

for (const state of STATES) {
  test(`内容が短いときシェルの本文列をウィンドウ高に伸ばさない (${state.name}, Issue #375 item 4)`, async () => {
    test.setTimeout(180_000);

    const app = await launchElectronApp({ env: state.env });
    try {
      const page = await app.firstWindow();
      await pollSidecarReady(page);
      await page
        .getByTestId("home-open-intake")
        .waitFor({ state: "visible", timeout: 30_000 });

      const banner = page.locator('[data-testid="grading-unavailable-banner"]');
      if (state.bannerVisible) {
        await expect(banner).toBeVisible({ timeout: 15_000 });
      } else {
        await expect(banner).toHaveCount(0);
      }

      // Settings has short content, so a tall window exposes any stretching.
      await page.getByTestId("sidebar-nav-settings").click();
      await page
        .getByTestId("settings-tab-intake")
        .waitFor({ state: "visible", timeout: 15_000 });
      await setViewport(page, 1536, 1600);

      const geometry = await page.evaluate(() => {
        const frame = document.querySelector(
          '[data-testid="app-shell-frame"]',
        ) as HTMLElement;
        const content = document.querySelector(
          '[data-testid="app-shell-content"]',
        ) as HTMLElement;
        const sidebar = document.querySelector(
          '[data-testid="app-sidebar"]',
        ) as HTMLElement;
        const contentRect = content.getBoundingClientRect();
        const sidebarRect = sidebar.getBoundingClientRect();
        return {
          innerHeight: window.innerHeight,
          docScrollHeight: document.documentElement.scrollHeight,
          rowContentHeight: frame.clientHeight - 48,
          contentHeight: Math.round(contentRect.height),
          contentTop: Math.round(contentRect.top),
          sidebarHeight: Math.round(sidebarRect.height),
          sidebarLeft: Math.round(sidebarRect.left),
          sidebarBottom: Math.round(sidebarRect.bottom),
        };
      });

      expect(geometry.innerHeight).toBe(1600);
      // No window scrollbar: the band plus the (definite) shell row == window.
      expect(geometry.docScrollHeight).toBeLessThanOrEqual(
        geometry.innerHeight + 1,
      );

      // The body column is content-height, not the row height.
      expect(geometry.contentHeight).toBeLessThan(geometry.rowContentHeight);

      // The Sidebar is the element that takes the row height, inset by p-xl.
      expect(geometry.sidebarHeight).toBeGreaterThanOrEqual(
        geometry.rowContentHeight - 1,
      );
      expect(geometry.sidebarBottom).toBeLessThanOrEqual(
        geometry.innerHeight + 1,
      );
      // Issue #348: still the floating panel (left ~24, clear of the bottom).
      expect(Math.abs(geometry.sidebarLeft - 24)).toBeLessThanOrEqual(1);
    } finally {
      await closeElectronApp(app);
    }
  });
}
