/// The child environment a real sidecar needs on Linux so it does not stall in
/// `import keyring`.
///
/// A logged-in Linux desktop session exports `DBUS_SESSION_BUS_ADDRESS`, so
/// keyring's default backend probes the Secret Service over D-Bus and never
/// answers. The sidecar's `create_credential_store()` calls `import keyring`
/// synchronously at startup, so it never reaches `/healthz` and every
/// integration test that boots one fails with
/// `SidecarFailure.startupTimedOut` (Issue #438 -- the `app/` half of the
/// Issue #425 fix PR #432 made in `desktop/e2e/electron-launch.ts`).
///
/// The null backend answers every read with "nothing stored", which is the
/// same supported no-credential configuration the app already runs in when no
/// OS credential store is available, so no test property is weakened.
///
/// Scoped to Linux by the call sites: Windows is the distributed platform and
/// must keep reading Credential Manager, so setting this there would break the
/// product. The map is meant for `Process.start(..., environment: ...)`, whose
/// default `includeParentEnvironment: true` adds it to the inherited
/// environment rather than replacing it.
const Map<String, String> linuxKeyringEnvironment = {
  'PYTHON_KEYRING_BACKEND': 'keyring.backends.null.Keyring',
};
