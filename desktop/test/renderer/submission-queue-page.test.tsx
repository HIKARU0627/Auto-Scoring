import { describe, expect, it } from "vitest";
import { fireEvent, screen } from "@testing-library/react";

import { submissionQueue } from "../../src/renderer/core/app-routes.js";
import { renderAppAt } from "./support/app-harness.js";
import {
  buildProgress,
  buildSubmission,
  buildTest,
} from "./support/mock-sidecar-client.js";

describe("SubmissionQueuePage (Issue #113 / Issue #242 / INV-021, 140..146, 158, 159)", () => {
  it("済んだ答案も含めて全件出る (INV-141)", async () => {
    renderAppAt(submissionQueue("t1"), {
      handlers: {
        getTest: async () => buildTest({ id: "t1", name: "国語 第1回" }),
        listSubmissions: async () => [
          buildSubmission({
            id: "done",
            testId: "t1",
            state: "reviewed",
            studentLabel: "答案A",
          }),
          buildSubmission({
            id: "todo",
            testId: "t1",
            state: "ai_processed",
            createdDay: 2,
            studentLabel: "答案B",
          }),
        ],
      },
    });

    await screen.findByTestId("queue-row-done");
    expect(screen.getByTestId("queue-row-todo")).toBeDefined();
    expect(screen.getByText("確認済み 1 / 2")).toBeDefined();
    expect(screen.getByText("国語 第1回")).toBeDefined();
  });

  it("行から状態と要約理由が読める (INV-158)", async () => {
    renderAppAt(submissionQueue("t1"), {
      handlers: {
        getTest: async () => buildTest({ id: "t1" }),
        listSubmissions: async () => [
          buildSubmission({
            id: "flagged",
            testId: "t1",
            state: "needs_review",
            studentLabel: "答案A",
            reviewReason: "answer_area_undefined:q-2",
          }),
        ],
      },
    });

    await screen.findByTestId("queue-row-flagged");
    expect(screen.getByText("要確認")).toBeDefined();
    expect(
      screen.getByText("回答欄が確定できない設問が1問あります"),
    ).toBeDefined();
    // 生のワイヤ形式は出さない
    expect(screen.queryByText(/answer_area_undefined/)).toBeNull();
  });

  it("知らない理由には何も言わない (INV-159)", async () => {
    // 新しいサイドカーが未知の旗を立てたとき、推測せず空にする
    renderAppAt(submissionQueue("t1"), {
      handlers: {
        getTest: async () => buildTest({ id: "t1" }),
        listSubmissions: async () => [
          buildSubmission({
            id: "odd",
            testId: "t1",
            state: "needs_review",
            studentLabel: "答案A",
            reviewReason: "something_novel_and_unrecognized:q-1",
          }),
        ],
      },
    });

    await screen.findByTestId("queue-row-odd");
    // 状態ラベルは出るが、未知理由の文章は出ない
    expect(screen.getByText("要確認")).toBeDefined();
    expect(screen.queryByText(/something_novel/)).toBeNull();
    expect(screen.queryByText(/あります/)).toBeNull();
  });

  it("途中まで確定した答案が、手つかずと区別できる (INV-144)", async () => {
    renderAppAt(submissionQueue("t1"), {
      handlers: {
        getTest: async () => buildTest({ id: "t1" }),
        listSubmissions: async () => [
          buildSubmission({
            id: "half",
            testId: "t1",
            state: "ai_processed",
            studentLabel: "答案A",
          }),
        ],
        listReviewProgress: async () => [
          buildProgress({ id: "half", confirmed: 3, total: 5 }),
        ],
      },
    });

    await screen.findByTestId("queue-row-half");
    expect(screen.getByText("3 / 5 問 確定")).toBeDefined();
  });

  it("AIが採点できなかった答案は、そうと分かる (INV-144)", async () => {
    renderAppAt(submissionQueue("t1"), {
      handlers: {
        getTest: async () => buildTest({ id: "t1" }),
        listSubmissions: async () => [
          buildSubmission({
            id: "stuck",
            testId: "t1",
            state: "ai_processed",
            studentLabel: "答案A",
          }),
          buildSubmission({
            id: "fine",
            testId: "t1",
            state: "ai_processed",
            createdDay: 2,
            studentLabel: "答案B",
          }),
        ],
        listReviewProgress: async () => [
          buildProgress({ id: "stuck", manualGrading: 1 }),
          buildProgress({ id: "fine", manualGrading: 0 }),
        ],
      },
    });

    await screen.findByTestId("queue-row-stuck");
    expect(screen.getByTestId("queue-manual-grade-stuck")).toBeDefined();
    expect(screen.queryByTestId("queue-manual-grade-fine")).toBeNull();
    expect(
      screen.getByText("AIが採点できなかった設問があります"),
    ).toBeDefined();
  });

  it("行をタップすると答案確定画面を開く（設問ごと承認ではない） (INV-021)", async () => {
    renderAppAt(submissionQueue("t1"), {
      handlers: {
        getTest: async () => buildTest({ id: "t1" }),
        listSubmissions: async () => [
          buildSubmission({
            id: "s1",
            testId: "t1",
            state: "ai_processed",
            studentLabel: "答案A",
          }),
        ],
      },
    });

    await screen.findByTestId("queue-row-s1");
    fireEvent.click(screen.getByTestId("queue-row-s1"));

    // 開く先は答案確定画面 (INV-021)
    await screen.findByTestId("confirm-question-list");
  });

  it("答案が1件も無いときは、そう言う", async () => {
    renderAppAt(submissionQueue("t1"), {
      handlers: {
        getTest: async () => buildTest({ id: "t1" }),
        listSubmissions: async () => [],
      },
    });

    await screen.findByTestId("queue-empty");
    expect(
      screen.getByText("このテストにはまだ答案が取り込まれていません。"),
    ).toBeDefined();
  });

  it("進捗が引けなくても一覧は出る (INV-144 / INV-146)", async () => {
    renderAppAt(submissionQueue("t1"), {
      handlers: {
        getTest: async () => buildTest({ id: "t1" }),
        listSubmissions: async () => [
          buildSubmission({
            id: "s1",
            testId: "t1",
            state: "ai_processed",
            studentLabel: "答案A",
          }),
        ],
        listReviewProgress: async () => {
          throw new Error("progress unavailable");
        },
      },
    });

    await screen.findByTestId("queue-row-s1");
    expect(screen.queryByTestId("queue-error")).toBeNull();
    // 進捗数だけが出ない
    expect(screen.queryByTestId("queue-progress-s1")).toBeNull();
  });

  it("一覧そのものが引けなければ、エラーと再読み込みを出す", async () => {
    renderAppAt(submissionQueue("t1"), {
      handlers: {
        getTest: async () => buildTest({ id: "t1" }),
        listSubmissions: async () => {
          throw new Error("サイドカーに接続できません");
        },
      },
    });

    await screen.findByTestId("queue-error");
    expect(
      screen.getByText(
        /答案の一覧を取得できません: サイドカーに接続できません/,
      ),
    ).toBeDefined();
    expect(screen.getByText("再読み込み")).toBeDefined();
  });

  describe("PDF出力 (INV-145 / INV-146 / INV-190)", () => {
    it("確定し終えた答案の行から、レビュー画面を開かずに出力できる (INV-190)", async () => {
      const requestedFor: string[] = [];
      renderAppAt(submissionQueue("t1"), {
        handlers: {
          getTest: async () => buildTest({ id: "t1" }),
          listSubmissions: async () => [
            buildSubmission({
              id: "done",
              testId: "t1",
              state: "reviewed",
              studentLabel: "答案A",
            }),
          ],
          listReviewProgress: async () => [
            buildProgress({ id: "done", total: 3, confirmed: 3 }),
          ],
          requestExport: async (submissionId) => {
            requestedFor.push(submissionId);
            return {
              decision: "reuse_existing",
              export: {
                id: "exp-1",
                job_id: "job-1",
                submission_id: submissionId,
                file_path: "exports/答案A_corrected.pdf",
                file_sha256: "0".repeat(64),
                created_at: new Date().toISOString(),
              },
            };
          },
        },
      });

      await screen.findByTestId("queue-row-done");
      const exportButton = screen.getByTestId("queue-export-done");
      expect(exportButton).toBeDefined();

      fireEvent.click(exportButton);

      await screen.findByTestId("export-dialog-success");
      expect(requestedFor).toEqual(["done"]);
      expect(
        screen.getByText("保存先: exports/答案A_corrected.pdf"),
      ).toBeDefined();
      // レビュー画面へは行かず、キュー画面の上で完結する
      expect(screen.queryByText("添削レビュー")).toBeNull();
      expect(screen.getByText("答案キュー")).toBeDefined();
    });

    it("状態が動いていなくても、全問確定していれば出力できる (INV-145)", async () => {
      // legacy ai_processed 答案
      renderAppAt(submissionQueue("t1"), {
        handlers: {
          getTest: async () => buildTest({ id: "t1" }),
          listSubmissions: async () => [
            buildSubmission({
              id: "legacy",
              testId: "t1",
              state: "ai_processed",
              studentLabel: "答案B",
            }),
          ],
          listReviewProgress: async () => [
            buildProgress({ id: "legacy", total: 3, confirmed: 3 }),
          ],
        },
      });

      await screen.findByTestId("queue-row-legacy");
      expect(screen.getByTestId("queue-export-legacy")).toBeDefined();
    });

    it("確定していない答案には出力を出さない (INV-145)", async () => {
      renderAppAt(submissionQueue("t1"), {
        handlers: {
          getTest: async () => buildTest({ id: "t1" }),
          listSubmissions: async () => [
            buildSubmission({
              id: "half",
              testId: "t1",
              state: "ai_processed",
              studentLabel: "答案A",
            }),
          ],
          listReviewProgress: async () => [
            buildProgress({ id: "half", total: 5, confirmed: 4 }),
          ],
        },
      });

      await screen.findByTestId("queue-row-half");
      expect(screen.getByTestId("queue-progress-half")).toBeDefined();
      expect(screen.queryByTestId("queue-export-half")).toBeNull();
    });

    it("進捗が引けなかった答案には出力を出さない (INV-146)", async () => {
      // 0 / 0 を全部確定と読まない
      renderAppAt(submissionQueue("t1"), {
        handlers: {
          getTest: async () => buildTest({ id: "t1" }),
          listSubmissions: async () => [
            buildSubmission({
              id: "done",
              testId: "t1",
              state: "reviewed",
              studentLabel: "答案A",
            }),
          ],
          listReviewProgress: async () => {
            throw new Error("progress unavailable");
          },
        },
      });

      await screen.findByTestId("queue-row-done");
      expect(screen.queryByTestId("queue-export-done")).toBeNull();
    });
  });
});
