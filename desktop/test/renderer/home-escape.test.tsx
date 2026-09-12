import { describe, expect, it } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";

import {
  AppRoutes,
  declaredRoutePatterns,
} from "../../src/renderer/core/app-routes.js";
import { BACK_OR_HOME_BUTTON_TEST_ID } from "../../src/renderer/navigation/BackOrHomeButton.js";
import { ROUTE_TABLE } from "../../src/renderer/navigation/route-table.js";
import { renderAppAt } from "./support/app-harness.js";
import { buildTest } from "./support/mock-sidecar-client.js";

const skipped: Record<string, string> = {
  [AppRoutes.starting]:
    "Not a screen: startup overlay placeholder while the sidecar is unusable.",
};

const covered = new Set<string>([
  AppRoutes.intake,
  AppRoutes.settings,
  AppRoutes.testList,
  AppRoutes.testSettingsPattern,
  AppRoutes.submissionQueuePattern,
  AppRoutes.submissionConfirmPattern,
  AppRoutes.pdfReviewPattern,
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

const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

/**
 * The elements a browser would move through when Tab is pressed, in document
 * order. jsdom does not implement sequential focus navigation, so the tests
 * below walk this list to stand in for pressing Tab.
 */
function sequentialFocusOrder(root: ParentNode): HTMLElement[] {
  return Array.from(
    root.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
  ).filter((element) => element.tabIndex >= 0);
}

/**
 * Waits for the routed page heading to be `text`. The sidebar (Issue #335)
 * repeats the destination labels, so the assertion targets the page heading
 * (`data-testid="page-title"`) instead of the first text match.
 */
async function expectPageTitle(text: string): Promise<void> {
  await waitFor(() => {
    expect(screen.getByTestId("page-title").textContent).toBe(text);
  });
}

/** Pins the viewport to the 700x720 narrow window from INV-016. */
function withNarrowViewport(): () => void {
  const width = Object.getOwnPropertyDescriptor(window, "innerWidth");
  const height = Object.getOwnPropertyDescriptor(window, "innerHeight");

  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    value: 700,
  });
  Object.defineProperty(window, "innerHeight", {
    configurable: true,
    value: 720,
  });
  window.dispatchEvent(new Event("resize"));

  return () => {
    if (width !== undefined) {
      Object.defineProperty(window, "innerWidth", width);
    }
    if (height !== undefined) {
      Object.defineProperty(window, "innerHeight", height);
    }
    window.dispatchEvent(new Event("resize"));
  };
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

  it("INV-020: every skipped route carries a non-empty reason", () => {
    for (const [route, reason] of Object.entries(skipped)) {
      expect(reason.trim().length, `${route} の除外理由が空`).toBeGreaterThan(
        0,
      );
    }
  });

  it("INV-020: a route is covered or skipped, never both", () => {
    const both = [...covered].filter((route) => route in skipped);
    expect(both).toEqual([]);
  });

  it("INV-020: the declared route patterns and the route table agree", () => {
    const declared = [...declaredRoutePatterns].sort();
    const table = ROUTE_TABLE.map((route) => route.pattern).sort();
    expect(declared).toEqual(table);
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

    it(`${location}: escape is clickable at 700x720 (INV-016)`, async () => {
      const restore = withNarrowViewport();
      try {
        renderAppAt(location, { handlers: defaultHandlers });
        const escape = await screen.findByTestId(BACK_OR_HOME_BUTTON_TEST_ID);

        fireEvent.click(escape);
        await screen.findByTestId("home-next-up");
      } finally {
        restore();
      }
    });

    it(`${location}: Tab then Enter alone reaches home (INV-017)`, async () => {
      renderAppAt(location, { handlers: defaultHandlers });
      const escape = await screen.findByTestId(BACK_OR_HOME_BUTTON_TEST_ID);

      // The escape control must sit in the sequential focus order, and be
      // reachable without a pointer.
      const order = sequentialFocusOrder(document.body);
      expect(order).toContain(escape);

      let reached = false;
      for (const element of order) {
        element.focus();
        if (element === escape) {
          reached = true;
          break;
        }
      }
      expect(reached).toBe(true);
      expect(document.activeElement).toBe(escape);

      // Chromium turns Enter on a focused <button> into a click; jsdom stops
      // short of that mapping, so press the key and then dispatch the click it
      // stands for.
      fireEvent.keyDown(escape, { key: "Enter", keyCode: 13 });
      fireEvent.keyUp(escape, { key: "Enter", keyCode: 13 });
      fireEvent.click(escape);

      await screen.findByTestId("home-next-up");
    });

    it(`${location}: escape pops one frame on a stacked history (INV-019)`, async () => {
      renderAppAt(location, {
        handlers: defaultHandlers,
        initialStack: [AppRoutes.home, AppRoutes.testList, location],
      });

      fireEvent.click(await screen.findByTestId(BACK_OR_HOME_BUTTON_TEST_ID));
      await expectPageTitle("テスト一覧");
      // Wait for the test-list rows: the home empty state is also loaded
      // asynchronously, so checking its absence synchronously ran before either
      // page had loaded and could not show where the escape actually landed.
      await screen.findByTestId("test-list-row-test-1");
      expect(screen.queryByText("まだテストが登録されていません")).toBeNull();
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

    await expectPageTitle("資料の取込");
    fireEvent.click(screen.getByTestId(BACK_OR_HOME_BUTTON_TEST_ID));
    await expectPageTitle("テスト一覧");
    // Same as the stacked-history case above: await the loaded rows before
    // proving the home empty state is absent.
    await screen.findByTestId("test-list-row-test-1");
    expect(screen.queryByText("まだテストが登録されていません")).toBeNull();
  });
});
