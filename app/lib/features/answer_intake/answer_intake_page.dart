import 'package:file_picker/file_picker.dart' as picker;
import 'package:flutter/material.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/app_dependencies.dart';
import 'package:auto_scoring_app/features/pdf_review/pdf_review_page.dart';

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

/// Which operation an [_AnswerIntakePageState._errorMessage] came from, so
/// the error banner's retry button can retry *that* operation instead of
/// always retrying the upload.
enum _ErrorKind { listLoad, filePick, submit }

class _AnswerIntakePageState extends State<AnswerIntakePage> {
  final _studentLabelController = TextEditingController();
  final _submitFocusNode = FocusNode(debugLabel: '取込ボタン');

  late Future<List<TestSummary>> _testsFuture;
  String? _selectedTestId;

  // Bumped at the start of every _selectTest call; a call only applies its
  // result (or clears _loadingSubmissions) if it's still the most recently
  // issued one when it resolves -- see _selectTest.
  int _selectTestRequestId = 0;

  List<SubmissionResponse> _submissions = const [];
  bool _loadingSubmissions = false;

  // Monotonic counter bumped on every locally-applied submission update
  // (a successful create or retry). _lastLocalUpdateSeq records, per
  // submission id, the counter value at the moment it was last updated
  // locally -- so a listSubmissions() response that was in flight *before*
  // that update can be recognized as stale for that id specifically and not
  // allowed to overwrite it, even though the id isn't new (see
  // _mergeFetchedSubmissions).
  int _localUpdateSeq = 0;
  final Map<String, int> _lastLocalUpdateSeq = {};

  String? _pickedFilePath;
  String? _pickedFileName;

  bool _isSubmitting = false;
  String? _errorMessage;
  _ErrorKind? _errorKind;

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
    // A→B→A leaves two in-flight requests for the same testId "A" (the
    // original one, and the new one from switching back) -- comparing
    // against _selectedTestId alone can't tell those apart, since it's "A"
    // for both by the time either resolves. Each call gets its own strictly
    // increasing id instead; only the most recently issued one is allowed to
    // apply its result or clear the loading flag, so an older, superseded
    // request can't clobber a newer one's data (or its loading state) no
    // matter which order their responses actually arrive in.
    final requestId = ++_selectTestRequestId;
    setState(() {
      _selectedTestId = testId;
      _submissions = const [];
      _errorMessage = null;
      _errorKind = null;
    });
    if (testId == null) return;
    setState(() => _loadingSubmissions = true);
    // Captured before the request goes out: any submission locally updated
    // at or before this point is exactly what this fetch's response should
    // (eventually) reflect; anything updated *after* this point happened
    // while the fetch was already in flight, so this fetch's answer for
    // that id predates it and must not overwrite it.
    final fetchStartSeq = _localUpdateSeq;
    try {
      final submissions = await widget.dependencies.listSubmissions(testId);
      if (!mounted || requestId != _selectTestRequestId) return;
      setState(
        () => _submissions = _mergeFetchedSubmissions(
          current: _submissions,
          fetched: submissions,
          fetchStartSeq: fetchStartSeq,
          lastLocalUpdateSeq: _lastLocalUpdateSeq,
        ),
      );
    } on SidecarApiException catch (error) {
      if (!mounted || requestId != _selectTestRequestId) return;
      setState(() {
        _errorMessage = error.message;
        _errorKind = _ErrorKind.listLoad;
      });
    } finally {
      if (mounted && requestId == _selectTestRequestId) {
        setState(() => _loadingSubmissions = false);
      }
    }
  }

  Future<void> _pickFile() async {
    try {
      final picked = await widget.pickFile();
      if (!mounted) return;
      if (picked == null) return;
      setState(() {
        _pickedFilePath = picked.path;
        _pickedFileName = picked.name;
        _errorMessage = null;
        _errorKind = null;
      });
    } catch (error) {
      // widget.pickFile() talks to a native platform channel/dialog, which
      // can fail (an OS-level error, a denied permission, ...). Left
      // uncaught, that would leak out of this button's onPressed callback
      // as an unhandled async error, leaving the screen showing no error
      // and no way to retry -- exactly the state every other failure path
      // here (list load, submit) already avoids.
      if (!mounted) return;
      setState(() {
        _errorMessage = 'ファイルの選択に失敗しました: $error';
        _errorKind = _ErrorKind.filePick;
      });
    }
  }

  Future<void> _submit() async {
    final testId = _selectedTestId;
    final filePath = _pickedFilePath;
    if (testId == null || filePath == null || _isSubmitting) return;

    setState(() {
      _isSubmitting = true;
      _errorMessage = null;
      _errorKind = null;
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
          _localUpdateSeq++;
          _lastLocalUpdateSeq[result.id] = _localUpdateSeq;
          _submissions = _withUpserted(_submissions, result);
        }
        _pickedFilePath = null;
        _pickedFileName = null;
        _studentLabelController.clear();
      });
      _showSnackBar('取込完了: ${_stateLabel(result.state)}');
    } on DuplicateSubmissionException catch (error) {
      if (!mounted) return;
      setState(() {
        _errorMessage =
            '同じ内容の答案は既に取り込まれています（既存の答案ID: ${error.existingSubmissionId}）';
        _errorKind = _ErrorKind.submit;
      });
    } on SidecarApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _errorMessage = error.message;
        _errorKind = _ErrorKind.submit;
      });
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
          // CustomScrollView, not a fixed Column+Expanded: on a short
          // viewport -- a small window, a phone in landscape, or the
          // student-label field's keyboard eating half the screen -- the
          // form controls above the submission list no longer fit their
          // non-flex space and would otherwise overflow (RenderFlex) and
          // hide whatever's below the cut. Everything scrolls as one unit
          // instead, and the submission list still fills any leftover space
          // when there's room for it (SliverFillRemaining below).
          child: CustomScrollView(
            slivers: [
              SliverToBoxAdapter(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    _buildTestPicker(),
                    const SizedBox(height: 16),
                    _buildFilePicker(),
                    const SizedBox(height: 16),
                    TextField(
                      controller: _studentLabelController,
                      enabled: !_isSubmitting,
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
                    Text(
                      '取込済み答案',
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    const SizedBox(height: 8),
                  ],
                ),
              ),
              _buildSubmissionSliver(),
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
          onPressed: _isSubmitting ? null : _pickFile,
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
    // A list-load failure must retry *that* fetch, not start an upload: the
    // shared error banner used to always wire this button to _submit, so a
    // list failure with a file already picked would silently upload instead
    // of reloading the list it actually reported failing to load.
    final VoidCallback? retry = switch (_errorKind) {
      _ErrorKind.listLoad =>
        _loadingSubmissions ? null : () => _selectTest(_selectedTestId),
      _ErrorKind.filePick => _isSubmitting ? null : _pickFile,
      _ErrorKind.submit || null => _canSubmit ? _submit : null,
    };
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
            TextButton(onPressed: retry, child: const Text('再試行')),
          ],
        ),
      ),
    );
  }

  Widget _buildSubmissionSliver() {
    if (_selectedTestId == null) {
      return const SliverFillRemaining(
        hasScrollBody: false,
        child: Center(child: Text('テストを選択してください')),
      );
    }
    if (_loadingSubmissions) {
      return const SliverFillRemaining(
        hasScrollBody: false,
        child: Center(child: CircularProgressIndicator()),
      );
    }
    if (_submissions.isEmpty) {
      return const SliverFillRemaining(
        hasScrollBody: false,
        child: Center(child: Text('まだ答案が取り込まれていません')),
      );
    }
    return SliverList.separated(
      itemCount: _submissions.length,
      separatorBuilder: (_, _) => const Divider(height: 1),
      itemBuilder: (context, index) {
        final submission = _submissions[index];
        final (icon, label) = _stateVisual(submission.state);
        return ListTile(
          key: Key('submission-tile-$index'),
          leading: Icon(icon),
          title: Text(submission.studentLabel ?? submission.id),
          subtitle: Text(
            submission.reviewReason != null
                ? '$label ・ ${submission.reviewReason}'
                : label,
          ),
          // 添削レビュー画面 (Issue #21) への入口 -- テストが選ばれている限り、
          // どの取込状態の答案でも開ける(要確認/エラーの答案ほどレビューが必要)。
          onTap: () => Navigator.of(context).push(
            MaterialPageRoute<void>(
              builder: (_) => PdfReviewPage(
                dependencies: widget.dependencies,
                testId: _selectedTestId!,
                submissionId: submission.id,
              ),
            ),
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

/// Merge a fresh `listSubmissions` [fetched] result with [current], without
/// letting [fetched] overwrite anything [current] knows is newer.
///
/// [fetched] reflects the server's state as of whenever the request that
/// produced it was actually *answered* server-side -- which can be before a
/// local update this page already applied, if that update (a create or a
/// successful retry, via [_withUpserted]) landed while the fetch was still
/// in flight. [lastLocalUpdateSeq] records the [_localUpdateSeq] value at
/// each such local update; a submission is kept from [current] instead of
/// [fetched] whenever its recorded sequence number is greater than
/// [fetchStartSeq] (the counter's value when this fetch was issued) --
/// whether or not [fetched] happens to already contain that id. This is what
/// [_withLocalOnlyPreserved]'s old "keep it if `fetched` doesn't have this id
/// at all" rule missed: an *existing* id updated locally after the fetch
/// started (e.g. a retry that reused its errored submission's id) would
/// still be found in a [fetched] response snapshotted before that retry
/// landed, and the old rule let that stale copy win.
List<SubmissionResponse> _mergeFetchedSubmissions({
  required List<SubmissionResponse> current,
  required List<SubmissionResponse> fetched,
  required int fetchStartSeq,
  required Map<String, int> lastLocalUpdateSeq,
}) {
  final updatedAfterFetchStarted = current.where(
    (local) => (lastLocalUpdateSeq[local.id] ?? 0) > fetchStartSeq,
  );
  final newerLocalIds = updatedAfterFetchStarted.map((s) => s.id).toSet();
  final notSupersededByLocal = fetched.where(
    (f) => !newerLocalIds.contains(f.id),
  );
  return [...updatedAfterFetchStarted, ...notSupersededByLocal];
}

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
