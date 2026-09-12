import { test, expect } from "@playwright/test";
import type { ElectronApplication, JSHandle, Page } from "@playwright/test";

import { closeElectronApp, launchElectronApp } from "./electron-launch";
import {
  ANSWER_SHEET_PDF,
  createDraftTest,
  openDraftTestSettings,
  waitForHomeReady,
} from "./registration-helpers";

/**
 * Frameless-window controls (Issue #428).
 *
 * The requirement is explicit that "the button exists" is not a test: the OS
 * caption is gone, so what matters is that clicking the drawn controls actually
 * changes the state of the **native `BrowserWindow`**. Playwright's Electron
 * API exposes that window, and `app.browserWindow(page)` lets these specs read
 * `isMaximized()`, `isMinimized()`, bounds, etc. from the main process. A
 * no-op IPC handler or an unwired button fails here.
 *
 * The second test is the trust-boundary one: the material window's own title
 * bar must move only the material window, which is what "resolve the window
 * from `event.sender`, never from a renderer-supplied id" buys.
 */

interface NativeWindow {
  isMaximized(): boolean;
  isMinimized(): boolean;
  isResizable(): boolean;
  isMaximizable(): boolean;
  isMinimizable(): boolean;
}

function nativeWindowOf(
  app: ElectronApplication,
  page: Page,
): Promise<JSHandle> {
  return app.browserWindow(page);
}

test("the drawn title bar maximizes, restores and minimizes the real window (Issue #428)", async () => {
  test.setTimeout(180_000);

  const app = await launchElectronApp();
  try {
    const page = await app.firstWindow();
    const bar = page.getByTestId("window-title-bar");
    await expect(bar).toBeVisible({
      timeout: 60_000,
    });

    // Issue #446: the app mark and the centred title were added to the band.
    // They are decorative, so they must inherit the band's drag region rather
    // than become dead zones; the controls must still opt out. Computed style
    // is read here because `-webkit-app-region` is inherited, so a class
    // assertion on the children would miss a `no-drag` regression.
    const regions = await page.evaluate(() => {
      const read = (testId: string): string => {
        const element = document.querySelector(`[data-testid="${testId}"]`);
        return element === null
          ? "missing"
          : getComputedStyle(element).getPropertyValue("-webkit-app-region");
      };
      return {
        bar: read("window-title-bar"),
        icon: read("window-title-bar-icon"),
        title: read("window-title-bar-title"),
        controls: read("window-title-bar-controls"),
      };
    });
    expect(regions).toEqual({
      bar: "drag",
      icon: "drag",
      title: "drag",
      controls: "no-drag",
    });

    // The bar's initial state must come from the main process (`isWindowFocused`
    // over IPC), not from the component's default. Compared against the native
    // value so this holds whatever focus the environment can give a window.
    const initiallyFocused = await app.evaluate(
      ({ BrowserWindow }) =>
        BrowserWindow.getAllWindows()[0]?.isFocused() ?? false,
    );
    await expect(bar).toHaveAttribute(
      "data-window-focus",
      initiallyFocused ? "focused" : "unfocused",
    );

    const nativeWindow = await nativeWindowOf(app, page);

    // The OS resize handles are what `frame: false` can silently take away.
    // (`frame: false` itself is pinned by `desktop/test/window-controls-main.test.ts`:
    // on Linux `getContentBounds()` equals `getBounds()` even with a frame, so a
    // runtime bounds comparison here would pass either way.)
    const capabilities = await nativeWindow.evaluate((w) => {
      const kind = w as unknown as NativeWindow;
      return {
        resizable: kind.isResizable(),
        maximizable: kind.isMaximizable(),
        minimizable: kind.isMinimizable(),
      };
    });
    expect(capabilities).toEqual({
      resizable: true,
      maximizable: true,
      minimizable: true,
    });

    // Maximize: the native window must actually become maximized, and the
    // control must say what it will do next.
    await page.getByTestId("window-maximize").click();
    await expect
      .poll(() =>
        nativeWindow.evaluate((w) => (w as NativeWindow).isMaximized()),
      )
      .toBe(true);
    await expect(page.getByTestId("window-maximize")).toHaveAttribute(
      "aria-label",
      "元に戻す",
    );

    // Restore from the same button.
    await page.getByTestId("window-maximize").click();
    await expect
      .poll(() =>
        nativeWindow.evaluate((w) => (w as NativeWindow).isMaximized()),
      )
      .toBe(false);
    await expect(page.getByTestId("window-maximize")).toHaveAttribute(
      "aria-label",
      "最大化",
    );

    // Minimize touches the native window state too. The test ends here: a
    // minimized window is what the teardown closes, and waking it again would
    // depend on the window manager rather than on the app.
    await page.getByTestId("window-minimize").click();
    await expect
      .poll(() =>
        nativeWindow.evaluate((w) => (w as NativeWindow).isMinimized()),
      )
      .toBe(true);
  } finally {
    await closeElectronApp(app);
  }
});

test("double-clicking the drag band maximizes and restores the window (Issue #428)", async () => {
  test.setTimeout(180_000);

  const app = await launchElectronApp();
  try {
    const page = await app.firstWindow();
    const bar = page.getByTestId("window-title-bar");
    await expect(bar).toBeVisible({ timeout: 60_000 });
    const nativeWindow = await nativeWindowOf(app, page);

    await bar.dblclick();
    await expect
      .poll(() =>
        nativeWindow.evaluate((w) => (w as NativeWindow).isMaximized()),
      )
      .toBe(true);

    await bar.dblclick();
    await expect
      .poll(() =>
        nativeWindow.evaluate((w) => (w as NativeWindow).isMaximized()),
      )
      .toBe(false);
  } finally {
    await closeElectronApp(app);
  }
});

test("the material window's controls move only the material window (Issue #428)", async () => {
  test.setTimeout(300_000);

  const app = await launchElectronApp({
    env: { AUTO_SCORING_E2E_PDF: ANSWER_SHEET_PDF },
  });

  try {
    const mainWindow = await app.firstWindow();
    await waitForHomeReady(mainWindow);

    const testId = await createDraftTest(mainWindow);
    await openDraftTestSettings(mainWindow, testId);

    const openedWindow = app.waitForEvent("window", { timeout: 30_000 });
    await mainWindow.getByTestId("test-settings-open-materials-button").click();
    const materialWindow = await openedWindow;
    await expect(materialWindow.getByTestId("window-title-bar")).toBeVisible({
      timeout: 60_000,
    });

    const mainNative = await nativeWindowOf(app, mainWindow);
    const materialNative = await nativeWindowOf(app, materialWindow);

    await materialWindow.getByTestId("window-maximize").click();
    await expect
      .poll(() =>
        materialNative.evaluate((w) => (w as NativeWindow).isMaximized()),
      )
      .toBe(true);
    // The main window must not have been touched: the handler acted on the
    // sender's window, not on some id the renderer supplied.
    expect(
      await mainNative.evaluate((w) => (w as NativeWindow).isMaximized()),
    ).toBe(false);

    await materialWindow.getByTestId("window-maximize").click();
    await expect
      .poll(() =>
        materialNative.evaluate((w) => (w as NativeWindow).isMaximized()),
      )
      .toBe(false);

    // The material window keeps its resize handles like the main one.
    expect(
      await materialNative.evaluate((w) => (w as NativeWindow).isResizable()),
    ).toBe(true);
  } finally {
    await closeElectronApp(app);
  }
});

test("the close control closes the window (Issue #428)", async () => {
  test.setTimeout(180_000);

  const app = await launchElectronApp();
  try {
    const page = await app.firstWindow();
    await expect(page.getByTestId("window-close")).toBeVisible({
      timeout: 60_000,
    });

    await page.getByTestId("window-close").click();
    await expect.poll(() => page.isClosed(), { timeout: 30_000 }).toBe(true);
  } finally {
    await closeElectronApp(app).catch(() => undefined);
  }
});

test("the title bar reflects window focus over the bridge (Issue #446)", async () => {
  test.setTimeout(180_000);

  const app = await launchElectronApp();
  try {
    const page = await app.firstWindow();
    const bar = page.getByTestId("window-title-bar");
    await expect(bar).toBeVisible({ timeout: 60_000 });

    // Both directions are driven through the exact channel `main.ts` sends on
    // (`onWindowFocusChange` in preload subscribes to it). A synthetic native
    // `blur`/`focus` is deliberately not used: `notifyFocus` reports
    // `window.isFocused()`, the OS's answer, which differs by environment
    // (Issue #417 / #439: measuring the environment, not the property). What
    // the renderer does with the channel is what this spec owns; that `main.ts`
    // registers `blur` as well as `focus` is pinned by
    // `desktop/test/window-controls-main.test.ts`.
    const sendFocus = (focused: boolean): Promise<void> =>
      app.evaluate(
        ({ BrowserWindow }, [channel, value]) => {
          BrowserWindow.getAllWindows()[0]?.webContents.send(channel, value);
        },
        ["auto-scoring:window-focus-changed", focused] as const,
      );

    await sendFocus(false);
    await expect(bar).toHaveAttribute("data-window-focus", "unfocused", {
      timeout: 15_000,
    });
    await expect(bar).toHaveClass(/text-on-surface-muted/);

    await sendFocus(true);
    await expect(bar).toHaveAttribute("data-window-focus", "focused", {
      timeout: 15_000,
    });
    await expect(bar).toHaveClass(/text-on-surface-variant/);
  } finally {
    await closeElectronApp(app);
  }
});
