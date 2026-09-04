/// Backend (Python sidecar) client layer.
///
/// This is the innermost layer of the app: it must not import `core` or
/// `features` (see `AGENTS.md` "Architecture" and
/// `docs/technology-stack.md` §5 — `features -> core -> api`).
///
/// For the MVP 0.2 base the client is a hand-written stub. It will be replaced
/// by a client generated from the FastAPI OpenAPI schema in a later issue.
library;

/// Health status reported by the backend sidecar.
enum BackendHealth {
  ok,
  unavailable;

  static BackendHealth fromStatus(String status) =>
      status == 'ok' ? BackendHealth.ok : BackendHealth.unavailable;
}

/// Minimal client for the local Python sidecar.
class ApiClient {
  const ApiClient({this.baseUrl = 'http://127.0.0.1:8000'});

  /// Base URL of the sidecar. The real port is assigned dynamically at
  /// startup (see `docs/technology-stack.md` §1); this default is a
  /// placeholder until process supervision exists.
  final String baseUrl;

  /// Returns the sidecar health. Hard-coded until the sidecar is wired in.
  Future<BackendHealth> health() async => BackendHealth.ok;
}
