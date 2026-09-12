import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";

import { AppRoutes } from "../../src/renderer/core/app-routes.js";
import { secondaryButtonClass } from "../../src/renderer/features/ui/screen-ui.js";
import {
  BACK_OR_HOME_BUTTON_TEST_ID,
  BackOrHomeButton,
} from "../../src/renderer/navigation/BackOrHomeButton.js";
import { RouterProvider } from "../../src/renderer/navigation/router.js";

/**
 * Issue #447: the escape control drew the raw characters `←` / `⌂`.
 *
 * This app ships no icon font and the CSP (`default-src 'none'`) blocks loading
 * one (Issue #392), so those characters took their weight, size, and baseline
 * from whatever font happened to fall through -- different per machine, and
 * visibly off next to the secondary controls. The tests below pin the fix:
 * a bundled `lucide-react` SVG instead of text, the shared secondary button
 * treatment, and the state carried by the accessible name, not by the glyph.
 */

/** Covered route with nothing under it: the control has to fall back to home. */
const EMPTY_STACK_COVERED = [AppRoutes.intake];
/** A pushed stack: the control pops one frame. */
const PUSHED_STACK = [AppRoutes.home, AppRoutes.intake];

/** The two raw glyphs the old implementation rendered as text. */
const RAW_GLYPHS = ["\u2190", "\u2302"];

function renderButton(stack: readonly string[]): HTMLElement {
  const { container } = render(
    <RouterProvider initialStack={stack}>
      <BackOrHomeButton />
    </RouterProvider>,
  );
  const button = container.querySelector<HTMLElement>(
    `[data-testid="${BACK_OR_HOME_BUTTON_TEST_ID}"]`,
  );
  if (button === null) {
    throw new Error("the escape control did not render");
  }
  return button;
}

function iconClass(button: HTMLElement): string {
  return button.querySelector("svg")?.getAttribute("class") ?? "";
}

describe("back or home control (Issue #447)", () => {
  it("draws the escape control with a lucide SVG, never a raw glyph", () => {
    for (const stack of [EMPTY_STACK_COVERED, PUSHED_STACK]) {
      const button = renderButton(stack);

      for (const glyph of RAW_GLYPHS) {
        expect(
          button.textContent,
          `the escaped glyph ${glyph} is visible text again`,
        ).not.toContain(glyph);
      }
      expect(button.textContent).toBe("");

      const icon = button.querySelector("svg");
      expect(icon).not.toBeNull();
      expect(icon?.getAttribute("class")).toContain("lucide");
      expect(icon?.getAttribute("aria-hidden")).toBe("true");
      expect(
        icon?.querySelector("path")?.getAttribute("d")?.length ?? 0,
      ).toBeGreaterThan(0);
    }
  });

  it("shows the back arrow when the stack can pop", () => {
    const button = renderButton(PUSHED_STACK);
    expect(iconClass(button)).toContain("lucide-arrow-left");
    expect(button.querySelector(".lucide-home")).toBeNull();
    expect(button.getAttribute("aria-label")).toBe("前の画面へ戻る");
    expect(button.getAttribute("title")).toBe("前の画面へ戻る");
  });

  it("falls back to the home icon on an empty-stack covered route", () => {
    const button = renderButton(EMPTY_STACK_COVERED);
    // lucide-react exports `Home` as an alias of the `house` glyph, so the
    // class is `lucide-house` even though the import reads `Home`.
    expect(iconClass(button)).toContain("lucide-house");
    expect(button.querySelector(".lucide-arrow-left")).toBeNull();
    expect(button.getAttribute("aria-label")).toBe("ホームへ戻る");
    expect(button.getAttribute("title")).toBe("ホームへ戻る");
  });

  it("borrows the shared secondary button treatment", () => {
    const button = renderButton(PUSHED_STACK);
    expect(button.className).toBe(secondaryButtonClass());

    const classes = button.className.split(/\s+/);
    for (const token of [
      "rounded-md",
      "bg-surface-container-high",
      "transition-colors",
      "hover:bg-surface-container-highest",
      "active:bg-surface-container-highest",
      "focus-visible:outline-2",
      "focus-visible:outline-offset-2",
      "focus-visible:outline-primary",
      "disabled:cursor-not-allowed",
      "disabled:bg-disabled-button-container",
      "disabled:text-disabled-button-label",
    ]) {
      expect(classes, `missing ${token}`).toContain(token);
    }
    expect(classes).not.toContain("border-outline");
  });
});
