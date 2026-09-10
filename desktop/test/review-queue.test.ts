import { describe, expect, it } from "vitest";

import {
  byReviewOrder,
  ReviewQueue,
  type SubmissionResponse,
  type SubmissionReviewProgressResponse,
} from "../src/renderer/core/review-queue.js";

function sub(input: {
  id: string;
  state: string;
  day?: number;
  timeIso?: string;
}): SubmissionResponse {
  const created_at =
    input.timeIso ?? new Date(Date.UTC(2026, 1, input.day ?? 1)).toISOString();

  return {
    id: input.id,
    test_id: "t1",
    state: input.state,
    page_count: 1,
    student_label: null,
    created_at,
    is_retry: false,
    original_filename: null,
    review_reason: null,
  };
}

function progress(input: {
  id: string;
  total?: number;
  confirmed?: number;
  manualGrading?: number;
}): SubmissionReviewProgressResponse {
  return {
    submission_id: input.id,
    total_questions: input.total ?? 5,
    confirmed_questions: input.confirmed ?? 0,
    manual_grading_questions: input.manualGrading ?? 0,
  };
}

describe("ReviewQueue domain logic (INV-007 / INV-140..146)", () => {
  describe("並び順 (INV-007 / INV-140)", () => {
    it("要確認が先、同じ状態なら取込の古い順 (INV-140)", () => {
      // ホーム画面の「レビューを続ける」が選ぶ1件とキューの先頭は一致していなければならない
      const queue = ReviewQueue.from({
        submissions: [
          sub({ id: "old-processed", state: "ai_processed", day: 1 }),
          sub({ id: "new-flagged", state: "needs_review", day: 5 }),
          sub({ id: "old-flagged", state: "needs_review", day: 3 }),
        ],
      });

      expect(queue.entries.map((e) => e.id)).toEqual([
        "old-flagged",
        "new-flagged",
        "old-processed",
      ]);
      expect(queue.first?.id).toBe("old-flagged");
    });

    it("境界: 同状態・取込時刻が同一の場合は ID 順で決定的に並ぶ (INV-140 境界)", () => {
      const sameTime = "2026-02-15T12:00:00.000Z";
      const a = sub({
        id: "sub-alpha",
        state: "needs_review",
        timeIso: sameTime,
      });
      const b = sub({
        id: "sub-beta",
        state: "needs_review",
        timeIso: sameTime,
      });

      // Deterministic comparator check
      expect(byReviewOrder(a, b)).toBeLessThan(0);
      expect(byReviewOrder(b, a)).toBeGreaterThan(0);

      const queue1 = ReviewQueue.from({ submissions: [b, a] });
      const queue2 = ReviewQueue.from({ submissions: [a, b] });
      expect(queue1.entries.map((e) => e.id)).toEqual([
        "sub-alpha",
        "sub-beta",
      ]);
      expect(queue2.entries.map((e) => e.id)).toEqual([
        "sub-alpha",
        "sub-beta",
      ]);
    });

    it("境界: 未知状態が混ざる場合、処理中バケットとして扱われ古い順に並ぶ (INV-140 境界)", () => {
      // 未知状態は homeWorkBucketOf により processing バケットへ倒される
      // Bucket 順: needs_review (0) < ai_processed (1) < processing/unknown (2) < error (3) < reviewed/exported (4)
      const queue = ReviewQueue.from({
        submissions: [
          sub({ id: "done", state: "reviewed", day: 1 }),
          sub({ id: "unknown-new", state: "future_ai_status_xyz", day: 6 }),
          sub({ id: "flagged", state: "needs_review", day: 10 }),
          sub({ id: "unknown-old", state: "quantum_processing", day: 2 }),
          sub({ id: "processed", state: "ai_processed", day: 8 }),
          sub({ id: "failed", state: "error", day: 4 }),
        ],
      });

      expect(queue.entries.map((e) => e.id)).toEqual([
        "flagged", // needs_review (bucket 0)
        "processed", // ai_processed (bucket 1)
        "unknown-old", // processing/unknown day 2 (bucket 2)
        "unknown-new", // processing/unknown day 6 (bucket 2)
        "failed", // error (bucket 3)
        "done", // reviewed (bucket 4)
      ]);
    });

    it("済んだ答案も一覧からは消えない (INV-141)", () => {
      const queue = ReviewQueue.from({
        submissions: [
          sub({ id: "done", state: "reviewed", day: 1 }),
          sub({ id: "todo", state: "ai_processed", day: 2 }),
        ],
      });

      expect(queue.entries.map((e) => e.id)).toContain("done");
      expect(queue.entries.map((e) => e.id)).toContain("todo");
      expect(queue.total).toBe(2);
      expect(queue.doneCount).toBe(1);
      expect(queue.isEmpty).toBe(false);
    });
  });

  describe("現在地 (INV-142)", () => {
    it("positionOf は1始まりで、表示順と一致する (INV-142)", () => {
      const queue = ReviewQueue.from({
        submissions: [
          sub({ id: "a", state: "ai_processed", day: 1 }),
          sub({ id: "b", state: "ai_processed", day: 2 }),
        ],
      });

      expect(queue.positionOf("a")).toBe(1);
      expect(queue.positionOf("b")).toBe(2);
      // 知らない答案を0にするのは、「1枚目」と紛れさせないため
      expect(queue.positionOf("no-such-id")).toBe(0);
    });
  });

  describe("次の1件 (INV-143)", () => {
    it("済んだ答案は飛ばす (INV-143)", () => {
      const queue = ReviewQueue.from({
        submissions: [
          sub({ id: "a", state: "ai_processed", day: 1 }),
          sub({ id: "b", state: "reviewed", day: 2 }),
          sub({ id: "c", state: "ai_processed", day: 3 }),
        ],
      });

      expect(queue.nextAfter("a")?.id).toBe("c");
    });

    it("末尾まで済んでいれば、前に残っている未了へ戻る (INV-143)", () => {
      // 「後回し (S)」で送った答案はキューの手前に残る。これが無いと拾えない
      const queue = ReviewQueue.from({
        submissions: [
          sub({ id: "deferred", state: "ai_processed", day: 1 }),
          sub({ id: "current", state: "ai_processed", day: 2 }),
        ],
      });

      expect(queue.nextAfter("current")?.id).toBe("deferred");
    });

    it("未了が自分しか無ければ次は無い (INV-143)", () => {
      const queue = ReviewQueue.from({
        submissions: [
          sub({ id: "done", state: "reviewed", day: 1 }),
          sub({ id: "current", state: "ai_processed", day: 2 }),
        ],
      });

      expect(queue.nextAfter("current")).toBeNull();
    });

    it("全部済んでいれば first も次も無い (INV-143)", () => {
      const queue = ReviewQueue.from({
        submissions: [sub({ id: "done", state: "reviewed", day: 1 })],
      });

      expect(queue.first).toBeNull();
      expect(queue.nextAfter("done")).toBeNull();
    });

    it("未知の submissionId の場合は先頭の未了を返す (INV-143)", () => {
      const queue = ReviewQueue.from({
        submissions: [
          sub({ id: "a", state: "reviewed", day: 1 }),
          sub({ id: "b", state: "ai_processed", day: 2 }),
        ],
      });

      expect(queue.nextAfter("unknown-sub")?.id).toBe("b");
    });
  });

  describe("設問粒度の進捗 (INV-144)", () => {
    it("途中まで確定した答案が、手つかずと区別できる (INV-144)", () => {
      const queue = ReviewQueue.from({
        submissions: [
          sub({ id: "half", state: "ai_processed", day: 1 }),
          sub({ id: "untouched", state: "ai_processed", day: 2 }),
        ],
        progress: [
          progress({ id: "half", confirmed: 3, total: 5 }),
          progress({ id: "untouched", confirmed: 0, total: 5 }),
        ],
      });

      const half = queue.entryFor("half")!;
      expect(half.isPartiallyReviewed).toBe(true);
      expect(half.confirmedQuestions).toBe(3);
      expect(half.totalQuestions).toBe(5);

      const untouched = queue.entryFor("untouched")!;
      expect(untouched.isPartiallyReviewed).toBe(false);
      expect(untouched.confirmedQuestions).toBe(0);
    });

    it("AIが採点できなかった答案は、手を動かす量が違うと分かる (INV-144)", () => {
      const queue = ReviewQueue.from({
        submissions: [
          sub({ id: "stuck", state: "ai_processed", day: 1 }),
          sub({ id: "fine", state: "ai_processed", day: 2 }),
        ],
        progress: [
          progress({ id: "stuck", manualGrading: 1 }),
          progress({ id: "fine", manualGrading: 0 }),
        ],
      });

      expect(queue.entryFor("stuck")!.needsManualGrading).toBe(true);
      expect(queue.entryFor("fine")!.needsManualGrading).toBe(false);
    });

    it("進捗が取れなくても一覧は成立する (INV-144)", () => {
      const queue = ReviewQueue.from({
        submissions: [sub({ id: "a", state: "ai_processed", day: 1 })],
      });

      expect(queue.total).toBe(1);
      expect(queue.entryFor("a")!.totalQuestions).toBe(0);
      expect(queue.entryFor("a")!.isPartiallyReviewed).toBe(false);
    });
  });

  describe("出力してよい答案 (INV-145 / INV-146)", () => {
    it("全設問が確定していれば、状態が reviewed でなくても出力できる (INV-145)", () => {
      // Issue #112 より前は ai_processed のまま全問確定している答案がある
      const queue = ReviewQueue.from({
        submissions: [sub({ id: "legacy", state: "ai_processed", day: 1 })],
        progress: [progress({ id: "legacy", total: 5, confirmed: 5 })],
      });

      const entry = queue.entryFor("legacy")!;
      expect(entry.isDone).toBe(false); // 状態は動いていない
      expect(entry.isFullyConfirmed).toBe(true); // それでも全問確定している
    });

    it("確認済みの答案はもちろん出力できる (INV-145)", () => {
      const queue = ReviewQueue.from({
        submissions: [sub({ id: "done", state: "reviewed", day: 1 })],
        progress: [progress({ id: "done", total: 3, confirmed: 3 })],
      });

      expect(queue.entryFor("done")!.isFullyConfirmed).toBe(true);
    });

    it("1問でも残っていれば出力できない (INV-145)", () => {
      const queue = ReviewQueue.from({
        submissions: [sub({ id: "half", state: "ai_processed", day: 1 })],
        progress: [progress({ id: "half", total: 5, confirmed: 4 })],
      });

      expect(queue.entryFor("half")!.isFullyConfirmed).toBe(false);
    });

    it("進捗が引けていないときは出力できると言わない (INV-146)", () => {
      // 0 / 0 を「全部確定した」と読まない。分からないときは出さない
      const queue = ReviewQueue.from({
        submissions: [sub({ id: "unknown", state: "reviewed", day: 1 })],
      });

      const entry = queue.entryFor("unknown")!;
      expect(entry.totalQuestions).toBe(0);
      expect(entry.isFullyConfirmed).toBe(false);
    });
  });
});
