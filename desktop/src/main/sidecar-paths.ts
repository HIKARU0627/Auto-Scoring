import * as fs from "node:fs";

/**
 * Subdirectory holding the PyInstaller onedir distribution, beside the
 * executable in a packaged install (docs/windows-distribution.md §2).
 */
export const SIDECAR_BUNDLE_DIRECTORY = "sidecar";

/**
 * Basename of the sidecar executable, matching backend/pyproject.toml.
 */
export const SIDECAR_EXECUTABLE_NAME = "auto-scoring-sidecar";

/** Removes the last path component, supporting both / and \ separators. */
export function parentDirectory(inputPath: string): string {
  const cut = Math.max(inputPath.lastIndexOf("/"), inputPath.lastIndexOf("\\"));
  if (cut <= 0) {
    return inputPath;
  }
  return inputPath.substring(0, cut);
}

export interface SidecarCandidateOptions {
  readonly resolvedExecutable: string;
  readonly workingDirectory: string;
  readonly isWindows: boolean;
}

/**
 * Returns candidate paths for the sidecar executable, best candidate first.
 *
 * Matches INV-042 (Windows: bundle first, venv fallback) and
 * INV-043 (POSIX: no .exe suffix, bin/ venv layout).
 */
export function sidecarExecutableCandidates({
  resolvedExecutable,
  workingDirectory,
  isWindows,
}: SidecarCandidateOptions): string[] {
  const separator = isWindows ? "\\" : "/";
  const suffix = isWindows ? ".exe" : "";
  const venvBinDir = isWindows ? "Scripts" : "bin";

  const join = (parts: string[]): string => parts.join(separator);

  const venvCandidate = (root: string): string =>
    join([
      root,
      "backend",
      ".venv",
      venvBinDir,
      `${SIDECAR_EXECUTABLE_NAME}${suffix}`,
    ]);

  return [
    join([
      parentDirectory(resolvedExecutable),
      SIDECAR_BUNDLE_DIRECTORY,
      `${SIDECAR_EXECUTABLE_NAME}${suffix}`,
    ]),
    venvCandidate(parentDirectory(workingDirectory)),
    venvCandidate(workingDirectory),
  ];
}

/**
 * Resolves the sidecar executable from candidates using the provided existence check.
 * Returns `null` if none exist (reported as SidecarFailure.executableMissing).
 */
export function resolveSidecarExecutable(
  candidates: readonly string[],
  exists: (filePath: string) => boolean = fs.existsSync,
): string | null {
  for (const candidate of candidates) {
    if (exists(candidate)) {
      return candidate;
    }
  }
  return null;
}
