import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import * as path from "node:path";

/**
 * Source contracts for the frameless windows (Issue #428).
 *
 * `frame: false` and `resizable` are constructor options: Electron exposes no
 * getter, and on Linux `getContentBounds()` equals `getBounds()` whether or not
 * a frame is present, so a Playwright assertion cannot tell the two apart on
 * the platform the e2e suite runs on. These read the main-process source the
 * same way `architecture.test.ts` reads it, which is what makes dropping
 * `frame: false` or disabling resizing fail a test.
 *
 * The runtime half -- that the drawn buttons really change `BrowserWindow`
 * state, and that the material window's buttons move only the material window
 * -- is `desktop/e2e/window-controls.spec.ts`.
 */
const PACKAGE_ROOT = path.resolve(import.meta.dirname, "..");
const MAIN = readFileSync(path.join(PACKAGE_ROOT, "src/main/main.ts"), "utf8");

describe("frameless windows (Issue #428)", () => {
  it("creates both windows without an OS frame", () => {
    const frameless = MAIN.match(/frame:\s*false/g) ?? [];
    // Main window and material window: one each.
    expect(frameless).toHaveLength(2);
    expect(MAIN).not.toMatch(/frame:\s*true/);
  });

  it("does not turn resizing off to make the frameless window behave", () => {
    // The failure mode the Issue warns about: a frameless window whose edge
    // handles were removed. Resizing stays with the OS (`thickFrame` default).
    expect(MAIN).not.toMatch(/resizable:\s*false/);
  });

  it("still denies renderer-opened windows", () => {
    expect(MAIN).toMatch(/setWindowOpenHandler/);
    expect(MAIN).toMatch(/action:\s*"deny"/);
  });
});

describe("window-control IPC resolves the window from the sender (Issue #428)", () => {
  // The trust boundary: `event.sender` is the only input. A renderer-supplied
  // window id would let one window close or maximize another.
  for (const channel of [
    "minimizeWindow",
    "toggleMaximizeWindow",
    "closeWindow",
    "isWindowMaximized",
  ] as const) {
    it(`${channel} acts on the sender's window`, () => {
      const start = MAIN.indexOf(`IpcChannel.${channel}`);
      expect(start).toBeGreaterThan(-1);
      const handler = MAIN.slice(start, start + 400);
      expect(handler).toContain("windowForIpcEvent(event)");
    });
  }

  it("resolves the window with BrowserWindow.fromWebContents", () => {
    expect(MAIN).toMatch(/BrowserWindow\.fromWebContents\(event\.sender\)/);
  });

  it("takes no window id from the renderer", () => {
    expect(MAIN).not.toMatch(/windowId|window-id/);
  });
});

describe("window focus is pushed to the window's renderer (Issue #446)", () => {
  // `notifyFocus` reports `window.isFocused()`, the OS's current answer, so a
  // synthetic `blur` is not a portable way to drive it (Windows CI reports the
  // window focused). The runtime half therefore drives only the IPC channel in
  // `desktop/e2e/window-controls.spec.ts`; this file owns the other half -- that
  // `main.ts` wires **both** native events -- which is what makes dropping the
  // `blur` registration fail a test instead of silently dimming nothing.
  const trackerStart = MAIN.indexOf("function trackFocusState");
  const TRACKER = MAIN.slice(trackerStart, MAIN.indexOf("\n}", trackerStart));

  it("registers a handler for both focus and blur", () => {
    expect(trackerStart).toBeGreaterThan(-1);
    expect(TRACKER).toMatch(/window\.on\(\s*"focus"/);
    expect(TRACKER).toMatch(/window\.on\(\s*"blur"/);
  });

  it("notifies the renderer once per native event, for that window", () => {
    expect(TRACKER.match(/notifyFocus\(window\)/g) ?? []).toHaveLength(2);
  });

  it("sends the state on the channel the preload subscribes to", () => {
    const notifyStart = MAIN.indexOf("function notifyFocus");
    const NOTIFY = MAIN.slice(notifyStart, notifyStart + 300);
    expect(NOTIFY).toContain("IpcChannel.windowFocusChanged");
  });
});
