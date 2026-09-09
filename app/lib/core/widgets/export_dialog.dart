import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/app_dependencies.dart';
import 'package:auto_scoring_app/core/design/design_tokens.dart';

/// Shows the "PDF出力" flow (Issue #23, simplified-design-specification.md
/// §16.5): request the annotated-PDF export, poll its `Job` until it reaches
/// a terminal state, and display the result -- the saved file's path on
/// success, or the failure with a 再試行 (retry) action.
///
/// Progress/retry are a thin UI over the existing job endpoints
/// (`AppDependencies.getJob`/`retryJob`) exactly as `api.export_router`
/// intends -- this dialog invents no new polling protocol of its own.
///
/// `features/pdf_review/` から `core/widgets/` へ移した (Issue #137)。出力を
/// 起動する画面が添削レビューだけではなくなり (答案キューの行からも出す)、
/// **`features` どうしの import を作らずに済ませるため**である -- 依存方向は
/// `features → core → api` (`docs/technology-stack.md` §5) で、`core/widgets/`
/// はまさに「複数画面で重複していた見た目の要素」の置き場。移す前の時点で
/// `features` を1つも import していなかったので、そのまま動く。
///
/// **答案の状態は見ない。** 出力してよいかを決めるのはサイドカーで、未確定の
/// 設問があれば 409 が返り、それを [_ExportStage.unconfirmed] が設問名まで
/// 出して伝える。呼ぶ側が先回りして「この答案はまだだろう」と判断しないこと --
/// 判断が2か所に増えれば、必ず食い違う。
Future<void> showExportDialog(
  BuildContext context, {
  required String submissionId,
}) {
  return showDialog<void>(
    context: context,
    barrierDismissible: false,
    builder: (dialogContext) => ExportDialog(submissionId: submissionId),
  );
}

enum _ExportStage { running, succeeded, unconfirmed, failed }

/// What `_retry()` should do once the reviewer taps 再試行, derived from the
/// *last actually-observed* job state (P2 review):
///
/// - [retryJob]: the sidecar told us the job is `failed` -- `POST
///   /jobs/{id}/retry` requeues that same job.
/// - [requestNew]: the job was `cancelled` (retrying a cancelled job is
///   rejected by the sidecar -- it only accepts FAILED ones), or we were
///   never able to observe its state at all (a transport failure persisted
///   through every poll attempt, or the very first `requestExport` call
///   itself failed before a job even existed) -- either way, the only thing
///   left to do is ask for a brand new export.
enum _RetryStrategy { retryJob, requestNew }

/// One export attempt's lifecycle, from request through completion.
/// `_stage == running` covers "request in flight", "job queued/running",
/// and "a transient polling failure we're still recovering from" -- the
/// reviewer only needs to know it hasn't finished yet.
class ExportDialog extends ConsumerStatefulWidget {
  const ExportDialog({
    super.key,
    required this.submissionId,
    this.pollInterval = const Duration(seconds: 1),
  });

  final String submissionId;

  /// Overridable so widget tests don't need to wait on a real 1-second timer.
  final Duration pollInterval;

  @override
  ConsumerState<ExportDialog> createState() => _ExportDialogState();
}

class _ExportDialogState extends ConsumerState<ExportDialog> {
  /// The sidecar operations this screen was opened against, captured once in
  /// [initState] -- never re-resolved from the provider mid-request. See
  /// [appDependenciesProvider] for why that rule exists.
  late final AppDependencies _dependencies;

  /// A transport-level failure while polling (sidecar unreachable, timeout,
  /// ...) says nothing about the job itself -- it may still be running or
  /// have already succeeded. Tolerate this many consecutive failures,
  /// silently resuming polling, before finally giving up and reporting it
  /// (P2 review: reporting immediately turned a hiccup into a dead-end
  /// "retry" that the sidecar would reject with 409, since the job is
  /// neither FAILED nor CANCELLED).
  static const int _maxTransientPollFailures = 5;

  _ExportStage _stage = _ExportStage.running;
  String? _jobId;
  String? _filePath;
  String? _errorMessage;
  List<String> _unconfirmedQuestionIds = const [];

  /// The job's own last-observed terminal state (`'failed'`/`'cancelled'`),
  /// or `null` if it was never observed as terminal (still running, or every
  /// observation attempt failed at the transport level) -- what [_retry]
  /// uses to decide [_RetryStrategy].
  String? _lastObservedJobState;
  int _transientPollFailures = 0;
  Timer? _pollTimer;

  _RetryStrategy get _retryStrategy => _lastObservedJobState == 'failed'
      ? _RetryStrategy.retryJob
      : _RetryStrategy.requestNew;

  @override
  void initState() {
    super.initState();
    _dependencies = ref.read(appDependenciesProvider);
    _start();
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    super.dispose();
  }

  Future<void> _start() async {
    setState(() {
      _stage = _ExportStage.running;
      _errorMessage = null;
      _unconfirmedQuestionIds = const [];
      _jobId = null;
      _lastObservedJobState = null;
      _transientPollFailures = 0;
    });
    try {
      final result = await _dependencies.requestExport(widget.submissionId);
      if (!mounted) return;
      final existing = result.export_;
      if (existing != null) {
        // `reuse_existing` (domain.pdf_export.ReexportDecision): the current
        // review state was already exported, nothing was queued.
        setState(() {
          _stage = _ExportStage.succeeded;
          _filePath = existing.filePath;
        });
        return;
      }
      final jobId = result.jobId;
      if (jobId == null) {
        setState(() {
          _stage = _ExportStage.failed;
          _errorMessage = 'sidecar は job_id を返しませんでした';
        });
        return;
      }
      setState(() => _jobId = jobId);
      _schedulePoll();
    } on SidecarApiException catch (error) {
      if (!mounted) return;
      if (error.kind == SidecarErrorKind.conflict) {
        setState(() {
          _stage = _ExportStage.unconfirmed;
          _unconfirmedQuestionIds = error.unconfirmedQuestionIds ?? const [];
          _errorMessage = error.message;
        });
      } else {
        // No job exists yet to retry -- `_retryStrategy` already defaults to
        // `requestNew` while `_lastObservedJobState` is null.
        setState(() {
          _stage = _ExportStage.failed;
          _errorMessage = error.message;
        });
      }
    }
  }

  void _schedulePoll() {
    _pollTimer?.cancel();
    _pollTimer = Timer(widget.pollInterval, _checkJob);
  }

  Future<void> _checkJob() async {
    final jobId = _jobId;
    if (jobId == null) return;
    try {
      final job = await _dependencies.getJob(jobId);
      if (!mounted) return;
      switch (job.state) {
        case 'succeeded':
          // Not resetting `_transientPollFailures` here -- only once
          // `_loadExportedFile` itself succeeds (P2 review, round 2): a
          // `getJob` that keeps succeeding while `listExports` keeps
          // failing would otherwise reset the counter back to 0 every
          // cycle (this method only ever increments it by 1 before
          // scheduling the next poll), so the failure cap below could
          // never actually trip and the dialog would spin forever.
          await _loadExportedFile(jobId);
        case 'failed':
          _transientPollFailures = 0;
          setState(() {
            _stage = _ExportStage.failed;
            _lastObservedJobState = 'failed';
            _errorMessage = job.lastError ?? '出力に失敗しました';
          });
        case 'cancelled':
          _transientPollFailures = 0;
          setState(() {
            _stage = _ExportStage.failed;
            _lastObservedJobState = 'cancelled';
            _errorMessage = '出力がキャンセルされました';
          });
        default:
          _transientPollFailures = 0;
          _schedulePoll();
      }
    } on SidecarApiException catch (error) {
      if (!mounted) return;
      _transientPollFailures += 1;
      if (_transientPollFailures < _maxTransientPollFailures) {
        // Resume observation rather than reporting a failure the job may
        // not actually have (see `_maxTransientPollFailures`'s docstring).
        _schedulePoll();
        return;
      }
      setState(() {
        _stage = _ExportStage.failed;
        _lastObservedJobState = null;
        _errorMessage = '進捗の取得に失敗しました: ${error.message}';
      });
    }
  }

  Future<void> _loadExportedFile(String jobId) async {
    try {
      final exports = await _dependencies.listExports(widget.submissionId);
      _transientPollFailures = 0;
      if (!mounted) return;
      final match = exports.where((export) => export.jobId == jobId);
      setState(() {
        _stage = _ExportStage.succeeded;
        _filePath = match.isNotEmpty ? match.last.filePath : null;
      });
    } on SidecarApiException catch (error) {
      if (!mounted) return;
      // The export job itself succeeded -- only fetching its resulting
      // `Export` row failed at the transport level. Resume observation the
      // same way `_checkJob` does for a mid-poll transport failure, rather
      // than reporting a job that actually succeeded as failed.
      _transientPollFailures += 1;
      if (_transientPollFailures < _maxTransientPollFailures) {
        _schedulePoll();
        return;
      }
      setState(() {
        _stage = _ExportStage.failed;
        _lastObservedJobState = null;
        _errorMessage = '出力結果の取得に失敗しました: ${error.message}';
      });
    }
  }

  Future<void> _retry() async {
    if (_retryStrategy == _RetryStrategy.requestNew) {
      // The job was cancelled (retrying it is rejected by the sidecar --
      // only a FAILED job can be requeued) or its state was never actually
      // observed -- a fresh export request is the only thing left to try.
      await _start();
      return;
    }
    final jobId = _jobId;
    if (jobId == null) return;
    setState(() {
      _stage = _ExportStage.running;
      _errorMessage = null;
    });
    try {
      await _dependencies.retryJob(jobId);
      _schedulePoll();
    } on SidecarApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _stage = _ExportStage.failed;
        _errorMessage = error.message;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('PDF出力'),
      content: SizedBox(
        width: AppLayout.dialogContentWidth,
        child: _buildContent(),
      ),
      actions: _buildActions(),
    );
  }

  Widget _buildContent() {
    switch (_stage) {
      case _ExportStage.running:
        return const Row(
          key: Key('export-dialog-progress'),
          mainAxisSize: MainAxisSize.min,
          children: [
            SizedBox(
              width: AppIconSize.standard,
              height: AppIconSize.standard,
              child: CircularProgressIndicator(strokeWidth: 2),
            ),
            SizedBox(width: AppSpacing.lg),
            Expanded(child: Text('出力しています…')),
          ],
        );
      case _ExportStage.succeeded:
        return Text(
          key: const Key('export-dialog-success'),
          _filePath != null ? '保存先: $_filePath' : '出力が完了しました',
        );
      case _ExportStage.unconfirmed:
        return Column(
          key: const Key('export-dialog-unconfirmed'),
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text('未確認の設問があるため出力できません:'),
            const SizedBox(height: AppSpacing.sm),
            if (_unconfirmedQuestionIds.isEmpty)
              Text(_errorMessage ?? '')
            else
              for (final questionId in _unconfirmedQuestionIds)
                Text('・$questionId'),
          ],
        );
      case _ExportStage.failed:
        return Text(
          key: const Key('export-dialog-error'),
          _errorMessage ?? '出力に失敗しました',
        );
    }
  }

  List<Widget> _buildActions() {
    switch (_stage) {
      case _ExportStage.running:
        return [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('閉じる'),
          ),
        ];
      case _ExportStage.failed:
        return [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('閉じる'),
          ),
          FilledButton(
            key: const Key('export-dialog-retry-button'),
            onPressed: _retry,
            child: const Text('再試行'),
          ),
        ];
      case _ExportStage.succeeded:
      case _ExportStage.unconfirmed:
        return [
          FilledButton(
            key: const Key('export-dialog-close-button'),
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('閉じる'),
          ),
        ];
    }
  }
}
