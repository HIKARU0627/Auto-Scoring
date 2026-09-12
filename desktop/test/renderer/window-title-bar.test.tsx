import { describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";

import {
  WINDOW_CLOSE_TEST_ID,
  WINDOW_MAXIMIZE_TEST_ID,
  WINDOW_MINIMIZE_TEST_ID,
  WINDOW_TITLE_BAR_TEST_ID,
  WindowTitleBar,
} from "../../src/renderer/navigation/WindowTitleBar";

/**
 * The frameless windows draw their own title bar (Issue #428). These fix the
 * parts jsdom can see: which elements are on which side of the drag boundary,
 * that the controls call the bridge methods (never an Electron API directly),
 * and that the maximize button's accessible name and pressed state follow the
 * native window state. The pixels and the native window state are fixed by
 * `desktop/e2e/window-controls.spec.ts`.
 */
interface BridgeStub {
  minimizeWindow: ReturnType<typeof vi.fn>;
  toggleMaximizeWindow: ReturnType<typeof vi.fn>;
  closeWindow: ReturnType<typeof vi.fn>;
  isWindowMaximized: ReturnType<typeof vi.fn>;
  emitMaximized(value: boolean): void;
}

function stubBridge(initialMaximized = false): BridgeStub {
  const listeners = new Set<(value: boolean) => void>();
  const stub: BridgeStub = {
    minimizeWindow: vi.fn(async () => undefined),
    toggleMaximizeWindow: vi.fn(async () => undefined),
    closeWindow: vi.fn(async () => undefined),
    isWindowMaximized: vi.fn(async () => initialMaximized),
    emitMaximized(value) {
      for (const listener of listeners) {
        listener(value);
      }
    },
  };
  vi.stubGlobal("autoScoring", {
    ...stub,
    onWindowMaximizedChange: (callback: (value: boolean) => void) => {
      listeners.add(callback);
      return () => {
        listeners.delete(callback);
      };
    },
  });
  return stub;
}

describe("WindowTitleBar (Issue #428)", () => {
  it("marks the band as draggable and the controls as no-drag", () => {
    stubBridge();
    render(<WindowTitleBar />);

    const bar = screen.getByTestId(WINDOW_TITLE_BAR_TEST_ID);
    expect(bar.dataset["windowDragRegion"]).toBe("drag");
    expect(bar.className).toContain("-webkit-app-region:drag");

    const controls = screen.getByTestId("window-title-bar-controls");
    expect(controls.dataset["windowDragRegion"]).toBe("no-drag");
    expect(controls.className).toContain("-webkit-app-region:no-drag");
  });

  it("labels every control so it is reachable and announced", () => {
    stubBridge();
    render(<WindowTitleBar />);

    expect(
      screen.getByTestId(WINDOW_MINIMIZE_TEST_ID).getAttribute("aria-label"),
    ).toBe("最小化");
    expect(
      screen.getByTestId(WINDOW_MAXIMIZE_TEST_ID).getAttribute("aria-label"),
    ).toBe("最大化");
    expect(
      screen.getByTestId(WINDOW_CLOSE_TEST_ID).getAttribute("aria-label"),
    ).toBe("閉じる");
  });

  it("sends minimize / maximize / close through the preload bridge", () => {
    const bridge = stubBridge();
    render(<WindowTitleBar />);

    fireEvent.click(screen.getByTestId(WINDOW_MINIMIZE_TEST_ID));
    fireEvent.click(screen.getByTestId(WINDOW_MAXIMIZE_TEST_ID));
    fireEvent.click(screen.getByTestId(WINDOW_CLOSE_TEST_ID));

    expect(bridge.minimizeWindow).toHaveBeenCalledTimes(1);
    expect(bridge.toggleMaximizeWindow).toHaveBeenCalledTimes(1);
    expect(bridge.closeWindow).toHaveBeenCalledTimes(1);
  });

  it("switches the maximize control to 元に戻す when the window is maximized", async () => {
    const bridge = stubBridge(true);
    render(<WindowTitleBar />);

    const button = await screen.findByTestId(WINDOW_MAXIMIZE_TEST_ID);
    expect(button.getAttribute("aria-label")).toBe("元に戻す");
    expect(button.getAttribute("aria-pressed")).toBe("true");

    // The glyph changes too: state is not carried by colour alone.
    expect(button.querySelector("svg")?.getAttribute("aria-hidden")).toBe(
      "true",
    );

    act(() => {
      bridge.emitMaximized(false);
    });
    expect(button.getAttribute("aria-label")).toBe("最大化");
    expect(button.getAttribute("aria-pressed")).toBe("false");
  });

  it("toggles maximize on a double-click of the drag band", () => {
    const bridge = stubBridge();
    render(<WindowTitleBar />);

    fireEvent.doubleClick(screen.getByTestId(WINDOW_TITLE_BAR_TEST_ID));
    expect(bridge.toggleMaximizeWindow).toHaveBeenCalledTimes(1);
  });

  it("does not toggle maximize for a double-click on the controls", () => {
    const bridge = stubBridge();
    render(<WindowTitleBar />);

    fireEvent.doubleClick(screen.getByTestId("window-title-bar-controls"));
    expect(bridge.toggleMaximizeWindow).not.toHaveBeenCalled();
  });
});
