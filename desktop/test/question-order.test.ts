import { describe, expect, it } from "vitest";

import {
  compareQuestionNumbers,
  sortQuestionsForReview,
} from "../src/renderer/core/question-order.js";
import type { components } from "../src/renderer/api/generated/schema.js";

type QuestionResponse = components["schemas"]["QuestionResponse"];

function question(number: string, page = 1): QuestionResponse {
  return {
    id: `q-${number}-p${page}`,
    test_id: "test-1",
    number,
    page,
    points: 5,
    scoring_method: "additive",
    rubric: [],
  };
}

describe("question order (INV-151)", () => {
  it("INV-151: question numbers sort naturally", () => {
    const numbers = ["10", "2", "1", "3"].sort(compareQuestionNumbers);
    expect(numbers).toEqual(["1", "2", "3", "10"]);
  });

  it("mixed digit and letter labels stay transitive", () => {
    expect(compareQuestionNumbers("2", "10")).toBeLessThan(0);
    expect(compareQuestionNumbers("10", "1a")).toBeGreaterThan(0);
    expect(compareQuestionNumbers("1a", "2")).toBeLessThan(0);
    const forwards = ["2", "10", "1a"].sort(compareQuestionNumbers);
    const backwards = ["1a", "10", "2"].sort(compareQuestionNumbers);
    expect(forwards).toEqual(backwards);
  });

  it("page first, then question number within page", () => {
    const sorted = sortQuestionsForReview([
      question("2", 2),
      question("10", 1),
      question("1", 2),
      question("2", 1),
    ]);
    expect(sorted.map((q) => `${q.page}-${q.number}`)).toEqual([
      "1-2",
      "1-10",
      "2-1",
      "2-2",
    ]);
  });

  it("does not mutate the input list", () => {
    const original = [question("2"), question("1")];
    sortQuestionsForReview(original);
    expect(original.map((q) => q.number)).toEqual(["2", "1"]);
  });
});
