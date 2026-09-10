import { describe, expect, it } from "vitest";

import {
  apiKeySaveRequirements,
  apiKeyVerifyRequirements,
  whileRunningRequirements,
} from "../src/renderer/core/action-requirements.js";

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
    // 1. 未設定時: キーが無い理由
    const unconfigured = apiKeyVerifyRequirements({
      busy: false,
      configured: false,
    });
    expect(unconfigured.map((r) => r.id)).toEqual(["api-key-not-configured"]);

    // 2. 処理中かつ未設定時: busy と未設定の両方
    const busyAndUnconfigured = apiKeyVerifyRequirements({
      busy: true,
      configured: false,
    });
    expect(busyAndUnconfigured.map((r) => r.id)).toEqual([
      "busy",
      "api-key-not-configured",
    ]);

    // 3. 設定済みで処理中: busy のみ
    const busyAndConfigured = apiKeyVerifyRequirements({
      busy: true,
      configured: true,
    });
    expect(busyAndConfigured.map((r) => r.id)).toEqual(["busy"]);

    // 4. 設定済みかつ待機時: 理由は 0 件 (有効)
    const configuredAndIdle = apiKeyVerifyRequirements({
      busy: false,
      configured: true,
    });
    expect(configuredAndIdle).toEqual([]);
  });

  it("資格情報ストアの条件変化で保存の理由が変わる", () => {
    // ストア利用不可
    const storeUnavailable = apiKeySaveRequirements({
      busy: false,
      credentialStoreAvailable: false,
    });
    expect(storeUnavailable.map((r) => r.id)).toEqual([
      "credential-store-unavailable",
    ]);

    // ストア利用不可 かつ 処理中
    const storeUnavailableBusy = apiKeySaveRequirements({
      busy: true,
      credentialStoreAvailable: false,
    });
    expect(storeUnavailableBusy.map((r) => r.id)).toEqual([
      "busy",
      "credential-store-unavailable",
    ]);

    // ストア利用可 かつ 処理中
    const storeAvailableBusy = apiKeySaveRequirements({
      busy: true,
      credentialStoreAvailable: true,
    });
    expect(storeAvailableBusy.map((r) => r.id)).toEqual(["busy"]);

    // 条件充足: 理由は 0 件
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
