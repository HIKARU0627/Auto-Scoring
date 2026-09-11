import { afterEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";

import { AppErrorBanner } from "../../src/renderer/core/AppErrorBanner.js";

/**
 * INV-096: the recoverable-failure banner every screen shares. The promise is
 * in three parts -- a working retry, a retry that is disabled (not removed)
 * while one is already in flight, and a fade-in that plays once and settles.
 */
describe("AppErrorBanner (INV-096)", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("shows the failure and runs the retry once", () => {
    let retries = 0;
    render(
      <AppErrorBanner
        message="読み込みに失敗しました。"
        onRetry={() => {
          retries += 1;
        }}
      />,
    );

    expect(screen.getByText("読み込みに失敗しました。")).toBeDefined();
    fireEvent.click(screen.getByTestId("app-error-banner-retry"));
    expect(retries).toBe(1);
  });

  it("keeps the retry button, disabled, while a retry is already running", () => {
    // `onRetry === null` is "busy": the button must stay in the DOM so the
    // banner does not change size under the reviewer's pointer.
    render(<AppErrorBanner message="offline" />);

    const retry = screen.getByTestId(
      "app-error-banner-retry",
    ) as HTMLButtonElement;
    expect(retry).toBeDefined();
    expect(retry.disabled).toBe(true);
  });

  it("offers no retry where the screen has nothing to re-run", () => {
    render(<AppErrorBanner message="offline" retryable={false} />);

    expect(screen.getByText("offline")).toBeDefined();
    expect(screen.queryByTestId("app-error-banner-retry")).toBeNull();
  });

  it("fades in once and then settles", () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });

    render(<AppErrorBanner message="offline" />);
    const banner = screen.getByTestId("app-error-banner");
    expect(banner.dataset["enter"]).toBe("running");
    expect((banner as HTMLElement).style.opacity).toBe("0");

    act(() => {
      vi.advanceTimersByTime(250);
    });

    expect(banner.dataset["enter"]).toBe("settled");
    expect((banner as HTMLElement).style.opacity).toBe("1");
    // No frame or timer left behind: the motion was one-shot, not a loop.
    expect(vi.getTimerCount()).toBe(0);
  });
});
