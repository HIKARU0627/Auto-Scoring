import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/app_dependencies.dart';
import 'package:auto_scoring_app/core/app_routes.dart';
import 'package:auto_scoring_app/core/design/design_tokens.dart';
import 'package:auto_scoring_app/core/folder_scan.dart';
import 'package:auto_scoring_app/core/grading_kickoff.dart';
import 'package:auto_scoring_app/core/intake_review.dart';
import 'package:auto_scoring_app/core/material_role_labels.dart';
import 'package:auto_scoring_app/core/widgets/app_error_banner.dart';

/// 資料取込画面 — the single flow that replaced テスト登録 and 答案取込
/// (Issue #101).
///
/// Three steps: **choose a folder → check what will be imported → import**.
/// They were two separate screens before, in the wrong order: answers had to
/// exist before a test could be finished, but the app made you register the
/// test first, and neither screen said what the other was for.
///
/// Two rules this screen exists to enforce:
///
/// * **Nothing is imported that has not been confirmed.** An AI proposal that
///   the reviewer has not looked at disables the import button; there is no
///   setting to skip it. The classifier's accuracy has not been measured, and
///   until it has, a silently misfiled answer would be graded against the
///   wrong test's criteria.
/// * **Importing is not "ready to grade".** The completion step says what is
///   still missing (points and marking criteria) and links to the screen where
///   it is entered, rather than implying grading can start.
class IntakePage extends ConsumerStatefulWidget {
  const IntakePage({super.key});

  @override
  ConsumerState<IntakePage> createState() => _IntakePageState();
}

enum _Step { choose, review, done }

/// How many classification requests are in flight at once.
///
/// The wait is a provider round trip, and page rendering already serializes on
/// the sidecar's PDFium lock, so a small amount of concurrency shortens the
/// wall clock without needing any new locking. Three rather than more because
/// the point is to keep a folder of forty unmatched files from taking minutes,
/// not to saturate anyone's rate limit.
const int _classifyConcurrency = 3;

class _ImportOutcome {
  const _ImportOutcome({
    required this.groupKey,
    required this.name,
    this.testId,
    this.materialCount = 0,
    this.submissionCount = 0,
    this.duplicateCount = 0,
    this.gradingStartedCount = 0,
    this.gradingFailure,
    this.error,
  });

  final String groupKey;
  final String name;
  final String? testId;
  final int materialCount;
  final int submissionCount;

  /// Answers whose content was already imported for this test. Not a failure:
  /// the sidecar recognizes the same bytes and returns the existing
  /// submission, which is what makes retrying a partial batch safe.
  final int duplicateCount;
  final String? error;

  /// Answers whose AI grading was actually queued.
  ///
  /// Separate from [submissionCount] because "the answer is in" and "grading
  /// started" are two different facts, and the second one fails on its own --
  /// most often because the test has no confirmed question dependencies yet,
  /// which is the normal state for a test registered moments ago (Issue #80).
  final int gradingStartedCount;

  /// Why grading did not start, in the reviewer's words. `null` when nothing
  /// tried or everything succeeded.
  final String? gradingFailure;

  bool get succeeded => error == null;
}

class _IntakePageState extends ConsumerState<IntakePage> {
  late final AppDependencies _dependencies;
  late final Future<String?> Function() _chooseFolder;
  late final Future<ScannedFolder> Function(String) _scanFolder;

  _Step _step = _Step.choose;
  bool _busy = false;
  String? _error;

  List<IntakeTemplateModel> _templates = const [];
  String? _templateId;
  double? _unitCost;
  List<TestSummary> _existingTests = const [];
  ClassificationAvailabilityResponse? _availability;

  IntakeReviewState? _review;

  /// Which already-registered tests the reviewer says this batch could belong
  /// to. Empty means "all of them".
  ///
  /// This is the real cost control: narrowing to one test means attribution is
  /// already decided and **no call is made at all**, which is the ordinary
  /// week-two case (one subject's answers arriving for a test registered
  /// earlier).
  final Set<String> _narrowedTestIds = {};

  int _classifiedCount = 0;
  bool _cancelClassification = false;
  bool _classifying = false;

  List<_ImportOutcome> _outcomes = const [];

  @override
  void initState() {
    super.initState();
    _dependencies = ref.read(appDependenciesProvider);
    _chooseFolder = ref.read(chooseFolderProvider);
    _scanFolder = ref.read(scanFolderProvider);
    _loadSettings();
  }

  Future<void> _loadSettings() async {
    try {
      final templates = await _dependencies.listIntakeTemplates();
      final cost = await _dependencies.intakeCost();
      final tests = await _dependencies.listTests();
      final availability = await _dependencies.classificationAvailability();
      if (!mounted) return;
      setState(() {
        _templates = templates;
        _templateId = templates.isEmpty ? null : templates.first.id;
        _unitCost = cost;
        _existingTests = tests;
        _availability = availability;
      });
    } on SidecarApiException catch (error) {
      if (!mounted) return;
      setState(() => _error = error.message);
    }
  }

  Future<void> _pickFolder() async {
    final templateId = _templateId;
    if (templateId == null) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final path = await _chooseFolder();
      if (path == null || !mounted) return;
      final folder = await _scanFolder(path);
      if (folder.entries.isEmpty) {
        if (!mounted) return;
        setState(() => _error = 'このフォルダには取り込めるファイルがありません。');
        return;
      }
      final plan = await _dependencies.planIntake(
        templateId: templateId,
        rootName: folder.name,
        files: [
          for (final entry in folder.entries)
            ScannedFileModel(
              (builder) => builder
                ..relativePath = entry.relativePath
                ..sizeBytes = entry.sizeBytes
                ..sha256 = entry.sha256,
            ),
        ],
      );
      if (!mounted) return;
      setState(() {
        _review = buildReviewState(
          plan: plan,
          folder: folder,
          unitCost: _unitCost,
        );
        _step = _Step.review;
      });
    } on SidecarApiException catch (error) {
      if (!mounted) return;
      setState(() => _error = error.message);
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = 'フォルダを読み取れませんでした: $error');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  /// Run classification over every file the rules left undecided.
  ///
  /// One request per file, a few at a time, filling rows as they resolve --
  /// so the reviewer sees progress rather than a frozen screen, and can stop
  /// part-way and keep whatever has already been answered.
  Future<void> _runClassification() async {
    final review = _review;
    if (review == null) return;
    final pending = review.pendingClassification;
    if (pending.isEmpty) return;

    setState(() {
      _classifying = true;
      _cancelClassification = false;
      _classifiedCount = 0;
      _error = null;
    });

    var next = 0;
    Future<void> worker() async {
      while (true) {
        if (_cancelClassification) return;
        final index = next++;
        if (index >= pending.length) return;
        final file = pending[index];
        try {
          final proposal = await _dependencies.classifyMaterial(
            path: file.absolutePath,
          );
          if (!mounted) return;
          setState(() {
            _classifiedCount++;
            _review = _review?.withFile(
              file.relativePath,
              (current) => current.copyWith(proposedRole: proposal.role),
            );
          });
        } on SidecarApiException catch (error) {
          if (!mounted) return;
          // One file failing must not abandon the rest: the file simply stays
          // undecided, which the reviewer resolves the same way they resolve
          // anything else the classifier could not tell.
          setState(() {
            _classifiedCount++;
            _error = error.message;
          });
        }
      }
    }

    await Future.wait([
      for (var i = 0; i < _classifyConcurrency; i++) worker(),
    ]);
    if (mounted) setState(() => _classifying = false);
  }

  /// The tests an answer could be routed to.
  ///
  /// Narrowed by the reviewer first. This is the real cost control: a week
  /// whose answers are all one subject narrows to one candidate, and then
  /// nothing is asked at all -- the answer is already decided.
  List<TestSummary> get _attributionCandidates => _narrowedTestIds.isEmpty
      ? _existingTests
      : _existingTests
            .where((test) => _narrowedTestIds.contains(test.id))
            .toList();

  /// Route one group's answers.
  ///
  /// With a single candidate nothing is sent: the reviewer already decided by
  /// narrowing, and asking a provider to choose from a list of one would spend
  /// money to confirm a foregone conclusion. Two or more, and each unrouted
  /// answer is asked about individually so progress and cancellation work.
  Future<void> _attributeAnswers(IntakeGroupState group) async {
    final candidates = _attributionCandidates;
    final unrouted = group.unroutedAnswers;
    if (unrouted.isEmpty || candidates.isEmpty) return;

    if (candidates.length == 1) {
      setState(() {
        for (final answer in unrouted) {
          _review = _review?.withFile(
            answer.relativePath,
            (current) => current.copyWith(answerTestId: candidates.first.id),
          );
        }
      });
      return;
    }

    setState(() {
      _classifying = true;
      _cancelClassification = false;
      _classifiedCount = 0;
      _error = null;
    });
    for (final answer in unrouted) {
      if (_cancelClassification) break;
      try {
        final proposal = await _dependencies.attributeAnswer(
          path: answer.absolutePath,
          candidates: [
            for (final test in candidates) (id: test.id, label: test.name),
          ],
        );
        if (!mounted) return;
        setState(() {
          _classifiedCount++;
          // `null` means the classifier could not tell, which is a real and
          // frequent answer -- the sheet often carries nothing identifying at
          // all. The row simply stays unrouted for the reviewer to decide.
          if (proposal.testId != null) {
            _review = _review?.withFile(
              answer.relativePath,
              (current) => current.copyWith(answerTestId: proposal.testId),
            );
          }
        });
      } on SidecarApiException catch (error) {
        if (!mounted) return;
        setState(() {
          _classifiedCount++;
          _error = error.message;
        });
      }
    }
    if (mounted) setState(() => _classifying = false);
  }

  Future<void> _import() async {
    final review = _review;
    if (review == null) return;
    setState(() {
      _busy = true;
      _error = null;
    });

    final outcomes = <_ImportOutcome>[];
    for (final group in review.groups) {
      final included = group.includedFiles;
      if (included.isEmpty) continue;
      outcomes.add(await _importGroup(group, included));
      if (mounted) setState(() => _outcomes = List.of(outcomes));
    }
    if (!mounted) return;
    setState(() {
      _outcomes = outcomes;
      _busy = false;
      _step = _Step.done;
    });
  }

  /// Import one group.
  ///
  /// Every write is its own request, so a batch that dies on its 27th answer
  /// keeps the 26 before it -- and a retry re-sends only what failed, which
  /// the sidecar recognizes by content rather than importing twice.
  Future<_ImportOutcome> _importGroup(
    IntakeGroupState group,
    List<IntakeFileState> included,
  ) async {
    final answers = included
        .where((file) => file.effectiveRole == MaterialRole.studentAnswer)
        .toList();
    final materials = [
      for (final file in included)
        if (file.effectiveRole != null &&
            file.effectiveRole != MaterialRole.studentAnswer &&
            file.effectiveRole != MaterialRole.ignore)
          (role: file.effectiveRole!, path: file.absolutePath),
    ];

    if (group.targetKind == IntakeTargetKind.perAnswer) {
      return _importRoutedAnswers(group, answers);
    }

    String? testId = group.targetTestId;
    var materialCount = 0;
    try {
      if (group.targetKind == IntakeTargetKind.create) {
        final criteria = included.firstWhere(
          (file) => file.effectiveRole == MaterialRole.gradingCriteria,
        );
        final extras = materials
            .where((material) => material.path != criteria.absolutePath)
            .toList();
        final test = await _dependencies.createTest(
          name: group.name.trim(),
          criteriaPath: criteria.absolutePath,
          materials: extras,
        );
        testId = test.id;
        materialCount = extras.length + 1;
      } else if (materials.isNotEmpty) {
        final attached = await _dependencies.addMaterials(
          testId!,
          materials: materials,
        );
        materialCount = attached.length;
      }

      final answersResult = await _importAnswers(testId!, answers);
      return _ImportOutcome(
        groupKey: group.key,
        name: group.name,
        testId: testId,
        materialCount: materialCount,
        submissionCount: answersResult.imported,
        duplicateCount: answersResult.duplicates,
        gradingStartedCount: answersResult.gradingStarted,
        gradingFailure: answersResult.gradingFailure,
        error: answersResult.failure,
      );
    } on SidecarApiException catch (error) {
      return _ImportOutcome(
        groupKey: group.key,
        name: group.name,
        testId: testId,
        error: error.message,
      );
    } on StateError {
      return _ImportOutcome(
        groupKey: group.key,
        name: group.name,
        error: '採点基準のファイルが選ばれていません。',
      );
    }
  }

  /// Import a group whose answers were routed individually.
  ///
  /// Each answer is its own request against its own test, so one failure
  /// costs one answer rather than the group.
  Future<_ImportOutcome> _importRoutedAnswers(
    IntakeGroupState group,
    List<IntakeFileState> answers,
  ) async {
    var imported = 0;
    var duplicates = 0;
    var gradingStarted = 0;
    String? gradingFailure;
    String? failure;
    for (final answer in answers) {
      final testId = answer.answerTestId;
      if (testId == null) continue;
      final result = await _importAnswers(testId, [answer]);
      imported += result.imported;
      duplicates += result.duplicates;
      gradingStarted += result.gradingStarted;
      gradingFailure ??= result.gradingFailure;
      failure ??= result.failure;
    }
    return _ImportOutcome(
      groupKey: group.key,
      name: group.name,
      submissionCount: imported,
      duplicateCount: duplicates,
      gradingStartedCount: gradingStarted,
      gradingFailure: gradingFailure,
      error: failure,
    );
  }

  /// Upload each answer and, when its intake landed on `ai_processed`, queue
  /// its grading jobs.
  ///
  /// The kickoff lives here for the same reason it lived in the screen this
  /// one replaced: nothing else in the app calls
  /// `POST /submissions/{id}/jobs`, so without it grading never starts at all
  /// (Issue #80, `docs/job-queue.md`「起票のタイミング」). A `needs_review` or
  /// `error` submission is deliberately left alone -- a human decides from the
  /// 添削レビュー screen.
  ///
  /// **A failed kickoff is not a failed import.** The answer is in either way,
  /// and the usual reason grading cannot start is that this test has no
  /// confirmed question dependencies yet, which is exactly the state a test
  /// registered moments ago is in.
  Future<
    ({
      int imported,
      int duplicates,
      int gradingStarted,
      String? gradingFailure,
      String? failure,
    })
  >
  _importAnswers(String testId, List<IntakeFileState> answers) async {
    var imported = 0;
    var duplicates = 0;
    var gradingStarted = 0;
    String? gradingFailure;
    String? failure;
    for (final answer in answers) {
      SubmissionResponse? submission;
      try {
        submission = await _dependencies.createSubmission(
          testId: testId,
          filePath: answer.absolutePath,
        );
        imported++;
      } on DuplicateSubmissionException {
        // The same bytes are already in this test. Not a failure -- it is what
        // makes retrying a partially-failed batch safe.
        duplicates++;
      } on SidecarApiException catch (error) {
        failure ??= error.message;
      }
      if (submission == null || submission.state != 'ai_processed') continue;
      try {
        await _dependencies.startGrading(submission.id);
        gradingStarted++;
      } on SidecarApiException catch (error) {
        gradingFailure ??= GradingKickoffFailure.of(error).message;
      }
    }
    return (
      imported: imported,
      duplicates: duplicates,
      gradingStarted: gradingStarted,
      gradingFailure: gradingFailure,
      failure: failure,
    );
  }

  Future<void> _deleteTest(String testId) async {
    setState(() => _busy = true);
    try {
      await _dependencies.deleteTest(testId);
      if (!mounted) return;
      setState(
        () => _outcomes = _outcomes
            .where((outcome) => outcome.testId != testId)
            .toList(),
      );
    } on SidecarApiException catch (error) {
      if (!mounted) return;
      setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('資料の取込'),
        actions: [
          IconButton(
            key: const Key('intake-open-settings'),
            tooltip: '設定',
            onPressed: () => context.push(AppRoutes.settings),
            icon: const Icon(Icons.settings),
          ),
        ],
      ),
      body: Padding(
        padding: AppSpacing.page,
        child: switch (_step) {
          _Step.choose => _buildChooseStep(),
          _Step.review => _buildReviewStep(),
          _Step.done => _buildDoneStep(),
        },
      ),
    );
  }

  Widget _buildChooseStep() {
    return ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: AppLayout.formMaxWidth),
      child: ListView(
        children: [
          const Text(
            '塾から受け取ったフォルダをそのまま選んでください。'
            '中身の役割は取込の型で自動的に振り分け、取り込む前に一覧で確認できます。',
          ),
          const SizedBox(height: AppSpacing.xl),
          DropdownButtonFormField<String>(
            key: const Key('intake-template-picker'),
            initialValue: _templateId,
            decoration: const InputDecoration(
              labelText: '取込の型',
              border: OutlineInputBorder(),
            ),
            items: [
              for (final template in _templates)
                DropdownMenuItem(
                  value: template.id,
                  child: Text(template.name),
                ),
            ],
            onChanged: _busy
                ? null
                : (value) => setState(() => _templateId = value),
          ),
          const SizedBox(height: AppSpacing.lg),
          if (_availability?.available == false)
            Card(
              child: Padding(
                padding: AppSpacing.card,
                child: Text(
                  'この端末ではAIによる自動判定を使えません。'
                  '取込の型で振り分けられなかったファイルは、一覧で役割を選んでください。'
                  '\n理由: ${_availability?.reason ?? ''}',
                ),
              ),
            ),
          const SizedBox(height: AppSpacing.lg),
          if (_busy) const LinearProgressIndicator(),
          if (_error != null) ...[
            const SizedBox(height: AppSpacing.sm),
            AppErrorBanner(message: _error!),
          ],
          const SizedBox(height: AppSpacing.lg),
          FilledButton.icon(
            key: const Key('intake-choose-folder'),
            onPressed: _busy || _templateId == null ? null : _pickFolder,
            icon: const Icon(Icons.folder_open),
            label: const Text('フォルダを選ぶ'),
          ),
        ],
      ),
    );
  }

  Widget _buildReviewStep() {
    final review = _review!;
    final pending = review.pendingClassification.length;
    final unconfirmed = review.unconfirmedProposals.length;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _buildEstimate(review, pending),
        if (_existingTests.isNotEmpty) _buildNarrowing(),
        const SizedBox(height: AppSpacing.md),
        if (_classifying)
          Padding(
            padding: const EdgeInsets.only(bottom: AppSpacing.sm),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    'AIが判定しています ($_classifiedCount / '
                    '${_classifiedCount + pending}件)',
                    key: const Key('intake-classify-progress'),
                  ),
                ),
                TextButton(
                  key: const Key('intake-cancel-classify'),
                  onPressed: () => setState(() => _cancelClassification = true),
                  child: const Text('中止'),
                ),
              ],
            ),
          ),
        if (_error != null) ...[
          AppErrorBanner(message: _error!),
          const SizedBox(height: AppSpacing.sm),
        ],
        Expanded(
          child: ListView(
            children: [
              for (final group in review.groups) _buildGroupCard(group),
            ],
          ),
        ),
        const SizedBox(height: AppSpacing.md),
        if (unconfirmed > 0)
          Padding(
            padding: const EdgeInsets.only(bottom: AppSpacing.sm),
            child: Text(
              key: const Key('intake-unconfirmed-notice'),
              'AIの提案を$unconfirmed件、まだ確認していません。'
              '内容を確かめて「この役割でよい」を押すと取り込めます。',
            ),
          ),
        Row(
          children: [
            if (pending > 0 && _availability?.available == true)
              Padding(
                padding: const EdgeInsets.only(right: AppSpacing.md),
                child: FilledButton.tonalIcon(
                  key: const Key('intake-run-classification'),
                  onPressed: _classifying || _busy ? null : _runClassification,
                  icon: const Icon(Icons.auto_awesome),
                  label: Text('AIで判定する ($pending件)'),
                ),
              ),
            FilledButton.icon(
              key: const Key('intake-import'),
              onPressed: _busy || _classifying || !review.canImport
                  ? null
                  : _import,
              icon: const Icon(Icons.download_done),
              label: const Text('この内容で取り込む'),
            ),
          ],
        ),
      ],
    );
  }

  /// The pre-flight numbers (acceptance criterion 7).
  ///
  /// The call count is exact. The cost is only shown when the reviewer has
  /// told the settings screen what their provider charges -- this app cannot
  /// know that, and a figure nobody verified is worse than none.
  Widget _buildEstimate(IntakeReviewState review, int pending) {
    final cost = review.estimatedCost;
    return Card(
      child: Padding(
        padding: AppSpacing.card,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              key: const Key('intake-call-estimate'),
              'AIに問い合わせる件数: $pending件',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: AppSpacing.xs),
            Text(
              key: const Key('intake-cost-estimate'),
              cost == null
                  ? '概算費用: 1件あたりの単価が未設定です（設定画面で入力できます）'
                  : '概算費用: 約${cost.toStringAsFixed(2)}（1件あたり'
                        '${_unitCost!.toStringAsFixed(2)}）',
            ),
          ],
        ),
      ),
    );
  }

  /// Narrowing the candidate list before any answer is attributed.
  ///
  /// Optional, and the reason it is worth offering: picking one test means the
  /// question is already answered and no provider call happens at all. That is
  /// the ordinary week -- one subject's answers arriving for a test registered
  /// earlier.
  Widget _buildNarrowing() {
    return Padding(
      padding: const EdgeInsets.only(top: AppSpacing.sm),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('このバッチはどのテストの答案ですか（絞ると判定が正確になり、費用も下がります）'),
          const SizedBox(height: AppSpacing.xs),
          Wrap(
            spacing: AppSpacing.sm,
            children: [
              for (final test in _existingTests)
                FilterChip(
                  key: Key('intake-narrow-${test.id}'),
                  label: Text(test.name),
                  selected: _narrowedTestIds.contains(test.id),
                  onSelected: (selected) => setState(() {
                    if (selected) {
                      _narrowedTestIds.add(test.id);
                    } else {
                      _narrowedTestIds.remove(test.id);
                    }
                  }),
                ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildGroupCard(IntakeGroupState group) {
    final unmet = group.unmetRequirements;
    return Card(
      key: Key('intake-group-${group.key}'),
      child: Padding(
        padding: AppSpacing.card,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: DropdownButtonFormField<String>(
                    key: Key('intake-target-${group.key}'),
                    initialValue: switch (group.targetKind) {
                      IntakeTargetKind.create => '__new__',
                      IntakeTargetKind.perAnswer => '__per_answer__',
                      _ => group.targetTestId,
                    },
                    decoration: const InputDecoration(
                      labelText: '取り込み先',
                      border: OutlineInputBorder(),
                    ),
                    items: [
                      const DropdownMenuItem(
                        value: '__new__',
                        child: Text('新しいテストとして登録する'),
                      ),
                      if (_existingTests.isNotEmpty)
                        const DropdownMenuItem(
                          value: '__per_answer__',
                          child: Text('答案ごとに登録済みのテストへ振り分ける'),
                        ),
                      for (final test in _existingTests)
                        DropdownMenuItem(
                          value: test.id,
                          child: Text('登録済み: ${test.name}'),
                        ),
                    ],
                    onChanged: _busy
                        ? null
                        : (value) => setState(() {
                            _review = _review?.withGroup(
                              group.key,
                              (current) => switch (value) {
                                '__new__' => current.copyWith(
                                  targetKind: IntakeTargetKind.create,
                                  clearTargetTestId: true,
                                ),
                                '__per_answer__' => current.copyWith(
                                  targetKind: IntakeTargetKind.perAnswer,
                                  clearTargetTestId: true,
                                ),
                                _ => current.copyWith(
                                  targetKind: IntakeTargetKind.existing,
                                  targetTestId: value,
                                ),
                              },
                            );
                          }),
                  ),
                ),
                if (group.targetKind == IntakeTargetKind.create) ...[
                  const SizedBox(width: AppSpacing.md),
                  Expanded(
                    child: TextFormField(
                      key: Key('intake-name-${group.key}'),
                      initialValue: group.name,
                      decoration: const InputDecoration(
                        labelText: 'テスト名',
                        border: OutlineInputBorder(),
                      ),
                      onChanged: (value) => setState(() {
                        _review = _review?.withGroup(
                          group.key,
                          (current) => current.copyWith(name: value),
                        );
                      }),
                    ),
                  ),
                ],
              ],
            ),
            if (unmet.isNotEmpty) ...[
              const SizedBox(height: AppSpacing.sm),
              Text(
                key: Key('intake-unmet-${group.key}'),
                '不足: ${unmet.map(materialRoleLabel).join('、')}。'
                'このままでは新しいテストとして登録できません。'
                '登録済みのテストに追加する場合は取り込み先を変えてください。',
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            ],
            if (group.targetKind == IntakeTargetKind.perAnswer) ...[
              const SizedBox(height: AppSpacing.sm),
              Row(
                children: [
                  FilledButton.tonalIcon(
                    key: Key('intake-attribute-${group.key}'),
                    onPressed:
                        _busy ||
                            _classifying ||
                            group.unroutedAnswers.isEmpty ||
                            _attributionCandidates.isEmpty
                        ? null
                        : () => _attributeAnswers(group),
                    icon: const Icon(Icons.call_split),
                    label: Text(
                      _attributionCandidates.length == 1
                          ? '絞り込んだテストに振り分ける (AI不要)'
                          : 'AIで振り分ける (${group.unroutedAnswers.length}件)',
                    ),
                  ),
                ],
              ),
              if (group.unroutableNonAnswers.isNotEmpty)
                Text(
                  key: Key('intake-unroutable-${group.key}'),
                  '答案以外のファイルは振り分け先が決まりません。'
                  '除外するか、取り込み先を1つのテストに変えてください。',
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
            ],
            const SizedBox(height: AppSpacing.sm),
            for (final file in group.files)
              _buildFileRow(
                file,
                perAnswer: group.targetKind == IntakeTargetKind.perAnswer,
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildFileRow(IntakeFileState file, {bool perAnswer = false}) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
      child: Row(
        children: [
          Checkbox(
            key: Key('intake-include-${file.relativePath}'),
            value: !file.excluded,
            onChanged: _busy
                ? null
                : (value) => setState(() {
                    _review = _review?.withFile(
                      file.relativePath,
                      (current) => current.copyWith(excluded: value != true),
                    );
                  }),
          ),
          Expanded(
            flex: 3,
            child: Text(file.fileName, overflow: TextOverflow.ellipsis),
          ),
          const SizedBox(width: AppSpacing.sm),
          _buildOriginBadge(file),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            flex: 2,
            child: DropdownButton<MaterialRole?>(
              key: Key('intake-role-${file.relativePath}'),
              isExpanded: true,
              value: file.effectiveRole,
              hint: const Text('未判定'),
              items: [
                for (final role in MaterialRole.values)
                  DropdownMenuItem(
                    value: role,
                    child: Text(materialRoleLabel(role)),
                  ),
              ],
              onChanged: _busy
                  ? null
                  : (value) => setState(() {
                      _review = _review?.withFile(
                        file.relativePath,
                        (current) => current.copyWith(
                          humanRole: value,
                          // Choosing a role *is* the confirmation. Requiring a
                          // second tap on "accept the proposal" after the
                          // reviewer already overrode it would be asking the
                          // same question twice.
                          proposalConfirmed: true,
                        ),
                      );
                    }),
            ),
          ),
          if (perAnswer && file.effectiveRole == MaterialRole.studentAnswer)
            Expanded(
              flex: 2,
              child: DropdownButton<String>(
                key: Key('intake-answer-target-${file.relativePath}'),
                isExpanded: true,
                value: file.answerTestId,
                hint: const Text('振り分け先'),
                items: [
                  for (final test in _attributionCandidates)
                    DropdownMenuItem(value: test.id, child: Text(test.name)),
                ],
                onChanged: _busy
                    ? null
                    : (value) => setState(() {
                        _review = _review?.withFile(
                          file.relativePath,
                          (current) => current.copyWith(answerTestId: value),
                        );
                      }),
              ),
            ),
          if (file.blocksImport && file.proposedRole != null)
            TextButton(
              key: Key('intake-confirm-${file.relativePath}'),
              onPressed: _busy
                  ? null
                  : () => setState(() {
                      _review = _review?.withFile(
                        file.relativePath,
                        (current) => current.copyWith(proposalConfirmed: true),
                      );
                    }),
              child: const Text('この役割でよい'),
            ),
        ],
      ),
    );
  }

  Widget _buildOriginBadge(IntakeFileState file) {
    final (label, tone) = switch (file.origin) {
      IntakeRoleOrigin.rule => ('規則', Theme.of(context).colorScheme.primary),
      IntakeRoleOrigin.proposal => (
        file.proposalConfirmed ? 'AI(確認済)' : 'AI提案',
        Theme.of(context).colorScheme.tertiary,
      ),
      IntakeRoleOrigin.human => ('手動', Theme.of(context).colorScheme.secondary),
      IntakeRoleOrigin.unresolved => (
        '未判定',
        Theme.of(context).colorScheme.error,
      ),
    };
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.sm,
        vertical: AppSpacing.xs,
      ),
      decoration: BoxDecoration(
        border: Border.all(color: tone),
        borderRadius: AppRadius.smAll,
      ),
      child: Text(label, style: TextStyle(color: tone)),
    );
  }

  /// The completion step.
  ///
  /// Says what happened, what is still needed, and offers the next action
  /// directly -- a screen that only reported success would leave the reviewer
  /// with no idea where to go, and one that said "registered" alone would read
  /// as "ready to grade", which it is not.
  Widget _buildDoneStep() {
    return ListView(
      children: [
        Card(
          child: Padding(
            padding: AppSpacing.card,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '取込が完了しました',
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                const SizedBox(height: AppSpacing.sm),
                const Text(
                  key: Key('intake-next-step-notice'),
                  '採点にはこのあと配点と採点基準が必要です。'
                  'いまのアプリは採点基準PDFからこれらを自動では取り出せないため、'
                  'テスト設定画面で入力してください。',
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: AppSpacing.md),
        for (final outcome in _outcomes)
          Card(
            key: Key('intake-outcome-${outcome.groupKey}'),
            child: Padding(
              padding: AppSpacing.card,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    outcome.name,
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  const SizedBox(height: AppSpacing.xs),
                  if (outcome.succeeded) ...[
                    Text(
                      '資料 ${outcome.materialCount}件 / '
                      '答案 ${outcome.submissionCount}件を取り込みました'
                      '${outcome.duplicateCount > 0 ? '（${outcome.duplicateCount}件は取込済み）' : ''}',
                    ),
                    // Said separately, never folded into the line above:
                    // "the answer is in" and "grading started" are two facts,
                    // and the screen must not assert the second one when it
                    // did not happen (Issue #80).
                    if (outcome.gradingStartedCount > 0)
                      Text('うち${outcome.gradingStartedCount}件のAI採点を開始しました'),
                    if (outcome.gradingFailure != null)
                      Text(
                        outcome.gradingFailure!,
                        style: TextStyle(
                          color: Theme.of(context).colorScheme.error,
                        ),
                      ),
                  ] else
                    Text(
                      '取り込めませんでした: ${outcome.error}',
                      style: TextStyle(
                        color: Theme.of(context).colorScheme.error,
                      ),
                    ),
                  const SizedBox(height: AppSpacing.sm),
                  Row(
                    children: [
                      if (outcome.testId != null) ...[
                        FilledButton.icon(
                          key: Key('intake-open-settings-${outcome.groupKey}'),
                          onPressed: () => context.push(
                            AppRoutes.testSettings(outcome.testId!),
                          ),
                          icon: const Icon(Icons.tune),
                          label: const Text('テスト設定を開く'),
                        ),
                        const SizedBox(width: AppSpacing.md),
                        TextButton.icon(
                          key: Key('intake-delete-${outcome.groupKey}'),
                          onPressed: _busy
                              ? null
                              : () => _deleteTest(outcome.testId!),
                          icon: const Icon(Icons.delete_outline),
                          label: const Text('このテストを削除'),
                        ),
                      ],
                    ],
                  ),
                ],
              ),
            ),
          ),
        const SizedBox(height: AppSpacing.lg),
        OutlinedButton.icon(
          key: const Key('intake-start-over'),
          onPressed: () => setState(() {
            _step = _Step.choose;
            _review = null;
            _outcomes = const [];
            _error = null;
          }),
          icon: const Icon(Icons.folder_open),
          label: const Text('別のフォルダを取り込む'),
        ),
      ],
    );
  }
}
