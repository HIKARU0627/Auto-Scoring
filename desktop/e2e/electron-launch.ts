import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

/** Built app root (`desktop/`). Playwright specs compile as CommonJS. */
export const PACKAGE_ROOT = path.resolve(__dirname, "..");

/** Per-test app-data so parallel/serial E2E runs do not fight over the sidecar lock. */
export function isolatedSidecarLaunchEnv(
  extra: Record<string, string> = {},
): Record<string, string> {
  const appDataDir = fs.mkdtempSync(
    path.join(os.tmpdir(), "auto-scoring-e2e-app-data-"),
  );
  return {
    ...Object.fromEntries(
      Object.entries(process.env).filter(
        (entry): entry is [string, string] => entry[1] !== undefined,
      ),
    ),
    AUTO_SCORING_E2E_APP_DATA: appDataDir,
    ...extra,
  };
}

/** Args passed to `_electron.launch()` for local dev and CI harnesses. */
export function electronLaunchArgs(): string[] {
  return [
    PACKAGE_ROOT,
    // Electron's bundled `chrome-sandbox` has to be root-owned and setuid to
    // start, which it is not inside node_modules on a Linux development
    // machine; without this the process aborts before any window exists.
    "--no-sandbox",
    ...(process.platform === "linux" ? ["--ozone-platform=x11"] : []),
  ];
}
