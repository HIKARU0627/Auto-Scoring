import { describe, expect, it } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import { AppRoutes } from "../../src/renderer/core/app-routes.js";
import {
  SIDEBAR_PRODUCT_DESCRIPTION,
  SIDEBAR_PRODUCT_NAME,
  SIDEBAR_TEST_ID,
  SIDEBAR_NAV_TEST_ID,
} from "../../src/renderer/navigation/Sidebar.js";
import { BACK_OR_HOME_BUTTON_TEST_ID } from "../../src/renderer/navigation/BackOrHomeButton.js";
import { renderAppAt } from "./support/app-harness.js";
import { buildTest } from "./support/mock-sidecar-client.js";

/**
 * Issue #335 regression guard for the persistent sidebar (parent #333).
 *
 * The four destinations are pinned as literal data rather than imported from
 * `SIDEBAR_NAV_ITEMS`, so deleting an item in the source turns this red instead
 * of shrinking the expectation with it.
 */
const EXPECTED_NAV = [
  { route: AppRoutes.home, label: "ホーム", testId: "sidebar-nav-home" },
  {
    route: AppRoutes.intake,
    label: "資料の取込",
    testId: "sidebar-nav-intake",
  },
  {
    route: AppRoutes.testList,
    label: "テスト一覧",
    testId: "sidebar-nav-tests",
  },
  { route: AppRoutes.settings, label: "設定", testId: "sidebar-nav-settings" },
] as const;

const defaultHandlers = {
  listTestRegistrations: async () => [
    buildTest({ id: "test-1", status: "draft" }),
  ],
  listSubmissions: async () => [],
};

async function expectPageTitle(text: string): Promise<void> {
  await waitFor(() => {
    expect(screen.getByTestId("page-title").textContent).toBe(text);
  });
}

describe("app sidebar (Issue #335)", () => {
  it("shows the product identity and all four destinations", async () => {
    renderAppAt(AppRoutes.home, { handlers: defaultHandlers });
    await screen.findByTestId("home-next-up");

    const sidebar = screen.getByTestId(SIDEBAR_TEST_ID);
    expect(sidebar).toBeDefined();
    expect(within(sidebar).getByText(SIDEBAR_PRODUCT_NAME)).toBeDefined();
    expect(
      within(sidebar).getByText(SIDEBAR_PRODUCT_DESCRIPTION),
    ).toBeDefined();

    const nav = screen.getByTestId(SIDEBAR_NAV_TEST_ID);
    const buttons = within(nav).getAllByRole("button");
    expect(buttons.map((button) => button.getAttribute("data-testid"))).toEqual(
      EXPECTED_NAV.map((item) => item.testId),
    );
    for (const item of EXPECTED_NAV) {
      expect(screen.getByTestId(item.testId).textContent).toContain(item.label);
    }
  });

  it("marks the current destination with aria-current and the primary fill", async () => {
    renderAppAt(AppRoutes.intake, { handlers: defaultHandlers });
    await screen.findByTestId("page-title");

    const current = screen.getByTestId("sidebar-nav-intake");
    expect(current.getAttribute("aria-current")).toBe("page");
    expect(current.className).toContain("bg-primary");
    expect(current.className).toContain("rounded-lg");

    for (const item of EXPECTED_NAV) {
      if (item.route === AppRoutes.intake) {
        continue;
      }
      expect(screen.getByTestId(item.testId).getAttribute("aria-current")).toBe(
        null,
      );
    }
  });

  it("keeps the test list lit for nested test routes", async () => {
    renderAppAt("/tests/test-1/settings", { handlers: defaultHandlers });
    await screen.findByTestId("page-title");

    expect(
      screen.getByTestId("sidebar-nav-tests").getAttribute("aria-current"),
    ).toBe("page");
    expect(
      screen.getByTestId("sidebar-nav-home").getAttribute("aria-current"),
    ).toBeNull();
  });

  it("pushes rather than discarding the stack, so Back returns to the origin", async () => {
    renderAppAt(AppRoutes.testList, { handlers: defaultHandlers });
    await expectPageTitle("テスト一覧");

    fireEvent.click(screen.getByTestId("sidebar-nav-intake"));
    await expectPageTitle("資料の取込");

    // A nav that replaced or reset the stack would leave no frame to pop, so
    // the escape control would fall back to home instead of the test list.
    fireEvent.click(screen.getByTestId(BACK_OR_HOME_BUTTON_TEST_ID));
    await expectPageTitle("テスト一覧");
  });

  it("exposes every destination to the keyboard in visual order with a visible focus style", async () => {
    renderAppAt(AppRoutes.home, { handlers: defaultHandlers });
    await screen.findByTestId("home-next-up");

    const nav = screen.getByTestId(SIDEBAR_NAV_TEST_ID);
    const buttons = within(nav).getAllByRole("button");
    expect(buttons).toHaveLength(EXPECTED_NAV.length);
    for (const button of buttons) {
      expect(button.tabIndex).toBeGreaterThanOrEqual(0);
      // `outline: none` with no replacement is the failure this guards against.
      expect(button.className).toContain("focus-visible:outline");
    }
  });
});

/**
 * Issue #348 (parent #333): the mock draws a floating, rounded panel at
 * ~208px, not a 240px full-bleed column. These assertions pin the class-level
 * contract -- the pixel values themselves cannot be measured in jsdom, so the
 * PR records the screenshots -- and each one is mutation-checked.
 */
describe("sidebar mock polish (Issue #348)", () => {
  it("floats as a rounded, inset panel instead of a full-bleed column", async () => {
    renderAppAt(AppRoutes.home, { handlers: defaultHandlers });
    await screen.findByTestId("home-next-up");

    const sidebar = screen.getByTestId(SIDEBAR_TEST_ID);
    // Mock: rounded panel, left edge x~24, width ~208px (w-52 = 13rem).
    expect(sidebar.classList.contains("rounded-xl")).toBe(true);
    expect(sidebar.classList.contains("w-52")).toBe(true);
    expect(sidebar.classList.contains("w-60")).toBe(false);

    // The inset is the shell's p-xl on all sides; the panel must not be
    // `top-0 h-screen` (which is exactly the old full-bleed shape).
    expect(sidebar.classList.contains("top-0")).toBe(false);
    expect(sidebar.classList.contains("h-screen")).toBe(false);
    const frame = sidebar.parentElement;
    expect(frame?.classList.contains("p-xl")).toBe(true);
    expect(frame?.classList.contains("gap-xl")).toBe(true);
  });

  it("gives the nav rows the mock's taller rhythm and pill inset", async () => {
    renderAppAt(AppRoutes.home, { handlers: defaultHandlers });
    await screen.findByTestId("home-next-up");

    const nav = screen.getByTestId(SIDEBAR_NAV_TEST_ID);
    // Mock: active pill ~185px wide inside a ~208px panel, so the nav holds a
    // horizontal inset and the pill is not full-bleed.
    expect(nav.classList.contains("px-md")).toBe(true);
    expect(nav.querySelector("ul")?.classList.contains("gap-md")).toBe(true);

    for (const button of within(nav).getAllByRole("button")) {
      // Mock: row height ~45px (~48px here), icon-to-label gap ~16px.
      expect(button.classList.contains("min-h-12")).toBe(true);
      expect(button.classList.contains("gap-lg")).toBe(true);
      expect(button.classList.contains("gap-xs")).toBe(false);
    }
  });

  it("draws solid icons, not the mock-mismatched line drawings", async () => {
    renderAppAt(AppRoutes.home, { handlers: defaultHandlers });
    await screen.findByTestId("home-next-up");

    const nav = screen.getByTestId(SIDEBAR_NAV_TEST_ID);
    const icons = Array.from(nav.querySelectorAll("svg"));
    expect(icons).toHaveLength(EXPECTED_NAV.length);
    for (const icon of icons) {
      expect(icon.getAttribute("fill")).toBe("currentColor");
      expect(icon.getAttribute("stroke")).toBeNull();
    }
  });
});
