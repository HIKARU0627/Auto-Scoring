import type { components } from "../api/generated/schema.js";

export type QuestionResponse = components["schemas"]["QuestionResponse"];

function tokenizeForNaturalSort(value: string): string[] {
  const tokens: string[] = [];
  let buffer = "";
  let previousWasDigit: boolean | undefined;
  for (const char of value) {
    const code = char.codePointAt(0) ?? 0;
    const isDigit = code >= 0x30 && code <= 0x39;
    if (previousWasDigit !== undefined && isDigit !== previousWasDigit) {
      tokens.push(buffer);
      buffer = "";
    }
    buffer += char;
    previousWasDigit = isDigit;
  }
  if (buffer.length > 0) {
    tokens.push(buffer);
  }
  return tokens;
}

export function compareQuestionNumbers(a: string, b: string): number {
  const tokensA = tokenizeForNaturalSort(a);
  const tokensB = tokenizeForNaturalSort(b);
  const sharedLength = Math.min(tokensA.length, tokensB.length);
  for (let i = 0; i < sharedLength; i += 1) {
    const tokenA = tokensA[i] ?? "";
    const tokenB = tokensB[i] ?? "";
    const numA = Number.parseInt(tokenA, 10);
    const numB = Number.parseInt(tokenB, 10);
    const aIsNum = !Number.isNaN(numA) && tokenA === String(numA);
    const bIsNum = !Number.isNaN(numB) && tokenB === String(numB);
    if (aIsNum && bIsNum) {
      const comparison = numA - numB;
      if (comparison !== 0) {
        return comparison;
      }
      continue;
    }
    if (aIsNum) {
      return -1;
    }
    if (bIsNum) {
      return 1;
    }
    const comparison = tokenA.localeCompare(tokenB);
    if (comparison !== 0) {
      return comparison;
    }
  }
  return tokensA.length - tokensB.length;
}

export function sortQuestionsForReview(
  questions: readonly QuestionResponse[],
): QuestionResponse[] {
  return [...questions].sort((a, b) => {
    const byPage = a.page - b.page;
    return byPage !== 0 ? byPage : compareQuestionNumbers(a.number, b.number);
  });
}
