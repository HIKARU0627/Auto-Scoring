import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { AppErrorBanner } from "../../src/renderer/core/AppErrorBanner.js";
import { GradingUnavailableBanner } from "../../src/renderer/core/GradingUnavailableBanner.js";
import { MaterialSymbolIcon } from "../../src/renderer/core/MaterialSymbolIcon.js";
import {
  MATERIAL_SYMBOL_NAMES,
  MATERIAL_SYMBOL_PATHS,
} from "../../src/renderer/core/material-symbols.js";
import { QuestionStatusBadge } from "../../src/renderer/core/QuestionStatusBadge.js";
import {
  QuestionStatus,
  type QuestionStatusKey,
} from "../../src/renderer/core/question-status.js";
import { SidecarStartupOverlay } from "../../src/renderer/features/startup/SidecarStartupOverlay.js";

/**
 * Issue #392: the four `material-symbols-outlined` usages rendered the ligature
 * name ("check_circle") as plain text because no font was shipped and the CSP
 * forbids loading one. The fix inlines the glyph as SVG, so the mechanical
 * checks here are the point of the file:
 *
 *   1. every icon is an `<svg>` drawing a non-empty path, not a text node;
 *   2. no rendered component has the `material-symbols-outlined` class or any
 *      icon name in its visible text;
 *   3. every icon still carries an accessible name.
 */

/** The class that used to render ligature names as text without a font. */
const LIGATURE_CLASS = "material-symbols-outlined";

function expectIconsAreSvgWithNoLigatureText(container: HTMLElement): void {
  const icons = container.querySelectorAll("svg[data-icon]");
  expect(icons.length).toBeGreaterThan(0);
  for (const icon of icons) {
    expect(icon.tagName.toLowerCase()).toBe("svg");
    expect(icon.textContent).toBe("");
    expect(
      icon.querySelector("path")?.getAttribute("d")?.length ?? 0,
    ).toBeGreaterThan(0);
    expect(icon.getAttribute("aria-label")?.trim().length ?? 0).toBeGreaterThan(
      0,
    );
  }
  expect(container.querySelectorAll(`.${LIGATURE_CLASS}`)).toHaveLength(0);
  const text = container.textContent ?? "";
  for (const name of MATERIAL_SYMBOL_NAMES) {
    expect(
      text.includes(name),
      `visible text leaked the icon name ${name}`,
    ).toBe(false);
  }
}

describe("MaterialSymbolIcon (Issue #392)", () => {
  it("draws a non-empty path for every declared icon name", () => {
    for (const name of MATERIAL_SYMBOL_NAMES) {
      const { container, unmount } = render(
        <MaterialSymbolIcon name={name} label={`icon ${name}`} />,
      );
      const path = container.querySelector("path");
      expect(path?.getAttribute("d")?.length ?? 0).toBeGreaterThan(0);
      expect(MATERIAL_SYMBOL_PATHS[name].length).toBeGreaterThan(0);
      unmount();
    }
  });

  it("never renders a ligature name as visible text in any of the four usages", () => {
    const statuses = Object.keys(QuestionStatus) as QuestionStatusKey[];

    for (const status of statuses) {
      const { container, unmount } = render(
        <QuestionStatusBadge status={status} testId={`badge-${status}`} />,
      );
      expectIconsAreSvgWithNoLigatureText(container);
      unmount();
    }

    const banner = render(
      <AppErrorBanner message="読み込みに失敗しました。" />,
    );
    expectIconsAreSvgWithNoLigatureText(banner.container);
    banner.unmount();

    const grading = render(
      <GradingUnavailableBanner availability={{ available: false }}>
        <div>画面の中身</div>
      </GradingUnavailableBanner>,
    );
    expectIconsAreSvgWithNoLigatureText(grading.container);
    grading.unmount();

    const startup = render(
      <SidecarStartupOverlay
        status={{
          kind: "failed",
          failure: "executableMissing",
          exitCode: null,
        }}
        onRestart={() => undefined}
      >
        <div>画面の中身</div>
      </SidecarStartupOverlay>,
    );
    expectIconsAreSvgWithNoLigatureText(startup.container);
    startup.unmount();
  });

  it("names every icon for assistive technology", () => {
    render(<QuestionStatusBadge status="approved" testId="approved" />);
    expect(screen.getByTestId("approved-icon").getAttribute("aria-label")).toBe(
      QuestionStatus.approved.label,
    );
  });
});
