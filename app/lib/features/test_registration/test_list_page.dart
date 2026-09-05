import 'package:flutter/material.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/app_dependencies.dart';
import 'package:auto_scoring_app/features/test_registration/test_settings_page.dart';

/// テスト一覧画面 (Issue #16).
///
/// The re-entry point for a test whose registration isn't finished yet:
/// `GET /tests` (答案取込のテスト選択) only offers `ready` tests, so once a
/// reviewer leaves `TestSettingsPage` mid-way -- or restarts the app --
/// there is otherwise no way back to a persisted `draft` registration. This
/// screen lists every test regardless of status and opens
/// [TestSettingsPage] for whichever one is tapped.
class TestListPage extends StatefulWidget {
  const TestListPage({super.key, required this.dependencies});

  final AppDependencies dependencies;

  @override
  State<TestListPage> createState() => _TestListPageState();
}

class _TestListPageState extends State<TestListPage> {
  late Future<List<TestResponse>> _testsFuture;

  @override
  void initState() {
    super.initState();
    _testsFuture = widget.dependencies.listTestRegistrations();
  }

  Future<void> _reload() async {
    final future = widget.dependencies.listTestRegistrations();
    setState(() => _testsFuture = future);
    await future;
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
                  onTap: () => Navigator.of(context).push(
                    MaterialPageRoute<void>(
                      builder: (_) => TestSettingsPage(
                        dependencies: widget.dependencies,
                        testId: test.id,
                      ),
                    ),
                  ),
                );
              },
            );
          },
        ),
      ),
    );
  }
}
