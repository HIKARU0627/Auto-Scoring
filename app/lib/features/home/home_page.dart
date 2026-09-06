import 'package:flutter/material.dart';

import 'package:auto_scoring_app/core/app_dependencies.dart';
import 'package:auto_scoring_app/features/answer_intake/answer_intake_page.dart';
import 'package:auto_scoring_app/features/test_registration/test_list_page.dart';
import 'package:auto_scoring_app/features/test_registration/test_registration_page.dart';

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
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            FutureBuilder<bool>(
              future: dependencies.healthCheck(),
              builder: (context, snapshot) {
                final label = switch (snapshot.data) {
                  true => 'backend: ok',
                  false => 'backend: unavailable',
                  null => 'backend: checking…',
                };
                return Text(
                  label,
                  style: Theme.of(context).textTheme.titleLarge,
                );
              },
            ),
            const SizedBox(height: 24),
            FilledButton.icon(
              onPressed: () => Navigator.of(context).push(
                MaterialPageRoute<void>(
                  builder: (_) =>
                      TestRegistrationPage(dependencies: dependencies),
                ),
              ),
              icon: const Icon(Icons.add_task),
              label: const Text('テスト登録'),
            ),
            const SizedBox(height: 12),
            // Re-entry point for a `draft` registration left mid-way (or
            // after an app restart) -- `GET /tests` (答案取込) only offers
            // `ready` tests, so without this a persisted draft would be
            // unreachable once its settings screen was closed (Issue #16
            // review).
            OutlinedButton.icon(
              onPressed: () => Navigator.of(context).push(
                MaterialPageRoute<void>(
                  builder: (_) => TestListPage(dependencies: dependencies),
                ),
              ),
              icon: const Icon(Icons.list_alt),
              label: const Text('テスト一覧'),
            ),
            const SizedBox(height: 12),
            FilledButton.icon(
              onPressed: () => Navigator.of(context).push(
                MaterialPageRoute<void>(
                  builder: (_) => AnswerIntakePage(dependencies: dependencies),
                ),
              ),
              icon: const Icon(Icons.upload_file),
              label: const Text('答案取込'),
            ),
          ],
        ),
      ),
    );
  }
}
