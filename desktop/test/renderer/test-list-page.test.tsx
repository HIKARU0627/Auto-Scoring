import { describe, expect, it } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";

import { AppRoutes } from "../../src/renderer/core/app-routes.js";
import { renderAppAt } from "./support/app-harness.js";
import { createIntakeMockClient } from "./support/intake-harness.js";
import {
  buildProgress,
  buildSubmission,
  buildTest,
  createMockSidecarClient,
} from "./support/mock-sidecar-client.js";

/**
 * Issue #379: the test list screen. The acceptance list fixes four behaviours
 * on this file -- the list itself, the empty state, each row's two destinations,
 * and the retry after a load failure -- plus the home entry point that used to
 * land on an empty placeholder.
 */
describe("TestListPage (Issue #379)", () => {
  it("lists every registered test with its status, answer count, and progress", async () => {
    renderAppAt(AppRoutes.testList, {
      handlers: {
        listTestRegistrations: async () => [
          buildTest({ id: "t-ready", name: "国語 第1回", status: "ready" }),
          buildTest({ id: "t-draft", name: "数学 第1回", status: "draft" }),
        ],
        listSubmissions: async (testId) =>
          testId === "t-ready"
            ? [
                buildSubmission({
                  id: "s1",
                  testId: "t-ready",
                  state: "reviewed",
                }),
              ]
            : [],
        listReviewProgress: async (testId) =>
          testId === "t-ready"
            ? [buildProgress({ id: "s1", confirmed: 3, total: 5 })]
            : [],
      },
    });

    await screen.findByTestId("test-list-row-t-ready");
    // draft and ready both appear (acceptance item 1).
    expect(screen.getByTestId("test-list-row-t-draft")).toBeDefined();
    expect(screen.getByTestId("test-list-name-t-ready").textContent).toBe(
      "国語 第1回",
    );
    expect(screen.getByTestId("test-list-name-t-draft").textContent).toBe(
      "数学 第1回",
    );
    // The status is on the row, and it is the shared HomeTestProgress badge.
    expect(screen.getByTestId("test-list-status-t-ready").textContent).toBe(
      "完了",
    );
    expect(screen.getByTestId("test-list-status-t-draft").textContent).toBe(
      "準備中",
    );
    expect(
      screen.getByTestId("test-list-progress-percent-t-ready").textContent,
    ).toBe("60%");
  });

  it("switches to one block per test at narrow widths", async () => {
    const originalWidth = Object.getOwnPropertyDescriptor(window, "innerWidth");
    Object.defineProperty(window, "innerWidth", {
      configurable: true,
      value: 700,
    });
    try {
      renderAppAt(AppRoutes.testList, {
        handlers: {
          listTestRegistrations: async () => [buildTest({ id: "t1" })],
          listSubmissions: async () => [],
        },
      });

      await screen.findByTestId("test-list-row-t1");
      expect(screen.getByTestId("test-list-row-t1").tagName).toBe("LI");
      expect(document.querySelector("table")).toBeNull();
    } finally {
      if (originalWidth !== undefined) {
        Object.defineProperty(window, "innerWidth", originalWidth);
      }
    }
  });

  it("opens the test settings screen from a row", async () => {
    renderAppAt(AppRoutes.testList, {
      handlers: {
        listTestRegistrations: async () => [buildTest({ id: "t1" })],
        listSubmissions: async () => [],
      },
    });

    await screen.findByTestId("test-list-row-t1");
    fireEvent.click(screen.getByTestId("test-list-open-settings-t1"));

    await waitFor(() => {
      expect(screen.getByTestId("page-title").textContent).toBe("テスト設定");
    });
  });

  it("opens the answer queue from a row", async () => {
    renderAppAt(AppRoutes.testList, {
      handlers: {
        listTestRegistrations: async () => [buildTest({ id: "t1" })],
        listSubmissions: async () => [],
      },
    });

    await screen.findByTestId("test-list-row-t1");
    fireEvent.click(screen.getByTestId("test-list-open-queue-t1"));

    await waitFor(() => {
      expect(screen.getByTestId("page-title").textContent).toBe("答案キュー");
    });
  });

  it("opens the intake screen with this test already chosen as the destination (Issue #414)", async () => {
    renderAppAt(AppRoutes.testList, {
      client: createIntakeMockClient({
        listTestRegistrations: async () => [
          buildTest({ id: "t1", name: "国語 第1回" }),
        ],
      }),
    });

    await screen.findByTestId("test-list-row-t1");
    fireEvent.click(screen.getByTestId("test-list-add-answers-t1"));

    await screen.findByTestId("intake-target-summary");
    expect(screen.getByTestId("page-title").textContent).toBe("資料の取込");
    expect(screen.getByTestId("intake-target-summary").textContent).toContain(
      "国語 第1回",
    );
  });

  it("shows the empty state and routes to intake when no test is registered", async () => {
    renderAppAt(AppRoutes.testList, {
      handlers: {
        listTestRegistrations: async () => [],
        listSubmissions: async () => [],
      },
    });

    await screen.findByTestId("test-list-empty");
    expect(screen.queryByTestId("test-list-table")).toBeNull();

    fireEvent.click(screen.getByTestId("test-list-empty-intake"));
    await waitFor(() => {
      expect(screen.getByTestId("page-title").textContent).toBe("資料の取込");
    });
  });

  it("shows a loading state before the list arrives", async () => {
    const deferred: {
      resolve: (tests: ReturnType<typeof buildTest>[]) => void;
    } = { resolve: () => {} };
    const pending = new Promise<ReturnType<typeof buildTest>[]>((resolve) => {
      deferred.resolve = resolve;
    });
    const client = createMockSidecarClient({
      listTestRegistrations: () => pending,
      listSubmissions: async () => [],
    });

    renderAppAt(AppRoutes.testList, { client });
    expect(screen.getByTestId("test-list-loading")).toBeDefined();

    deferred.resolve([buildTest({ id: "t1" })]);
    await screen.findByTestId("test-list-row-t1");
  });

  it("shows the error banner and retries the load", async () => {
    let attempts = 0;
    renderAppAt(AppRoutes.testList, {
      handlers: {
        listTestRegistrations: async () => {
          attempts += 1;
          if (attempts === 1) {
            throw new Error("sidecar is not connected");
          }
          return [buildTest({ id: "t1" })];
        },
        listSubmissions: async () => [],
      },
    });

    await screen.findByTestId("test-list-error");
    expect(screen.queryByTestId("test-list-row-t1")).toBeNull();

    fireEvent.click(screen.getByTestId("test-list-error-retry"));
    await screen.findByTestId("test-list-row-t1");
    expect(screen.queryByTestId("test-list-error")).toBeNull();
  });

  it("shows the full list when the home overflow link is pressed", async () => {
    renderAppAt(AppRoutes.home, {
      handlers: {
        listTestRegistrations: async () => [
          buildTest({ id: "t1", name: "国語 第1回" }),
        ],
        listSubmissions: async () => [],
      },
    });

    await screen.findByTestId("home-test-card-t1");
    fireEvent.click(screen.getByTestId("home-open-all-tests"));

    await waitFor(() => {
      expect(screen.getByTestId("page-title").textContent).toBe("テスト一覧");
    });
    // The page title is set synchronously by the router, but the rows only
    // appear once the list request resolves; a synchronous `getByTestId` here
    // raced the load and failed under full-suite load. Await the row instead.
    await screen.findByTestId("test-list-row-t1");
  });
});
