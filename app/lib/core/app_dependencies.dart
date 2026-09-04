Future<bool> _stubHealthCheck() async => true;

/// Composition-root dependency container.
///
/// Features read their collaborators from here instead of constructing them,
/// so the dependency direction stays `features -> core -> api`. A richer DI
/// solution (Riverpod) arrives with the first real feature.
class AppDependencies {
  const AppDependencies({this.healthCheck = _stubHealthCheck});

  /// Replaced with `SidecarApiClient.isHealthy` when process supervision lands.
  final Future<bool> Function() healthCheck;
}
