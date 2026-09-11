import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";

import { AppRoutes } from "../../src/renderer/core/app-routes.js";
import { renderAppAt } from "./support/app-harness.js";
import {
  buildSubmission,
  buildTest,
  type MockSidecarHandlers,
} from "./support/mock-sidecar-client.js";

/**
 * Regression tests for the Issue #353 dashboard polish (parent #333).
 *
 * Each test names the value the implementation must produce, so the mutation
 * list in the PR turns the matching test red:
 *   1. status pills: one distinct token fill per state
 *   2. donut: no gap when a single phase is 100%
 *   3. quick actions: every row is its own raised surface
 */

const SUBMISSIONS: Record<string, ReturnType<typeof buildSubmission>[]> = {
  "t-prep": [],
  "t-attn": [
    buildSubmission({ id: "a1", testId: "t-attn", state: "needs_review" }),
  ],
  "t-fail": [buildSubmission({ id: "f1", testId: "t-fail", state: "error" })],
  "t-done": [
    buildSubmission({ id: "d1", testId: "t-done", state: "reviewed" }),
  ],
  "t-prog": [
    buildSubmission({ id: "p1", testId: "t-prog", state: "ai_processing" }),
  ],
};

describe("home dashboard polish: status pills (Issue #353)", () => {
  it("gives every test state its own token-derived fill", async () => {
    const handlers: MockSidecarHandlers = {
      listTestRegistrations: async () => [
        buildTest({ id: "t-prep", name: "準備", status: "draft" }),
        buildTest({ id: "t-attn", name: "要確認" }),
        buildTest({ id: "t-fail", name: "失敗" }),
        buildTest({ id: "t-done", name: "完了" }),
        buildTest({ id: "t-prog", name: "進行" }),
        buildTest({ id: "t-unavail", name: "取得不可" }),
      ],
      listSubmissions: async (testId) => {
        if (testId === "t-unavail") {
          throw new Error("submissions unavailable");
        }
        return SUBMISSIONS[testId] ?? [];
      },
    };
    renderAppAt(AppRoutes.home, { handlers });

    const ids = ["t-prep", "t-attn", "t-fail", "t-done", "t-prog", "t-unavail"];
    await waitFor(() => {
      for (const id of ids) {
        expect(screen.getByTestId(`home-test-status-${id}`)).toBeDefined();
      }
    });

    const classes = ids.map((id) => {
      const pill = screen.getByTestId(`home-test-status-${id}`);
      const background = Array.from(pill.classList).find((name) =>
        name.startsWith("bg-"),
      );
      expect(background, `${id} must carry a background token`).toBeDefined();
      return `${id}:${background}`;
    });

    // Every state is a different token, so no two states read the same.
    expect(new Set(classes).size).toBe(ids.length);

    // The fills are the vivid status tokens, not the old sunk containers.
    const fills = classes.map((entry) => entry.split(":")[1]);
    expect(fills).toEqual([
      "bg-outline",
      "bg-attention",
      "bg-error-container",
      "bg-success",
      "bg-primary",
      "bg-secondary-container",
    ]);
  });
});

describe("home dashboard polish: donut gap (Issue #353)", () => {
  it("draws no gap when a single phase is 100%", async () => {
    renderAppAt(AppRoutes.home, {
      handlers: {
        listTestRegistrations: async () => [
          buildTest({ id: "p1", name: "進行1" }),
          buildTest({ id: "p2", name: "進行2" }),
        ],
        listSubmissions: async (testId) => [
          buildSubmission({
            id: `s-${testId}`,
            testId,
            state: "ai_processing",
          }),
        ],
      },
    });

    await screen.findByTestId("home-phase-chart");
    expect(screen.getByTestId("home-phase-inProgress").textContent).toContain(
      "100%",
    );
    expect(
      screen.getByTestId("home-phase-chart").getAttribute("data-padding-angle"),
    ).toBe("0");
  });

  it("keeps the gap between phases when more than one phase is present", async () => {
    renderAppAt(AppRoutes.home, {
      handlers: {
        listTestRegistrations: async () => [
          buildTest({ id: "p1", name: "進行" }),
          buildTest({ id: "p2", name: "完了" }),
        ],
        listSubmissions: async (testId) => [
          buildSubmission({
            id: `s-${testId}`,
            testId,
            state: testId === "p2" ? "reviewed" : "ai_processing",
          }),
        ],
      },
    });

    await screen.findByTestId("home-phase-chart");
    expect(
      screen.getByTestId("home-phase-chart").getAttribute("data-padding-angle"),
    ).toBe("2");
  });
});

describe("home dashboard polish: quick actions (Issue #353)", () => {
  it("puts every quick-action row on its own surface", async () => {
    renderAppAt(AppRoutes.home, {
      handlers: {
        listTestRegistrations: async () => [buildTest({ id: "t1" })],
        listSubmissions: async () => [],
      },
    });

    await screen.findByTestId("home-test-card-t1");
    for (const testId of [
      "home-open-intake",
      "home-open-test-list-footer",
      "home-open-settings",
    ]) {
      expect(
        screen.getByTestId(testId).className,
        `${testId} must be a raised row`,
      ).toContain("bg-surface-container-highest");
    }
  });
});
