/**
 * E2E-only environment overrides (UG-05).
 *
 * Packaged builds must ignore these variables so release artifacts cannot be
 * steered by the environment or import files the user did not choose.
 */
export function readE2eEnv(
  name: string,
  isPackaged: boolean,
  env: NodeJS.ProcessEnv = process.env,
): string | undefined {
  if (isPackaged) {
    return undefined;
  }
  const value = env[name];
  if (value === undefined || value.length === 0) {
    return undefined;
  }
  return value;
}
