import { describe, expect, it } from "vitest";
import { fireEvent, screen, within } from "@testing-library/react";

import {
  UNASSIGNED_QUESTION_DISPLAY_LABEL,
  UNASSIGNED_QUESTION_LABEL,
} from "../../src/renderer/core/answer-area-constants.js";
import {
  buildRegion,
  dragOnElement,
  renderAnswerAreaEditor,
} from "./support/answer-area-harness.js";

describe("missing questions are split by cause (INV-170–176, INV-201-10)", () => {
  it("INV-170: undetected and absent groups are shown separately", () => {
    renderAnswerAreaEditor({
      regions: [],
      questionNumbers: ["問1", "問2"],
      undetected: ["問1"],
      absent: ["問2"],
    });

    expect(screen.getByTestId("answer-area-undetected-group")).toBeDefined();
    expect(screen.getByTestId("answer-area-absent-group")).toBeDefined();
    expect(screen.getByTestId("answer-area-undetected-問1")).toBeDefined();
    expect(screen.getByTestId("answer-area-absent-問2")).toBeDefined();
  });

  it("INV-171: only the group that applies is shown", () => {
    renderAnswerAreaEditor({
      regions: [],
      questionNumbers: ["問1", "問2"],
      absent: ["問1", "問2"],
    });

    expect(screen.queryByTestId("answer-area-undetected-group")).toBeNull();
    expect(screen.getByTestId("answer-area-absent-group")).toBeDefined();
  });

  it("INV-172: all-clear needs both groups empty", () => {
    renderAnswerAreaEditor({
      regions: [],
      questionNumbers: ["問1"],
      absent: ["問1"],
    });

    expect(screen.queryByTestId("answer-area-all-detected")).toBeNull();
  });

  it("INV-173: absent group says what was found, not what the paper has", () => {
    renderAnswerAreaEditor({
      regions: [],
      questionNumbers: ["問1"],
      absent: ["問1"],
    });

    const group = screen.getByTestId("answer-area-absent-group");
    const text =
      within(group).getByText(/見つけられなかった/).textContent ?? "";
    expect(text).toContain("見つけられなかった");
    expect(text).not.toContain("判定された");
    expect(text).not.toContain("回答欄が無い");
  });

  it("INV-174: no measured ratio is printed on the screen", () => {
    renderAnswerAreaEditor({
      regions: [],
      questionNumbers: ["問1", "問2"],
      undetected: ["問1"],
      absent: ["問2"],
    });

    const text = screen.getByTestId("answer-area-undetected").textContent ?? "";
    expect(/\d+\s*件中/.test(text)).toBe(false);
    expect(/\d+\s*%/.test(text)).toBe(false);
    expect(text).not.toContain("実測");
  });

  it("INV-175: the way out sits directly above the chips it applies to", () => {
    renderAnswerAreaEditor({
      regions: [],
      questionNumbers: ["問1"],
      absent: ["問1"],
    });

    const action = screen.getByTestId("answer-area-absent-action");
    const chip = screen.getByTestId("answer-area-absent-問1");
    expect(action.compareDocumentPosition(chip)).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );
    expect(action.textContent).toContain("枠を引いて");
  });

  it("INV-176: draw target defaults to absent question when nothing is undetected", () => {
    renderAnswerAreaEditor({
      regions: [],
      questionNumbers: ["問1", "問2"],
      absent: ["問2"],
    });

    const dropdown = screen.getByTestId(
      "answer-area-draw-target",
    ) as HTMLSelectElement;
    expect(dropdown.value).toBe("問2");
  });

  it("absent question chip sets draw target", () => {
    renderAnswerAreaEditor({
      regions: [],
      questionNumbers: ["問1"],
      absent: ["問1"],
    });

    fireEvent.click(screen.getByTestId("answer-area-absent-問1"));
    const dropdown = screen.getByTestId(
      "answer-area-draw-target",
    ) as HTMLSelectElement;
    expect(dropdown.value).toBe("問1");
  });
});

describe("reading order disagrees with question numbers (INV-177–178)", () => {
  const twoColumns = () => [
    buildRegion({
      regionId: "r-1",
      label: "問一",
      x0: 0.639,
      y0: 0.27,
      x1: 0.703,
      y1: 0.72,
    }),
    buildRegion({
      regionId: "r-2",
      label: "問二",
      x0: 0.798,
      y0: 0.27,
      x1: 0.843,
      y1: 0.671,
    }),
  ];

  it("INV-177: nothing is shown when the order agrees", () => {
    renderAnswerAreaEditor({
      regions: twoColumns(),
      questionNumbers: ["問一", "問二"],
    });

    expect(screen.queryByTestId("answer-area-reading-order")).toBeNull();
  });

  it("INV-178: suspicious pair is named with swap action", () => {
    renderAnswerAreaEditor({
      regions: twoColumns(),
      questionNumbers: ["問一", "問二"],
      conflicts: [["問一", "問二"]],
    });

    expect(screen.getByTestId("answer-area-reading-order")).toBeDefined();
    expect(screen.getByText("問一 と 問二")).toBeDefined();
    expect(screen.getByTestId("answer-area-all-detected")).toBeDefined();
  });

  it("swapping moves the questions, not the rectangles", () => {
    const view = renderAnswerAreaEditor({
      regions: twoColumns(),
      questionNumbers: ["問一", "問二"],
      conflicts: [["問一", "問二"]],
    });

    fireEvent.click(screen.getByTestId("answer-area-swap-問一-問二"));
    const after = view.getRegions();
    expect(after.map((region) => region.label)).toEqual(["問二", "問一"]);
    expect(after[0]?.bbox.x0).toBeCloseTo(0.639, 9);
    expect(after[1]?.bbox.x0).toBeCloseTo(0.798, 9);
  });
});

describe("showing what was and was not found", () => {
  it("lists every question detection did not find", () => {
    renderAnswerAreaEditor({
      regions: [buildRegion({ regionId: "a0" })],
      undetected: ["問2", "問3"],
    });

    expect(screen.getByTestId("answer-area-undetected")).toBeDefined();
    expect(screen.getByTestId("answer-area-undetected-問2")).toBeDefined();
    expect(screen.getByTestId("answer-area-undetected-問3")).toBeDefined();
  });

  it("says an undetected question can still be confirmed", () => {
    renderAnswerAreaEditor({
      regions: [buildRegion({ regionId: "a0" })],
      undetected: ["問2"],
    });
    expect(screen.getByText(/このまま確定もできますが/)).toBeDefined();
  });

  it("says so when every question has an area", () => {
    renderAnswerAreaEditor({
      regions: [
        buildRegion({ regionId: "a0" }),
        buildRegion({ regionId: "a1", label: "問2" }),
      ],
    });
    expect(screen.getByTestId("answer-area-all-detected")).toBeDefined();
  });

  it("says why nothing can be assigned before 配点 is confirmed", () => {
    renderAnswerAreaEditor({
      regions: [],
      questionNumbers: [],
    });
    expect(screen.getByTestId("answer-area-no-questions")).toBeDefined();
  });

  it("claims nothing about how accurate detection was", () => {
    renderAnswerAreaEditor({
      regions: [buildRegion({ regionId: "a0" })],
      undetected: ["問2"],
    });
    for (const claim of ["精度", "正確", "自動で完了", "すべて検出"]) {
      expect(screen.queryByText(new RegExp(claim))).toBeNull();
    }
  });
});

describe("editing", () => {
  it("assigning a question is a choice, not a text field", () => {
    const view = renderAnswerAreaEditor({
      regions: [
        buildRegion({
          regionId: "a0",
          label: UNASSIGNED_QUESTION_LABEL,
        }),
      ],
    });

    fireEvent.change(screen.getByTestId("answer-area-question-0"), {
      target: { value: "問2" },
    });
    expect(view.getRegions()[0]?.label).toBe("問2");
  });

  it("deleting removes the box", () => {
    const view = renderAnswerAreaEditor({
      regions: [
        buildRegion({ regionId: "a0" }),
        buildRegion({ regionId: "a1", label: "問2" }),
      ],
    });

    fireEvent.click(screen.getByTestId("answer-area-delete-0"));
    expect(view.getRegions().map((region) => region.region_id)).toEqual(["a1"]);
  });

  it("dragging on an empty page draws a new answer area", async () => {
    const view = renderAnswerAreaEditor({
      regions: [],
      undetected: ["問1", "問2"],
    });

    const surface = screen.getByTestId("answer-area-draw-surface-0");
    await dragOnElement(surface, { x: 120, y: 170 }, { x: 240, y: 255 });

    expect(view.getRegions()).toHaveLength(1);
    const drawn = view.getRegions()[0];
    expect(drawn).toBeDefined();
    expect(drawn?.kind).toBe("answer_area");
    expect(drawn?.bbox.x0).toBeCloseTo(0.2, 0.02);
    expect(drawn?.bbox.y1).toBeCloseTo(0.5, 0.02);
  });

  it("a drawn box goes to the first question still missing one", async () => {
    const view = renderAnswerAreaEditor({
      regions: [buildRegion({ regionId: "a0" })],
      undetected: ["問2"],
    });

    const surface = screen.getByTestId("answer-area-draw-surface-0");
    await dragOnElement(surface, { x: 390, y: 550 }, { x: 120, y: 85 });

    expect(view.getRegions()).toHaveLength(2);
    expect(view.getRegions().at(-1)?.label).toBe("問2");
  });

  it("a drawn box is unassigned when nothing is missing one", async () => {
    const view = renderAnswerAreaEditor({
      regions: [
        buildRegion({ regionId: "a0" }),
        buildRegion({ regionId: "a1", label: "問2" }),
      ],
    });

    const surface = screen.getByTestId("answer-area-draw-surface-0");
    await dragOnElement(surface, { x: 390, y: 550 }, { x: 120, y: 85 });

    expect(view.getRegions()).toHaveLength(3);
    expect(view.getRegions().at(-1)?.label).toBe(UNASSIGNED_QUESTION_LABEL);
  });

  it("unassigned label is shown as display text, never the sentinel", () => {
    renderAnswerAreaEditor({
      regions: [
        buildRegion({
          regionId: "a0",
          label: UNASSIGNED_QUESTION_LABEL,
        }),
      ],
    });

    expect(
      screen.getAllByText(UNASSIGNED_QUESTION_DISPLAY_LABEL).length,
    ).toBeGreaterThan(0);
    expect(screen.queryByText(UNASSIGNED_QUESTION_LABEL)).toBeNull();
  });

  it("a confirmed profile offers no swap", () => {
    renderAnswerAreaEditor({
      regions: [
        buildRegion({
          regionId: "r-1",
          label: "問一",
          x0: 0.639,
          y0: 0.27,
          x1: 0.703,
          y1: 0.72,
        }),
        buildRegion({
          regionId: "r-2",
          label: "問二",
          x0: 0.798,
          y0: 0.27,
          x1: 0.843,
          y1: 0.671,
        }),
      ],
      questionNumbers: ["問一", "問二"],
      conflicts: [["問一", "問二"]],
      readOnly: true,
    });

    const button = screen.getByTestId("answer-area-swap-問一-問二");
    expect((button as HTMLButtonElement).disabled).toBe(true);
  });
});
