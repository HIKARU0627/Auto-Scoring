/**
 * Whether one submission may be confirmed in a single action (Issue #145 / INV-005).
 *
 * Confidence is intentionally not an input — §25.2 / Issue #136.
 */

export interface QuestionConfirmation {
  readonly questionId: string;
  readonly number: string;
  readonly materialLoaded: boolean;
  readonly isConfirmed: boolean;
  readonly aiGradeId: string | null;
  readonly expectedVersion: number;
  readonly isReached: boolean;
}

export function questionNeedsApproval(question: QuestionConfirmation): boolean {
  return (
    question.materialLoaded &&
    !question.isConfirmed &&
    question.aiGradeId != null
  );
}

export function questionNeedsHumanScore(
  question: QuestionConfirmation,
): boolean {
  return (
    question.materialLoaded &&
    !question.isConfirmed &&
    question.aiGradeId == null
  );
}

export function questionIsUnreached(question: QuestionConfirmation): boolean {
  return questionNeedsApproval(question) && !question.isReached;
}

export const SubmissionConfirmBlock = {
  noQuestions: "noQuestions",
  materialUnavailable: "materialUnavailable",
  humanScoreRequired: "humanScoreRequired",
  unreached: "unreached",
  nothingToConfirm: "nothingToConfirm",
} as const;

export type SubmissionConfirmBlock =
  (typeof SubmissionConfirmBlock)[keyof typeof SubmissionConfirmBlock];

export class SubmissionConfirmation {
  constructor(public readonly questions: readonly QuestionConfirmation[]) {}

  get unloaded(): QuestionConfirmation[] {
    return this.questions.filter((q) => !q.materialLoaded);
  }

  get pending(): QuestionConfirmation[] {
    return this.questions.filter((q) => questionNeedsApproval(q));
  }

  get unreached(): QuestionConfirmation[] {
    return this.questions.filter((q) => questionIsUnreached(q));
  }

  get needingHumanScore(): QuestionConfirmation[] {
    return this.questions.filter((q) => questionNeedsHumanScore(q));
  }

  get confirmedCount(): number {
    return this.questions.filter((q) => q.isConfirmed).length;
  }

  get total(): number {
    return this.questions.length;
  }

  get isFullyConfirmed(): boolean {
    return (
      this.questions.length > 0 &&
      this.questions.every((question) => question.isConfirmed)
    );
  }

  get blocker(): SubmissionConfirmBlock | null {
    if (this.questions.length === 0) {
      return SubmissionConfirmBlock.noQuestions;
    }
    if (this.unloaded.length > 0) {
      return SubmissionConfirmBlock.materialUnavailable;
    }
    if (this.needingHumanScore.length > 0) {
      return SubmissionConfirmBlock.humanScoreRequired;
    }
    if (this.unreached.length > 0) {
      return SubmissionConfirmBlock.unreached;
    }
    if (this.pending.length === 0) {
      return SubmissionConfirmBlock.nothingToConfirm;
    }
    return null;
  }

  get canConfirm(): boolean {
    return this.blocker === null;
  }
}

export function createSubmissionConfirmation(
  questions: readonly QuestionConfirmation[],
): SubmissionConfirmation {
  return new SubmissionConfirmation(questions);
}

export interface SubmissionConfirmationOutcome {
  readonly confirmed: readonly string[];
  readonly remaining: readonly string[];
  readonly failedNumber: string | null;
  readonly message: string | null;
}

export async function runSubmissionConfirmation(params: {
  readonly questions: readonly QuestionConfirmation[];
  readonly approve: (question: QuestionConfirmation) => Promise<void>;
}): Promise<SubmissionConfirmationOutcome> {
  const confirmed: string[] = [];
  for (let index = 0; index < params.questions.length; index += 1) {
    const question = params.questions[index];
    if (question == null) {
      continue;
    }
    try {
      await params.approve(question);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      return {
        confirmed,
        remaining: params.questions.slice(index).map((q) => q.number),
        failedNumber: question.number,
        message,
      };
    }
    confirmed.push(question.number);
  }
  return {
    confirmed,
    remaining: [],
    failedNumber: null,
    message: null,
  };
}

export function formatQuestionNumbers(
  questions: readonly QuestionConfirmation[],
): string {
  return questions.map((question) => `問${question.number}`).join("・");
}
