import { app } from "electron";

/**
 * E2E-only environment overrides (UG-05).
 *
 * Packaged builds must ignore these variables so release artifacts cannot be
 * steered by the environment or import files the user did not choose.
 *
 * The packaged gate reads `app.isPackaged` here so callers cannot bypass it by
 * passing a literal `false`.
 */
export function readE2eEnv(
  name: string,
  env: NodeJS.ProcessEnv = process.env,
): string | undefined {
  if (app.isPackaged) {
    return undefined;
  }
  const value = env[name];
  if (value === undefined || value.length === 0) {
    return undefined;
  }
  return value;
}
