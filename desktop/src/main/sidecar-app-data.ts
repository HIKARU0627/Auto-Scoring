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
