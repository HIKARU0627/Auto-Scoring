import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";

import { submissionQueue } from "../../src/renderer/core/app-routes.js";
import {
  MATERIAL_SYMBOL_NAMES,
  MATERIAL_SYMBOL_PATHS,
} from "../../src/renderer/core/material-symbols.js";
import {
  submissionStatusVisualOf,
  type SubmissionStatusVisual,
} from "../../src/renderer/core/submission-status.js";
import { renderAppAt } from "./support/app-harness.js";
import { renderSubmissionConfirm } from "./support/submission-confirm-harness.js";
import { buildSubmission, buildTest } from "./support/mock-sidecar-client.js";

/**
 * Issue #397: `SubmissionStatusVisual.icon` was never drawn, and two of the
 * names it held (`check_circle_outline`, `verified_outlined`) were not in the
 * shipped Material Symbols table at all. The queue and confirm screens now
 * draw it as SVG, the way the Flutter original did.
 *
 * The checks below are mechanical on purpose: a state whose icon has no path,
 * a state that drifts back to a retired ligature name, or an icon rendered as
 * its name in text all turn this file red.
 */

/** The font class that used to leak ligature names as visible text. */
const LIGATURE_CLASS = "material-symbols-outlined";

const KNOWN_STATES = [
  null,
  undefined,
  "unprocessed",
  "ai_processing",
  "ai_processed",
  "needs_review",
  "reviewed",
  "exported",
  "error",
  "state_we_do_not_know_yet",
] as const;

const QUEUE_STATES = [
  "unprocessed",
  "ai_processing",
  "ai_processed",
  "needs_review",
  "reviewed",
  "exported",
  "error",
] as const;

function expectDrawableIcon(visual: SubmissionStatusVisual): void {
  expect(
    MATERIAL_SYMBOL_NAMES,
    `${visual.label} icon is not a MaterialSymbolName`,
  ).toContain(visual.icon);
  expect(
    MATERIAL_SYMBOL_PATHS[visual.icon].length,
    `${visual.label} (${visual.icon}) has no SVG path`,
  ).toBeGreaterThan(0);
}

function expectIconIsSvg(icon: Element, visual: SubmissionStatusVisual): void {
  expect(icon.tagName.toLowerCase()).toBe("svg");
  expect(icon.getAttribute("data-icon")).toBe(visual.icon);
  expect(icon.getAttribute("aria-label")).toBe(visual.label);
  expect(icon.textContent).toBe("");
  expect(
    icon.querySelector("path")?.getAttribute("d")?.length ?? 0,
  ).toBeGreaterThan(0);
}

function expectNoLigatureText(container: HTMLElement): void {
  expect(container.querySelectorAll(`.${LIGATURE_CLASS}`)).toHaveLength(0);
  const text = container.textContent ?? "";
  for (const name of MATERIAL_SYMBOL_NAMES) {
    expect(text.includes(name), `visible text leaked ${name}`).toBe(false);
  }
}

describe("submission status icons (Issue #397)", () => {
  it("maps every submission state to a current, drawable Material Symbol", () => {
    for (const state of KNOWN_STATES) {
      expectDrawableIcon(submissionStatusVisualOf(state));
    }
  });

  it("uses the current glyph names, not the retired ligatures", () => {
    expect(submissionStatusVisualOf("ai_processed").icon).toBe("check_circle");
    expect(submissionStatusVisualOf("reviewed").icon).toBe("verified");
    expect(MATERIAL_SYMBOL_NAMES as readonly string[]).not.toContain(
      "check_circle_outline",
    );
    expect(MATERIAL_SYMBOL_NAMES as readonly string[]).not.toContain(
      "verified_outlined",
    );
  });

  it("draws the queue state as SVG, never as the ligature name", async () => {
    const { container } = renderAppAt(submissionQueue("t1"), {
      handlers: {
        getTest: async () => buildTest({ id: "t1" }),
        listSubmissions: async () =>
          QUEUE_STATES.map((state, index) =>
            buildSubmission({
              id: `s-${state}`,
              testId: "t1",
              state,
              studentLabel: `答案${index}`,
              createdDay: index + 1,
            }),
          ),
      },
    });

    for (const state of QUEUE_STATES) {
      const visual = submissionStatusVisualOf(state);
      await screen.findByTestId(`queue-row-s-${state}`);
      expectIconIsSvg(
        screen.getByTestId(`queue-status-s-${state}-icon`),
        visual,
      );
      expect(
        screen.getByTestId(`queue-status-s-${state}`).textContent,
      ).toContain(visual.label);
    }

    expectNoLigatureText(container);
  });

  it("draws the confirm state chip as SVG, never as the ligature name", async () => {
    const visual = submissionStatusVisualOf("ai_processed");
    const { container } = renderSubmissionConfirm();

    const icon = await screen.findByTestId("confirm-submission-state-icon");
    expectIconIsSvg(icon, visual);
    expect(
      screen.getByTestId("confirm-submission-state").textContent,
    ).toContain(visual.label);

    expectNoLigatureText(container);
  });
});
