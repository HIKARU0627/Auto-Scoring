import { describe, expect, it } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";

import { AppRoutes } from "../../src/renderer/core/app-routes.js";
import { HomeDashboard } from "../../src/renderer/core/home-dashboard.js";
import { renderAppAt } from "./support/app-harness.js";
import {
  buildSubmission,
  buildTest,
  createMockSidecarClient,
} from "./support/mock-sidecar-client.js";

describe("HomePage", () => {
  it("does not show backend debug text (INV-048)", async () => {
    renderAppAt(AppRoutes.home, {
      handlers: {
        listTestRegistrations: async () => [buildTest({ id: "t1" })],
        listSubmissions: async () => [],
      },
    });

    await screen.findByTestId("home-test-card-t1");
    expect(screen.queryByText(/backend/i)).toBeNull();
  });

  it("shows progress breakdown and per-test counts", async () => {
    renderAppAt(AppRoutes.home, {
      handlers: {
        listTestRegistrations: async () => [
          buildTest({ id: "t1", name: "国語 第1回" }),
        ],
        listSubmissions: async () => [
          buildSubmission({ id: "s1", testId: "t1", state: "needs_review" }),
          buildSubmission({ id: "s2", testId: "t1", state: "ai_processing" }),
          buildSubmission({ id: "s3", testId: "t1", state: "error" }),
          buildSubmission({ id: "s4", testId: "t1", state: "reviewed" }),
          buildSubmission({ id: "s5", testId: "t1", state: "exported" }),
        ],
      },
    });

    await screen.findByTestId("home-test-card-t1");
    expect(screen.getByText("国語 第1回")).toBeDefined();
    expect(screen.getByText("確認済み 2 / 5")).toBeDefined();
    expect(screen.getByText("要確認 1件")).toBeDefined();
    expect(screen.getByText("処理中 1件")).toBeDefined();
    expect(screen.getByText("取込失敗 1件")).toBeDefined();
    expect(screen.queryByText("取込済み 0件")).toBeNull();
    expect(screen.queryByText(/確認済み 2件/)).toBeNull();
  });

  it("opens the oldest needs_review submission from next action (INV-148)", async () => {
    renderAppAt(AppRoutes.home, {
      handlers: {
        listTestRegistrations: async () => [buildTest({ id: "t1" })],
        listSubmissions: async () => [
          buildSubmission({
            id: "newer",
            testId: "t1",
            state: "needs_review",
            createdDay: 5,
          }),
          buildSubmission({
            id: "oldest",
            testId: "t1",
            state: "needs_review",
            createdDay: 2,
          }),
        ],
      },
    });

    await screen.findByText("要確認の答案が2件あります");
    fireEvent.click(screen.getByTestId("home-next-up-action"));
    await screen.findByText("添削レビュー");
    expect(screen.getByTestId("review-question-rail")).toBeDefined();
  });

  it("does not count ai_processed as done (INV-147)", async () => {
    renderAppAt(AppRoutes.home, {
      handlers: {
        listTestRegistrations: async () => [
          buildTest({ id: "t1", name: "国語 第1回" }),
        ],
        listSubmissions: async () => [
          buildSubmission({ id: "done", testId: "t1", state: "reviewed" }),
          buildSubmission({
            id: "todo",
            testId: "t1",
            state: "ai_processed",
          }),
        ],
      },
    });

    await screen.findByText("確認済み 1 / 2");
  });

  it("opens the submission queue from confirmed progress only (INV-149)", async () => {
    renderAppAt(AppRoutes.home, {
      handlers: {
        listTestRegistrations: async () => [
          buildTest({ id: "t1", name: "国語 第1回" }),
        ],
        listSubmissions: async () => [
          buildSubmission({ id: "done", testId: "t1", state: "reviewed" }),
          buildSubmission({ id: "todo", testId: "t1", state: "ai_processed" }),
        ],
      },
    });

    await screen.findByText("確認済み 1 / 2");
    fireEvent.click(screen.getByTestId("home-open-queue-t1"));
    await screen.findByText("答案キュー");
    expect(screen.getByText("testId=t1")).toBeDefined();
  });

  it("rejects deprecated empty-state copy (INV-128 / INV-129)", async () => {
    renderAppAt(AppRoutes.home, {
      handlers: {
        listTestRegistrations: async () => [],
        listSubmissions: async () => [],
      },
    });

    await screen.findByText("まだテストが登録されていません");
    expect(screen.queryByText(/模範解答/)).toBeNull();
    expect(screen.queryByText(/採点マニュアル/)).toBeNull();
  });

  it("fetches submissions for overflow tests (INV-150)", async () => {
    const flaggedNames = ["化学", "古漢"];
    const flagged = flaggedNames.map((name, index) =>
      buildTest({ id: `flagged-${index}`, name, createdDay: index + 1 }),
    );
    const settled = Array.from({ length: 9 }, (_, index) =>
      buildTest({
        id: `settled-${index}`,
        name: `テスト${index}`,
        createdDay: index + 10,
      }),
    );
    const fetched: string[] = [];
    renderAppAt(AppRoutes.home, {
      handlers: {
        listTestRegistrations: async () => [...settled, ...flagged],
        listSubmissions: async (testId) => {
          fetched.push(testId);
          return testId.startsWith("flagged-")
            ? [
                buildSubmission({
                  id: `s-${testId}`,
                  testId,
                  state: "needs_review",
                }),
              ]
            : [
                buildSubmission({
                  id: `s-${testId}`,
                  testId,
                  state: "exported",
                }),
              ];
        },
      },
    });

    await screen.findByText("要確認の答案が2件あります");
    expect(fetched).toEqual(
      expect.arrayContaining(flagged.map((test) => test.id)),
    );
    for (const test of flagged) {
      expect(screen.getByTestId(`home-test-card-${test.id}`)).toBeDefined();
    }
    expect(screen.getByText("他3件を見る")).toBeDefined();
  });

  it("shows retry after load failure", async () => {
    let attempts = 0;
    const client = createMockSidecarClient({
      listTestRegistrations: async () => {
        attempts += 1;
        if (attempts === 1) {
          throw new Error("sidecar is not connected");
        }
        return [buildTest({ id: "t1" })];
      },
      listSubmissions: async () => [],
    });

    renderAppAt(AppRoutes.home, { client });
    await screen.findByTestId("home-error");
    fireEvent.click(screen.getByText("再試行"));
    await screen.findByTestId("home-test-card-t1");
    expect(screen.queryByTestId("home-error")).toBeNull();
  });

  it("reloads only when AI processing is the only actionable state", async () => {
    let loads = 0;
    renderAppAt(AppRoutes.home, {
      handlers: {
        listTestRegistrations: async () => {
          loads += 1;
          return [buildTest({ id: "t1" })];
        },
        listSubmissions: async () => [
          buildSubmission({ id: "s1", testId: "t1", state: "ai_processing" }),
        ],
      },
    });

    await screen.findByText("処理中の答案が1件あります");
    expect(loads).toBe(1);
    fireEvent.click(screen.getByTestId("home-next-up-action"));
    await waitFor(() => {
      expect(loads).toBe(2);
    });
    expect(screen.getByText("処理中の答案が1件あります")).toBeDefined();
  });

  it("shows hidden overflow count", async () => {
    const tests = Array.from(
      { length: HomeDashboard.maxTests + 3 },
      (_, index) =>
        buildTest({
          id: `t${index}`,
          name: `テスト${index}`,
          createdDay: index + 1,
        }),
    );
    renderAppAt(AppRoutes.home, {
      handlers: {
        listTestRegistrations: async () => tests,
        listSubmissions: async () => [],
      },
    });

    await screen.findByText("他3件を見る");
    expect(
      screen.getByTestId(`home-test-card-t${HomeDashboard.maxTests + 2}`),
    ).toBeDefined();
    expect(screen.queryByTestId("home-test-card-t0")).toBeNull();
  });
});
