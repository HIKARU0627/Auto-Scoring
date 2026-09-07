import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/app_dependencies.dart';
import 'package:auto_scoring_app/core/app_routes.dart';

/// テスト一覧画面 (Issue #16).
///
/// The re-entry point for a test whose registration isn't finished yet:
/// `GET /tests` (答案取込のテスト選択) only offers `ready` tests, so once a
/// reviewer leaves テスト設定画面 mid-way -- or restarts the app -- there is
/// otherwise no way back to a persisted `draft` registration. This screen
/// lists every test regardless of status and opens `TestSettingsPage` for
/// whichever one is tapped.
class TestListPage extends ConsumerStatefulWidget {
  const TestListPage({super.key});

  @override
  ConsumerState<TestListPage> createState() => _TestListPageState();
}

class _TestListPageState extends ConsumerState<TestListPage> {
  /// The live sidecar operations. Read on every use rather than captured
  /// once: the composition root swaps this provider's value whenever the
  /// connection changes (`main.dart`).
  AppDependencies get _dependencies => ref.read(appDependenciesProvider);

  late Future<List<TestResponse>> _testsFuture;

  @override
  void initState() {
    super.initState();
    _testsFuture = _dependencies.listTestRegistrations();
  }

  Future<void> _reload() async {
    final future = _dependencies.listTestRegistrations();
    // A block body, not `() => _testsFuture = future` -- an assignment
    // expression evaluates to the assigned value, so an arrow body would
    // hand `setState` a closure that returns the `Future` itself, which
    // Flutter rejects at runtime ("setState() callback argument returned a
    // Future").
    setState(() {
      _testsFuture = future;
    });
    try {
      await future;
    } catch (_) {
      // `_testsFuture` above already carries this failure to `FutureBuilder`,
      // which renders it as `snapshot.hasError` -- swallow it here so a
      // normal, recoverable sidecar failure during pull-to-refresh (or
      // returning from the settings screen) doesn't *also* surface as an
      // unhandled async exception from this callback's own caller
      // (`RefreshIndicator.onRefresh`, or a tile's `onTap`, neither of
      // which awaits/catches this Future itself) (Issue #16 review round 8).
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('テスト一覧')),
      body: RefreshIndicator(
        onRefresh: _reload,
        child: FutureBuilder<List<TestResponse>>(
          future: _testsFuture,
          builder: (context, snapshot) {
            if (snapshot.connectionState != ConnectionState.done) {
              return const Center(child: CircularProgressIndicator());
            }
            if (snapshot.hasError) {
              final error = snapshot.error;
              final message = error is SidecarApiException
                  ? error.message
                  : '$error';
              return ListView(
                children: [
                  const SizedBox(height: 24),
                  Center(
                    key: const Key('test-list-error'),
                    child: Text('テスト一覧を取得できません: $message'),
                  ),
                ],
              );
            }
            final tests = snapshot.data ?? const [];
            if (tests.isEmpty) {
              return ListView(
                children: const [
                  SizedBox(height: 24),
                  Center(child: Text('登録済みのテストがありません')),
                ],
              );
            }
            return ListView.separated(
              itemCount: tests.length,
              separatorBuilder: (_, _) => const Divider(height: 1),
              itemBuilder: (context, index) {
                final test = tests[index];
                final isReady = test.status == 'ready';
                return ListTile(
                  key: Key('test-list-tile-${test.id}'),
                  leading: Icon(
                    isReady ? Icons.verified : Icons.pending_actions,
                  ),
                  title: Text(test.name),
                  subtitle: Text(isReady ? '登録完了' : '下書き'),
                  onTap: () async {
                    // Awaited, then followed by a reload: a draft opened
                    // from here can reach `ready` on the settings screen,
                    // and without this the tile would keep showing "下書き"
                    // from the response this page fetched before the push
                    // until the reviewer pulled to refresh manually (Issue
                    // #16 review round 5).
                    await context.push(AppRoutes.testSettings(test.id));
                    if (!mounted) return;
                    await _reload();
                  },
                );
              },
            );
          },
        ),
      ),
    );
  }
}
