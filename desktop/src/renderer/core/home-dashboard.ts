import type { components } from "../api/generated/schema.js";
import {
  AppRoutes,
  pdfReview,
  submissionQueue,
  testSettings,
} from "./app-routes.js";
import {
  dailySubmissionCounts,
  type HomeDailyPoint,
} from "./home-analytics.js";
import {
  HOME_WORK_BUCKET_ORDER,
  HomeWorkBucket,
  homeWorkBucketOf,
  homeWorkBucketMeta,
} from "./submission-work-bucket.js";

export type TestResponse = components["schemas"]["TestResponse"];
export type SubmissionResponse = components["schemas"]["SubmissionResponse"];
export type SubmissionReviewProgressResponse =
  components["schemas"]["SubmissionReviewProgressResponse"];

const RESUMABLE_BUCKETS = new Set<HomeWorkBucket>([
  HomeWorkBucket.needsReview,
  HomeWorkBucket.intakeDone,
]);

/**
 * The three-way rollup of a test shown by the home donut (Issue #336).
 *
 * The backend only has the two `TestStatus` values (`draft` / `ready`), so the
 * third bucket is read from the answers already loaded for the test: a `ready`
 * test whose answers are all human-confirmed is 完了, one with work left is
 * 進行中. Nothing here guesses -- a test with no answers is 進行中, not 完了.
 */
export const HomeTestPhase = {
  preparing: "preparing",
  inProgress: "inProgress",
  done: "done",
} as const;

export type HomeTestPhase = (typeof HomeTestPhase)[keyof typeof HomeTestPhase];

export const HOME_TEST_PHASE_ORDER: readonly HomeTestPhase[] = [
  HomeTestPhase.preparing,
  HomeTestPhase.inProgress,
  HomeTestPhase.done,
];

export interface HomeTestPhaseMeta {
  readonly label: string;
  readonly tone: "neutral" | "info" | "success";
}

const PHASE_META: Record<HomeTestPhase, HomeTestPhaseMeta> = {
  [HomeTestPhase.preparing]: { label: "準備中", tone: "neutral" },
  [HomeTestPhase.inProgress]: { label: "進行中", tone: "info" },
  [HomeTestPhase.done]: { label: "完了", tone: "success" },
};

export function homeTestPhaseMeta(phase: HomeTestPhase): HomeTestPhaseMeta {
  return PHASE_META[phase];
}

export interface HomeTestStatusBadge {
  readonly label: string;
  readonly tone:
    "neutral" | "info" | "attention" | "danger" | "success" | "error";
}

export interface HomeReviewSummary {
  readonly confirmed: number;
  readonly total: number;
}

export interface HomeTestProgressOptions {
  /** `false` when this test's submissions could not be read. */
  readonly submissionsAvailable?: boolean;
  /** `false` when this test's review progress could not be read. */
  readonly reviewProgressAvailable?: boolean;
  readonly reviewProgress?: readonly SubmissionReviewProgressResponse[];
}

export class HomeTestProgress {
  readonly test: TestResponse;
  readonly counts: Readonly<Partial<Record<HomeWorkBucket, number>>>;
  readonly resumableSubmission: SubmissionResponse | null;
  /** `false` when the submissions list for this test failed to load. */
  readonly submissionsAvailable: boolean;
  /** `false` when the review progress for this test failed to load. */
  readonly reviewProgressAvailable: boolean;
  /** Summed question-level review progress, or `null` when unavailable. */
  readonly reviewSummary: HomeReviewSummary | null;
  /** Most recent known timestamp for the row: last answer, else registration. */
  readonly lastUpdatedAt: string;

  constructor(
    test: TestResponse,
    submissions: readonly SubmissionResponse[],
    options: HomeTestProgressOptions = {},
  ) {
    this.test = test;
    this.submissionsAvailable = options.submissionsAvailable ?? true;
    this.reviewProgressAvailable = options.reviewProgressAvailable ?? true;
    this.counts = HomeTestProgress.countByBucket(submissions);
    this.resumableSubmission = HomeTestProgress.pickResumable(submissions);
    this.reviewSummary = this.reviewProgressAvailable
      ? HomeTestProgress.summarizeReview(options.reviewProgress ?? [])
      : null;
    this.lastUpdatedAt = HomeTestProgress.latestOf(test, submissions);
  }

  get isDraft(): boolean {
    return this.test.status !== "ready";
  }

  get total(): number {
    return Object.values(this.counts).reduce(
      (sum, count) => sum + (count ?? 0),
      0,
    );
  }

  countOf(bucket: HomeWorkBucket): number {
    return this.counts[bucket] ?? 0;
  }

  get doneCount(): number {
    return this.countOf(HomeWorkBucket.done);
  }

  /** Answers loaded for this test, or `null` when the list failed to load. */
  get answerCount(): number | null {
    return this.submissionsAvailable ? this.total : null;
  }

  /** `confirmed / total` percent across answers, or `null` when unknown. */
  get reviewPercent(): number | null {
    const summary = this.reviewSummary;
    if (summary === null || summary.total <= 0) {
      return null;
    }
    return Math.round((summary.confirmed / summary.total) * 100);
  }

  get phase(): HomeTestPhase {
    if (this.test.status !== "ready") {
      return HomeTestPhase.preparing;
    }
    if (!this.submissionsAvailable) {
      return HomeTestPhase.inProgress;
    }
    if (this.total > 0 && this.doneCount === this.total) {
      return HomeTestPhase.done;
    }
    return HomeTestPhase.inProgress;
  }

  /**
   * The pill in the recent-tests table. Precedence mirrors `nextAction`: a
   * failed import, then a flagged answer, outrank "in progress".
   */
  get statusBadge(): HomeTestStatusBadge {
    if (!this.submissionsAvailable) {
      return { label: "取得できません", tone: "neutral" };
    }
    if (this.test.status !== "ready") {
      return { label: "準備中", tone: "neutral" };
    }
    if (this.countOf(HomeWorkBucket.failed) > 0) {
      return { label: "取込失敗", tone: "danger" };
    }
    if (this.countOf(HomeWorkBucket.needsReview) > 0) {
      return { label: "要確認", tone: "attention" };
    }
    if (this.total > 0 && this.doneCount === this.total) {
      return { label: "完了", tone: "success" };
    }
    return { label: "進行中", tone: "info" };
  }

  static readonly settledOrder = 3;

  get order(): number {
    if (this.countOf(HomeWorkBucket.needsReview) > 0) {
      return 0;
    }
    if (this.countOf(HomeWorkBucket.intakeDone) > 0) {
      return 1;
    }
    if (this.isDraft || this.countOf(HomeWorkBucket.failed) > 0) {
      return 2;
    }
    return HomeTestProgress.settledOrder;
  }

  private static countByBucket(
    submissions: readonly SubmissionResponse[],
  ): Readonly<Partial<Record<HomeWorkBucket, number>>> {
    const counts: Partial<Record<HomeWorkBucket, number>> = {};
    for (const submission of submissions) {
      const bucket = homeWorkBucketOf(submission.state);
      counts[bucket] = (counts[bucket] ?? 0) + 1;
    }
    return counts;
  }

  private static summarizeReview(
    rows: readonly SubmissionReviewProgressResponse[],
  ): HomeReviewSummary | null {
    let confirmed = 0;
    let total = 0;
    for (const row of rows) {
      confirmed += row.confirmed_questions;
      total += row.total_questions;
    }
    if (total <= 0) {
      return null;
    }
    return { confirmed, total };
  }

  private static latestOf(
    test: TestResponse,
    submissions: readonly SubmissionResponse[],
  ): string {
    let latest = test.created_at;
    let latestMs = Date.parse(latest);
    for (const submission of submissions) {
      const ms = Date.parse(submission.created_at);
      if (!Number.isNaN(ms) && ms > latestMs) {
        latest = submission.created_at;
        latestMs = ms;
      }
    }
    return latest;
  }

  private static pickResumable(
    submissions: readonly SubmissionResponse[],
  ): SubmissionResponse | null {
    const open = submissions
      .filter((submission) =>
        RESUMABLE_BUCKETS.has(homeWorkBucketOf(submission.state)),
      )
      .sort((a, b) => {
        const byBucket =
          HOME_WORK_BUCKET_ORDER.indexOf(homeWorkBucketOf(a.state)) -
          HOME_WORK_BUCKET_ORDER.indexOf(homeWorkBucketOf(b.state));
        if (byBucket !== 0) {
          return byBucket;
        }
        return Date.parse(a.created_at) - Date.parse(b.created_at);
      });
    return open[0] ?? null;
  }
}

export interface HomeNextAction {
  readonly tone: "attention" | "neutral" | "danger" | "success";
  readonly headline: string;
  readonly detail: string;
  readonly actionLabel: string;
  readonly route: string | null;
}

export interface HomeDegradedTest {
  readonly testId: string;
  readonly testName: string;
  readonly missingSubmissions: boolean;
  readonly missingReviewProgress: boolean;
}

export interface HomeDashboardInput {
  readonly tests: readonly TestResponse[];
  readonly submissionsByTestId: Readonly<
    Record<string, readonly SubmissionResponse[]>
  >;
  /** Tests whose `GET /tests/{id}/submissions` failed. */
  readonly unavailableSubmissionTestIds?: readonly string[];
  readonly reviewProgressByTestId?: Readonly<
    Record<string, readonly SubmissionReviewProgressResponse[]>
  >;
  /** Tests whose `GET /tests/{id}/review-progress` failed. */
  readonly unavailableReviewProgressTestIds?: readonly string[];
  readonly now?: Date;
}

export class HomeDashboard {
  static readonly maxTests = 8;

  readonly tests: readonly HomeTestProgress[];
  readonly visibleTests: readonly HomeTestProgress[];
  readonly degradedTests: readonly HomeDegradedTest[];

  private readonly submissions: readonly SubmissionResponse[];
  private readonly now: Date;

  private constructor(
    tests: readonly HomeTestProgress[],
    visibleTests: readonly HomeTestProgress[],
    submissions: readonly SubmissionResponse[],
    degradedTests: readonly HomeDegradedTest[],
    now: Date,
  ) {
    this.tests = tests;
    this.visibleTests = visibleTests;
    this.submissions = submissions;
    this.degradedTests = degradedTests;
    this.now = now;
  }

  get hiddenTestCount(): number {
    return this.tests.length - this.visibleTests.length;
  }

  get isEmpty(): boolean {
    return this.tests.length === 0;
  }

  static from(input: HomeDashboardInput): HomeDashboard {
    const unavailableSubmissions = new Set(
      input.unavailableSubmissionTestIds ?? [],
    );
    const unavailableReview = new Set(
      input.unavailableReviewProgressTestIds ?? [],
    );

    const progress = input.tests
      .map(
        (test) =>
          new HomeTestProgress(
            test,
            unavailableSubmissions.has(test.id)
              ? []
              : (input.submissionsByTestId[test.id] ?? []),
            {
              submissionsAvailable: !unavailableSubmissions.has(test.id),
              reviewProgressAvailable: !unavailableReview.has(test.id),
              ...(input.reviewProgressByTestId?.[test.id] !== undefined
                ? { reviewProgress: input.reviewProgressByTestId[test.id] }
                : {}),
            },
          ),
      )
      .sort((a, b) => {
        const byOrder = a.order - b.order;
        if (byOrder !== 0) {
          return byOrder;
        }
        return Date.parse(b.test.created_at) - Date.parse(a.test.created_at);
      });

    const submissions: SubmissionResponse[] = [];
    for (const test of progress) {
      if (!test.submissionsAvailable) {
        continue;
      }
      submissions.push(...(input.submissionsByTestId[test.test.id] ?? []));
    }

    const degradedTests: HomeDegradedTest[] = progress
      .filter(
        (test) => !test.submissionsAvailable || !test.reviewProgressAvailable,
      )
      .map((test) => ({
        testId: test.test.id,
        testName: test.test.name,
        missingSubmissions: !test.submissionsAvailable,
        missingReviewProgress: !test.reviewProgressAvailable,
      }));

    return new HomeDashboard(
      progress,
      HomeDashboard.pickVisible(progress),
      submissions,
      degradedTests,
      input.now ?? new Date(),
    );
  }

  private static pickVisible(
    ordered: readonly HomeTestProgress[],
  ): readonly HomeTestProgress[] {
    const settledFrom = ordered.findIndex(
      (test) => test.order === HomeTestProgress.settledOrder,
    );
    if (settledFrom < 0) {
      return ordered;
    }
    const limit =
      settledFrom < HomeDashboard.maxTests
        ? HomeDashboard.maxTests
        : settledFrom;
    return ordered.slice(0, limit);
  }

  count(bucket: HomeWorkBucket): number {
    return this.tests.reduce(
      (sum, test) =>
        sum + (test.submissionsAvailable ? test.countOf(bucket) : 0),
      0,
    );
  }

  /** Number of tests whose submissions are known (used for count disclosure). */
  get countedTestCount(): number {
    return this.tests.filter((test) => test.submissionsAvailable).length;
  }

  phaseCount(phase: HomeTestPhase): number {
    return this.tests.filter((test) => test.phase === phase).length;
  }

  /** One point per day for the last 7 days, oldest first. */
  dailySubmissions(): readonly HomeDailyPoint[] {
    return dailySubmissionCounts(this.submissions, this.now);
  }

  private get resumeTarget(): [HomeTestProgress, SubmissionResponse] | null {
    for (const test of this.tests) {
      const submission = test.resumableSubmission;
      if (submission !== null) {
        return [test, submission];
      }
    }
    return null;
  }

  private get firstFailedTest(): HomeTestProgress | null {
    return (
      this.tests.find((test) => test.countOf(HomeWorkBucket.failed) > 0) ?? null
    );
  }

  private get firstDraftTest(): HomeTestProgress | null {
    return this.tests.find((test) => test.isDraft) ?? null;
  }

  get nextAction(): HomeNextAction {
    const resume = this.resumeTarget;
    if (resume !== null) {
      const [test, submission] = resume;
      const bucket = homeWorkBucketOf(submission.state);
      const isFlagged = bucket === HomeWorkBucket.needsReview;
      const awaiting = this.count(HomeWorkBucket.intakeDone);
      return {
        tone: homeWorkBucketMeta(bucket).tone,
        headline: isFlagged
          ? `要確認の答案が${this.count(HomeWorkBucket.needsReview)}件あります`
          : `取込済みの答案が${awaiting}件あります`,
        detail: isFlagged
          ? `人の確認が必要と判定された答案から開きます${awaiting > 0 ? `（ほかに取込済みが${awaiting}件）` : ""}`
          : "取込と回答欄の抽出は終わっています。AI採点とレビューがどこまで進んだかはホームでは分かりません。テストごとに、取込の古い順に開きます",
        actionLabel: "レビューを続ける",
        route: pdfReview(test.test.id, submission.id),
      };
    }

    const failed = this.firstFailedTest;
    if (failed !== null) {
      return {
        tone: "danger",
        headline: `取込に失敗した答案が${this.count(HomeWorkBucket.failed)}件あります`,
        detail: `答案取込画面で対象のテストを選ぶと、失敗した答案が一覧に出ます（${failed.test.name}）`,
        actionLabel: "答案取込を開く",
        route: AppRoutes.intake,
      };
    }

    const draft = this.firstDraftTest;
    if (draft !== null) {
      return {
        tone: "neutral",
        headline: "登録が途中のテストがあります",
        detail: `${draft.test.name} の登録がまだ完了していません（回答欄と設問依存関係の確認が要ります）`,
        actionLabel: "登録を続ける",
        route: testSettings(draft.test.id),
      };
    }

    const processingCount = this.count(HomeWorkBucket.processing);
    if (processingCount > 0) {
      return {
        tone: "neutral",
        headline: `処理中の答案が${processingCount}件あります`,
        detail: "終わると取込済み・要確認・取込失敗のいずれかになります",
        actionLabel: "最新の状況に更新",
        route: null,
      };
    }

    if (this.tests.length > 0) {
      return {
        tone: "success",
        headline: "いま開く答案はありません",
        detail:
          "次の答案を取り込むと、回答欄の抽出まで自動で行われ、問題がなければAI採点もそのまま始まります",
        actionLabel: "答案を取り込む",
        route: AppRoutes.intake,
      };
    }

    return {
      tone: "neutral",
      headline: "まだテストが登録されていません",
      detail:
        "教科のフォルダを選ぶと、採点基準と答案をまとめて取り込めます。取り込んだあと、配点と回答欄を確認すると採点を始められます",
      actionLabel: "テストを登録する",
      route: AppRoutes.intake,
    };
  }

  queueRouteFor(testId: string): string {
    return submissionQueue(testId);
  }
}
