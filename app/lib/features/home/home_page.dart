import 'package:flutter/material.dart';

import 'package:auto_scoring_app/api/api_client.dart';
import 'package:auto_scoring_app/core/app_dependencies.dart';

/// Landing screen. Confirms the app boots and can reach the (stubbed) backend.
///
/// `features` may depend on `core` and `api`.
class HomePage extends StatelessWidget {
  const HomePage({super.key, required this.dependencies});

  final AppDependencies dependencies;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Auto-Scoring')),
      body: Center(
        child: FutureBuilder<BackendHealth>(
          future: dependencies.apiClient.health(),
          builder: (context, snapshot) {
            final label = switch (snapshot.data) {
              BackendHealth.ok => 'backend: ok',
              BackendHealth.unavailable => 'backend: unavailable',
              null => 'backend: checking…',
            };
            return Text(label, style: Theme.of(context).textTheme.titleLarge);
          },
        ),
      ),
    );
  }
}
