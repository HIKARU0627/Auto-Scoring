import type { components } from "../api/generated/schema.js";
import {
  AppRoutes,
  pdfReview,
  submissionQueue,
  testSettings,
} from "./app-routes.js";
import {
  HOME_WORK_BUCKET_ORDER,
  HomeWorkBucket,
  homeWorkBucketOf,
  homeWorkBucketMeta,
} from "./submission-work-bucket.js";

export type TestResponse = components["schemas"]["TestResponse"];
export type SubmissionResponse = components["schemas"]["SubmissionResponse"];

const RESUMABLE_BUCKETS = new Set<HomeWorkBucket>([
  HomeWorkBucket.needsReview,
  HomeWorkBucket.intakeDone,
]);

export class HomeTestProgress {
  readonly test: TestResponse;
  readonly counts: Readonly<Partial<Record<HomeWorkBucket, number>>>;
  readonly resumableSubmission: SubmissionResponse | null;

  constructor(test: TestResponse, submissions: readonly SubmissionResponse[]) {
    this.test = test;
    this.counts = HomeTestProgress.countByBucket(submissions);
    this.resumableSubmission = HomeTestProgress.pickResumable(submissions);
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

export class HomeDashboard {
  static readonly maxTests = 8;

  readonly tests: readonly HomeTestProgress[];
  readonly visibleTests: readonly HomeTestProgress[];

  private constructor(
    tests: readonly HomeTestProgress[],
    visibleTests: readonly HomeTestProgress[],
  ) {
    this.tests = tests;
    this.visibleTests = visibleTests;
  }

  get hiddenTestCount(): number {
    return this.tests.length - this.visibleTests.length;
  }

  get isEmpty(): boolean {
    return this.tests.length === 0;
  }

  static from(input: {
    tests: readonly TestResponse[];
    submissionsByTestId: Readonly<
      Record<string, readonly SubmissionResponse[]>
    >;
  }): HomeDashboard {
    const progress = input.tests
      .map(
        (test) =>
          new HomeTestProgress(test, input.submissionsByTestId[test.id] ?? []),
      )
      .sort((a, b) => {
        const byOrder = a.order - b.order;
        if (byOrder !== 0) {
          return byOrder;
        }
        return Date.parse(b.test.created_at) - Date.parse(a.test.created_at);
      });
    return new HomeDashboard(progress, HomeDashboard.pickVisible(progress));
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
    return this.tests.reduce((sum, test) => sum + test.countOf(bucket), 0);
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
