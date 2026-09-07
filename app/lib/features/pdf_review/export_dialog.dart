import 'dart:async';

import 'package:flutter/material.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/app_dependencies.dart';

/// Shows the "PDF出力" flow (Issue #23, simplified-design-specification.md
/// §16.5): request the annotated-PDF export, poll its `Job` until it reaches
/// a terminal state, and display the result -- the saved file's path on
/// success, or the failure with a 再試行 (retry) action.
///
/// Progress/retry are a thin UI over the existing job endpoints
/// (`AppDependencies.getJob`/`retryJob`) exactly as `api.export_router`
/// intends -- this dialog invents no new polling protocol of its own.
Future<void> showExportDialog(
  BuildContext context, {
  required AppDependencies dependencies,
  required String submissionId,
}) {
  return showDialog<void>(
    context: context,
    barrierDismissible: false,
    builder: (dialogContext) =>
        ExportDialog(dependencies: dependencies, submissionId: submissionId),
  );
}

enum _ExportStage { running, succeeded, unconfirmed, failed }

/// One export attempt's lifecycle, from request through completion.
/// `_stage == running` covers both "request in flight" and "job queued/
/// running" -- the reviewer only needs to know it hasn't finished yet.
class ExportDialog extends StatefulWidget {
  const ExportDialog({
    super.key,
    required this.dependencies,
    required this.submissionId,
    this.pollInterval = const Duration(seconds: 1),
  });

  final AppDependencies dependencies;
  final String submissionId;

  /// Overridable so widget tests don't need to wait on a real 1-second timer.
  final Duration pollInterval;

  @override
  State<ExportDialog> createState() => _ExportDialogState();
}

class _ExportDialogState extends State<ExportDialog> {
  _ExportStage _stage = _ExportStage.running;
  String? _jobId;
  String? _filePath;
  String? _errorMessage;
  List<String> _unconfirmedQuestionIds = const [];
  Timer? _pollTimer;

  @override
  void initState() {
    super.initState();
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
    });
    try {
      final result = await widget.dependencies.requestExport(
        widget.submissionId,
      );
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
      final job = await widget.dependencies.getJob(jobId);
      if (!mounted) return;
      switch (job.state) {
        case 'succeeded':
          await _loadExportedFile(jobId);
        case 'failed':
          setState(() {
            _stage = _ExportStage.failed;
            _errorMessage = job.lastError ?? '出力に失敗しました';
          });
        case 'cancelled':
          setState(() {
            _stage = _ExportStage.failed;
            _errorMessage = '出力がキャンセルされました';
          });
        default:
          _schedulePoll();
      }
    } on SidecarApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _stage = _ExportStage.failed;
        _errorMessage = error.message;
      });
    }
  }

  Future<void> _loadExportedFile(String jobId) async {
    try {
      final exports = await widget.dependencies.listExports(
        widget.submissionId,
      );
      if (!mounted) return;
      final match = exports.where((export) => export.jobId == jobId);
      setState(() {
        _stage = _ExportStage.succeeded;
        _filePath = match.isNotEmpty ? match.last.filePath : null;
      });
    } on SidecarApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _stage = _ExportStage.failed;
        _errorMessage = error.message;
      });
    }
  }

  Future<void> _retry() async {
    final jobId = _jobId;
    if (jobId == null) return;
    setState(() {
      _stage = _ExportStage.running;
      _errorMessage = null;
    });
    try {
      await widget.dependencies.retryJob(jobId);
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
      content: SizedBox(width: 360, child: _buildContent()),
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
              width: 20,
              height: 20,
              child: CircularProgressIndicator(strokeWidth: 2),
            ),
            SizedBox(width: 16),
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
            const SizedBox(height: 8),
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
            onPressed: _jobId == null ? null : _retry,
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
