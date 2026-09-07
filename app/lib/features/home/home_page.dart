import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'package:auto_scoring_app/core/app_dependencies.dart';
import 'package:auto_scoring_app/core/app_routes.dart';
import 'package:auto_scoring_app/core/design/app_theme_context.dart';
import 'package:auto_scoring_app/core/design/design_tokens.dart';

/// Landing screen. Confirms the app boots and can reach the (stubbed) backend.
///
/// `features` may depend on `core` and `api`.
class HomePage extends ConsumerWidget {
  const HomePage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final dependencies = ref.watch(appDependenciesProvider);
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
                return Text(label, style: context.texts.titleLarge);
              },
            ),
            const SizedBox(height: AppSpacing.xl),
            FilledButton.icon(
              onPressed: () => context.push(AppRoutes.testRegistration),
              icon: const Icon(Icons.add_task),
              label: const Text('テスト登録'),
            ),
            const SizedBox(height: AppSpacing.md),
            // Re-entry point for a `draft` registration left mid-way (or
            // after an app restart) -- `GET /tests` (答案取込) only offers
            // `ready` tests, so without this a persisted draft would be
            // unreachable once its settings screen was closed (Issue #16
            // review).
            OutlinedButton.icon(
              onPressed: () => context.push(AppRoutes.testList),
              icon: const Icon(Icons.list_alt),
              label: const Text('テスト一覧'),
            ),
            const SizedBox(height: AppSpacing.md),
            FilledButton.icon(
              onPressed: () => context.push(AppRoutes.answerIntake),
              icon: const Icon(Icons.upload_file),
              label: const Text('答案取込'),
            ),
          ],
        ),
      ),
    );
  }
}
