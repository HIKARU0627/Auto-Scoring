import * as fs from "node:fs";
import * as path from "node:path";

import { test, expect } from "@playwright/test";
import type { Page } from "@playwright/test";

import {
  closeElectronApp,
  launchElectronApp,
  pollSidecarReady,
} from "./electron-launch";

/**
 * Issue #427 acceptance: the sidebar is a fixed floating panel, not a column
 * that rides the screen down.
 *
 * The regression this pins: with a screen taller than the window, the document
 * scrolled and the sidebar went with it. `sticky` alone never held because
 * `position: sticky` is clamped to its containing block, and the frame's box
 * ends at the viewport while the screen's content overflows it. `AppShell` now
 * keeps the document at the viewport and scrolls the routed screen inside the
 * body column, so the panel -- and the 採点不可バナー above it -- stay put.
 *
 * Location and size are measured against the real Electron window: jsdom has no
 * layout, so `desktop/test/renderer/sidebar-fixed.test.tsx` fixes the class
 * contract and this spec fixes the pixels.
 *
 * The four squares are バナーあり／なし x 内容が低い／高い:
 *
 * - 低い: the home body fits 1536x1024, so the body column must not scroll and
 *   the panel spans the frame.
 * - 高い: the narrow 700x900 wraps the body past the viewport, so the column
 *   scrolls and the panel must not move.
 *
 * Every screen is the empty home (isolated app-data), so no real answer data
 * can appear in a screenshot.
 */

const BANNER_ENV = {
  AUTO_SCORING_AI_GRADING_TRANSPORT: "openrouter",
  AUTO_SCORING_OPENROUTER_API_KEY: "dummy",
  AUTO_SCORING_OPENROUTER_MODEL: "google/gemini-2.5-flash",
} as const;

interface Scenario {
  readonly name: string;
  readonly bannerVisible: boolean;
  readonly width: number;
  readonly height: number;
  readonly tall: boolean;
  readonly screenshot: string;
}

const SCENARIOS: readonly Scenario[] = [
  {
    name: "バナーあり・内容が低い (1536x1024)",
    bannerVisible: true,
    width: 1536,
    height: 1024,
    tall: false,
    screenshot: "sidebar-fixed-banner-1536x1024",
  },
  {
    name: "バナーなし・内容が低い (1536x1024)",
    bannerVisible: false,
    width: 1536,
    height: 1024,
    tall: false,
    screenshot: "sidebar-fixed-no-banner-1536x1024",
  },
  {
    name: "バナーあり・内容が高い (700x900)",
    bannerVisible: true,
    width: 700,
    height: 900,
    tall: true,
    screenshot: "sidebar-fixed-banner-700x900",
  },
  {
    name: "バナーなし・内容が高い (700x900)",
    bannerVisible: false,
    width: 700,
    height: 900,
    tall: true,
    screenshot: "sidebar-fixed-no-banner-700x900",
  },
];

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
  await page.waitForTimeout(400);
}

interface Geometry {
  readonly innerHeight: number;
  readonly docScrollHeight: number;
  readonly scrollY: number;
  readonly frame: { height: number };
  readonly content: {
    clientHeight: number;
    scrollHeight: number;
    scrollTop: number;
  };
  readonly sidebar: {
    top: number;
    bottom: number;
    left: number;
    width: number;
    height: number;
    borderRadius: number;
  };
}

async function readGeometry(page: Page): Promise<Geometry> {
  return page.evaluate(() => {
    const sidebar = document.querySelector(
      '[data-testid="app-sidebar"]',
    ) as HTMLElement;
    const frame = document.querySelector(
      '[data-testid="app-shell-frame"]',
    ) as HTMLElement;
    const content = document.querySelector(
      '[data-testid="app-shell-content"]',
    ) as HTMLElement;
    const sidebarRect = sidebar.getBoundingClientRect();
    return {
      innerHeight: window.innerHeight,
      docScrollHeight: document.documentElement.scrollHeight,
      scrollY: window.scrollY,
      frame: { height: Math.round(frame.getBoundingClientRect().height) },
      content: {
        clientHeight: content.clientHeight,
        scrollHeight: content.scrollHeight,
        scrollTop: content.scrollTop,
      },
      sidebar: {
        top: Math.round(sidebarRect.top),
        bottom: Math.round(sidebarRect.bottom),
        left: Math.round(sidebarRect.left),
        width: Math.round(sidebarRect.width),
        height: Math.round(sidebarRect.height),
        borderRadius: Number.parseFloat(
          getComputedStyle(sidebar).borderTopLeftRadius,
        ),
      },
    };
  });
}

/** `p-xl` on both sides of the shell frame. */
const FRAME_VERTICAL_PADDING = 48;

async function captureScreenshot(page: Page, name: string): Promise<void> {
  const session = await page.context().newCDPSession(page);
  const shot = await session.send("Page.captureScreenshot", { format: "png" });
  const dir = path.join("test-results", "sidebar-fixed");
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(
    path.join(dir, `${name}.png`),
    Buffer.from(shot.data, "base64"),
  );
}

for (const scenario of SCENARIOS) {
  test(`サイドバーは本文と一緒にスクロールしない (${scenario.name}, Issue #427)`, async () => {
    test.setTimeout(180_000);

    const app = await launchElectronApp({
      env: scenario.bannerVisible ? {} : BANNER_ENV,
    });

    try {
      const page = await app.firstWindow();
      await pollSidecarReady(page);
      await page
        .getByTestId("home-open-intake")
        .waitFor({ state: "visible", timeout: 30_000 });

      const banner = page.locator('[data-testid="grading-unavailable-banner"]');
      if (scenario.bannerVisible) {
        await expect(banner).toBeVisible({ timeout: 15_000 });
      } else {
        await expect(banner).toHaveCount(0);
      }

      await setViewport(page, scenario.width, scenario.height);
      // Deterministic: a previous size must not leave the body column scrolled.
      await page.evaluate(() => {
        (
          document.querySelector(
            '[data-testid="app-shell-content"]',
          ) as HTMLElement
        ).scrollTop = 0;
      });
      await page.waitForTimeout(200);

      const before = await readGeometry(page);
      expect(before.innerHeight).toBe(scenario.height);

      // The document never scrolls: that is what keeps the panel from riding it.
      expect(before.docScrollHeight).toBeLessThanOrEqual(
        before.innerHeight + 1,
      );
      expect(before.scrollY).toBe(0);

      // Issue #348: still the floating, rounded panel, inset from the left.
      expect(before.sidebar.borderRadius).toBeGreaterThan(0);
      expect(Math.abs(before.sidebar.left - 24)).toBeLessThanOrEqual(1);
      // The panel is on screen, clear of the bottom edge the same way it is of
      // the top.
      expect(before.sidebar.top).toBeGreaterThanOrEqual(0);
      expect(before.sidebar.bottom).toBeLessThanOrEqual(before.innerHeight + 1);

      const bodyScrollable =
        before.content.scrollHeight > before.content.clientHeight + 1;

      if (scenario.tall) {
        // The screen is taller than the body column, so only the column scrolls.
        expect(bodyScrollable).toBe(true);

        await captureScreenshot(page, scenario.screenshot);

        await page.evaluate(() => {
          const content = document.querySelector(
            '[data-testid="app-shell-content"]',
          ) as HTMLElement;
          content.scrollTop = content.scrollHeight;
        });
        await page.waitForTimeout(200);

        const after = await readGeometry(page);
        expect(after.content.scrollTop).toBeGreaterThan(0);
        // Scrolling the screen moved the body, not the panel.
        expect(
          Math.abs(after.sidebar.top - before.sidebar.top),
        ).toBeLessThanOrEqual(1);
        expect(
          Math.abs(after.sidebar.bottom - before.sidebar.bottom),
        ).toBeLessThanOrEqual(1);
        expect(after.scrollY).toBe(0);
        expect(after.docScrollHeight).toBeLessThanOrEqual(
          after.innerHeight + 1,
        );
      } else {
        // The screen fits: the panel spans the frame's content box instead.
        expect(bodyScrollable).toBe(false);
        expect(before.sidebar.height).toBeGreaterThanOrEqual(
          before.frame.height - FRAME_VERTICAL_PADDING - 1,
        );

        await captureScreenshot(page, scenario.screenshot);
      }
    } finally {
      await closeElectronApp(app);
    }
  });
}
