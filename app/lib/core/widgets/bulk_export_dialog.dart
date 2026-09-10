/// テスト単位の一括PDF出力の画面 (Issue #142)。
///
/// 単発出力 (`export_dialog.dart`) は残してある。1枚だけ出し直したい場面は
/// 実在するし、あちらは答案の状態を一切見ないので、いつでも押せる。
///
/// 進み方は4段 -- **対象の確認 → 出力先を1回選ぶ → 進捗 → 結果**。
/// `docs/pdf-export.md` §12 の決定そのままである:
///
/// * 対象一覧と件数を出してから走り出す。**押した瞬間に40ファイル書き始めない。**
/// * 対象外は隠さず、理由を並べる。
/// * 途中で止めない。失敗は理由付きで一覧に出し、その分だけ再実行できる。
/// * 「n / 全件」といま出している答案が見える。中止できる。
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:auto_scoring_app/core/app_dependencies.dart';
import 'package:auto_scoring_app/core/bulk_export.dart';
import 'package:auto_scoring_app/core/bulk_export_writer.dart';
import 'package:auto_scoring_app/core/design/app_status_tone.dart';
import 'package:auto_scoring_app/core/design/app_theme_context.dart';
import 'package:auto_scoring_app/core/design/design_tokens.dart';
import 'package:auto_scoring_app/core/review_queue.dart';

/// [queue] のうち全設問が確定した答案を、選んだフォルダへまとめて出力する。
Future<void> showBulkExportDialog(
  BuildContext context, {
  required String testId,
  required ReviewQueue queue,
  Future<String?> Function()? chooseDirectory,
  BulkExportFileWriter? writeFile,
  Duration pollInterval = const Duration(milliseconds: 500),
}) {
  return showDialog<void>(
    context: context,
    barrierDismissible: false,
    builder: (dialogContext) => BulkExportDialog(
      testId: testId,
      plan: BulkExportPlan.from(queue),
      chooseDirectory: chooseDirectory ?? chooseBulkExportDirectory,
      writeFile: writeFile ?? writeBulkExportFile,
      pollInterval: pollInterval,
    ),
  );
}

enum _Stage { confirm, running, finished }

class BulkExportDialog extends ConsumerStatefulWidget {
  const BulkExportDialog({
    super.key,
    required this.testId,
    required this.plan,
    required this.chooseDirectory,
    required this.writeFile,
    this.pollInterval = const Duration(milliseconds: 500),
  });

  final String testId;
  final BulkExportPlan plan;

  /// 出力先フォルダを選ばせる。ウィジェットテストがネイティブの
  /// フォルダ選択ダイアログを開かずに済むよう注入できる。
  final Future<String?> Function() chooseDirectory;

  final BulkExportFileWriter writeFile;
  final Duration pollInterval;

  @override
  ConsumerState<BulkExportDialog> createState() => _BulkExportDialogState();
}

class _BulkExportDialogState extends ConsumerState<BulkExportDialog> {
  /// The sidecar operations this screen was opened against, captured once in
  /// [initState] -- never re-resolved from the provider mid-request. See
  /// [appDependenciesProvider] for why that rule exists.
  late final AppDependencies _dependencies;

  _Stage _stage = _Stage.confirm;
  BulkExportRunner? _runner;
  BulkExportProgress? _progress;
  String? _destinationDirectory;

  /// いま走らせている対象。再実行では**失敗した分だけ**に入れ替わる。
  late List<BulkExportTarget> _targets = widget.plan.targets;

  @override
  void initState() {
    super.initState();
    _dependencies = ref.read(appDependenciesProvider);
  }

  @override
  void dispose() {
    _runner?.cancel();
    super.dispose();
  }

  Future<void> _startWithNewDirectory() async {
    final directory = await widget.chooseDirectory();
    // 選ばなかった = やめた。何も起きずに確認の段へ戻る。
    if (directory == null || !mounted) return;
    _destinationDirectory = directory;
    await _run();
  }

  Future<void> _run() async {
    final directory = _destinationDirectory;
    if (directory == null) return;
    final runner = BulkExportRunner(
      dependencies: _dependencies,
      writeFile: widget.writeFile,
      pollInterval: widget.pollInterval,
    );
    setState(() {
      _runner = runner;
      _stage = _Stage.running;
      _progress = null;
    });
    final result = await runner.run(
      testId: widget.testId,
      targets: _targets,
      destinationDirectory: directory,
      onProgress: (progress) {
        if (!mounted) return;
        setState(() => _progress = progress);
      },
    );
    if (!mounted) return;
    setState(() {
      _progress = result;
      _stage = _Stage.finished;
      _runner = null;
    });
  }

  Future<void> _retryFailures() async {
    final retryable = _progress?.retryableTargets ?? const <BulkExportTarget>[];
    if (retryable.isEmpty) return;
    _targets = retryable;
    await _run();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('まとめてPDF出力'),
      content: SizedBox(
        width: AppLayout.dialogContentWidth,
        child: SingleChildScrollView(child: _buildContent()),
      ),
      actions: _buildActions(),
    );
  }

  Widget _buildContent() {
    switch (_stage) {
      case _Stage.confirm:
        return _ConfirmBody(plan: widget.plan);
      case _Stage.running:
        return _RunningBody(
          progress: _progress,
          totalCount: _targets.length,
          destinationDirectory: _destinationDirectory,
        );
      case _Stage.finished:
        return _FinishedBody(
          progress: _progress,
          destinationDirectory: _destinationDirectory,
        );
    }
  }

  List<Widget> _buildActions() {
    switch (_stage) {
      case _Stage.confirm:
        return [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('閉じる'),
          ),
          FilledButton(
            key: const Key('bulk-export-start-button'),
            // 対象が0件なら押せない。押した先で必ず何も起きないボタンを
            // 生かしておくと、講師は自分の操作を疑うことになる。
            onPressed: widget.plan.hasTargets ? _startWithNewDirectory : null,
            child: const Text('出力先を選んで開始'),
          ),
        ];
      case _Stage.running:
        return [
          TextButton(
            key: const Key('bulk-export-cancel-button'),
            onPressed: () => _runner?.cancel(),
            child: const Text('中止'),
          ),
        ];
      case _Stage.finished:
        final retryable =
            _progress?.retryableTargets ?? const <BulkExportTarget>[];
        return [
          if (retryable.isNotEmpty)
            TextButton(
              key: const Key('bulk-export-retry-button'),
              onPressed: _retryFailures,
              child: Text('失敗した${retryable.length}件を再実行'),
            ),
          FilledButton(
            key: const Key('bulk-export-close-button'),
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('閉じる'),
          ),
        ];
    }
  }
}

/// 実行前に人が見るもの -- 何件出るか、何件出ないか、なぜ出ないか。
class _ConfirmBody extends StatelessWidget {
  const _ConfirmBody({required this.plan});

  final BulkExportPlan plan;

  @override
  Widget build(BuildContext context) {
    if (!plan.hasTargets) {
      return Column(
        key: const Key('bulk-export-empty'),
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          // **0件でも理由まで出す。** 「出力できる答案がありません」だけでは、
          // 講師は次に何をすればよいのか分からないまま画面を閉じることになる。
          Text(
            plan.excluded.isEmpty
                ? 'このテストにはまだ答案がありません。'
                : '出力できる答案がありません。全設問を確定させると対象になります。',
          ),
          if (plan.excluded.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.md),
            _ExclusionList(excluded: plan.excluded),
          ],
        ],
      );
    }
    return Column(
      key: const Key('bulk-export-confirm'),
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text('対象 ${plan.targets.length}件', style: context.texts.titleSmall),
        const SizedBox(height: AppSpacing.sm),
        for (final target in plan.targets) Text('・${target.label}'),
        if (plan.excluded.isNotEmpty) ...[
          const SizedBox(height: AppSpacing.lg),
          _ExclusionList(excluded: plan.excluded),
        ],
        const SizedBox(height: AppSpacing.lg),
        Text('答案ごとに1ファイルへ分けて、選んだフォルダに保存します。', style: context.texts.bodySmall),
      ],
    );
  }
}

class _ExclusionList extends StatelessWidget {
  const _ExclusionList({required this.excluded});

  final List<BulkExportExclusion> excluded;

  @override
  Widget build(BuildContext context) {
    return Column(
      key: const Key('bulk-export-excluded'),
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text('対象外 ${excluded.length}件', style: context.texts.titleSmall),
        const SizedBox(height: AppSpacing.sm),
        for (final row in excluded) Text('・${row.label}: ${row.reason}'),
      ],
    );
  }
}

/// 走っている最中。**無音で止まって見える状態を作らない。**
class _RunningBody extends StatelessWidget {
  const _RunningBody({
    required this.progress,
    required this.totalCount,
    required this.destinationDirectory,
  });

  final BulkExportProgress? progress;
  final int totalCount;
  final String? destinationDirectory;

  @override
  Widget build(BuildContext context) {
    final settled = progress?.settledCount ?? 0;
    final total = progress?.totalCount ?? totalCount;
    return Column(
      key: const Key('bulk-export-progress'),
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text('$settled / $total 件'),
        const SizedBox(height: AppSpacing.sm),
        LinearProgressIndicator(
          value: total == 0 ? 0 : settled / total,
          borderRadius: AppRadius.smAll,
          semanticsLabel: '一括PDF出力の進捗',
        ),
        const SizedBox(height: AppSpacing.md),
        // どの答案で待たされているのかが見えないと、遅いのか壊れたのかが
        // 区別できない。
        Text('出力中: ${progress?.currentLabel ?? '準備しています…'}'),
        if (destinationDirectory != null) ...[
          const SizedBox(height: AppSpacing.md),
          Text('保存先: $destinationDirectory', style: context.texts.bodySmall),
        ],
      ],
    );
  }
}

/// 終わったあと -- 何件書けて、何が出せなかったか。
class _FinishedBody extends StatelessWidget {
  const _FinishedBody({
    required this.progress,
    required this.destinationDirectory,
  });

  final BulkExportProgress? progress;
  final String? destinationDirectory;

  @override
  Widget build(BuildContext context) {
    final result = progress;
    if (result == null) {
      return const Text('出力が終わりました。');
    }
    final failures = result.failures;
    final cancelled = result.cancelled;
    return Column(
      key: const Key('bulk-export-result'),
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text('${result.writtenCount} / ${result.totalCount} 件を出力しました。'),
        if (destinationDirectory != null) ...[
          const SizedBox(height: AppSpacing.sm),
          Text('保存先: $destinationDirectory', style: context.texts.bodySmall),
        ],
        if (cancelled.isNotEmpty) ...[
          const SizedBox(height: AppSpacing.md),
          // 講師が自分で止めたものを「失敗」と呼ばない。
          Text('中止したため${cancelled.length}件は出していません。'),
        ],
        if (failures.isNotEmpty) ...[
          const SizedBox(height: AppSpacing.lg),
          Text(
            '出せなかった答案 ${failures.length}件',
            key: const Key('bulk-export-failures'),
            style: context.texts.titleSmall?.copyWith(
              color: AppStatusTone.danger.color(context),
            ),
          ),
          const SizedBox(height: AppSpacing.sm),
          for (final failure in failures)
            Text(
              '・${failure.target.label}: ${failure.failureReason ?? '理由不明'}',
            ),
        ],
      ],
    );
  }
}
