import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/app_dependencies.dart';
import 'package:auto_scoring_app/core/app_routes.dart';
import 'package:auto_scoring_app/core/design/app_status_tone.dart';
import 'package:auto_scoring_app/core/design/app_theme_context.dart';
import 'package:auto_scoring_app/core/design/design_tokens.dart';
import 'package:auto_scoring_app/core/widgets/app_error_banner.dart';
import 'package:auto_scoring_app/features/home/home_dashboard.dart';

/// ホーム画面 (簡易設計書 §16.1, Issue #68).
///
/// アプリを開いた瞬間に「今どうなっていて、次に何をすればいいか」が分かる
/// ことだけを目的にしている。上半分が次の一手 ([HomeNextAction]) 、下半分が
/// テストごとの進み具合で、どちらからも中断した作業へ直接戻れる
/// (`docs/home-dashboard.md`)。
///
/// サイドカーの生死はここでは扱わない。到達できないときはそもそも
/// `SidecarStartupOverlay` (Issue #24) がアプリ全体を覆っていて、この画面は
/// 見えない。
///
/// `features` may depend on `core` and `api`.
class HomePage extends ConsumerStatefulWidget {
  const HomePage({super.key});

  @override
  ConsumerState<HomePage> createState() => _HomePageState();
}

class _HomePageState extends ConsumerState<HomePage> {
  /// The sidecar operations this screen was opened against, captured once in
  /// [initState] -- never re-resolved from the provider mid-request. See
  /// [appDependenciesProvider] for why that rule exists.
  late final AppDependencies _dependencies;

  late Future<HomeDashboard> _dashboardFuture;

  @override
  void initState() {
    super.initState();
    _dependencies = ref.read(appDependenciesProvider);
    _dashboardFuture = _load();
  }

  /// テストの一覧と、そのそれぞれの答案を1回ぶんまとめて読む。
  ///
  /// `listSubmissions` はテストごとのAPIなので、これは 1 + N リクエストに
  /// なる。N は [HomeDashboard.maxTests] で頭打ちにしてある。相手はローカルの
  /// サイドカー (SQLite) で、まとめて取る集計APIを足すのは新しいバックエンド
  /// APIになるため、この Issue では取らない選択をした
  /// (`docs/home-dashboard.md` §5)。
  Future<HomeDashboard> _load() async {
    final all = await _dependencies.listTestRegistrations();
    final recent = [...all]..sort((a, b) => b.createdAt.compareTo(a.createdAt));
    final shown = recent.take(HomeDashboard.maxTests).toList();
    // Future.wait: N件を直列に待つとテスト8件ぶんの往復が積み上がる。1件でも
    // 失敗したらこの Future 全体が失敗し、画面はエラーバナーと再試行を出す
    // -- 個々の失敗を握り潰して欠けた内訳を正しい数字として見せるより、
    // 取れていないことを言うほうがよい。
    final submissions = await Future.wait(
      shown.map((test) => _dependencies.listSubmissions(test.id)),
    );
    return HomeDashboard.from(
      tests: shown,
      submissionsByTestId: {
        for (final (index, test) in shown.indexed) test.id: submissions[index],
      },
      hiddenTestCount: all.length - shown.length,
    );
  }

  Future<void> _reload() async {
    final future = _load();
    // A block body, not an arrow: an assignment expression evaluates to the
    // assigned value, and `setState` rejects a callback that returns a Future.
    setState(() {
      _dashboardFuture = future;
    });
    try {
      await future;
    } catch (_) {
      // `_dashboardFuture` already carries this failure to `FutureBuilder`,
      // which renders it. Swallow it here so a recoverable sidecar failure
      // does not *also* surface as an unhandled async error out of the
      // callers that do not await this (button callbacks).
    }
  }

  /// 別の画面へ行き、戻ってきたら数え直す。ホームの数字はレビュー1件・
  /// 取込1件で変わるので、戻ってきた画面が古い件数のままだと「次に何を
  /// すればいいか」が嘘になる。
  Future<void> _openAndReload(String route) async {
    await context.push(route);
    if (!mounted) return;
    await _reload();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Auto-Scoring'),
        actions: [
          IconButton(
            key: const Key('home-refresh'),
            onPressed: _reload,
            icon: const Icon(Icons.refresh),
            tooltip: '最新の状況に更新',
          ),
        ],
      ),
      body: _CenteredPanel(
        child: ListView(
          padding: AppSpacing.page,
          children: [
            FutureBuilder<HomeDashboard>(
              future: _dashboardFuture,
              builder: (context, snapshot) {
                if (snapshot.connectionState != ConnectionState.done) {
                  return const Center(child: CircularProgressIndicator());
                }
                if (snapshot.hasError) {
                  return AppErrorBanner(
                    message: '作業状況を取得できません: ${_describeError(snapshot.error)}',
                    messageKey: const Key('home-error'),
                    onRetry: _reload,
                  );
                }
                return _DashboardBody(
                  dashboard: snapshot.data!,
                  onOpen: _openAndReload,
                  onRefresh: _reload,
                );
              },
            ),
            const SizedBox(height: AppSpacing.xl),
            const Divider(),
            const SizedBox(height: AppSpacing.md),
            // 作業状況が取れなくてもこの行だけは残す。サイドカーが一度
            // 応えなかっただけのことがあり、そのときホームから動けなくなる
            // のは困る (各画面は自分の失敗を自分で報告する)。
            _EntryPointRow(onOpen: _openAndReload),
          ],
        ),
      ),
    );
  }
}

String _describeError(Object? error) =>
    error is SidecarApiException ? error.message : '$error';

/// ページの内容を読みやすい幅に収めて上寄せする器。最大化したデスクトップで
/// カード1枚を画面いっぱいに引き伸ばさないためのもので、狭い幅では素通しになる。
class _CenteredPanel extends StatelessWidget {
  const _CenteredPanel({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.topCenter,
      child: ConstrainedBox(
        constraints: const BoxConstraints(
          maxWidth: AppLayout.dashboardMaxWidth,
        ),
        child: child,
      ),
    );
  }
}

class _DashboardBody extends StatelessWidget {
  const _DashboardBody({
    required this.dashboard,
    required this.onOpen,
    required this.onRefresh,
  });

  final HomeDashboard dashboard;
  final ValueChanged<String> onOpen;
  final VoidCallback onRefresh;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _NextUpCard(
          action: dashboard.nextAction,
          onOpen: onOpen,
          onRefresh: onRefresh,
        ),
        if (dashboard.tests.isNotEmpty) ...[
          const SizedBox(height: AppSpacing.xl),
          _SectionHeader(
            title: 'テストの進み具合',
            hiddenTestCount: dashboard.hiddenTestCount,
            onOpen: onOpen,
          ),
          const SizedBox(height: AppSpacing.sm),
          for (final test in dashboard.tests) ...[
            _TestProgressCard(progress: test, onOpen: onOpen),
            const SizedBox(height: AppSpacing.md),
          ],
        ],
      ],
    );
  }
}

/// 一番上のカード。この画面で一番大きい文字と、いちばん強いボタンを持つ。
class _NextUpCard extends StatelessWidget {
  const _NextUpCard({
    required this.action,
    required this.onOpen,
    required this.onRefresh,
  });

  final HomeNextAction action;
  final ValueChanged<String> onOpen;
  final VoidCallback onRefresh;

  @override
  Widget build(BuildContext context) {
    final route = action.route;
    return Card(
      key: const Key('home-next-up'),
      child: Padding(
        padding: AppSpacing.card,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // アイコンは色の代わりではなく色と一緒に出す。色が見えなくても
                // 「要確認」「失敗」「処理中」が形で区別できる (Issue #25)。
                Icon(
                  action.icon,
                  size: AppIconSize.display,
                  color: action.tone.color(context),
                ),
                const SizedBox(width: AppSpacing.lg),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(action.headline, style: context.texts.titleLarge),
                      const SizedBox(height: AppSpacing.xs),
                      Text(
                        action.detail,
                        style: context.texts.bodyMedium?.copyWith(
                          color: context.colors.onSurfaceVariant,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
            const SizedBox(height: AppSpacing.lg),
            // ボタンを行の中ではなく下に置くのは、狭い幅でも折り返さずに
            // 済ませるため。見出しが長くなってもレイアウトが壊れない。
            Align(
              alignment: Alignment.centerRight,
              child: FilledButton(
                key: const Key('home-next-up-action'),
                onPressed: route == null ? onRefresh : () => onOpen(route),
                child: Text(action.actionLabel),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SectionHeader extends StatelessWidget {
  const _SectionHeader({
    required this.title,
    required this.hiddenTestCount,
    required this.onOpen,
  });

  final String title;
  final int hiddenTestCount;
  final ValueChanged<String> onOpen;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(child: Text(title, style: context.texts.titleMedium)),
        // ホームは直近 [HomeDashboard.maxTests] 件しか載せない。溢れた件数を
        // 言わないと「もう無い」と読めてしまうので、隠した数をここで出す。
        // 0件のときは下の入口行にある「テスト一覧」と同じ行き先なので出さない。
        if (hiddenTestCount > 0)
          TextButton(
            key: const Key('home-open-hidden-tests'),
            onPressed: () => onOpen(AppRoutes.testList),
            child: Text('他$hiddenTestCount件を見る'),
          ),
      ],
    );
  }
}

/// テスト1件のカード。「今どうなっているか」の実体はここ。
class _TestProgressCard extends StatelessWidget {
  const _TestProgressCard({required this.progress, required this.onOpen});

  final HomeTestProgress progress;
  final ValueChanged<String> onOpen;

  @override
  Widget build(BuildContext context) {
    final test = progress.test;
    return Card(
      key: Key('home-test-card-${test.id}'),
      child: Padding(
        padding: AppSpacing.card,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(test.name, style: context.texts.titleMedium),
            const SizedBox(height: AppSpacing.sm),
            if (progress.isDraft)
              const _DraftNotice()
            else ...[
              _SubmissionProgress(progress: progress, onOpen: onOpen),
              const SizedBox(height: AppSpacing.sm),
              _BucketCounts(progress: progress),
            ],
            // 手を動かす先が無いテストにはボタンも、そのぶんの余白も置かない。
            if (_resumeAction(progress, onOpen) case final action?) ...[
              const SizedBox(height: AppSpacing.md),
              action,
            ],
          ],
        ),
      ),
    );
  }
}

class _DraftNotice extends StatelessWidget {
  const _DraftNotice();

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(
          Icons.pending_actions,
          size: AppIconSize.inline,
          color: AppStatusTone.neutral.color(context),
        ),
        const SizedBox(width: AppSpacing.xs),
        Expanded(
          child: Text(
            '登録が未完了です。回答欄と設問依存関係を確認するまで答案を取り込めません。',
            style: context.texts.bodyMedium?.copyWith(
              color: context.colors.onSurfaceVariant,
            ),
          ),
        ),
      ],
    );
  }
}

/// 「進んでいる実感」の担当。件数の羅列ではなく、そのテストで自分がどこまで
/// 来たかを1本のバーで見せる。
class _SubmissionProgress extends StatelessWidget {
  const _SubmissionProgress({required this.progress, required this.onOpen});

  final HomeTestProgress progress;
  final ValueChanged<String> onOpen;

  @override
  Widget build(BuildContext context) {
    if (progress.total == 0) {
      return Text(
        'まだ答案が取り込まれていません',
        style: context.texts.bodyMedium?.copyWith(
          color: context.colors.onSurfaceVariant,
        ),
      );
    }
    final done = progress.doneCount;
    final total = progress.total;
    // **数そのものを入口にする** (Issue #113)。ボタンを1つ増やすより、既に
    // 出ている「確認済み N / M」を押せるほうが素直である -- 新しい要素が増えず、
    // 押した先が何かも自明になる。
    //
    // #68 でホームの情報量を絞ったのは正しい判断だったが、**あのときは答案キューが
    // 存在しなかった**。いまは「40枚のうちどれを見たか分からない」ほうが問題である。
    return InkWell(
      key: Key('home-open-queue-${progress.test.id}'),
      onTap: () => onOpen(AppRoutes.submissionQueue(progress.test.id)),
      borderRadius: AppRadius.smAll,
      child: Padding(
        // InkWell の反応する範囲を、文字の行より少しだけ広げる。行そのものと
        // 同じ高さだと、押せることが指先で分かりにくい。
        padding: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Text('確認済み $done / $total', style: context.texts.bodyMedium),
                // **数のすぐ隣に置く。** 押せることは形でも示さないと、InkWell の
                // 波紋だけでは触ってみるまで分からない。カードの右端へ寄せると
                // 数から600px以上離れ、別の部品に見えてしまう（実機で確認）。
                Icon(
                  Icons.chevron_right,
                  size: AppIconSize.inline,
                  color: context.colors.onSurfaceVariant,
                ),
              ],
            ),
            const SizedBox(height: AppSpacing.xs),
            // semanticsValue は渡さない -- Flutter が既定で百分率を読み上げる。
            // 件数そのものは真上の行が読まれるので、ここで重ねる必要は無い。
            LinearProgressIndicator(
              value: done / total,
              borderRadius: AppRadius.smAll,
              semanticsLabel: '${progress.test.name} の確認済み答案',
            ),
          ],
        ),
      ),
    );
  }
}

/// 0件でないbucketだけを並べる。確認済みは上の進捗バーが担当しているので
/// ここには出さない -- 同じ数字を2回書くと、どちらを読めばいいのか
/// 分からなくなる。
class _BucketCounts extends StatelessWidget {
  const _BucketCounts({required this.progress});

  final HomeTestProgress progress;

  @override
  Widget build(BuildContext context) {
    final shown = [
      for (final bucket in HomeWorkBucket.values)
        if (bucket != HomeWorkBucket.done && progress.countOf(bucket) > 0)
          (bucket, progress.countOf(bucket)),
    ];
    if (shown.isEmpty) return const SizedBox.shrink();
    return Wrap(
      spacing: AppSpacing.md,
      runSpacing: AppSpacing.xs,
      children: [
        for (final (bucket, count) in shown)
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                bucket.icon,
                size: AppIconSize.inline,
                color: bucket.tone.color(context),
              ),
              const SizedBox(width: AppSpacing.xs),
              // 「要確認 3件」まで書く。アイコンと日本語ラベルが状態を伝え、
              // 色はその区別を早く見つけさせるだけ (Issue #25)。
              Text('${bucket.label} $count件', style: context.textRoles.uiLabel),
            ],
          ),
      ],
    );
  }
}

/// そのテストで中断している作業へ戻るボタン。戻る先が無ければ `null`。
///
/// 「答案を取り込む」はここに置かない。入口行と同じ行き先が並ぶだけで、しかも
/// `AppRoutes.answerIntake` はテストを指定できないので、隣に書いてあるテスト名
/// と関係があるように見えて実際には無い (`docs/home-dashboard.md` §9)。
Widget? _resumeAction(HomeTestProgress progress, ValueChanged<String> onOpen) {
  final test = progress.test;
  if (progress.isDraft) {
    return FilledButton.tonalIcon(
      key: Key('home-resume-registration-${test.id}'),
      onPressed: () => onOpen(AppRoutes.testSettings(test.id)),
      icon: const Icon(Icons.pending_actions),
      label: const Text('登録を続ける'),
    );
  }
  final resumable = progress.resumableSubmission;
  if (resumable == null) return null;
  return FilledButton.tonalIcon(
    key: Key('home-resume-review-${test.id}'),
    onPressed: () => onOpen(
      AppRoutes.pdfReview(testId: test.id, submissionId: resumable.id),
    ),
    icon: const Icon(Icons.rate_review_outlined),
    // どの答案が開くのかを言う。ラベルの無い答案はIDしか名乗れないので、
    // そのときは「レビューを続ける」とだけ言う。
    label: Text(
      resumable.studentLabel == null
          ? 'レビューを続ける'
          : 'レビューを続ける（${resumable.studentLabel}）',
    ),
  );
}

/// 進行中の作業と関係なく常に要る入口。下に置いてあるのは、押す頻度では
/// なく「今やること」の後に来るという順序のため。
class _EntryPointRow extends StatelessWidget {
  const _EntryPointRow({required this.onOpen});

  final ValueChanged<String> onOpen;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: AppSpacing.sm,
      runSpacing: AppSpacing.sm,
      children: [
        // One entry point, not two. "テスト登録" and "答案取込" were separate
        // buttons whose names said nothing about what they were for, and they
        // stood in the wrong order -- answers had to exist before a test could
        // be finished (Issue #101).
        OutlinedButton.icon(
          key: const Key('home-open-intake'),
          onPressed: () => onOpen(AppRoutes.intake),
          icon: const Icon(Icons.drive_folder_upload),
          label: const Text('資料を取り込む'),
        ),
        OutlinedButton.icon(
          key: const Key('home-open-test-list-footer'),
          onPressed: () => onOpen(AppRoutes.testList),
          icon: const Icon(Icons.list_alt),
          label: const Text('テスト一覧'),
        ),
        OutlinedButton.icon(
          key: const Key('home-open-settings'),
          onPressed: () => onOpen(AppRoutes.settings),
          icon: const Icon(Icons.settings),
          label: const Text('設定'),
        ),
      ],
    );
  }
}
