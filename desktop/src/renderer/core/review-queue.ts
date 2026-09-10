/**
 * Review queue order and position logic for a test's submissions (Issue #113 / INV-007).
 *
 * Placed here in `core` so the review queue screen and review screen advance
 * through submissions in the exact same order.
 */

import type { components } from "../api/generated/schema.js";
import {
  HOME_WORK_BUCKET_ORDER,
  HomeWorkBucket,
  homeWorkBucketOf,
} from "./submission-work-bucket.js";

export type SubmissionResponse = components["schemas"]["SubmissionResponse"];
export type SubmissionReviewProgressResponse =
  components["schemas"]["SubmissionReviewProgressResponse"];

/** One submission entry inside the review queue. */
export class ReviewQueueEntry {
  constructor(
    public readonly submission: SubmissionResponse,
    public readonly totalQuestions: number,
    public readonly confirmedQuestions: number,
    public readonly manualGradingQuestions: number,
  ) {}

  get id(): string {
    return this.submission.id;
  }

  /** Human confirmed this submission (`reviewed` or `exported`). */
  get isDone(): boolean {
    return homeWorkBucketOf(this.submission.state) === HomeWorkBucket.done;
  }

  /** Submission requires human intervention (`needs_review`). */
  get needsAttention(): boolean {
    return (
      homeWorkBucketOf(this.submission.state) === HomeWorkBucket.needsReview
    );
  }

  /** AI failed to grade some questions; human needs to grade manually (Issue #118). */
  get needsManualGrading(): boolean {
    return this.manualGradingQuestions > 0;
  }

  /** Not fully done, but has at least 1 confirmed question. */
  get isPartiallyReviewed(): boolean {
    return (
      !this.isDone &&
      this.confirmedQuestions > 0 &&
      this.confirmedQuestions < this.totalQuestions
    );
  }

  /**
   * All questions are confirmed; ready to export (Issue #137 / INV-145).
   *
   * True even if submission.state is not `reviewed` (e.g. legacy `ai_processed`).
   * When progress is unknown (totalQuestions === 0), returns false (INV-146).
   */
  get isFullyConfirmed(): boolean {
    return (
      this.totalQuestions > 0 && this.confirmedQuestions === this.totalQuestions
    );
  }
}

/**
 * Ordering comparator for submissions in the review queue (INV-140).
 *
 * Rules:
 * 1. Bucket priority: needsReview < intakeDone < processing < failed < done.
 * 2. Within same bucket: older created_at first.
 * 3. Boundary tie-breaker: submission ID for deterministic ordering.
 */
export function byReviewOrder(
  a: SubmissionResponse,
  b: SubmissionResponse,
): number {
  const bucketA = HOME_WORK_BUCKET_ORDER.indexOf(homeWorkBucketOf(a.state));
  const bucketB = HOME_WORK_BUCKET_ORDER.indexOf(homeWorkBucketOf(b.state));
  if (bucketA !== bucketB) {
    return bucketA - bucketB;
  }

  const timeA = new Date(a.created_at).getTime();
  const timeB = new Date(b.created_at).getTime();
  if (timeA !== timeB) {
    return timeA - timeB;
  }

  return a.id.localeCompare(b.id);
}

/** Review queue for a test's submissions. */
export class ReviewQueue {
  private constructor(public readonly entries: readonly ReviewQueueEntry[]) {}

  /**
   * Builds a review queue from submissions and optional per-question progress.
   *
   * Submissions are ordered according to [byReviewOrder].
   * Submissions without matching progress default to 0 counts gracefully.
   */
  static from(params: {
    submissions: readonly SubmissionResponse[];
    progress?: readonly SubmissionReviewProgressResponse[];
  }): ReviewQueue {
    const progressById = new Map<string, SubmissionReviewProgressResponse>();
    if (params.progress) {
      for (const row of params.progress) {
        progressById.set(row.submission_id, row);
      }
    }

    const ordered = [...params.submissions].sort(byReviewOrder);
    const entries = ordered.map((submission) => {
      const p = progressById.get(submission.id);
      return new ReviewQueueEntry(
        submission,
        p?.total_questions ?? 0,
        p?.confirmed_questions ?? 0,
        p?.manual_grading_questions ?? 0,
      );
    });

    return new ReviewQueue(entries);
  }

  get total(): number {
    return this.entries.length;
  }

  get doneCount(): number {
    return this.entries.filter((entry) => entry.isDone).length;
  }

  get isEmpty(): boolean {
    return this.entries.length === 0;
  }

  /** First non-done submission in queue. */
  get first(): ReviewQueueEntry | null {
    for (const entry of this.entries) {
      if (!entry.isDone) {
        return entry;
      }
    }
    return null;
  }

  /** 1-based position of submission in queue. Returns 0 if not found (INV-142). */
  positionOf(submissionId: string): number {
    const index = this.entries.findIndex((entry) => entry.id === submissionId);
    return index < 0 ? 0 : index + 1;
  }

  entryFor(submissionId: string): ReviewQueueEntry | null {
    return this.entries.find((entry) => entry.id === submissionId) ?? null;
  }

  /**
   * Next submission to review after [submissionId] (INV-143).
   *
   * Skips done submissions. If at the end of the queue, wraps around to
   * earlier unreviewed submissions. Returns null if none remain.
   */
  nextAfter(submissionId: string): ReviewQueueEntry | null {
    const index = this.entries.findIndex((entry) => entry.id === submissionId);
    if (index >= 0) {
      for (let i = index + 1; i < this.entries.length; i++) {
        const entry = this.entries[i];
        if (entry && !entry.isDone) {
          return entry;
        }
      }
      for (let i = 0; i < index; i++) {
        const entry = this.entries[i];
        if (entry && !entry.isDone) {
          return entry;
        }
      }
      return null;
    }

    return this.first;
  }
}
