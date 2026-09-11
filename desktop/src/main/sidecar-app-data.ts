import * as path from "node:path";

/**
 * Directory name the app owns under the OS's per-user data location.
 *
 * Mirrors `auto_scoring.api.sidecar.APP_NAME`. Kept here (not read from the
 * backend) because the error screen has to name the log's location even when
 * startup failed before the sidecar ever wrote a handshake (UG-14).
 */
export const APP_DIRECTORY_NAME = "Auto-Scoring";

/**
 * Resolves an optional sidecar app-data override for non-packaged runs.
 *
 * UG-05: packaged builds must not read configuration from the environment.
 * UG-06: production must not pass `--app-data-dir`; only E2E/dev harnesses may.
 */
export function resolveSidecarAppDataDirectory(options: {
  readonly isPackaged: boolean;
  readonly env: NodeJS.ProcessEnv;
}): string | null {
  if (options.isPackaged) {
    return null;
  }

  const override = options.env["AUTO_SCORING_E2E_APP_DATA"];
  if (override !== undefined && override.length > 0) {
    return override;
  }

  return null;
}

/**
 * The per-user `app-data/` root the sidecar falls back to when no
 * `--app-data-dir` is passed.
 *
 * Mirrors `auto_scoring.api.sidecar.default_app_data_dir` (UG-14). The display
 * path on the crash screen is derived from this same root, so the two only
 * agree while both sides keep one convention. The backend owns the real
 * location; this mirror exists because on a failed startup there is no
 * handshake to ask. `environment`/`platform`/`homeDirectory` are injected so
 * every OS's layout can be checked from any host, exactly as the backend's
 * unit test does.
 */
export function defaultSidecarAppDataDirectory(options: {
  readonly platform: NodeJS.Platform;
  readonly env: NodeJS.ProcessEnv;
  readonly homeDirectory: string;
}): string {
  const { platform, env, homeDirectory } = options;

  if (platform === "win32") {
    const local = env["LOCALAPPDATA"];
    const base =
      local !== undefined && local.length > 0
        ? local
        : path.join(homeDirectory, "AppData", "Local");
    return path.join(base, APP_DIRECTORY_NAME, "app-data");
  }

  if (platform === "darwin") {
    return path.join(
      homeDirectory,
      "Library",
      "Application Support",
      APP_DIRECTORY_NAME,
      "app-data",
    );
  }

  const dataHome = env["XDG_DATA_HOME"];
  const base =
    dataHome !== undefined && dataHome.length > 0
      ? dataHome
      : path.join(homeDirectory, ".local", "share");
  return path.join(base, "auto-scoring", "app-data");
}
