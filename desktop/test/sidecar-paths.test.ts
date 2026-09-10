import { describe, expect, it } from "vitest";
import {
  resolveSidecarExecutable,
  SIDECAR_BUNDLE_DIRECTORY,
  SIDECAR_EXECUTABLE_NAME,
  sidecarExecutableCandidates,
} from "../src/main/sidecar-paths";

describe("sidecarExecutableCandidates", () => {
  describe("on Windows (INV-042)", () => {
    const candidates = (
      resolvedExecutable = "C:\\Program Files\\Auto-Scoring\\auto_scoring_app.exe",
      workingDirectory = "C:\\repo\\desktop",
    ) =>
      sidecarExecutableCandidates({
        resolvedExecutable,
        workingDirectory,
        isWindows: true,
      });

    it("prefers the bundle beside the app executable", () => {
      expect(candidates()[0]).toBe(
        "C:\\Program Files\\Auto-Scoring\\sidecar\\auto-scoring-sidecar.exe",
      );
    });

    it("falls back to the venv console script from desktop and root", () => {
      const rest = candidates().slice(1);
      expect(rest).toEqual([
        "C:\\repo\\backend\\.venv\\Scripts\\auto-scoring-sidecar.exe",
        "C:\\repo\\desktop\\backend\\.venv\\Scripts\\auto-scoring-sidecar.exe",
      ]);
    });
  });

  describe("on POSIX (INV-043)", () => {
    const candidates = () =>
      sidecarExecutableCandidates({
        resolvedExecutable: "/opt/auto-scoring/auto_scoring_app",
        workingDirectory: "/repo/desktop",
        isWindows: false,
      });

    it("uses no .exe suffix and the bin/ venv layout", () => {
      expect(candidates()).toEqual([
        "/opt/auto-scoring/sidecar/auto-scoring-sidecar",
        "/repo/backend/.venv/bin/auto-scoring-sidecar",
        "/repo/desktop/backend/.venv/bin/auto-scoring-sidecar",
      ]);
    });
  });

  it("resolves to the first candidate that exists", () => {
    const installed = "/opt/app/sidecar/auto-scoring-sidecar";
    const venv = "/repo/backend/.venv/bin/auto-scoring-sidecar";

    expect(resolveSidecarExecutable([installed, venv], (p) => p === venv)).toBe(
      venv,
    );
    expect(resolveSidecarExecutable([installed, venv], () => true)).toBe(
      installed,
    );
  });

  it("resolves to null when the sidecar executable is missing (INV-035)", () => {
    expect(resolveSidecarExecutable(["/a", "/b"], () => false)).toBeNull();
  });

  it("defines standard constants", () => {
    expect(SIDECAR_BUNDLE_DIRECTORY).toBe("sidecar");
    expect(SIDECAR_EXECUTABLE_NAME).toBe("auto-scoring-sidecar");
  });
});
