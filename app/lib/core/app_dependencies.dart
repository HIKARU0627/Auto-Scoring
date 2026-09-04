import 'package:auto_scoring_app/api/api_client.dart';

/// Composition-root dependency container.
///
/// Features read their collaborators from here instead of constructing them,
/// so the dependency direction stays `features -> core -> api`. A richer DI
/// solution (Riverpod) arrives with the first real feature.
class AppDependencies {
  const AppDependencies({this.apiClient = const ApiClient()});

  final ApiClient apiClient;
}
