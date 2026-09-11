import { describe, expect, it } from "vitest";

import {
  ActionRequirements,
  answerProfileConfirmRequirements,
  answerProfileSaveRequirements,
  apiKeySaveRequirements,
  apiKeyVerifyRequirements,
  completeRegistrationRequirements,
  dependencyGraphConfirmRequirements,
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
