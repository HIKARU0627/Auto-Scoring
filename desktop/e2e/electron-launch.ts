import * as path from "node:path";

/** Built app root (`desktop/`). Playwright specs compile as CommonJS. */
export const PACKAGE_ROOT = path.resolve(__dirname, "..");

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
