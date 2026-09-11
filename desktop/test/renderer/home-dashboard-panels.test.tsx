import { describe, expect, it } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";

import { ActionRequirements } from "../../src/renderer/core/action-requirements.js";
import { AppRoutes } from "../../src/renderer/core/app-routes.js";
import { HomeWorkBucket } from "../../src/renderer/core/submission-work-bucket.js";
import { renderAppAt } from "./support/app-harness.js";
import {
  buildProgress,
  buildSubmission,
  buildTest,
  createMockSidecarClient,
  type MockSidecarHandlers,
} from "./support/mock-sidecar-client.js";

/**
 * Regression tests for the home dashboard panels (Issue #336).
 *
 * Every assertion is positive: it names the value the implementation must
 * produce, so breaking the implementation turns it red (the mutation list is
 * in the PR). Recharts draws SVG, so the bars and donut sectors are real DOM
 * nodes the tests can read.
 */

const DAY_MS = 86_400_000;

/** A submission dated `daysAgo` days before noon today. */
function submissionDaysAgo(input: {
  id: string;
  testId: string;
  state: string;
  daysAgo: number;
}): ReturnType<typeof buildSubmission> {
  const noon = new Date();
  noon.setHours(12, 0, 0, 0);
  return {
    ...buildSubmission({
      id: input.id,
      testId: input.testId,
      state: input.state,
    }),
    created_at: new Date(noon.getTime() - input.daysAgo * DAY_MS).toISOString(),
  };
}

function barElements(container: HTMLElement): Element[] {
  return Array.from(
    container.querySelectorAll("[data-testid='home-daily-bar']"),
  );
}

function barHeight(bar: Element): number {
  return Number(bar.getAttribute("height") ?? "0");
}

describe("home dashboard: 全体の進捗 (Issue #336)", () => {
  it("shows the four bucket counts from HomeWorkBucket", async () => {
    renderAppAt(AppRoutes.home, {
      handlers: {
        listTestRegistrations: async () => [
          buildTest({ id: "t1", name: "国語" }),
          buildTest({ id: "t2", name: "数学" }),
        ],
        listSubmissions: async (testId) =>
          testId === "t1"
            ? [
                buildSubmission({ id: "n1", testId, state: "needs_review" }),
                buildSubmission({ id: "n2", testId, state: "needs_review" }),
                buildSubmission({ id: "p1", testId, state: "ai_processed" }),
                buildSubmission({ id: "p2", testId, state: "ai_processed" }),
                buildSubmission({ id: "p3", testId, state: "ai_processed" }),
              ]
            : [
                buildSubmission({ id: "r1", testId, state: "ai_processing" }),
                buildSubmission({ id: "d1", testId, state: "reviewed" }),
                buildSubmission({ id: "d2", testId, state: "exported" }),
              ],
      },
    });

    // The four mock statistics, each read from the bucket the label names.
    await waitFor(() => {
      expect(screen.getByTestId("home-bucket-needsReview").textContent).toBe(
        "2",
      );
    });
    expect(screen.getByTestId("home-bucket-intakeDone").textContent).toBe("3");
    expect(screen.getByTestId("home-bucket-processing").textContent).toBe("1");
    expect(screen.getByTestId("home-bucket-done").textContent).toBe("2");
    // Nothing failed, so the failure row must not be drawn as a zero.
    expect(screen.queryByTestId("home-bucket-failed")).toBeNull();

    expect(HomeWorkBucket.needsReview).toBe("needsReview");
  });
});

describe("home dashboard: daily bar chart (Issue #336)", () => {
  it("draws one bar per day and scales bar height from the counts", async () => {
    const { container } = renderAppAt(AppRoutes.home, {
      handlers: {
        listTestRegistrations: async () => [buildTest({ id: "t1" })],
        listSubmissions: async () => [
          submissionDaysAgo({
            id: "a",
            testId: "t1",
            state: "reviewed",
            daysAgo: 0,
          }),
          submissionDaysAgo({
            id: "b",
            testId: "t1",
            state: "reviewed",
            daysAgo: 0,
          }),
          submissionDaysAgo({
            id: "c",
            testId: "t1",
            state: "reviewed",
            daysAgo: 0,
          }),
          submissionDaysAgo({
            id: "d",
            testId: "t1",
            state: "reviewed",
            daysAgo: 3,
          }),
        ],
      },
    });

    await waitFor(() => {
      expect(barElements(container)).toHaveLength(7);
    });
    const bars = barElements(container);
    const counts = bars.map((bar) => Number(bar.getAttribute("data-count")));
    expect(counts.filter((count) => count === 3)).toHaveLength(1);
    expect(counts.filter((count) => count === 1)).toHaveLength(1);
    expect(counts.filter((count) => count === 0)).toHaveLength(5);

    const three = bars.find((bar) => bar.getAttribute("data-count") === "3");
    const one = bars.find((bar) => bar.getAttribute("data-count") === "1");
    const zero = bars.find((bar) => bar.getAttribute("data-count") === "0");
    expect(three).toBeDefined();
    expect(one).toBeDefined();
    expect(zero).toBeDefined();
    expect(barHeight(zero!)).toBe(0);
    expect(barHeight(one!)).toBeGreaterThan(0);
    expect(barHeight(three!)).toBeGreaterThan(barHeight(one!));
    // Heights are proportional, not merely ordered.
    expect(barHeight(one!) / barHeight(three!)).toBeCloseTo(1 / 3, 1);

    // The numbers are also readable as text, not only as a picture.
    expect(screen.getByTestId("home-daily-chart").textContent ?? "").toContain(
      "3",
    );
  });
});

describe("home dashboard: test progress donut (Issue #336)", () => {
  it("matches each donut slice to the count of tests in that phase", async () => {
    const work: Record<string, ReturnType<typeof buildSubmission>[]> = {};
    // 3 preparing (draft), 2 in progress (ready, unfinished), 1 done.
    const drafts = ["d1", "d2", "d3"].map((id) =>
      buildTest({ id, name: `下書き${id}`, status: "draft" }),
    );
    const inProgress = ["p1", "p2"].map((id) => {
      work[id] = [
        submissionDaysAgo({
          id: `s-${id}`,
          testId: id,
          state: "needs_review",
          daysAgo: 1,
        }),
      ];
      return buildTest({ id, name: `進行${id}` });
    });
    const done = ["c1"].map((id) => {
      work[id] = [
        submissionDaysAgo({
          id: `s-${id}`,
          testId: id,
          state: "reviewed",
          daysAgo: 2,
        }),
      ];
      return buildTest({ id, name: `完了${id}` });
    });

    renderAppAt(AppRoutes.home, {
      handlers: {
        listTestRegistrations: async () => [...drafts, ...inProgress, ...done],
        listSubmissions: async (testId) => work[testId] ?? [],
      },
    });

    await waitFor(() => {
      expect(screen.getByTestId("home-phase-total").textContent).toBe("6");
    });
    expect(screen.getByTestId("home-phase-preparing").textContent).toContain(
      "3",
    );
    expect(screen.getByTestId("home-phase-inProgress").textContent).toContain(
      "2",
    );
    expect(screen.getByTestId("home-phase-done").textContent).toContain("1");
    // Legend carries percents, so colour is not the only signal.
    expect(screen.getByTestId("home-phase-preparing").textContent).toContain(
      "50%",
    );
  });
});

describe("home dashboard: recent tests table (Issue #336)", () => {
  it("sizes the progress bar from review-progress, not from answer states", async () => {
    renderAppAt(AppRoutes.home, {
      handlers: {
        listTestRegistrations: async () => [
          buildTest({ id: "t1", name: "国語" }),
        ],
        listSubmissions: async () => [
          buildSubmission({ id: "s1", testId: "t1", state: "reviewed" }),
          buildSubmission({ id: "s2", testId: "t1", state: "ai_processed" }),
        ],
        listReviewProgress: async () => [
          buildProgress({ id: "s1", total: 5, confirmed: 3 }),
          buildProgress({ id: "s2", total: 3, confirmed: 0 }),
        ],
      },
    });

    await waitFor(() => {
      expect(screen.getByTestId("home-test-progress-fill-t1").style.width).toBe(
        "38%",
      );
    });
    expect(
      screen.getByTestId("home-test-progress-percent-t1").textContent,
    ).toBe("38%");
    const bar = screen.getByTestId("home-test-progress-t1");
    expect(bar.getAttribute("aria-valuenow")).toBe("3");
    expect(bar.getAttribute("aria-valuemax")).toBe("8");
  });

  it("keeps old queue entry text and testids (INV-149)", async () => {
    renderAppAt(AppRoutes.home, {
      handlers: {
        listTestRegistrations: async () => [
          buildTest({ id: "t1", name: "国語 第1回" }),
        ],
        listSubmissions: async () => [
          buildSubmission({ id: "d1", testId: "t1", state: "reviewed" }),
          buildSubmission({ id: "n1", testId: "t1", state: "needs_review" }),
        ],
      },
    });
    await screen.findByTestId("home-test-card-t1");
    expect(screen.getByText("確認済み 1 / 2")).toBeDefined();
    expect(screen.getByTestId("home-open-queue-t1")).toBeDefined();
  });
});

describe("home dashboard: empty state (Issue #336)", () => {
  it("shows guidance and no charts when there are no tests", async () => {
    renderAppAt(AppRoutes.home, {
      handlers: {
        listTestRegistrations: async () => [],
        listSubmissions: async () => [],
      },
    });

    await screen.findByTestId("home-empty-state");
    expect(screen.getByText("まだテストが登録されていません")).toBeDefined();
    expect(screen.getByTestId("home-next-up-action")).toBeDefined();
    expect(screen.queryByTestId("home-daily-chart")).toBeNull();
    expect(screen.queryByTestId("home-phase-chart")).toBeNull();
    expect(screen.queryByTestId("home-recent-tests")).toBeNull();
    expect(screen.queryByTestId("home-bucket-needsReview")).toBeNull();
  });
});

describe("home dashboard: partial data (Issue #336)", () => {
  it("keeps the dashboard up and marks only the test it could not read", async () => {
    const handlers: MockSidecarHandlers = {
      listTestRegistrations: async () => [
        buildTest({ id: "good", name: "読めるテスト" }),
        buildTest({ id: "bad", name: "読めないテスト" }),
      ],
      listSubmissions: async (testId) => {
        if (testId === "bad") {
          throw new Error("submissions unavailable");
        }
        return [buildSubmission({ id: "g1", testId, state: "needs_review" })];
      },
      listReviewProgress: async (testId) => {
        if (testId === "bad") {
          throw new Error("review progress unavailable");
        }
        return [buildProgress({ id: "g1", total: 4, confirmed: 1 })];
      },
    };
    renderAppAt(AppRoutes.home, { handlers });

    await screen.findByTestId("home-degraded");
    expect(
      within(screen.getByTestId("home-degraded")).getByText(/読めないテスト/),
    ).toBeDefined();
    // The good test's answer still counts; the unreadable one is not shown as 0.
    expect(screen.getByTestId("home-bucket-needsReview").textContent).toBe("1");
    expect(
      screen.getByTestId("home-test-progress-unavailable-bad"),
    ).toBeDefined();
  });
});

const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

function focusOrder(root: ParentNode): HTMLElement[] {
  return Array.from(
    root.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
  ).filter((element) => element.tabIndex >= 0);
}

describe("home dashboard: states and accessibility (Issue #336)", () => {
  it("keeps a skeleton, and disables refresh with the shared busy reason, while loading", () => {
    const client = createMockSidecarClient({
      listTestRegistrations: () => new Promise(() => {}),
    });
    renderAppAt(AppRoutes.home, { client });

    expect(screen.getByTestId("home-loading")).toBeDefined();
    // The entry points stay usable while the dashboard loads.
    expect(screen.getByTestId("home-open-intake")).toBeDefined();

    const refresh = screen.getByTestId("home-refresh") as HTMLButtonElement;
    expect(refresh.disabled).toBe(true);
    expect(screen.getByTestId("home-reason-busy").textContent).toBe(
      ActionRequirements.busy.message,
    );
  });

  it("puts every control in the visual Tab order and keeps focus visible", async () => {
    renderAppAt(AppRoutes.home, {
      handlers: {
        listTestRegistrations: async () => [
          buildTest({ id: "draft-1", name: "準備中のテスト", status: "draft" }),
          buildTest({ id: "work-1", name: "要確認のテスト" }),
        ],
        listSubmissions: async (testId) =>
          testId === "work-1"
            ? [
                buildSubmission({
                  id: "s1",
                  testId,
                  state: "needs_review",
                  studentLabel: "S-1",
                }),
              ]
            : [],
      },
    });

    await screen.findByTestId("home-test-card-work-1");
    const order = focusOrder(document.body).map((element) => ({
      testId: element.getAttribute("data-testid"),
      cls: element.className,
    }));
    const ids = order.map((entry) => entry.testId);
    expect(ids).toEqual([
      "home-refresh",
      "home-next-up-action",
      "home-open-intake",
      "home-open-test-list-footer",
      "home-open-settings",
      "home-resume-review-work-1",
      "home-open-queue-work-1",
      "home-resume-registration-draft-1",
      "home-open-queue-draft-1",
    ]);
    // Every focusable control has a visible focus treatment.
    for (const entry of order) {
      expect(entry.cls).toContain("focus-visible:outline");
    }
  });

  it("truncates a long test name without letting it widen the table", async () => {
    const longName =
      "とても長いテスト名がここに入り、狭い画面でもレイアウトを壊さないことを確かめるための名前";
    renderAppAt(AppRoutes.home, {
      handlers: {
        listTestRegistrations: async () => [
          buildTest({ id: "t1", name: longName }),
        ],
        listSubmissions: async () => [],
      },
    });

    const name = await screen.findByTestId("home-test-name-t1");
    expect(name.className).toContain("truncate");
    expect(name.getAttribute("title")).toBe(longName);
    const scroller = screen
      .getByTestId("home-recent-tests")
      .querySelector(".overflow-x-auto");
    expect(scroller).not.toBeNull();
  });
});
