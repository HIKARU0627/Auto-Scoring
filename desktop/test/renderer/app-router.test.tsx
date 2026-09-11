import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";

import {
  AppRoutes,
  pdfReview,
  submissionConfirm,
  submissionQueue,
  testSettings,
} from "../../src/renderer/core/app-routes.js";
import { matchRoutePattern } from "../../src/renderer/navigation/router.js";
import { ROUTE_TABLE } from "../../src/renderer/navigation/route-table.js";
import { renderAppAt } from "./support/app-harness.js";
import { buildTest } from "./support/mock-sidecar-client.js";

const defaultHandlers = {
  listTestRegistrations: async () => [
    buildTest({ id: "test-1", status: "draft" }),
  ],
  listSubmissions: async () => [],
};

function fill(path: string): string {
  return path.replace(":testId", "test-1").replace(":submissionId", "sub-1");
}

/**
 * One expected screen per route definition. Keyed by the same pattern string
 * `ROUTE_TABLE` declares, so an author who adds a route must register it here
 * or the meta test below turns red (`INV-012`, mirroring the `INV-020` shape in
 * `home-escape.test.tsx`).
 *
 * The marker is rendered by the screen itself -- its ShellScreen title, its own
 * heading, or a placeholder `data-testid` -- so this asserts that rendering the
 * location actually mounted that component, not merely that a path was known.
 */
const covered: Readonly<
  Record<string, { readonly text: string } | { readonly testId: string }>
> = {
  [AppRoutes.home]: { testId: "home-refresh" },
  [AppRoutes.starting]: { testId: "route-starting" },
  [AppRoutes.intake]: { text: "資料の取込" },
  [AppRoutes.settings]: { text: "設定" },
  [AppRoutes.testList]: { text: "テスト一覧" },
  [AppRoutes.testSettingsPattern]: { text: "テスト設定" },
  [AppRoutes.submissionQueuePattern]: { text: "答案キュー" },
  [AppRoutes.submissionConfirmPattern]: { text: "答案の確定" },
  [AppRoutes.pdfReviewPattern]: { text: "添削レビュー" },
};

/**
 * Route patterns deliberately left out of the render loop, with the reason
 * written down. Empty today: every location renders its own screen. It exists
 * so a future non-screen placeholder can be excluded explicitly rather than
 * silently dropped.
 */
const skipped: Readonly<Record<string, string>> = {};

describe("app router (INV-012)", () => {
  it("every route definition is covered or skipped with a reason (meta)", () => {
    const registered = new Set([
      ...Object.keys(covered),
      ...Object.keys(skipped),
    ]);
    const unregistered = ROUTE_TABLE.map((route) => route.pattern).filter(
      (pattern) => !registered.has(pattern),
    );

    expect(unregistered).toEqual([]);
  });

  it("flags a route that is declared but not registered", () => {
    const registered = new Set([
      ...Object.keys(covered),
      ...Object.keys(skipped),
    ]);
    const rogue = "/rogue-screen";
    const unregistered = [
      ...ROUTE_TABLE.map((route) => route.pattern),
      rogue,
    ].filter((pattern) => !registered.has(pattern));
    expect(unregistered).toEqual([rogue]);
  });

  for (const [pattern, expected] of Object.entries(covered)) {
    const location = fill(pattern);

    it(`${location} opens its screen`, () => {
      renderAppAt(location, { handlers: defaultHandlers });

      if ("testId" in expected) {
        expect(screen.getByTestId(expected.testId)).toBeDefined();
        return;
      }
      expect(screen.getByText(expected.text)).toBeDefined();
    });
  }
});

describe("parameter decoding (INV-013)", () => {
  // Contains every character class that a naive "pass the raw segment through"
  // bug would either split on (`/`), truncate at (`?`), or mis-decode (`%`),
  // plus non-ASCII.
  const trickyTestId = "a/b?c%25日本語";
  const trickySubmissionId = "s/1?2%25採点";

  it("testId is decoded before it reaches the settings screen", () => {
    const matched = matchRoutePattern(
      AppRoutes.testSettingsPattern,
      testSettings(trickyTestId),
    );

    expect(matched).not.toBeNull();
    expect(matched?.params.testId).toBe(trickyTestId);
  });

  it("testId is decoded for the submission queue", () => {
    const matched = matchRoutePattern(
      AppRoutes.submissionQueuePattern,
      submissionQueue(trickyTestId),
    );

    expect(matched?.params.testId).toBe(trickyTestId);
  });

  it("testId and submissionId are decoded for the confirm screen", () => {
    const matched = matchRoutePattern(
      AppRoutes.submissionConfirmPattern,
      submissionConfirm(trickyTestId, trickySubmissionId),
    );

    expect(matched?.params.testId).toBe(trickyTestId);
    expect(matched?.params.submissionId).toBe(trickySubmissionId);
  });

  it("testId, submissionId, and questionId are decoded for the review screen", () => {
    const trickyQuestionId = "問/1 ?%252";
    const matched = matchRoutePattern(
      AppRoutes.pdfReviewPattern,
      pdfReview(trickyTestId, trickySubmissionId, trickyQuestionId),
    );

    expect(matched?.params.testId).toBe(trickyTestId);
    expect(matched?.params.submissionId).toBe(trickySubmissionId);
    expect(matched?.params.questionId).toBe(trickyQuestionId);
  });

  it("the decoded testId actually reaches the rendered component", () => {
    renderAppAt(submissionQueue(trickyTestId), { handlers: defaultHandlers });

    expect(screen.getByText(`testId=${trickyTestId}`)).toBeDefined();
  });
});
