import { describe, expect, it } from "vitest";

import {
  dailySubmissionCounts,
  formatHomeDate,
  latestTimestamp,
  HOME_DAILY_DAYS,
} from "../src/renderer/core/home-analytics.js";
import {
  HomeTestPhase,
  HomeTestProgress,
} from "../src/renderer/core/home-dashboard.js";
import { HomeWorkBucket } from "../src/renderer/core/submission-work-bucket.js";
import {
  buildProgress,
  buildSubmission,
  buildTest,
} from "./renderer/support/mock-sidecar-client.js";

const DAY_MS = 86_400_000;

function isoDaysAgo(daysAgo: number): string {
  const noon = new Date();
  noon.setHours(12, 0, 0, 0);
  return new Date(noon.getTime() - daysAgo * DAY_MS).toISOString();
}

describe("dailySubmissionCounts (Issue #336)", () => {
  it("returns exactly one point per requested day, oldest first", () => {
    const points = dailySubmissionCounts([], new Date(), HOME_DAILY_DAYS);
    expect(points).toHaveLength(HOME_DAILY_DAYS);
    for (const point of points) {
      expect(point.count).toBe(0);
    }
  });

  it("counts a submission on the day it was created and ignores older ones", () => {
    const submissions = [
      {
        ...buildSubmission({ id: "a", state: "reviewed" }),
        created_at: isoDaysAgo(0),
      },
      {
        ...buildSubmission({ id: "b", state: "reviewed" }),
        created_at: isoDaysAgo(0),
      },
      {
        ...buildSubmission({ id: "c", state: "reviewed" }),
        created_at: isoDaysAgo(2),
      },
      {
        ...buildSubmission({ id: "old", state: "reviewed" }),
        created_at: isoDaysAgo(30),
      },
    ];
    const points = dailySubmissionCounts(submissions, new Date());
    const counts = points.map((point) => point.count);
    expect(counts.reduce((sum, count) => sum + count, 0)).toBe(3);
    expect(counts[counts.length - 1]).toBe(2);
    expect(counts[counts.length - 3]).toBe(1);
  });

  it("changes the number of points when the day count changes", () => {
    expect(dailySubmissionCounts([], new Date(), 5)).toHaveLength(5);
    expect(dailySubmissionCounts([], new Date(), 8)).toHaveLength(8);
  });
});

describe("home date formatting (Issue #336)", () => {
  it("formats a timestamp as YYYY/MM/DD", () => {
    expect(formatHomeDate(new Date(2026, 8, 4, 12).toISOString())).toBe(
      "2026/09/04",
    );
  });

  it("shows a dash instead of inventing a date", () => {
    expect(formatHomeDate(null)).toBe("—");
    expect(formatHomeDate("")).toBe("—");
  });

  it("picks the latest valid timestamp", () => {
    expect(
      latestTimestamp([
        new Date(2026, 0, 1).toISOString(),
        null,
        new Date(2026, 5, 1).toISOString(),
      ]),
    ).toBe(new Date(2026, 5, 1).toISOString());
    expect(latestTimestamp([null, undefined])).toBeNull();
  });
});

describe("test phase and status badge (Issue #336)", () => {
  function progress(input: {
    status: string;
    submissions?: ReturnType<typeof buildSubmission>[];
    reviewProgress?: ReturnType<typeof buildProgress>[];
  }): HomeTestProgress {
    return new HomeTestProgress(
      buildTest({ id: "t1", status: input.status }),
      input.submissions ?? [],
      { reviewProgress: input.reviewProgress ?? [] },
    );
  }

  it("is preparing while the registration is a draft", () => {
    const test = progress({ status: "draft" });
    expect(test.phase).toBe(HomeTestPhase.preparing);
    expect(test.statusBadge.label).toBe("準備中");
  });

  it("is in progress while a ready test still has unfinished answers", () => {
    const test = progress({
      status: "ready",
      submissions: [
        buildSubmission({ id: "a", state: "reviewed" }),
        buildSubmission({ id: "b", state: "needs_review" }),
      ],
    });
    expect(test.phase).toBe(HomeTestPhase.inProgress);
    expect(test.statusBadge.label).toBe("要確認");
  });

  it("is done only when a ready test has answers and all are confirmed", () => {
    const test = progress({
      status: "ready",
      submissions: [
        buildSubmission({ id: "a", state: "reviewed" }),
        buildSubmission({ id: "b", state: "exported" }),
      ],
    });
    expect(test.phase).toBe(HomeTestPhase.done);
    expect(test.statusBadge.label).toBe("完了");
  });

  it("does not call a ready test with no answers done", () => {
    const test = progress({ status: "ready" });
    expect(test.phase).toBe(HomeTestPhase.inProgress);
    expect(test.statusBadge.label).toBe("進行中");
  });

  it("surfaces an import failure ahead of in-progress", () => {
    const test = progress({
      status: "ready",
      submissions: [
        buildSubmission({ id: "a", state: "error" }),
        buildSubmission({ id: "b", state: "ai_processed" }),
      ],
    });
    expect(test.statusBadge.label).toBe("取込失敗");
  });

  it("distinguishes unavailable progress from a real zero", () => {
    const unavailable = new HomeTestProgress(buildTest({ id: "t1" }), [], {
      submissionsAvailable: false,
      reviewProgressAvailable: false,
    });
    expect(unavailable.answerCount).toBeNull();
    expect(unavailable.reviewSummary).toBeNull();
    expect(unavailable.reviewPercent).toBeNull();
    expect(unavailable.statusBadge.label).toBe("取得できません");

    const zero = progress({
      status: "ready",
      submissions: [buildSubmission({ id: "a", state: "ai_processed" })],
      reviewProgress: [buildProgress({ id: "a", total: 4, confirmed: 0 })],
    });
    expect(zero.answerCount).toBe(1);
    expect(zero.reviewSummary).toEqual({ confirmed: 0, total: 4 });
    expect(zero.reviewPercent).toBe(0);
  });

  it("counts answers by bucket so the home statistics stay correct", () => {
    const test = progress({
      status: "ready",
      submissions: [
        buildSubmission({ id: "a", state: "needs_review" }),
        buildSubmission({ id: "b", state: "ai_processed" }),
        buildSubmission({ id: "c", state: "ai_processing" }),
        buildSubmission({ id: "d", state: "reviewed" }),
      ],
    });
    expect(test.countOf(HomeWorkBucket.needsReview)).toBe(1);
    expect(test.countOf(HomeWorkBucket.intakeDone)).toBe(1);
    expect(test.countOf(HomeWorkBucket.processing)).toBe(1);
    expect(test.countOf(HomeWorkBucket.done)).toBe(1);
  });
});
