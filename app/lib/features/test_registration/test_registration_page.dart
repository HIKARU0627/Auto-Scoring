import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/app_dependencies.dart';
import 'package:auto_scoring_app/core/app_routes.dart';
import 'package:auto_scoring_app/core/pdf_file_picker.dart';

/// テスト登録画面 (simplified-design-specification.md §16.2, Issue #16).
///
/// Registers a new test's 模範解答PDF (model answer) + 採点マニュアルPDF
/// (marking manual). On success, opens `TestSettingsPage` so the reviewer can
/// immediately run candidate detection and confirm the profile / dependency
/// graph -- registration is not "complete" until that follow-up flow finishes
/// (`Test.status` stays `draft` until `completeRegistration` succeeds).
class TestRegistrationPage extends ConsumerStatefulWidget {
  const TestRegistrationPage({super.key});

  @override
  ConsumerState<TestRegistrationPage> createState() =>
      _TestRegistrationPageState();
}

enum _PdfSlot { modelAnswer, manual }

class _TestRegistrationPageState extends ConsumerState<TestRegistrationPage> {
  /// The sidecar operations this screen was opened against, captured once in
  /// [initState] -- never re-resolved from the provider mid-request. See
  /// [appDependenciesProvider] for why that rule exists.
  late final AppDependencies _dependencies;

  /// The native "choose a PDF" dialog. Captured in [initState] for the same
  /// reason as [_dependencies].
  late final Future<PickedPdfFile?> Function() _pickPdfFile;

  final _nameController = TextEditingController();
  final _subjectController = TextEditingController();

  String? _modelAnswerPath;
  String? _modelAnswerName;
  String? _manualPath;
  String? _manualName;

  bool _isSubmitting = false;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    _dependencies = ref.read(appDependenciesProvider);
    _pickPdfFile = ref.read(pickPdfFileProvider);
  }

  @override
  void dispose() {
    _nameController.dispose();
    _subjectController.dispose();
    super.dispose();
  }

  bool get _canSubmit =>
      !_isSubmitting &&
      _nameController.text.trim().isNotEmpty &&
      _modelAnswerPath != null &&
      _manualPath != null;

  Future<void> _pickFile(_PdfSlot slot) async {
    try {
      final picked = await _pickPdfFile();
      if (!mounted || picked == null) return;
      setState(() {
        switch (slot) {
          case _PdfSlot.modelAnswer:
            _modelAnswerPath = picked.path;
            _modelAnswerName = picked.name;
          case _PdfSlot.manual:
            _manualPath = picked.path;
            _manualName = picked.name;
        }
        _errorMessage = null;
      });
    } catch (error) {
      // Mirrors AnswerIntakePage._pickFile: a native file-picker failure must
      // surface through the same retry-able error banner, not crash the
      // button's onPressed callback as an unhandled async error.
      if (!mounted) return;
      setState(() => _errorMessage = 'ファイルの選択に失敗しました: $error');
    }
  }

  Future<void> _submit() async {
    final modelAnswerPath = _modelAnswerPath;
    final manualPath = _manualPath;
    if (modelAnswerPath == null || manualPath == null || _isSubmitting) return;

    setState(() {
      _isSubmitting = true;
      _errorMessage = null;
    });
    final name = _nameController.text.trim();
    final subject = _subjectController.text.trim();
    try {
      final test = await _dependencies.createTest(
        name: name,
        subject: subject.isEmpty ? null : subject,
        modelAnswerPath: modelAnswerPath,
        manualPath: manualPath,
      );
      if (!mounted) return;
      // `GoRouter.of` rather than the `context.pushReplacement` extension:
      // that extension returns `void`, and awaiting the replacement's own
      // lifetime is what keeps the `finally` below from resetting
      // `_isSubmitting` on a screen that has already been replaced.
      await GoRouter.of(
        context,
      ).pushReplacement<void>(AppRoutes.testSettings(test.id));
    } on SidecarApiException catch (error) {
      if (!mounted) return;
      setState(() => _errorMessage = error.message);
    } finally {
      if (mounted) setState(() => _isSubmitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('テスト登録')),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 640),
          child: SingleChildScrollView(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                TextField(
                  key: const Key('test-name-field'),
                  controller: _nameController,
                  enabled: !_isSubmitting,
                  decoration: const InputDecoration(
                    labelText: 'テスト名',
                    border: OutlineInputBorder(),
                  ),
                  onChanged: (_) => setState(() {}),
                ),
                const SizedBox(height: 16),
                TextField(
                  key: const Key('test-subject-field'),
                  controller: _subjectController,
                  enabled: !_isSubmitting,
                  decoration: const InputDecoration(
                    labelText: '教科（任意）',
                    border: OutlineInputBorder(),
                  ),
                ),
                const SizedBox(height: 24),
                _buildFilePickerRow(
                  key: const Key('model-answer-picker'),
                  label: '模範解答PDF',
                  fileName: _modelAnswerName,
                  onPressed: () => _pickFile(_PdfSlot.modelAnswer),
                ),
                const SizedBox(height: 16),
                _buildFilePickerRow(
                  key: const Key('manual-picker'),
                  label: '採点マニュアルPDF',
                  fileName: _manualName,
                  onPressed: () => _pickFile(_PdfSlot.manual),
                ),
                const SizedBox(height: 24),
                if (_isSubmitting) const LinearProgressIndicator(),
                if (_errorMessage != null) ...[
                  const SizedBox(height: 8),
                  _buildErrorBanner(),
                ],
                const SizedBox(height: 16),
                FilledButton.icon(
                  key: const Key('register-test-button'),
                  onPressed: _canSubmit ? _submit : null,
                  icon: const Icon(Icons.add_task),
                  label: const Text('登録して解析へ進む'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildFilePickerRow({
    required Key key,
    required String label,
    required String? fileName,
    required VoidCallback onPressed,
  }) {
    return Row(
      children: [
        OutlinedButton.icon(
          key: key,
          onPressed: _isSubmitting ? null : onPressed,
          icon: const Icon(Icons.picture_as_pdf),
          label: Text(label),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Text(fileName ?? '未選択', overflow: TextOverflow.ellipsis),
        ),
      ],
    );
  }

  Widget _buildErrorBanner() {
    return Card(
      color: Theme.of(context).colorScheme.errorContainer,
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          children: [
            Icon(
              Icons.error_outline,
              color: Theme.of(context).colorScheme.onErrorContainer,
            ),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                _errorMessage!,
                style: TextStyle(
                  color: Theme.of(context).colorScheme.onErrorContainer,
                ),
              ),
            ),
            TextButton(
              onPressed: _canSubmit ? _submit : null,
              child: const Text('再試行'),
            ),
          ],
        ),
      ),
    );
  }
}
