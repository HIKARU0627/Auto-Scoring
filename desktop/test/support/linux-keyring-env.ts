/**
 * Linux only: point `keyring` at its null backend before the sidecar's lazy
 * `import keyring` runs.
 *
 * A logged-in desktop session exports `DBUS_SESSION_BUS_ADDRESS`, so keyring's
 * default backend probes the Secret Service over D-Bus and never answers: the
 * sidecar never reaches `/healthz`, and the vitest `node` integration tests
 * that boot a real sidecar time out after 60s (Issue #438 -- the `desktop/test/`
 * half of the Issue #425 fix PR #432 made in `desktop/e2e/electron-launch.ts`).
 * The null backend answers every read with "nothing stored", the same supported
 * no-credential configuration CI and non-Windows already run in, so no test
 * property is weakened.
 *
 * Deliberately local to `desktop/test/` rather than imported from
 * `desktop/e2e/electron-launch.ts`: those are separate test runners, and
 * `e2e/` is a Playwright asset. Sharing would point the vitest `node` project
 * at the Playwright runner's module for a three-line constant.
 *
 * Scoped to Linux because Windows is the distributed platform and must keep
 * reading Credential Manager; setting this there would break the product.
 */
export const linuxKeyringEnvironment: Record<string, string> =
  process.platform === "linux"
    ? { PYTHON_KEYRING_BACKEND: "keyring.backends.null.Keyring" }
    : {};

/**
 * Adds {@link linuxKeyringEnvironment} to this process's environment.
 *
 * `NodeSidecarPlatform.start` spawns children with `process.env` inherited
 * (`desktop/src/main/sidecar-platform.ts`), and `simulated-parent.cjs` passes
 * it on again, so setting it here is what reaches the real sidecar without
 * touching `desktop/src/`. Call once per test file before any sidecar starts.
 */
export function applyLinuxKeyringEnvironment(): void {
  Object.assign(process.env, linuxKeyringEnvironment);
}
