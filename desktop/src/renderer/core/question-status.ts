import type { components } from "../api/generated/schema.js";
import type { MaterialSymbolName } from "./material-symbols.js";

export type JobResponse = components["schemas"]["JobResponse"];
export type ReviewResponse = components["schemas"]["ReviewResponse"];

export type QuestionStatusTone = "neutral" | "attention" | "danger" | "success";

export interface QuestionStatusMeta {
  readonly label: string;
  readonly icon: MaterialSymbolName;
  readonly tone: QuestionStatusTone;
}

export const QuestionStatus = {
  pending: { label: "未処理", icon: "radio_button_unchecked", tone: "neutral" },
  blocked: { label: "前提待ち", icon: "lock_clock", tone: "neutral" },
  queued: { label: "実行待ち", icon: "schedule", tone: "neutral" },
  running: { label: "AI処理中", icon: "play_circle", tone: "neutral" },
  needsCheck: { label: "要確認", icon: "help_outline", tone: "attention" },
  failed: { label: "失敗", icon: "error_outline", tone: "danger" },
  cancelled: { label: "中止", icon: "block", tone: "neutral" },
  graded: {
    label: "レビュー待ち",
    icon: "rate_review",
    tone: "neutral",
  },
  regradeRequested: {
    label: "再判定待ち",
    icon: "autorenew",
    tone: "neutral",
  },
  rejected: { label: "却下", icon: "cancel", tone: "neutral" },
  approved: { label: "承認済み", icon: "check_circle", tone: "success" },
} as const satisfies Record<string, QuestionStatusMeta>;

export type QuestionStatusKey = keyof typeof QuestionStatus;

export interface QuestionWait {
  readonly questionId: string;
  readonly number: string;
  readonly status: QuestionStatusKey;
}

export function labelWaitingFor(
  status: QuestionStatusKey,
  waitingOn: QuestionWait | null | undefined,
): string {
  if (status !== "blocked" || waitingOn == null) {
    return QuestionStatus[status].label;
  }
  switch (waitingOn.status) {
    case "failed":
      return `問${waitingOn.number} 失敗で停止`;
    case "needsCheck":
      return `問${waitingOn.number} 確認待ち`;
    default:
      return `問${waitingOn.number} 待ち`;
  }
}

/**
 * Whether a grading job has neither succeeded nor reached a terminal failure
 * state (Issue #319).
 *
 * The review screen polls only while this is true, and the mapping from
 * `job.state` to a question status belongs here so feature screens do not
 * hand-roll it (INV-006).
 */
export function jobIsInProgress(job: JobResponse | null | undefined): boolean {
  if (job == null) {
    return false;
  }
  return (
    job.state === "queued" || job.state === "running" || job.state === "blocked"
  );
}

export function resolveQuestionWait(
  questionId: string,
  lookups: {
    blockedOn: (id: string) => string | null | undefined;
    statusOf: (id: string) => QuestionStatusKey;
    numberOf: (id: string) => string | null | undefined;
  },
): QuestionWait | null {
  const seen = new Set<string>([questionId]);
  let direct: QuestionWait | null = null;
  let current = lookups.blockedOn(questionId);
  while (current != null && seen.add(current)) {
    const number = lookups.numberOf(current);
    if (number == null) {
      return direct;
    }
    const status = lookups.statusOf(current);
    const wait: QuestionWait = { questionId: current, number, status };
    direct ??= wait;
    if (status === "failed" || status === "needsCheck") {
      return wait;
    }
    if (status !== "blocked") {
      return direct;
    }
    current = lookups.blockedOn(current);
  }
  return direct;
}

function reviewStatus(
  review: ReviewResponse | null | undefined,
  job: JobResponse | null | undefined,
): QuestionStatusKey | null {
  switch (review?.action) {
    case "approved":
    case "modified":
      return "approved";
    case "rejected":
      return "rejected";
    case "regrade_requested":
      return regradeAnswered(review, job) ? null : "regradeRequested";
    default:
      return null;
  }
}

function decisionSince(
  review: ReviewResponse | null | undefined,
  job: JobResponse,
): QuestionStatusKey | null {
  if (
    review == null ||
    new Date(review.created_at) <= new Date(job.created_at)
  ) {
    return null;
  }
  return reviewStatus(review, job);
}

function regradeAnswered(
  review: ReviewResponse,
  job: JobResponse | null | undefined,
): boolean {
  if (job == null) {
    return false;
  }
  return (
    job.id === review.regrade_job_id ||
    new Date(job.created_at) > new Date(review.created_at)
  );
}

export function deriveQuestionStatus(input: {
  job: JobResponse | null | undefined;
  review: ReviewResponse | null | undefined;
  hasWaitingDependents: boolean;
}): QuestionStatusKey {
  const { job, review, hasWaitingDependents } = input;
  if (job == null) {
    return reviewStatus(review, job) ?? "pending";
  }
  switch (job.state) {
    case "blocked":
      return "blocked";
    case "queued":
      return "queued";
    case "running":
      return "running";
    case "failed":
      return decisionSince(review, job) ?? "failed";
    case "cancelled":
      return decisionSince(review, job) ?? "cancelled";
    case "succeeded":
      if (job.usable === false && hasWaitingDependents) {
        return decisionSince(review, job) ?? "needsCheck";
      }
      return reviewStatus(review, job) ?? "graded";
    default:
      return "pending";
  }
}
