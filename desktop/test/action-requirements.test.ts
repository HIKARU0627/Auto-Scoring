import { describe, expect, it } from "vitest";

import {
  ActionRequirements,
  answerCoverageRequirements,
  answerDetectRequirements,
  answerDetectionOutcomeRequirements,
  answerProfileConfirmRequirements,
  answerProfileSaveRequirements,
  answerProfileUndetectedConfirmRequirements,
  answerRegionAddRequirements,
  apiKeySaveRequirements,
  apiKeyVerifyRequirements,
  completeRegistrationRequirements,
  dependencyGraphConfirmRequirements,
  reviewApproveRequirements,
  whileRunningRequirements,
} from "../src/renderer/core/action-requirements.js";

function expectActionable(requirement: { id: string; message: string }): void {
  expect(requirement.id.length).toBeGreaterThan(0);
  expect(requirement.message.endsWith("。")).toBe(true);
  expect(requirement.message).not.toMatch(/Exception|Error|HTTP|[0-9]{3} /);
}

describe("action requirements: API key (INV-107, INV-201-04)", () => {
  it("資格情報ストアが使えないとき、代わりの手を言う", () => {
    const unmet = apiKeySaveRequirements({
      busy: false,
      credentialStoreAvailable: false,
    });
    expect(unmet.map((r) => r.id)).toEqual(["credential-store-unavailable"]);
    expect(unmet[0]?.message).toContain("環境変数");
  });

  it("キーが無いと疎通は確認できない (INV-107)", () => {
    const unmet = apiKeyVerifyRequirements({
      busy: false,
      configured: false,
    });
    expect(unmet.map((r) => r.id)).toEqual(["api-key-not-configured"]);
    expect(unmet[0]?.message).toContain("キーがまだありません");
  });

  it("条件を変えたら理由も変わる（無効条件そのものから導かれる）", () => {
    const unconfigured = apiKeyVerifyRequirements({
      busy: false,
      configured: false,
    });
    expect(unconfigured.map((r) => r.id)).toEqual(["api-key-not-configured"]);

    const busyAndUnconfigured = apiKeyVerifyRequirements({
      busy: true,
      configured: false,
    });
    expect(busyAndUnconfigured.map((r) => r.id)).toEqual([
      "busy",
      "api-key-not-configured",
    ]);

    const busyAndConfigured = apiKeyVerifyRequirements({
      busy: true,
      configured: true,
    });
    expect(busyAndConfigured.map((r) => r.id)).toEqual(["busy"]);

    const configuredAndIdle = apiKeyVerifyRequirements({
      busy: false,
      configured: true,
    });
    expect(configuredAndIdle).toEqual([]);
  });

  it("資格情報ストアの条件変化で保存の理由が変わる", () => {
    const storeUnavailable = apiKeySaveRequirements({
      busy: false,
      credentialStoreAvailable: false,
    });
    expect(storeUnavailable.map((r) => r.id)).toEqual([
      "credential-store-unavailable",
    ]);

    const storeUnavailableBusy = apiKeySaveRequirements({
      busy: true,
      credentialStoreAvailable: false,
    });
    expect(storeUnavailableBusy.map((r) => r.id)).toEqual([
      "busy",
      "credential-store-unavailable",
    ]);

    const storeAvailableBusy = apiKeySaveRequirements({
      busy: true,
      credentialStoreAvailable: true,
    });
    expect(storeAvailableBusy.map((r) => r.id)).toEqual(["busy"]);

    const ready = apiKeySaveRequirements({
      busy: false,
      credentialStoreAvailable: true,
    });
    expect(ready).toEqual([]);
  });

  it("進行中しか理由にならない操作", () => {
    expect(
      whileRunningRequirements({ running: true }).map((r) => r.id),
    ).toEqual(["busy"]);
    expect(whileRunningRequirements({ running: false })).toEqual([]);
  });
});

describe("action requirements: 回答欄検出 (Issue #294)", () => {
  it("検出 0 件の結果を区別する", () => {
    expect(
      answerDetectionOutcomeRequirements({ outcome: "zero-results" }).map(
        (item) => item.id,
      ),
    ).toEqual(["answer-detection-zero-results"]);
    expect(
      answerDetectionOutcomeRequirements({ outcome: "role-mismatch" }).map(
        (item) => item.id,
      ),
    ).toEqual(["answer-sheet-role-mismatch"]);
    expect(answerDetectionOutcomeRequirements({ outcome: "none" })).toEqual([]);
  });

  it("provider のレート制限を 0 件と別の系統として、次にやることを言う (Issue #304)", () => {
    const withWait = answerDetectionOutcomeRequirements({
      outcome: "rate-limited",
      retryAfterSeconds: 30,
    });
    expect(withWait.map((item) => item.id)).toEqual([
      "answer-detection-rate-limited",
    ]);
    expect(withWait[0]?.message).toContain("30秒");
    expect(withWait[0]?.message).toContain("回答欄を自動検出");
    expect(withWait[0]?.id).not.toBe("answer-detection-zero-results");

    const withoutWait = answerDetectionOutcomeRequirements({
      outcome: "rate-limited",
      retryAfterSeconds: null,
    });
    expect(withoutWait[0]?.id).toBe("answer-detection-rate-limited");
    expect(withoutWait[0]?.message).not.toMatch(/[0-9０-９]+秒/);
  });

  it("手動追加は答案登録後なら有効", () => {
    expect(
      answerRegionAddRequirements({
        busy: false,
        alreadyConfirmed: false,
        answerSheetRegistered: true,
      }),
    ).toEqual([]);
    expect(
      answerRegionAddRequirements({
        busy: false,
        alreadyConfirmed: false,
        answerSheetRegistered: false,
      }).map((item) => item.id),
    ).toEqual(["answer-sheet-unseen"]);
  });

  it("自動検出は設定不足と未確定配点を区別する", () => {
    expect(
      answerDetectRequirements({
        busy: false,
        alreadyConfirmed: false,
        answerSheetRegistered: true,
        detectionAvailable: false,
        criteriaConfirmed: false,
      }).map((item) => item.id),
    ).toEqual([
      "answer-detect-criteria-unconfirmed",
      "answer-detection-unavailable",
    ]);
    expect(
      answerDetectRequirements({
        busy: false,
        alreadyConfirmed: false,
        answerSheetRegistered: false,
        detectionAvailable: true,
        criteriaConfirmed: true,
      }).map((item) => item.id),
    ).toEqual(["answer-detect-layout-missing"]);
  });
});

describe("test settings registration action requirements", () => {
  it("complete registration stays blocked until profile and graph are confirmed", () => {
    expect(
      completeRegistrationRequirements({
        busy: false,
        alreadyComplete: false,
        profileConfirmed: false,
        dependencyGraphConfirmed: false,
      }).map((item) => item.id),
    ).toEqual(["profile-unconfirmed", "dependency-graph-unconfirmed"]);
    expect(
      completeRegistrationRequirements({
        busy: false,
        alreadyComplete: false,
        profileConfirmed: true,
        dependencyGraphConfirmed: true,
      }),
    ).toEqual([]);
  });

  it("dependency graph confirm requires an analyzed graph", () => {
    expect(
      dependencyGraphConfirmRequirements({
        busy: false,
        hasGraph: false,
        alreadyConfirmed: false,
      }).map((item) => item.id),
    ).toEqual(["dependency-graph-missing"]);
    expectActionable(ActionRequirements.dependencyGraphMissing);
  });
});

describe("action requirements: テスト設定 プロファイル (INV-110, INV-201-04)", () => {
  function confirmIds(options?: {
    busy?: boolean;
    alreadyConfirmed?: boolean;
    regionCount?: number;
    unassignedRegionCount?: number;
    mustSeeAnswerSheetFirst?: boolean;
    answerSheetRegistered?: boolean;
  }): string[] {
    return answerProfileConfirmRequirements({
      busy: options?.busy ?? false,
      alreadyConfirmed: options?.alreadyConfirmed ?? false,
      regionCount: options?.regionCount ?? 1,
      unassignedRegionCount: options?.unassignedRegionCount ?? 0,
      mustSeeAnswerSheetFirst: options?.mustSeeAnswerSheetFirst ?? false,
      answerSheetRegistered: options?.answerSheetRegistered ?? true,
    }).map((r) => r.id);
  }

  it("枠が1つも無ければ、引き方まで言う", () => {
    expect(confirmIds({ regionCount: 0 })).toEqual(["answer-regions-missing"]);
    expect(ActionRequirements.answerRegionsMissing.message).toContain(
      "回答欄を自動検出",
    );
  });

  it("未割り当ての枠は件数ごと出る", () => {
    expect(confirmIds({ unassignedRegionCount: 3 })).toEqual([
      "answer-regions-unassigned",
    ]);
    expect(ActionRequirements.answerRegionsUnassigned(3).message).toContain(
      "3件",
    );
  });

  it("答案が未登録か、登録済みで描けていないかで文を分ける", () => {
    expect(
      confirmIds({
        mustSeeAnswerSheetFirst: true,
        answerSheetRegistered: false,
      }),
    ).toEqual(["answer-sheet-unseen"]);
    expect(
      confirmIds({
        mustSeeAnswerSheetFirst: true,
        answerSheetRegistered: true,
      }),
    ).toEqual(["answer-sheet-unrendered"]);
  });

  it("確定済みなら「確定済み」と言う", () => {
    expect(confirmIds({ alreadyConfirmed: true })).toEqual([
      "profile-already-confirmed",
    ]);
  });

  it("条件が揃えば理由は0件", () => {
    expect(confirmIds()).toEqual([]);
  });

  it("理由はすべて、次にできることを言う形になっている", () => {
    for (const unmet of [
      confirmIds({ regionCount: 0 }),
      confirmIds({ unassignedRegionCount: 1 }),
      confirmIds({
        mustSeeAnswerSheetFirst: true,
        answerSheetRegistered: false,
      }),
      confirmIds({
        mustSeeAnswerSheetFirst: true,
        answerSheetRegistered: true,
      }),
    ]) {
      expect(unmet.length).toBeGreaterThan(0);
    }
    for (const requirement of [
      ActionRequirements.busy,
      ActionRequirements.answerRegionsMissing,
      ActionRequirements.answerRegionsUnassigned(1),
      ActionRequirements.answerSheetUnseen,
      ActionRequirements.answerSheetUnrendered,
      ActionRequirements.profileAlreadyConfirmed,
    ]) {
      expect(requirement.id.length).toBeGreaterThan(0);
      expect(requirement.message.length).toBeGreaterThan(0);
    }
  });

  it("「修正内容を保存」が無効な状態は、確定ボタンの理由が必ず覆う（INV-110: confirm 理由 ⊇ save 理由）", () => {
    for (const busy of [false, true]) {
      for (const confirmed of [false, true]) {
        for (const regionCount of [0, 1]) {
          const save = answerProfileSaveRequirements({
            busy,
            hasRegions: regionCount > 0,
            alreadyConfirmed: confirmed,
          });
          const confirm = answerProfileConfirmRequirements({
            busy,
            alreadyConfirmed: confirmed,
            regionCount,
            unassignedRegionCount: 0,
            mustSeeAnswerSheetFirst: false,
            answerSheetRegistered: true,
          });
          const saveIds = new Set(save.map((r) => r.id));
          const confirmIds = new Set(confirm.map((r) => r.id));

          for (const saveId of saveIds) {
            expect(
              confirmIds.has(saveId),
              `busy=${busy} confirmed=${confirmed} regions=${regionCount}: ` +
                `保存が無効(理由: ${saveId})なのに、確定の理由集合[${[...confirmIds].join(", ")}]に含まれていない`,
            ).toBe(true);
          }
        }
      }
    }
  });

  it("全条件の組み合わせにおいて包含関係（confirm 理由 ⊇ save 理由）が保たれる（網羅的検査）", () => {
    const busyCases = [false, true];
    const confirmedCases = [false, true];
    const regionScenarios = [
      { hasRegions: false, regionCount: 0 },
      { hasRegions: true, regionCount: 0 },
      { hasRegions: true, regionCount: 1 },
      { hasRegions: true, regionCount: 5 },
    ];
    const unassignedCases = [0, 1, 3];
    const mustSeeCases = [false, true];
    const sheetRegisteredCases = [false, true];

    for (const busy of busyCases) {
      for (const alreadyConfirmed of confirmedCases) {
        for (const { hasRegions, regionCount } of regionScenarios) {
          for (const unassignedRegionCount of unassignedCases) {
            for (const mustSeeAnswerSheetFirst of mustSeeCases) {
              for (const answerSheetRegistered of sheetRegisteredCases) {
                const save = answerProfileSaveRequirements({
                  busy,
                  hasRegions,
                  alreadyConfirmed,
                });
                const confirm = answerProfileConfirmRequirements({
                  busy,
                  alreadyConfirmed,
                  regionCount,
                  unassignedRegionCount,
                  mustSeeAnswerSheetFirst,
                  answerSheetRegistered,
                });
                const saveIds = new Set(save.map((r) => r.id));
                const confirmIds = new Set(confirm.map((r) => r.id));

                for (const saveId of saveIds) {
                  expect(
                    confirmIds.has(saveId),
                    `busy=${busy}, confirmed=${alreadyConfirmed}, hasRegions=${hasRegions}, regionCount=${regionCount}, ` +
                      `unassigned=${unassignedRegionCount}, mustSee=${mustSeeAnswerSheetFirst}, registered=${answerSheetRegistered}: ` +
                      `saveId '${saveId}' missing from confirm [${[...confirmIds].join(", ")}]`,
                  ).toBe(true);
                }
              }
            }
          }
        }
      }
    }
  });
});

describe("action requirements: 答案確定・回答欄の理由 (Issue #278)", () => {
  it("答案確定が止まる理由を core の文言から出す", () => {
    expect(ActionRequirements.submissionConfirmReady(3).message).toBe(
      "全設問の判断材料を表示しました。3問をまとめて確定できます。",
    );
    expect(ActionRequirements.submissionConfirmNoQuestions.message).toBe(
      "このテストには設問が登録されていません。",
    );
    expect(
      ActionRequirements.submissionConfirmMaterialUnavailable("問1・問2")
        .message,
    ).toBe(
      "判断材料を読み込めていない設問があります（問1・問2）。再読み込みしてください。",
    );
    expect(
      ActionRequirements.submissionConfirmHumanScoreRequired("問2").message,
    ).toBe(
      "AIが採点できなかった設問があります（問2）。その設問を開いて点数を入力すると、まとめて確定できます。",
    );
    expect(
      ActionRequirements.submissionConfirmUnreached("問3", true).message,
    ).toBe(
      "まだ表示していない設問があります（問3）。上方向へスクロールすると確定できます。",
    );
    expect(
      ActionRequirements.submissionConfirmUnreached("問3", false).message,
    ).toBe(
      "まだ表示していない設問があります（問3）。下方向へスクロールすると確定できます。",
    );
    expect(ActionRequirements.submissionConfirmNothingToConfirm.message).toBe(
      "この答案は全設問を確定済みです。",
    );
  });

  it("回答欄が見つからないときの理由も core の文言から出す", () => {
    expect(ActionRequirements.answerAreaUndetected(2).message).toBe(
      "回答欄が見つからなかった設問が2件あります。このまま確定もできますが、その設問は答案のページ全体を採点に送り、要確認として人の目に回ります。",
    );
    expect(ActionRequirements.answerAreaUndetectedAction.message).toBe(
      "答案には回答欄があるはずです。設問名を押して枠を引いてください。",
    );
    expect(ActionRequirements.answerAreaAbsent(3).message).toBe(
      "この答案では回答欄を見つけられなかった設問が3件あります。登録した答案が課題の一部のページで、採点基準がそれより広い範囲を含んでいることがあります。まず答案と採点基準を確かめてください。",
    );
    expect(ActionRequirements.answerAreaAbsentAction.message).toBe(
      "答案に回答欄があるのに挙がっているときは、設問名を押して枠を引いてください。",
    );
  });
});

describe("action requirements: 未検出のまま確定 (Issue #314)", () => {
  it("未検出が残っているときだけ、件数を示す確認を求める", () => {
    expect(
      answerProfileUndetectedConfirmRequirements({
        undetectedQuestionCount: 0,
      }),
    ).toEqual([]);
    const pending = answerProfileUndetectedConfirmRequirements({
      undetectedQuestionCount: 3,
    });
    expect(pending.map((item) => item.id)).toEqual([
      "profile-confirm-undetected",
    ]);
    expect(pending[0]?.message).toContain("3件");
    expect(pending[0]?.message).toContain("ページ全体を採点に送り");
    expect(pending[0]?.message).not.toContain("absent");
  });

  it("覆えていない件数だけを示し、すべて覆えていれば完了を言う", () => {
    expect(answerCoverageRequirements({ expected: 0, covered: 0 })).toEqual([]);
    const partial = answerCoverageRequirements({ expected: 5, covered: 2 });
    expect(partial.map((item) => item.id)).toEqual([
      "answer-coverage-incomplete",
    ]);
    expect(partial[0]?.message).toContain("覆えていない設問が3件");

    const complete = answerCoverageRequirements({ expected: 5, covered: 5 });
    expect(complete.map((item) => item.id)).toEqual([
      "answer-coverage-complete",
    ]);
    expect(complete[0]?.message).toContain("5件すべて");
  });
});

describe("action requirements: 添削レビューの承認 (Issue #319)", () => {
  it("採点中は、なぜ承認できないかを採点の言葉で言う", () => {
    const unmet = reviewApproveRequirements({
      busy: false,
      gradingInProgress: true,
    });
    expect(unmet.map((item) => item.id)).toEqual(["grading-in-progress"]);
    expect(unmet[0]?.message).toContain("AIが採点中");
    expect(unmet[0]?.message).toContain("承認");
    expectActionable(unmet[0]!);
  });

  it("画面が処理中なら busy、採点が終われば理由は0件", () => {
    expect(
      reviewApproveRequirements({ busy: true, gradingInProgress: true }).map(
        (item) => item.id,
      ),
    ).toEqual(["busy", "grading-in-progress"]);
    expect(
      reviewApproveRequirements({ busy: false, gradingInProgress: false }),
    ).toEqual([]);
  });

  it("更新が取れていないことを黙って隠さない", () => {
    expectActionable(ActionRequirements.gradingStatusStale);
    expect(ActionRequirements.gradingStatusStale.message).toContain(
      "更新できませんでした",
    );
    expect(ActionRequirements.gradingStatusStale.message).toContain(
      "再読み込み",
    );
  });
});
