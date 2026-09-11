import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

import { _electron as electron } from "@playwright/test";
import type { ElectronApplication, Page } from "@playwright/test";

type ElectronLaunchOptions = NonNullable<Parameters<typeof electron.launch>[0]>;

/** Built app root (`desktop/`). Playwright specs compile as CommonJS. */
export const PACKAGE_ROOT = path.resolve(__dirname, "..");

/** UG-08: sidecar startup may take up to 60s on first run (Defender, migration). */
export const SIDECAR_READY_POLL_TIMEOUT_MS = 60_000;

/** Per-test app-data so serial E2E runs do not fight over the sidecar lock. */
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

/** Args for the dev/CI harness. Specs must launch via {@link launchElectronApp}. */
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

/**
 * Playwright launch options for the dev/CI harness: built `out/` args plus
 * per-run isolated app-data. Every spec that drives the unpackaged app should
 * use {@link launchElectronApp} so a new spec cannot forget the isolation.
 */
export function electronLaunchOptions(
  overrides: Omit<ElectronLaunchOptions, "args" | "env"> & {
    env?: Record<string, string>;
  } = {},
): ElectronLaunchOptions {
  const { env: extraEnv, ...rest } = overrides;
  return {
    args: electronLaunchArgs(),
    env: isolatedSidecarLaunchEnv(extraEnv ?? {}),
    ...rest,
  };
}

/** Launches the unpackaged Electron app with isolated sidecar app-data. */
export async function launchElectronApp(
  overrides: Omit<ElectronLaunchOptions, "args" | "env"> & {
    env?: Record<string, string>;
  } = {},
): Promise<ElectronApplication> {
  return electron.launch(electronLaunchOptions(overrides));
}

type SidecarStatus = Awaited<
  ReturnType<NonNullable<Window["autoScoring"]>["getSidecarStatus"]>
>;

function formatSidecarFailure(
  status: SidecarStatus & { kind: "failed" },
): string {
  const exitSuffix =
    status.exitCode === null ? "" : ` (exit code ${status.exitCode})`;
  return `Sidecar failed with ${status.failure}${exitSuffix}`;
}

/**
 * Polls until the sidecar is ready. Failures surface the SidecarFailure kind so
 * CI logs point at executableMissing / alreadyRunning / startupTimedOut / …
 */
export async function pollSidecarReady(page: Page): Promise<void> {
  const deadline = Date.now() + SIDECAR_READY_POLL_TIMEOUT_MS;
  let lastStatus: SidecarStatus = { kind: "starting" };

  while (Date.now() < deadline) {
    lastStatus = await page.evaluate(async () => {
      return window.autoScoring.getSidecarStatus();
    });

    if (lastStatus.kind === "ready") {
      return;
    }

    if (lastStatus.kind === "failed") {
      throw new Error(formatSidecarFailure(lastStatus));
    }

    await page.waitForTimeout(250);
  }

  throw new Error(
    `Sidecar did not become ready within ${SIDECAR_READY_POLL_TIMEOUT_MS}ms; last status: ${JSON.stringify(lastStatus)}`,
  );
}

/** Waits for the Electron process to exit so app-data locks and ports are released. */
export async function closeElectronApp(
  app: ElectronApplication,
  timeoutMs = 30_000,
): Promise<void> {
  const child = app.process();
  await app.close();

  if (!child || child.exitCode !== null) {
    return;
  }

  await new Promise<void>((resolve, reject) => {
    const timer = setTimeout(() => {
      reject(new Error("Electron process did not exit after app.close()"));
    }, timeoutMs);

    child.once("exit", () => {
      clearTimeout(timer);
      resolve();
    });
  });
}
