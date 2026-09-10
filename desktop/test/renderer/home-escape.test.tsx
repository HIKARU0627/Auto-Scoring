import { describe, expect, it } from "vitest";
import { fireEvent, screen } from "@testing-library/react";

import {
  AppRoutes,
  declaredRoutePatterns,
} from "../../src/renderer/core/app-routes.js";
import { BACK_OR_HOME_BUTTON_TEST_ID } from "../../src/renderer/navigation/BackOrHomeButton.js";
import { renderAppAt } from "./support/app-harness.js";
import { buildTest } from "./support/mock-sidecar-client.js";

const skipped: Record<string, string> = {
  [AppRoutes.starting]:
    "Not a screen: startup overlay placeholder while the sidecar is unusable.",
  [AppRoutes.submissionQueuePattern]:
    "Submission queue. Follow-up Issue #192 (same wave as Flutter home_escape_test.dart).",
  [AppRoutes.pdfReviewPattern]:
    "PDF review. Follow-up Issue #192 (same wave as Flutter home_escape_test.dart).",
};

const covered = new Set<string>([
  AppRoutes.intake,
  AppRoutes.settings,
  AppRoutes.testList,
  AppRoutes.testSettingsPattern,
  AppRoutes.submissionConfirmPattern,
]);

function fill(path: string): string {
  return path.replace(":testId", "test-1").replace(":submissionId", "sub-1");
}

function uncoveredRoutes(
  patterns: readonly string[],
  registered: ReadonlySet<string>,
): string[] {
  return patterns.filter(
    (path) => path !== AppRoutes.home && !registered.has(path),
  );
}

const defaultHandlers = {
  listTestRegistrations: async () => [
    buildTest({ id: "test-1", status: "draft" }),
  ],
  listSubmissions: async () => [],
};

describe("home escape meta test (INV-201-05)", () => {
  it("skipped routes still exist in the route table", () => {
    expect(declaredRoutePatterns).toEqual(
      expect.arrayContaining(Object.keys(skipped)),
    );
  });

  it("every declared route is covered or skipped with a reason", () => {
    const registered = new Set<string>([...Object.keys(skipped), ...covered]);
    expect(uncoveredRoutes(declaredRoutePatterns, registered)).toEqual([]);
  });

  it("flags a route that is declared but not registered", () => {
    const registered = new Set<string>([...Object.keys(skipped), ...covered]);
    const rogue = "/rogue-screen";
    expect(
      uncoveredRoutes([...declaredRoutePatterns, rogue], registered),
    ).toEqual([rogue]);
  });

  for (const path of covered) {
    const location = fill(path);

    it(`${location}: shows an escape control on an empty stack`, async () => {
      renderAppAt(location, { handlers: defaultHandlers });
      expect(
        await screen.findByTestId(BACK_OR_HOME_BUTTON_TEST_ID),
      ).toBeDefined();
    });

    it(`${location}: escape returns to home`, async () => {
      renderAppAt(location, { handlers: defaultHandlers });
      fireEvent.click(await screen.findByTestId(BACK_OR_HOME_BUTTON_TEST_ID));
      await screen.findByTestId("home-next-up");
    });
  }

  it("home does not show an escape control (INV-018)", async () => {
    renderAppAt(AppRoutes.home, {
      handlers: {
        listTestRegistrations: async () => [],
        listSubmissions: async () => [],
      },
    });
    await screen.findByText("まだテストが登録されていません");
    expect(screen.queryByTestId(BACK_OR_HOME_BUTTON_TEST_ID)).toBeNull();
  });

  it("escape pops one frame when the stack is not empty (INV-019)", async () => {
    renderAppAt(AppRoutes.intake, {
      handlers: defaultHandlers,
      initialStack: [AppRoutes.home, AppRoutes.testList, AppRoutes.intake],
    });

    await screen.findByText("資料の取込");
    fireEvent.click(screen.getByTestId(BACK_OR_HOME_BUTTON_TEST_ID));
    await screen.findByText("テスト一覧");
    expect(screen.queryByText("まだテストが登録されていません")).toBeNull();
  });
});
