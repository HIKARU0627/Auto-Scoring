import * as path from "node:path";

import {
  defaultSidecarAppDataDirectory,
  resolveSidecarAppDataDirectory,
} from "./sidecar-app-data.js";

/**
 * Directory (under app-data) the sidecar writes its rotating log into.
 * Mirrors `auto_scoring.api.sidecar.LOG_DIRECTORY_NAME` (UG-14).
 */
export const SIDECAR_LOG_DIRECTORY = "logs";

/**
 * Basename of the sidecar's rotating log file.
 * Mirrors `auto_scoring.api.sidecar.LOG_FILENAME` (UG-14).
 */
export const SIDECAR_LOG_FILENAME = "sidecar.log";

/**
 * The one place the desktop composes the log location from its parts.
 *
 * Both the path the error screen shows and any other desktop consumer derive
 * from this function, so the two can never drift by each hard-coding its own
 * `logs\sidecar.log` literal (UG-14).
 */
export function sidecarLogPath(appDataDirectory: string): string {
  return path.join(
    appDataDirectory,
    SIDECAR_LOG_DIRECTORY,
    SIDECAR_LOG_FILENAME,
  );
}

/**
 * Resolves the log path the user is pointed at when the sidecar fails.
 *
 * Uses the same app-data root the sidecar is handed (the E2E/dev override) or,
 * in a packaged build, the same default the sidecar itself resolves. Startup
 * failures can happen before a handshake, so this cannot ask the sidecar; the
 * backend owns the real location and `test_sidecar.py` pins its half (UG-14).
 */
export function resolveSidecarLogPath(options: {
  readonly isPackaged: boolean;
  readonly env: NodeJS.ProcessEnv;
  readonly platform: NodeJS.Platform;
  readonly homeDirectory: string;
}): string {
  const override = resolveSidecarAppDataDirectory({
    isPackaged: options.isPackaged,
    env: options.env,
  });
  const appDataDirectory =
    override ??
    defaultSidecarAppDataDirectory({
      platform: options.platform,
      env: options.env,
      homeDirectory: options.homeDirectory,
    });
  return sidecarLogPath(appDataDirectory);
}
