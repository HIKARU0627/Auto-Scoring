import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/app_dependencies.dart';
import 'package:auto_scoring_app/core/app_routes.dart';
import 'package:auto_scoring_app/core/design/app_status_tone.dart';
import 'package:auto_scoring_app/core/design/design_tokens.dart';

/// テスト一覧画面 (Issue #16).
///
/// The re-entry point for a test whose registration isn't finished yet:
/// `GET /tests` (答案取込のテスト選択) only offers `ready` tests, so once a
/// reviewer leaves テスト設定画面 mid-way -- or restarts the app -- there is
/// otherwise no way back to a persisted `draft` registration. This screen
/// lists every test regardless of status.
///
/// **登録を終えたテストからは、答案キューへ入る** (Issue #151)。#113 が作った
/// 答案キューの入口はホームのテストカードだけで、ホームはテストを絞って
/// 載せるので、**カードに載らなかったテストの答案には到達手段が無かった**。
/// この画面は全テストを出す唯一の画面なので、ここが最後の受け皿になる。
///
/// タップの行き先を `status` で分けているのは、その2つが別の作業だからである。
/// `draft` のテストは答案を取り込めない (§6.1) のでキューは必ず空で、そこへ
/// 送っても行き止まりが1つ増えるだけになる。テスト設定は `ready` のタイルでも
/// 末尾のボタンから開ける。
class TestListPage extends ConsumerStatefulWidget {
  const TestListPage({super.key});

  @override
  ConsumerState<TestListPage> createState() => _TestListPageState();
}

class _TestListPageState extends ConsumerState<TestListPage> {
  /// The sidecar operations this screen was opened against, captured once in
  /// [initState] -- never re-resolved from the provider mid-request. See
  /// [appDependenciesProvider] for why that rule exists.
  late final AppDependencies _dependencies;

  late Future<List<TestResponse>> _testsFuture;

  @override
  void initState() {
    super.initState();
    _dependencies = ref.read(appDependenciesProvider);
    _testsFuture = _dependencies.listTestRegistrations();
  }

  /// テスト設定へ行き、戻ってきたら読み直す。
  ///
  /// Awaited, then followed by a reload: a draft opened from here can reach
  /// `ready` on the settings screen, and without this the tile would keep
  /// showing "下書き" from the response this page fetched before the push
  /// until the reviewer pulled to refresh manually (Issue #16 review round 5).
  Future<void> _openSettings(String testId) async {
    await context.push(AppRoutes.testSettings(testId));
    if (!mounted) return;
    await _reload();
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
                  const SizedBox(height: AppSpacing.xl),
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
                  SizedBox(height: AppSpacing.xl),
                  Center(child: Text('登録済みのテストがありません')),
                ],
              );
            }
            return ListView.separated(
              itemCount: tests.length,
              separatorBuilder: (_, _) =>
                  const Divider(height: AppLayout.hairline),
              itemBuilder: (context, index) {
                final test = tests[index];
                final isReady = test.status == 'ready';
                return ListTile(
                  key: Key('test-list-tile-${test.id}'),
                  // 登録完了 is a finished state, so it recedes; a draft is
                  // not a problem to fix, so it stays neutral rather than
                  // pulling the eye (`AppStatusTone`).
                  leading: Icon(
                    isReady ? Icons.verified : Icons.pending_actions,
                    color:
                        (isReady
                                ? AppStatusTone.success
                                : AppStatusTone.neutral)
                            .color(context),
                  ),
                  title: Text(test.name),
                  // 行き先を副題に書く。同じ見た目のタイルが2つの画面へ
                  // 分かれるので、押す前にどちらへ行くかが読めないと、
                  // 状態表示だけでは足りない。
                  subtitle: Text(isReady ? '登録完了 — 答案を見る' : '下書き — 登録を続ける'),
                  // 登録を終えたテストの設定へは、こちらから。読み直しが要る
                  // のは `draft` からの復帰だけだが、経路を分けても得が無い。
                  trailing: isReady
                      ? IconButton(
                          key: Key('test-list-settings-${test.id}'),
                          icon: const Icon(Icons.tune),
                          tooltip: 'テスト設定',
                          onPressed: () => _openSettings(test.id),
                        )
                      : null,
                  onTap: isReady
                      // 戻ってきても読み直さない。答案キューは登録の状態
                      // (`ready` / `draft`) を動かさず、この一覧はそれと名前
                      // しか出していない。
                      ? () => context.push(AppRoutes.submissionQueue(test.id))
                      : () => _openSettings(test.id),
                );
              },
            );
          },
        ),
      ),
    );
  }
}
