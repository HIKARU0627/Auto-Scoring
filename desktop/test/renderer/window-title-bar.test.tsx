import { describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";

import {
  WINDOW_CLOSE_TEST_ID,
  WINDOW_MAXIMIZE_TEST_ID,
  WINDOW_MINIMIZE_TEST_ID,
  WINDOW_TITLE_BAR_ICON_TEST_ID,
  WINDOW_TITLE_BAR_TEST_ID,
  WINDOW_TITLE_BAR_TITLE_TEST_ID,
  WindowTitleBar,
} from "../../src/renderer/navigation/WindowTitleBar";

/**
 * The frameless windows draw their own title bar (Issue #428). These fix the
 * parts jsdom can see: which elements are on which side of the drag boundary,
 * that the controls call the bridge methods (never an Electron API directly),
 * that the maximize button's accessible name and pressed state follow the
 * native window state, and that the band dims when the window is not focused
 * (Issue #446). The pixels and the native window state are fixed by
 * `desktop/e2e/window-controls.spec.ts`.
 */
interface BridgeStub {
  minimizeWindow: ReturnType<typeof vi.fn>;
  toggleMaximizeWindow: ReturnType<typeof vi.fn>;
  closeWindow: ReturnType<typeof vi.fn>;
  isWindowMaximized: ReturnType<typeof vi.fn>;
  isWindowFocused: ReturnType<typeof vi.fn>;
  emitMaximized(value: boolean): void;
  emitFocused(value: boolean): void;
}

function stubBridge(
  initialMaximized = false,
  initialFocused = true,
): BridgeStub {
  const maximizedListeners = new Set<(value: boolean) => void>();
  const focusListeners = new Set<(value: boolean) => void>();
  const stub: BridgeStub = {
    minimizeWindow: vi.fn(async () => undefined),
    toggleMaximizeWindow: vi.fn(async () => undefined),
    closeWindow: vi.fn(async () => undefined),
    isWindowMaximized: vi.fn(async () => initialMaximized),
    isWindowFocused: vi.fn(async () => initialFocused),
    emitMaximized(value) {
      for (const listener of maximizedListeners) {
        listener(value);
      }
    },
    emitFocused(value) {
      for (const listener of focusListeners) {
        listener(value);
      }
    },
  };
  vi.stubGlobal("autoScoring", {
    ...stub,
    onWindowMaximizedChange: (callback: (value: boolean) => void) => {
      maximizedListeners.add(callback);
      return () => {
        maximizedListeners.delete(callback);
      };
    },
    onWindowFocusChange: (callback: (value: boolean) => void) => {
      focusListeners.add(callback);
      return () => {
        focusListeners.delete(callback);
      };
    },
  });
  return stub;
}

describe("WindowTitleBar (Issue #428)", () => {
  it("marks the band, app mark and title as draggable and the controls as no-drag", () => {
    stubBridge();
    render(<WindowTitleBar />);

    const bar = screen.getByTestId(WINDOW_TITLE_BAR_TEST_ID);
    expect(bar.dataset["windowDragRegion"]).toBe("drag");
    expect(bar.className).toContain("-webkit-app-region:drag");

    // Issue #446: the app mark and the centred title are decorative, so they
    // must stay on the drag side rather than becoming dead spots.
    for (const testId of [
      WINDOW_TITLE_BAR_ICON_TEST_ID,
      WINDOW_TITLE_BAR_TITLE_TEST_ID,
    ]) {
      const region = screen.getByTestId(testId);
      expect(region.dataset["windowDragRegion"], testId).toBe("drag");
    }

    const controls = screen.getByTestId("window-title-bar-controls");
    expect(controls.dataset["windowDragRegion"]).toBe("no-drag");
    expect(controls.className).toContain("-webkit-app-region:no-drag");
  });

  it("renders the app mark and the centred window title (Issue #446)", () => {
    stubBridge();
    render(<WindowTitleBar title="資料" />);

    const icon = screen.getByTestId(WINDOW_TITLE_BAR_ICON_TEST_ID);
    expect(icon.querySelector("svg")).not.toBeNull();
    expect(screen.getByTestId(WINDOW_TITLE_BAR_TITLE_TEST_ID).textContent).toBe(
      "資料",
    );
  });

  it("uses the page surface and the Windows caption height (Issue #446)", () => {
    stubBridge();
    render(<WindowTitleBar />);

    const bar = screen.getByTestId(WINDOW_TITLE_BAR_TEST_ID);
    // The band must be continuous with the content, not a lighter strip: the
    // Issue traced the "pasted-on" look to `bg-surface-container-low`.
    expect(bar.className).toContain("bg-surface");
    expect(bar.className).not.toContain("bg-surface-container-low");
    expect(bar.className).toContain("h-8");
  });

  it("centres the title and keeps it inside the drag band (Issue #446)", () => {
    stubBridge();
    render(<WindowTitleBar />);

    const titleBox = screen.getByTestId(WINDOW_TITLE_BAR_TITLE_TEST_ID);
    expect(titleBox.className).toContain("absolute");
    expect(titleBox.className).toContain("inset-x-33");
    expect(titleBox.className).toContain("justify-center");
    // Not interactive, so it must let the band's double-click through.
    expect(titleBox.className).toContain("pointer-events-none");
  });

  it("uses the Windows close red and a subtle overlay for the others (Issue #446)", () => {
    stubBridge();
    render(<WindowTitleBar />);

    const close = screen.getByTestId(WINDOW_CLOSE_TEST_ID);
    expect(close.className).toContain("hover:bg-window-close-hover");
    expect(close.className).toContain("hover:text-on-window-close-hover");
    // The theme's soft `error` is not the fixed OS red.
    expect(close.className).not.toContain("hover:bg-error");

    for (const testId of [WINDOW_MINIMIZE_TEST_ID, WINDOW_MAXIMIZE_TEST_ID]) {
      expect(screen.getByTestId(testId).className).toContain(
        "hover:bg-on-surface/10",
      );
    }
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

  it("dims the band, mark and title when the window loses focus (Issue #446)", async () => {
    const bridge = stubBridge(false, false);
    render(<WindowTitleBar />);

    const bar = await screen.findByTestId(WINDOW_TITLE_BAR_TEST_ID);
    expect(bar.dataset["windowFocus"]).toBe("unfocused");
    expect(bar.className).toContain("text-on-surface-muted");
    expect(bar.className).not.toContain("text-on-surface-variant");
    // The mark follows the band into the dim state.
    expect(
      screen
        .getByTestId(WINDOW_TITLE_BAR_ICON_TEST_ID)
        .querySelector("svg")
        ?.getAttribute("class"),
    ).toContain("text-on-surface-muted");

    act(() => {
      bridge.emitFocused(true);
    });
    expect(bar.dataset["windowFocus"]).toBe("focused");
    expect(bar.className).toContain("text-on-surface-variant");
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
