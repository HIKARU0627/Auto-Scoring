import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { SidecarClient } from "../../src/renderer/api/client.js";
import { SidecarApiProvider } from "../../src/renderer/api/SidecarApiProvider.js";
import { AppRoutes } from "../../src/renderer/core/app-routes.js";
import { HomePage } from "../../src/renderer/features/home/HomePage.js";
import { RouterProvider } from "../../src/renderer/navigation/router.js";
import { ThemeProvider } from "../../src/renderer/theme/ThemeProvider.js";
import {
  buildTest,
  createMockSidecarClient,
} from "./support/mock-sidecar-client.js";

/**
 * Issue #383: the home reload button. The timing itself is pinned by
 * `use-refresh-state.test.ts`; these tests pin the wiring -- that the shared
 * hook drives the busy reason and the always-visible last-updated label.
 */
afterEach(() => {
  vi.useRealTimers();
});

function renderHome(client: SidecarClient): void {
  render(
    <ThemeProvider>
      <SidecarApiProvider client={client}>
        <RouterProvider initialStack={[AppRoutes.home]}>
          <HomePage />
        </RouterProvider>
      </SidecarApiProvider>
    </ThemeProvider>,
  );
}

/** Drain the loader's microtask chain without letting any timer fire. */
async function flush(): Promise<void> {
  await act(async () => {
    for (let tick = 0; tick < 40; tick += 1) {
      await Promise.resolve();
    }
  });
}

describe("home reload feedback (Issue #383)", () => {
  it("shows the last-updated time and changes it on each successful reload", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date(2026, 8, 12, 1, 2, 3));
    renderHome(
      createMockSidecarClient({
        listTestRegistrations: async () => [buildTest({ id: "t1" })],
        listSubmissions: async () => [],
      }),
    );

    await waitFor(() => {
      expect(screen.getByTestId("home-last-updated").textContent).toContain(
        "01:02:03",
      );
    });

    vi.setSystemTime(new Date(2026, 8, 12, 4, 5, 6));
    fireEvent.click(screen.getByTestId("home-refresh"));
    await waitFor(() => {
      expect(screen.getByTestId("home-last-updated").textContent).toContain(
        "04:05:06",
      );
    });
  });

  it("does not show the busy reason during a fast reload", async () => {
    vi.useFakeTimers();
    renderHome(
      createMockSidecarClient({
        listTestRegistrations: async () => [buildTest({ id: "t1" })],
        listSubmissions: async () => [],
      }),
    );
    await flush();
    expect(screen.getByTestId("home-test-card-t1")).toBeDefined();

    fireEvent.click(screen.getByTestId("home-refresh"));
    expect(screen.queryByTestId("home-reason-busy")).toBeNull();

    await flush();
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(screen.queryByTestId("home-reason-busy")).toBeNull();
  });

  it("shows the busy reason after the delay and holds it for the minimum", async () => {
    vi.useFakeTimers();
    let calls = 0;
    let releaseSecond: (() => void) | null = null;
    const client = createMockSidecarClient({
      listTestRegistrations: async () => {
        calls += 1;
        if (calls > 1) {
          await new Promise<void>((resolve) => {
            releaseSecond = resolve;
          });
        }
        return [buildTest({ id: "t1" })];
      },
      listSubmissions: async () => [],
    });
    renderHome(client);
    await flush();
    expect(screen.getByTestId("home-test-card-t1")).toBeDefined();

    fireEvent.click(screen.getByTestId("home-refresh"));
    expect(screen.queryByTestId("home-reason-busy")).toBeNull();

    await act(async () => {
      vi.advanceTimersByTime(150);
    });
    expect(screen.getByTestId("home-reason-busy")).toBeDefined();

    await act(async () => {
      releaseSecond?.();
    });
    await flush();
    // The operation finished, but the treatment must stay for 400ms from show.
    expect(screen.getByTestId("home-reason-busy")).toBeDefined();

    await act(async () => {
      vi.advanceTimersByTime(400);
    });
    expect(screen.queryByTestId("home-reason-busy")).toBeNull();
  });

  it("keeps the last-updated time and shows the error banner when a reload fails", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date(2026, 8, 12, 1, 2, 3));
    let calls = 0;
    renderHome(
      createMockSidecarClient({
        listTestRegistrations: async () => {
          calls += 1;
          if (calls > 1) {
            throw new Error("sidecar is not connected");
          }
          return [buildTest({ id: "t1" })];
        },
        listSubmissions: async () => [],
      }),
    );

    await waitFor(() => {
      expect(screen.getByTestId("home-last-updated").textContent).toContain(
        "01:02:03",
      );
    });

    vi.setSystemTime(new Date(2026, 8, 12, 4, 5, 6));
    fireEvent.click(screen.getByTestId("home-refresh"));
    await screen.findByTestId("home-error");
    // The failure must not look like a successful update.
    expect(screen.getByTestId("home-last-updated").textContent).toContain(
      "01:02:03",
    );
  });
});
