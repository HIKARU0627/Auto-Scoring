import { describe, expect, it } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import type { QuestionResponse } from "../../src/renderer/api/test-registration-data.js";
import { ScoringTargetsCard } from "../../src/renderer/features/test-settings/ScoringTargetsCard.js";

function question(number: string, isTarget: boolean): QuestionResponse {
  return {
    id: `q-${number}`,
    test_id: "test-1",
    number,
    page: 1,
    points: 5,
    scoring_method: "additive",
    rubric: [],
    is_scoring_target: isTarget,
  };
}

describe("ScoringTargetsCard (Issue #449)", () => {
  it("既定はサーバーの選択どおりで、外した結果が保存に渡る", async () => {
    const saved: string[][] = [];
    render(
      <ScoringTargetsCard
        questions={[question("問1", true), question("問2", true)]}
        edges={[]}
        busy={false}
        onSave={async (ids) => {
          saved.push([...ids]);
        }}
      />,
    );

    const first = screen.getByTestId("scoring-target-問1") as HTMLInputElement;
    expect(first.checked).toBe(true);
    fireEvent.click(first);
    expect(first.checked).toBe(false);

    fireEvent.click(screen.getByTestId("save-scoring-targets-button"));
    await waitFor(() => {
      expect(saved).toEqual([["q-問2"]]);
    });
  });

  it("全部外すと保存できず、理由を画面に出す", () => {
    render(
      <ScoringTargetsCard
        questions={[question("問1", true)]}
        edges={[]}
        busy={false}
        onSave={async () => {}}
      />,
    );

    fireEvent.click(screen.getByTestId("scoring-target-問1"));

    const save = screen.getByTestId(
      "save-scoring-targets-button",
    ) as HTMLButtonElement;
    expect(save.disabled).toBe(true);
    expect(
      screen.getByTestId("disabled-reason-scoring-targets-empty").textContent,
    ).toContain("1つも選ばれていません");
  });

  it("前提を採点対象外にすると、依存先の設問名を知らせる", () => {
    render(
      <ScoringTargetsCard
        questions={[question("問1", true), question("問2", true)]}
        edges={[
          {
            from_question_id: "q-問1",
            to_question_id: "q-問2",
            provides: ["score"],
            rationale: "問2は問1の結果を使う",
            confidence: null,
          },
        ]}
        busy={false}
        onSave={async () => {}}
      />,
    );

    expect(
      screen.queryByTestId(
        "disabled-reason-scoring-target-prerequisite-excluded",
      ),
    ).toBeNull();
    fireEvent.click(screen.getByTestId("scoring-target-問1"));
    const notice = screen.getByTestId(
      "disabled-reason-scoring-target-prerequisite-excluded",
    );
    expect(notice.textContent).toContain("問2");
  });
});
