import { describe, expect, it } from "vitest";
import * as path from "node:path";

import { defaultSidecarAppDataDirectory } from "../src/main/sidecar-app-data.js";
import {
  resolveSidecarLogPath,
  sidecarLogPath,
  SIDECAR_LOG_DIRECTORY,
  SIDECAR_LOG_FILENAME,
} from "../src/main/sidecar-log-path.js";

describe("sidecarLogPath (UG-14)", () => {
  it("is composed from the shared directory and filename, not a literal", () => {
    // The literal `logs` / `sidecar.log` lives only in the module's constants,
    // so the two assertions below fail together if either is renamed.
    expect(SIDECAR_LOG_DIRECTORY).toBe("logs");
    expect(SIDECAR_LOG_FILENAME).toBe("sidecar.log");
    expect(sidecarLogPath("/tmp/app-data")).toBe(
      path.join("/tmp/app-data", "logs", "sidecar.log"),
    );
    expect(sidecarLogPath("/elsewhere")).toBe(
      path.join("/elsewhere", "logs", "sidecar.log"),
    );
  });
});

describe("defaultSidecarAppDataDirectory (UG-14)", () => {
  it("mirrors the backend for a Windows install", () => {
    // Same shape as `backend/tests/test_sidecar.py`
    // `test_windows_falls_back_to_the_home_directory_layout`, resolved with
    // this host's separator (the backend test uses the host `Path` too).
    expect(
      defaultSidecarAppDataDirectory({
        platform: "win32",
        env: {},
        homeDirectory: "/home/t",
      }),
    ).toBe(
      path.join("/home/t", "AppData", "Local", "Auto-Scoring", "app-data"),
    );
  });

  it("mirrors the backend on macOS", () => {
    expect(
      defaultSidecarAppDataDirectory({
        platform: "darwin",
        env: {},
        homeDirectory: "/Users/t",
      }),
    ).toBe(
      path.join(
        "/Users/t",
        "Library",
        "Application Support",
        "Auto-Scoring",
        "app-data",
      ),
    );
  });

  it("honours XDG_DATA_HOME on POSIX", () => {
    expect(
      defaultSidecarAppDataDirectory({
        platform: "linux",
        env: { XDG_DATA_HOME: "/tmp/xdg" },
        homeDirectory: "/home/t",
      }),
    ).toBe(path.join("/tmp/xdg", "auto-scoring", "app-data"));
  });
});

describe("resolveSidecarLogPath (UG-14)", () => {
  it("uses the sidecar's app-data override so the shown path is the real one", () => {
    expect(
      resolveSidecarLogPath({
        isPackaged: false,
        env: { AUTO_SCORING_E2E_APP_DATA: "/tmp/e2e-app-data" },
        platform: "linux",
        homeDirectory: "/home/t",
      }),
    ).toBe(path.join("/tmp/e2e-app-data", "logs", "sidecar.log"));
  });

  it("falls back to the sidecar default in a packaged build (UG-06)", () => {
    const env = { XDG_DATA_HOME: "/tmp/xdg" };
    const appData = defaultSidecarAppDataDirectory({
      platform: "linux",
      env,
      homeDirectory: "/home/t",
    });
    expect(
      resolveSidecarLogPath({
        isPackaged: true,
        env,
        platform: "linux",
        homeDirectory: "/home/t",
      }),
    ).toBe(sidecarLogPath(appData));
  });

  it("ignores the override when packaged (UG-05)", () => {
    expect(
      resolveSidecarLogPath({
        isPackaged: true,
        env: { AUTO_SCORING_E2E_APP_DATA: "/tmp/evil" },
        platform: "linux",
        homeDirectory: "/home/t",
      }),
    ).not.toContain("/tmp/evil");
  });
});
