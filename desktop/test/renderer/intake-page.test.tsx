import { describe, expect, it } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";

import { AppRoutes } from "../../src/renderer/core/app-routes.js";
import {
  createIntakeBridge,
  createIntakeMockClient,
  buildPlan,
  defaultTemplate,
  plannedFile,
} from "./support/intake-harness.js";
import { buildTest } from "./support/mock-sidecar-client.js";
import { renderAppAt } from "./support/app-harness.js";

const READY_TEST = () => [buildTest({ id: "test-1", name: "subject-a" })];

const RULE_MATCHED = [
  plannedFile("subject-a/01_answers.pdf", { role: "student_answer" }),
  plannedFile("subject-a/02_criteria.pdf", { role: "grading_criteria" }),
];

const STRAY_PATHS = [
  "subject-a/01_answers.pdf",
  "subject-a/02_criteria.pdf",
  "subject-a/stray.pdf",
];

interface Deferred<T> {
  readonly promise: Promise<T>;
  readonly resolve: (value: T) => void;
}

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

async function openReview(
  options: {
    plan?: ReturnType<typeof buildPlan>;
    paths?: readonly string[];
    unitCost?: number | null;
    bridge?: ReturnType<typeof createIntakeBridge>;
    handlers?: Parameters<typeof createIntakeMockClient>[0];
  } = {},
): Promise<void> {
  const paths = options.paths ?? [
    "subject-a/01_answers.pdf",
    "subject-a/02_criteria.pdf",
  ];
  renderAppAt(AppRoutes.intake, {
    client: createIntakeMockClient({
      intakeCost: async () => options.unitCost ?? null,
      planIntake: async () => options.plan ?? buildPlan(RULE_MATCHED),
      ...options.handlers,
    }),
    bridge: options.bridge ?? createIntakeBridge({ folderPaths: paths }),
  });
  await screen.findByTestId("intake-template-picker");
  fireEvent.click(screen.getByTestId("intake-choose-folder"));
  await screen.findByTestId("intake-call-estimate");
}

describe("IntakePage invariants", () => {
  it("INV-103: template not selected disables folder pick with intake-template reason", async () => {
    renderAppAt(AppRoutes.intake, {
      client: createIntakeMockClient({
        listIntakeTemplates: async () => [],
      }),
      bridge: createIntakeBridge(),
    });
    await screen.findByTestId("intake-template-picker");
    expect(screen.getByTestId("disabled-reason-intake-template")).toBeDefined();
    expect(screen.getByTestId("intake-choose-folder")).toHaveProperty(
      "disabled",
      true,
    );
  });

  it("INV-124: rule-matched files never call classify API (count must be 0)", async () => {
    let classifyCalls = 0;
    await openReview({
      bridge: createIntakeBridge({
        folderPaths: ["subject-a/01_answers.pdf", "subject-a/02_criteria.pdf"],
        classifyMaterial: async () => {
          classifyCalls += 1;
          throw new Error("must not classify");
        },
      }),
    });
    expect(classifyCalls).toBe(0);
    expect(screen.queryByTestId("intake-run-classification")).toBeNull();
    expect(screen.getByTestId("intake-import")).toHaveProperty(
      "disabled",
      false,
    );
  });

  it("INV-125: shows call count and estimated cost before import", async () => {
    await openReview({
      plan: buildPlan(
        [
          ...RULE_MATCHED,
          plannedFile("subject-a/stray.pdf", {
            classification: "pending",
          }),
        ],
        1,
      ),
      paths: [
        "subject-a/01_answers.pdf",
        "subject-a/02_criteria.pdf",
        "subject-a/stray.pdf",
      ],
      unitCost: 2.5,
    });
    expect(screen.getByText(/AIに問い合わせる件数: 合計1件/)).toBeDefined();
    expect(screen.getByText(/役割の判定 1件/)).toBeDefined();
    expect(screen.getByText(/概算費用: 約2\.50/)).toBeDefined();
  });

  it("INV-126: does not print a numeric cost when unit price is unset", async () => {
    await openReview({
      plan: buildPlan(
        [
          ...RULE_MATCHED,
          plannedFile("subject-a/stray.pdf", {
            classification: "pending",
          }),
        ],
        1,
      ),
      paths: [
        "subject-a/01_answers.pdf",
        "subject-a/02_criteria.pdf",
        "subject-a/stray.pdf",
      ],
    });
    expect(screen.getByText(/単価が未設定/)).toBeDefined();
    expect(screen.queryByText(/概算費用: 約0/)).toBeNull();
    expect(screen.queryByText(/0\.00/)).toBeNull();
  });

  it("INV-127: completion screen does not claim grading is ready", async () => {
    await openReview({
      handlers: {
        startGrading: async () => undefined,
      },
    });
    fireEvent.click(screen.getByTestId("intake-import"));
    await screen.findByTestId("intake-next-step-notice");
    expect(screen.getByText(/配点と採点基準の確定が必要です/)).toBeDefined();
    expect(screen.queryByText(/採点できます/)).toBeNull();
    expect(screen.queryByText(/採点を開始できます/)).toBeNull();
  });

  it("INV-130 / INV-201-07: retired placeholder copy never appears", async () => {
    await openReview();
    fireEvent.click(screen.getByTestId("intake-import"));
    await screen.findByTestId("intake-done-heading");
    expect(screen.queryByText(/画面はまだありません/)).toBeNull();
    expect(screen.queryByText(/Issue #103/)).toBeNull();
  });

  it("Issue #306: 第 1 段で答案 0 件のとき「取り込んだ答案」と言わない", async () => {
    await openReview();
    fireEvent.click(screen.getByTestId("intake-import"));
    await screen.findByTestId("intake-done-heading");
    expect(screen.queryByText(/取り込んだ答案/)).toBeNull();
    expect(screen.queryByText(/答案 0件/)).toBeNull();
    expect(screen.getByTestId("intake-deferred-subject-a")).toBeDefined();
    expect(
      screen.getAllByText(/このテストはまだ登録が済んでいないので/).length,
    ).toBeGreaterThan(0);
  });

  it("Issue #306: ready なテストへの取込は答案件数を事実どおり出す", async () => {
    await openReview({
      handlers: { listTestRegistrations: async () => READY_TEST() },
    });
    fireEvent.click(screen.getByTestId("intake-import"));
    await screen.findByTestId("intake-done-heading");
    expect(screen.getByText(/答案 1件を取り込みました/)).toBeDefined();
    expect(screen.queryByTestId("intake-deferred-subject-a")).toBeNull();
  });

  it("INV-131: partial failure keeps earlier submissions", async () => {
    let created = 0;
    await openReview({
      plan: buildPlan([
        plannedFile("subject-a/01_answers-0.pdf", { role: "student_answer" }),
        plannedFile("subject-a/01_answers-1.pdf", { role: "student_answer" }),
        plannedFile("subject-a/01_answers-2.pdf", { role: "student_answer" }),
        plannedFile("subject-a/02_criteria.pdf", { role: "grading_criteria" }),
      ]),
      paths: [
        "subject-a/01_answers-0.pdf",
        "subject-a/01_answers-1.pdf",
        "subject-a/01_answers-2.pdf",
        "subject-a/02_criteria.pdf",
      ],
      bridge: createIntakeBridge({
        folderPaths: [
          "subject-a/01_answers-0.pdf",
          "subject-a/01_answers-1.pdf",
          "subject-a/01_answers-2.pdf",
          "subject-a/02_criteria.pdf",
        ],
        createSubmission: async () => {
          created += 1;
          if (created === 3) {
            throw new Error("simulated disk failure");
          }
        },
      }),
      handlers: { listTestRegistrations: async () => READY_TEST() },
    });
    fireEvent.click(screen.getByTestId("intake-import"));
    await screen.findByTestId("intake-outcome-subject-a");
    expect(created).toBe(3);
    expect(screen.getByText(/取り込めませんでした/)).toBeDefined();
  });

  it("INV-132: starts grading after successful import into a ready test", async () => {
    const graded: string[] = [];
    await openReview({
      handlers: {
        listTestRegistrations: async () => READY_TEST(),
        startGrading: async (submissionId) => {
          graded.push(submissionId);
        },
      },
    });
    fireEvent.click(screen.getByTestId("intake-import"));
    await screen.findByText(/AI採点を開始しました/);
    expect(graded).toEqual(["sub-1"]);
  });

  it("INV-133: grading kickoff failure still counts as import success", async () => {
    await openReview({
      handlers: {
        listTestRegistrations: async () => READY_TEST(),
        startGrading: async () => {
          throw new Error("no confirmed dependency graph");
        },
      },
    });
    fireEvent.click(screen.getByTestId("intake-import"));
    await screen.findByText(/答案 1件を取り込みました/);
    expect(screen.getByText(/AI採点を開始できませんでした/)).toBeDefined();
    expect(screen.queryByText(/AI採点を開始しました/)).toBeNull();
  });

  it("UG-13: long file names truncate instead of pushing the picker off-screen", async () => {
    renderAppAt(AppRoutes.intake, {
      client: createIntakeMockClient(),
      bridge: createIntakeBridge(),
    });
    await screen.findByTestId("intake-choose-folder");
    const name = screen.getByTestId("file-picker-name");
    expect(name.className).toContain("truncate");
    expect(name.className).toContain("min-w-0");
  });

  it("Issue #346: the steps show folder → routing → import progress", async () => {
    await openReview();
    expect(
      screen.getByTestId("intake-steps-choose").getAttribute("data-state"),
    ).toBe("done");
    const review = screen.getByTestId("intake-steps-review");
    expect(review.getAttribute("data-state")).toBe("current");
    expect(review.getAttribute("aria-current")).toBe("step");
    expect(
      screen.getByTestId("intake-steps-done").getAttribute("data-state"),
    ).toBe("upcoming");
  });

  it("Issue #346: classification says what is running and how far it is", async () => {
    const gate = deferred<unknown>();
    await openReview({
      plan: buildPlan(
        [
          ...RULE_MATCHED,
          plannedFile("subject-a/stray.pdf", { classification: "pending" }),
        ],
        1,
      ),
      paths: STRAY_PATHS,
      bridge: createIntakeBridge({
        folderPaths: STRAY_PATHS,
        classifyMaterial: () => gate.promise,
      }),
    });

    fireEvent.click(screen.getByTestId("intake-run-classification"));

    const notice = await screen.findByTestId("intake-running-notice");
    expect(notice.textContent).toContain("AIが資料の役割を判定しています");
    expect(notice.textContent).toContain("数秒から十数秒");
    const progress = screen.getByTestId("intake-running-progress");
    expect(
      progress
        .querySelector('[role="progressbar"]')
        ?.getAttribute("aria-valuemax"),
    ).toBe("1");

    gate.resolve({ role: "reference", confidence: 1, cached: false });
  });

  it("Issue #346: failed imports list the failing file names", async () => {
    await openReview({
      handlers: { listTestRegistrations: async () => READY_TEST() },
      bridge: createIntakeBridge({
        folderPaths: ["subject-a/01_answers.pdf", "subject-a/02_criteria.pdf"],
        createSubmission: async () => {
          throw new Error("simulated disk failure");
        },
      }),
    });

    fireEvent.click(screen.getByTestId("intake-import"));

    await screen.findByTestId("intake-failed-subject-a");
    const list = screen.getByTestId("intake-failed-files-subject-a");
    expect(list.querySelectorAll("li")).toHaveLength(1);
    expect(list.textContent).toContain("01_answers.pdf");
  });

  it("Issue #450: a draft import names テスト設定 as the next step and opens it", async () => {
    await openReview();
    fireEvent.click(screen.getByTestId("intake-import"));
    await screen.findByTestId("intake-next-step-heading");
    expect(screen.getByTestId("intake-next-step-heading").textContent).toBe(
      "次は、テスト設定で登録を完了します",
    );

    fireEvent.click(screen.getByTestId("intake-next-step-action"));
    await waitFor(() => {
      expect(screen.getByTestId("page-title").textContent).toBe("テスト設定");
    });
  });

  it("Issue #450: a ready-test import names 答案キュー as the next step and opens it", async () => {
    await openReview({
      handlers: {
        listTestRegistrations: async () => READY_TEST(),
        startGrading: async () => undefined,
      },
    });
    fireEvent.click(screen.getByTestId("intake-import"));
    await screen.findByTestId("intake-next-step-heading");
    expect(screen.getByTestId("intake-next-step-heading").textContent).toBe(
      "次は、答案キューで採点を確認します",
    );
    // The per-group card offers the same destination for the imported group.
    expect(screen.getByTestId("intake-open-queue-subject-a")).toBeDefined();

    fireEvent.click(screen.getByTestId("intake-next-step-action"));
    await waitFor(() => {
      expect(screen.getByTestId("page-title").textContent).toBe("答案キュー");
    });
  });

  it("Issue #346: the folder step shows a skeleton before data arrives", async () => {
    const gate = deferred<ReturnType<typeof defaultTemplate>[]>();
    renderAppAt(AppRoutes.intake, {
      client: createIntakeMockClient({
        listIntakeTemplates: () => gate.promise,
      }),
      bridge: createIntakeBridge(),
    });

    expect(screen.getByTestId("intake-loading")).toBeDefined();

    gate.resolve([defaultTemplate()]);
    await screen.findByTestId("intake-template-picker");
  });
});
