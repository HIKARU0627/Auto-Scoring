import 'package:file_picker/file_picker.dart' as picker;
import 'package:flutter/material.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/app_dependencies.dart';

/// A PDF chosen from the native file picker. Kept separate from
/// `package:file_picker`'s own `PlatformFile` so [AnswerIntakePage] can be
/// driven by a fake in widget tests without touching a platform channel.
class PickedPdfFile {
  const PickedPdfFile({required this.path, required this.name});

  final String path;
  final String name;
}

Future<PickedPdfFile?> _pickPdfFromNativeDialog() async {
  final picked = await picker.FilePicker.pickFile(
    type: picker.FileType.custom,
    allowedExtensions: const ['pdf'],
  );
  if (picked?.path == null) return null;
  return PickedPdfFile(path: picked!.path!, name: picked.name);
}

/// 答案取込画面 (simplified-design-specification.md §16.4).
///
/// Picks a test, picks one answer PDF, and uploads it. Shows upload
/// progress, surfaces intake errors with a retry action, and lists every
/// submission already imported for the selected test so the outcome
/// (`ai_processed` / `needs_review` / `error`, see §25) is visible without
/// leaving the screen.
///
/// `features` may depend on `core` and `api` (see `AGENTS.md` "Architecture").
class AnswerIntakePage extends StatefulWidget {
  const AnswerIntakePage({
    super.key,
    required this.dependencies,
    this.pickFile = _pickPdfFromNativeDialog,
  });

  final AppDependencies dependencies;

  /// Opens the native "choose a PDF" dialog. Overridable so widget tests can
  /// simulate a pick without a real platform channel.
  final Future<PickedPdfFile?> Function() pickFile;

  @override
  State<AnswerIntakePage> createState() => _AnswerIntakePageState();
}

class _AnswerIntakePageState extends State<AnswerIntakePage> {
  final _studentLabelController = TextEditingController();
  final _submitFocusNode = FocusNode(debugLabel: '取込ボタン');

  late Future<List<TestSummary>> _testsFuture;
  String? _selectedTestId;

  List<SubmissionResponse> _submissions = const [];
  bool _loadingSubmissions = false;

  String? _pickedFilePath;
  String? _pickedFileName;

  bool _isSubmitting = false;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    _testsFuture = widget.dependencies.listTests();
  }

  @override
  void dispose() {
    _studentLabelController.dispose();
    _submitFocusNode.dispose();
    super.dispose();
  }

  bool get _canSubmit =>
      !_isSubmitting && _selectedTestId != null && _pickedFilePath != null;

  Future<void> _selectTest(String? testId) async {
    setState(() {
      _selectedTestId = testId;
      _submissions = const [];
      _errorMessage = null;
    });
    if (testId == null) return;
    setState(() => _loadingSubmissions = true);
    try {
      final submissions = await widget.dependencies.listSubmissions(testId);
      if (!mounted || _selectedTestId != testId) return;
      setState(() => _submissions = submissions);
    } on SidecarApiException catch (error) {
      if (!mounted || _selectedTestId != testId) return;
      setState(() => _errorMessage = error.message);
    } finally {
      if (mounted && _selectedTestId == testId) {
        setState(() => _loadingSubmissions = false);
      }
    }
  }

  Future<void> _pickFile() async {
    final picked = await widget.pickFile();
    if (picked == null) return;
    setState(() {
      _pickedFilePath = picked.path;
      _pickedFileName = picked.name;
      _errorMessage = null;
    });
  }

  Future<void> _submit() async {
    final testId = _selectedTestId;
    final filePath = _pickedFilePath;
    if (testId == null || filePath == null || _isSubmitting) return;

    setState(() {
      _isSubmitting = true;
      _errorMessage = null;
    });
    final label = _studentLabelController.text.trim();
    try {
      final result = await widget.dependencies.createSubmission(
        testId: testId,
        filePath: filePath,
        studentLabel: label.isEmpty ? null : label,
      );
      if (!mounted) return;
      setState(() {
        // The test picker is disabled while `_isSubmitting`, so this should
        // always still be true; kept as a defensive check (not just the
        // disabled picker) against upserting testId's result into a
        // different test's list that happens to be showing.
        if (_selectedTestId == testId) {
          _submissions = _withUpserted(_submissions, result);
        }
        _pickedFilePath = null;
        _pickedFileName = null;
        _studentLabelController.clear();
      });
      _showSnackBar('取込完了: ${_stateLabel(result.state)}');
    } on DuplicateSubmissionException catch (error) {
      if (!mounted) return;
      setState(
        () => _errorMessage =
            '同じ内容の答案は既に取り込まれています（既存の答案ID: ${error.existingSubmissionId}）',
      );
    } on SidecarApiException catch (error) {
      if (!mounted) return;
      setState(() => _errorMessage = error.message);
    } finally {
      if (mounted) setState(() => _isSubmitting = false);
    }
  }

  void _showSnackBar(String message) {
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(SnackBar(content: Text(message)));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('答案取込')),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 640),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _buildTestPicker(),
              const SizedBox(height: 16),
              _buildFilePicker(),
              const SizedBox(height: 16),
              TextField(
                controller: _studentLabelController,
                decoration: const InputDecoration(
                  labelText: '生徒ラベル（任意）',
                  border: OutlineInputBorder(),
                ),
                textInputAction: TextInputAction.done,
                onSubmitted: (_) => _submit(),
              ),
              const SizedBox(height: 16),
              if (_isSubmitting) const LinearProgressIndicator(),
              if (_errorMessage != null) ...[
                const SizedBox(height: 8),
                _buildErrorBanner(),
              ],
              const SizedBox(height: 16),
              FilledButton.icon(
                focusNode: _submitFocusNode,
                onPressed: _canSubmit ? _submit : null,
                icon: const Icon(Icons.upload_file),
                label: const Text('取り込む'),
              ),
              const SizedBox(height: 24),
              const Divider(),
              const SizedBox(height: 8),
              Text('取込済み答案', style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 8),
              Expanded(child: _buildSubmissionList()),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildTestPicker() {
    return FutureBuilder<List<TestSummary>>(
      future: _testsFuture,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const LinearProgressIndicator();
        }
        if (snapshot.hasError) {
          return Text(
            'テスト一覧を取得できません: ${_describeError(snapshot.error)}',
            key: const Key('test-list-error'),
          );
        }
        final tests = snapshot.data ?? const [];
        if (tests.isEmpty) {
          return const Text('登録済みのテストがありません。先にテストを登録してください。');
        }
        return DropdownButtonFormField<String>(
          key: const Key('test-picker'),
          initialValue: _selectedTestId,
          decoration: const InputDecoration(
            labelText: '対象テスト',
            border: OutlineInputBorder(),
          ),
          items: [
            for (final test in tests)
              DropdownMenuItem(value: test.id, child: Text(test.name)),
          ],
          // Disabled while an upload is in flight: switching tests mid-upload
          // would otherwise let that upload's result land in whichever test's
          // list happens to be showing when it finishes.
          onChanged: _isSubmitting ? null : _selectTest,
        );
      },
    );
  }

  Widget _buildFilePicker() {
    return Row(
      children: [
        OutlinedButton.icon(
          onPressed: _pickFile,
          icon: const Icon(Icons.picture_as_pdf),
          label: const Text('ファイルを選択'),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Text(
            _pickedFileName ?? '未選択',
            overflow: TextOverflow.ellipsis,
          ),
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

  Widget _buildSubmissionList() {
    if (_selectedTestId == null) {
      return const Center(child: Text('テストを選択してください'));
    }
    if (_loadingSubmissions) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_submissions.isEmpty) {
      return const Center(child: Text('まだ答案が取り込まれていません'));
    }
    return ListView.separated(
      itemCount: _submissions.length,
      separatorBuilder: (_, _) => const Divider(height: 1),
      itemBuilder: (context, index) {
        final submission = _submissions[index];
        final (icon, label) = _stateVisual(submission.state);
        return ListTile(
          leading: Icon(icon),
          title: Text(submission.studentLabel ?? submission.id),
          subtitle: Text(
            submission.reviewReason != null
                ? '$label ・ ${submission.reviewReason}'
                : label,
          ),
        );
      },
    );
  }
}

/// Insert [result] at the front of [submissions], replacing an existing
/// entry with the same id rather than duplicating it. A successful retry
/// returns the *same* submission id as the earlier failed attempt (Issue
/// #17's reintake policy reuses the row), so without this the list would
/// show both the stale error row and the new one for the same submission.
List<SubmissionResponse> _withUpserted(
  List<SubmissionResponse> submissions,
  SubmissionResponse result,
) => [result, ...submissions.where((s) => s.id != result.id)];

String _describeError(Object? error) =>
    error is SidecarApiException ? error.message : '$error';

String _stateLabel(String state) => _stateVisual(state).$2;

(IconData, String) _stateVisual(String state) => switch (state) {
  'unprocessed' => (Icons.hourglass_empty, '未処理'),
  'ai_processing' => (Icons.autorenew, '処理中'),
  'ai_processed' => (Icons.check_circle_outline, '処理済み'),
  'needs_review' => (Icons.warning_amber, '要確認'),
  'reviewed' => (Icons.verified_outlined, '確認済み'),
  'exported' => (Icons.file_download_done, '出力済み'),
  'error' => (Icons.error_outline, 'エラー'),
  _ => (Icons.help_outline, state),
};
