import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import {
  QuestionStatus,
  type QuestionStatusKey,
} from "../../src/renderer/core/question-status.js";
import { QuestionStatusBadge } from "../../src/renderer/core/QuestionStatusBadge.js";

/**
 * INV-097: every question status carries a distinct Japanese label **and** a
 * distinct icon, so colour is never the only thing telling two states apart.
 *
 * The state set is derived from `QuestionStatus`, not written out here: adding
 * a state there puts it on this loop automatically, so a new state shipped
 * without a label or icon turns this red instead of being missed.
 */
const STATUS_KEYS = Object.keys(QuestionStatus) as QuestionStatusKey[];

describe("QuestionStatusBadge (INV-097)", () => {
  it("derives the state set from the code (guard against an empty loop)", () => {
    expect(STATUS_KEYS.length).toBeGreaterThan(0);
  });

  it("gives every state its own label and its own icon, not just a colour", () => {
    const labels = new Set<string>();
    const icons = new Set<string>();

    for (const status of STATUS_KEYS) {
      const testId = `status-${status}`;
      const { unmount } = render(
        <QuestionStatusBadge status={status} testId={testId} />,
      );

      const label = screen.getByTestId(`${testId}-label`).textContent ?? "";
      const iconElement = screen.getByTestId(`${testId}-icon`);
      const icon = iconElement.getAttribute("data-icon") ?? "";

      expect(label.length, `${status} has no label`).toBeGreaterThan(0);
      expect(icon.length, `${status} has no icon`).toBeGreaterThan(0);
      // Issue #392: the icon is an inline SVG, not the ligature name rendered
      // as text by a font that was never shipped.
      expect(iconElement.tagName.toLowerCase(), `${status} icon`).toBe("svg");
      expect(iconElement.textContent, `${status} icon text`).toBe("");
      expect(labels.has(label), `${status} reuses the label ${label}`).toBe(
        false,
      );
      expect(icons.has(icon), `${status} reuses the icon ${icon}`).toBe(false);

      labels.add(label);
      icons.add(icon);
      unmount();
    }

    expect(labels.size).toBe(STATUS_KEYS.length);
    expect(icons.size).toBe(STATUS_KEYS.length);
  });
});
