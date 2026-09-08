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
    this.createdTest = false,
    this.materialCount = 0,
    this.submissionCount = 0,
    this.duplicateCount = 0,
    this.gradingStartedCount = 0,
    this.gradingFailure,
    this.error,
    this.failedFiles = const [],
  });

  final String groupKey;
  final String name;
  final String? testId;

  /// Whether **this** import created the test, as opposed to adding to one
  /// that already existed.
  ///
  /// Decides what the completion screen may offer. Deleting a test this import
  /// created undoes this import; deleting a test it merely added to would
  /// throw away every previous week's answers and grading along with it, which
  /// is not what "undo" means to anyone.
  final bool createdTest;
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

  /// The files that could not be imported, so the reviewer can find them.
  ///
  /// A count is not enough: "1件失敗" in a folder of forty leaves them
  /// comparing lists by hand.
  final List<String> failedFiles;

  /// Whether anything at all landed.
  ///
  /// Deliberately not "did every file land": every write is its own request
  /// precisely so a batch can partly succeed, and reporting the whole group as
  /// a failure because one answer of forty failed would hide the thirty-nine
  /// that are in -- and make the reviewer re-import them.
  bool get importedAnything =>
      materialCount > 0 || submissionCount > 0 || duplicateCount > 0;
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

  /// Bumped whenever the candidate list changes, so a response from an
  /// attribution run issued against the *previous* list can be recognized as
  /// stale and dropped.
  int _attributionGeneration = 0;

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

  /// Re-read the registered tests, without failing the caller.
  ///
  /// A stale list only costs the reviewer a target they could have picked; a
  /// thrown exception here would cost them the whole folder they just chose.
  Future<void> _refreshExistingTests() async {
    try {
      final tests = await _dependencies.listTests();
      if (!mounted) return;
      setState(() => _existingTests = tests);
    } on SidecarApiException {
      // Keep whatever list we had.
    }
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
        // Keep the reviewer's own choice across a reload; only fall back to
        // the first template when what they had picked is gone.
        _templateId = templates.any((template) => template.id == _templateId)
            ? _templateId
            : (templates.isEmpty ? null : templates.first.id);
        _unitCost = cost;
        _existingTests = tests;
        _availability = availability;
        // A plan already on screen was priced with the old figure.
        _review = _review?.copyWith(unitCost: cost);
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
      // Re-read at the start of every batch, not once in initState. The
      // ordinary sequence is "import the criteria folder, then import the
      // answers folder" -- and the test just created has to be offerable as a
      // target for the second one.
      await _refreshExistingTests();
      if (!mounted) return;
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
  Future<void> _runClassification({bool cachedOnly = false}) async {
    final review = _review;
    if (review == null) return;
    // Cached files are asked about too. They cost nothing and the sidecar
    // answers instantly -- skipping them is what made a re-selected folder
    // throw away proposals it had already paid for. ``cachedOnly`` runs just
    // those, which is what makes the free path usable on a host with no
    // provider configured.
    final pending = cachedOnly
        ? review.classifiableFiles
              .where((file) => file.cachedClassification)
              .toList()
        : review.classifiableFiles;
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
              // Marked as asked even when the answer was "could not tell":
              // that is a real answer, and asking again buys the same reply
              // at the same price.
              (current) => current.copyWith(
                proposedRole: proposal.role,
                classificationAttempted: true,
              ),
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
            // Not marked as asked: a call that failed produced no answer, so
            // retrying is the reviewer buying something rather than
            // re-buying it.
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
    // Answers already asked about are not asked again, even when the reply was
    // "could not tell" -- the same rule role classification follows.
    final unrouted = group.unroutedAnswers
        .where((answer) => !answer.attributionAttempted)
        .toList();
    if (unrouted.isEmpty || candidates.isEmpty) return;

    if (candidates.length == 1) {
      // Not a proposal: the reviewer narrowed the batch to one test, which is
      // them stating the answer. Nothing was guessed, so there is nothing to
      // confirm.
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

    final generation = ++_attributionGeneration;
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
        // A candidate change while this was in flight makes the answer stale:
        // the reviewer has since said this batch is not that test's, and a
        // response that arrives afterwards must not quietly reinstate it. The
        // dropdown hides an out-of-range value, so without this the screen
        // would show "not routed" while the state said otherwise.
        if (generation != _attributionGeneration) return;
        setState(() {
          _classifiedCount++;
          // Recorded as a **proposal**, never as the routing itself.
          // Attribution decides which criteria an answer is graded against, so
          // it goes through the same confirmation the role does -- see
          // `IntakeFileState.answerTestId`.
          //
          // `null` means the classifier could not tell, which is a real and
          // frequent answer: the sheet often carries nothing identifying at
          // all. The row stays unrouted for the reviewer to decide, and is
          // marked as asked so a second run does not re-buy the same reply.
          _review = _review?.withFile(
            answer.relativePath,
            (current) => current.copyWith(
              proposedAnswerTestId: proposal.testId,
              attributionAttempted: true,
            ),
          );
        });
      } on SidecarApiException catch (error) {
        if (!mounted || generation != _attributionGeneration) return;
        setState(() {
          _classifiedCount++;
          _error = error.message;
          // Not marked as asked: a failed call produced no answer.
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
        createdTest: group.targetKind == IntakeTargetKind.create,
        materialCount: materialCount,
        submissionCount: answersResult.imported,
        duplicateCount: answersResult.duplicates,
        gradingStartedCount: answersResult.gradingStarted,
        gradingFailure: answersResult.gradingFailure,
        error: answersResult.failure,
        failedFiles: answersResult.failedFiles,
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
    final failedFiles = <String>[];
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
      failedFiles.addAll(result.failedFiles);
    }
    return _ImportOutcome(
      groupKey: group.key,
      name: group.name,
      submissionCount: imported,
      duplicateCount: duplicates,
      gradingStartedCount: gradingStarted,
      gradingFailure: gradingFailure,
      error: failure,
      failedFiles: failedFiles,
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
      List<String> failedFiles,
    })
  >
  _importAnswers(String testId, List<IntakeFileState> answers) async {
    var imported = 0;
    var duplicates = 0;
    var gradingStarted = 0;
    final failedFiles = <String>[];
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
        failedFiles.add(answer.fileName);
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
      failedFiles: failedFiles,
    );
  }

  /// Delete a test this import created, after saying what goes with it.
  ///
  /// Only ever offered for a test **this** import created (see
  /// `_ImportOutcome.createdTest`): the underlying operation removes the test
  /// and everything under it, so calling it on a test that already existed
  /// would throw away every previous week's answers and grading -- from a
  /// button the reviewer pressed meaning "undo what I just did".
  ///
  /// The confirmation names the blast radius rather than asking "are you
  /// sure?", and the counts are read back from the sidecar rather than taken
  /// from this screen's own tally, so a submission imported by something else
  /// is included in what the reviewer is warned about (`AGENTS.md`
  /// "Security": confirm scope and blast radius before a destructive
  /// operation).
  Future<void> _deleteTest(_ImportOutcome outcome) async {
    final testId = outcome.testId;
    if (testId == null || !outcome.createdTest) return;

    // `null` means "could not read it", which is a different thing from a
    // number. Falling back to this screen's own tally would show a count that
    // understates whatever else has been added since -- a confident number
    // nobody verified, in front of an irreversible action.
    int? submissionCount;
    int? materialCount;
    try {
      submissionCount = (await _dependencies.listSubmissions(testId)).length;
      materialCount = (await _dependencies.listMaterials(testId)).length;
    } on SidecarApiException {
      // Left null; the dialog says so.
    }

    if (!mounted) return;
    final counted = submissionCount != null && materialCount != null;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        key: const Key('intake-delete-confirm'),
        title: Text('「${outcome.name}」を削除しますか'),
        content: Text(
          counted
              ? 'このテストと、それに紐づくものをすべて削除します。\n\n'
                    '・答案 $submissionCount件\n'
                    '・その答案の採点結果・添削・レビュー履歴\n'
                    '・登録した資料 $materialCount件\n\n'
                    '元に戻せません。'
              : 'このテストと、それに紐づくものをすべて削除します。\n\n'
                    '**いま何件あるかを確認できませんでした。**'
                    'この画面で取り込んだ以外の答案や資料が含まれている'
                    '可能性があります。\n\n'
                    '元に戻せません。',
        ),
        actions: [
          TextButton(
            key: const Key('intake-delete-cancel'),
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text('やめる'),
          ),
          FilledButton(
            key: const Key('intake-delete-confirmed'),
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: const Text('削除する'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;

    setState(() => _busy = true);
    try {
      await _dependencies.deleteTest(testId);
      if (!mounted) return;
      setState(
        () => _outcomes = _outcomes
            .where((entry) => entry.testId != testId)
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
            // Re-read on the way back. The settings screen promises "次の取込
            // から反映されます", and without this that promise is false: a
            // newly added template would not be selectable, and a unit price
            // changed from 0 would still show the old estimate right before
            // the reviewer spends money against it.
            onPressed: () async {
              await context.push(AppRoutes.settings);
              await _loadSettings();
            },
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
    final billable = review.pendingClassification.length;
    final classifiable = review.classifiableFiles.length;
    final cachedOnly = classifiable - billable;
    final unconfirmed = review.unconfirmedProposals.length;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _buildEstimate(review, billable),
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
                    '${_classifiedCount + classifiable}件)',
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
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    key: const Key('intake-unconfirmed-notice'),
                    'AIの提案を$unconfirmed件、まだ確認していません。'
                    '内容を確かめてから取り込んでください。',
                  ),
                ),
                if (review.confirmableProposals.isNotEmpty)
                  TextButton(
                    key: const Key('intake-confirm-all'),
                    // Explicit bulk approval, not an auto-accept: the reviewer
                    // still has to press it, and it only touches rows that
                    // actually carry a proposal. A folder of forty answers no
                    // rule matched would otherwise cost forty taps.
                    onPressed: _busy || _classifying
                        ? null
                        : () => setState(
                            () => _review = _review?.confirmAllProposals(),
                          ),
                    child: Text(
                      'AIの提案 ${review.confirmableProposals.length}件を'
                      'まとめて確認済みにする',
                    ),
                  ),
              ],
            ),
          ),
        Row(
          children: [
            // Cached answers are free and the sidecar serves them without
            // touching a provider, so this stays available on a host that has
            // no provider configured at all. Tying it to availability meant a
            // reviewer whose credentials were missing had to redo forty
            // classifications they had already paid for.
            if (cachedOnly > 0)
              Padding(
                padding: const EdgeInsets.only(right: AppSpacing.md),
                child: OutlinedButton.icon(
                  key: const Key('intake-fetch-cached'),
                  onPressed: _classifying || _busy
                      ? null
                      : () => _runClassification(cachedOnly: true),
                  icon: const Icon(Icons.history),
                  label: Text('前回の判定を取得する ($cachedOnly件・無料)'),
                ),
              ),
            if (billable > 0 && _availability?.available == true)
              Padding(
                padding: const EdgeInsets.only(right: AppSpacing.md),
                child: FilledButton.tonalIcon(
                  key: const Key('intake-run-classification'),
                  onPressed: _classifying || _busy ? null : _runClassification,
                  icon: const Icon(Icons.auto_awesome),
                  label: Text('AIで判定する ($billable件)'),
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
  /// **Two kinds of call, counted separately.** Role classification and answer
  /// attribution are both billed, and a batch can need many of one and none of
  /// the other -- forty answers whose names every rule matched cost nothing to
  /// classify and forty calls to attribute. One combined number would have hidden
  /// that, and a role-only number would have read as "free".
  ///
  /// Attribution is only counted when there is more than one candidate: with
  /// one, the reviewer has already decided and no call is made.
  Widget _buildEstimate(IntakeReviewState review, int billableRoleCalls) {
    final candidates = _attributionCandidates.length;
    final attributionCalls = candidates >= 2
        ? review.answersNeedingAttribution.length
        : 0;
    final totalCalls = billableRoleCalls + attributionCalls;
    final cost = review.estimatedCostForCalls(totalCalls);
    return Card(
      child: Padding(
        padding: AppSpacing.card,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              key: const Key('intake-call-estimate'),
              'AIに問い合わせる件数: 合計$totalCalls件',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: AppSpacing.xs),
            Text(
              key: const Key('intake-call-breakdown'),
              '内訳: 役割の判定 $billableRoleCalls件 / '
              '答案の振り分け $attributionCalls件'
              '${attributionCalls > 0 ? '（候補$candidates件）' : ''}',
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
                    // Any attribution run still in flight was issued against
                    // the old candidate list; its answers are about a question
                    // the reviewer has since changed.
                    _attributionGeneration++;
                    // An answer already routed to a test the reviewer has just
                    // narrowed away has to lose that routing: the dropdown it
                    // is shown in no longer offers that value, and leaving it
                    // set would both crash the control and keep a decision the
                    // reviewer has implicitly withdrawn.
                    _dropRoutingOutsideCandidates();
                  }),
                ),
            ],
          ),
        ],
      ),
    );
  }

  /// Clear any answer routed to a test that is no longer a candidate.
  void _dropRoutingOutsideCandidates() {
    final allowed = _attributionCandidates.map((test) => test.id).toSet();
    var review = _review;
    if (review == null) return;
    for (final file in review.allFiles) {
      final routed = file.answerTestId;
      final proposed = file.proposedAnswerTestId;
      if ((routed != null && !allowed.contains(routed)) ||
          (proposed != null && !allowed.contains(proposed))) {
        review = review!.withFile(
          file.relativePath,
          (current) => current.copyWith(
            clearAnswerTestId: routed != null && !allowed.contains(routed),
            clearProposedAnswerTestId:
                proposed != null && !allowed.contains(proposed),
          ),
        );
      }
    }
    _review = review;
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
                    // A test name is whatever the reviewer typed, and a folder
                    // name is whatever the school chose. Neither is bounded,
                    // so the control has to shrink its label rather than
                    // overflow the row.
                    isExpanded: true,
                    // Same guard as the per-answer routing dropdown: the
                    // registered-test list is re-read at the start of every
                    // batch, so a group bound to a test that has since gone
                    // would otherwise hold a value with no matching item and
                    // trip `DropdownButton`'s assert.
                    initialValue: switch (group.targetKind) {
                      IntakeTargetKind.create => '__new__',
                      IntakeTargetKind.perAnswer => '__per_answer__',
                      _ =>
                        _existingTests.any(
                              (test) => test.id == group.targetTestId,
                            )
                            ? group.targetTestId
                            : null,
                    },
                    decoration: const InputDecoration(
                      labelText: '取り込み先',
                      border: OutlineInputBorder(),
                    ),
                    items: [
                      const DropdownMenuItem(
                        value: '__new__',
                        child: Text(
                          '新しいテストとして登録する',
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                      if (_existingTests.isNotEmpty)
                        const DropdownMenuItem(
                          value: '__per_answer__',
                          child: Text(
                            '答案ごとに登録済みのテストへ振り分ける',
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                      for (final test in _existingTests)
                        DropdownMenuItem(
                          value: test.id,
                          child: Text(
                            '登録済み: ${test.name}',
                            overflow: TextOverflow.ellipsis,
                          ),
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
                            group.unroutedAnswers
                                .where((a) => !a.attributionAttempted)
                                .isEmpty ||
                            _attributionCandidates.isEmpty
                        ? null
                        : () => _attributeAnswers(group),
                    icon: const Icon(Icons.call_split),
                    label: Text(
                      _attributionCandidates.length == 1
                          ? '絞り込んだテストに振り分ける (AI不要)'
                          : 'AIで振り分ける '
                                '(${group.unroutedAnswers.where((a) => !a.attributionAttempted).length}件)',
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
                    child: Text(
                      materialRoleLabel(role),
                      overflow: TextOverflow.ellipsis,
                    ),
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
          if (perAnswer &&
              file.effectiveRole == MaterialRole.studentAnswer &&
              file.answerTestId == null &&
              file.proposedAnswerTestId != null) ...[
            // An attribution proposal is shown as a proposal, with its own
            // accept action -- it is not the routing until somebody says so.
            Text(
              'AI提案: '
              '${_testName(file.proposedAnswerTestId!)}',
              style: TextStyle(color: Theme.of(context).colorScheme.tertiary),
            ),
            TextButton(
              key: Key('intake-confirm-target-${file.relativePath}'),
              onPressed: _busy
                  ? null
                  : () => setState(() {
                      _review = _review?.withFile(
                        file.relativePath,
                        (current) => current.copyWith(
                          answerTestId: current.proposedAnswerTestId,
                        ),
                      );
                    }),
              child: const Text('この振り分けでよい'),
            ),
          ],
          if (perAnswer && file.effectiveRole == MaterialRole.studentAnswer)
            Expanded(
              flex: 2,
              child: DropdownButton<String>(
                key: Key('intake-answer-target-${file.relativePath}'),
                isExpanded: true,
                // Only ever a value the item list actually offers.
                // `DropdownButton` asserts on a value with no matching item,
                // and the candidate list is narrowed by the reviewer while
                // routings already exist -- `_dropRoutingOutsideCandidates`
                // clears those, and this makes the control safe regardless.
                value:
                    _attributionCandidates.any(
                      (test) => test.id == file.answerTestId,
                    )
                    ? file.answerTestId
                    : null,
                hint: const Text('振り分け先'),
                items: [
                  for (final test in _attributionCandidates)
                    DropdownMenuItem(
                      value: test.id,
                      child: Text(test.name, overflow: TextOverflow.ellipsis),
                    ),
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

  /// A registered test's name, for showing a proposal in the reviewer's own
  /// words rather than as an opaque id.
  String _testName(String testId) => _existingTests
      .firstWhere(
        (test) => test.id == testId,
        orElse: () => TestSummary(
          (builder) => builder
            ..id = testId
            ..name = testId,
        ),
      )
      .name;

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
                  '採点にはこのあと配点と採点基準が必要ですが、'
                  'それを入力する画面はまだありません（Issue #103 で作成中）。'
                  'そのため、取り込んだ答案はまだ採点できません。',
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
                  // What landed is reported whether or not something also
                  // failed. Every write is its own request so a batch can
                  // partly succeed; showing only the failure would hide the
                  // thirty-nine answers that are in and send the reviewer to
                  // re-import them.
                  if (outcome.importedAnything)
                    Text(
                      key: Key('intake-imported-${outcome.groupKey}'),
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
                  if (outcome.error != null) ...[
                    Text(
                      key: Key('intake-failed-${outcome.groupKey}'),
                      outcome.importedAnything
                          ? '一部を取り込めませんでした: ${outcome.error}'
                          : '取り込めませんでした: ${outcome.error}',
                      style: TextStyle(
                        color: Theme.of(context).colorScheme.error,
                      ),
                    ),
                    // Named, not counted: "1件失敗" in a folder of forty
                    // leaves the reviewer comparing lists by hand.
                    if (outcome.failedFiles.isNotEmpty)
                      Text(
                        '失敗したファイル: ${outcome.failedFiles.join('、')}',
                        style: TextStyle(
                          color: Theme.of(context).colorScheme.error,
                        ),
                      ),
                  ],
                  const SizedBox(height: AppSpacing.sm),
                  Row(
                    children: [
                      if (outcome.testId != null) ...[
                        // No link to テスト設定画面. That screen's manual
                        // region editor is disabled until a profile exists,
                        // and generating one needs a model-answer-shaped
                        // reference PDF -- which the standard input for this
                        // flow (採点基準 PDF + 答案) does not include. Sending
                        // the reviewer there would be sending them somewhere
                        // they cannot do what the notice above asks. Saying
                        // the app cannot do it yet is worse news and better
                        // information.
                        if (outcome.createdTest) ...[
                          TextButton.icon(
                            key: Key('intake-delete-${outcome.groupKey}'),
                            onPressed: _busy
                                ? null
                                : () => _deleteTest(outcome),
                            icon: const Icon(Icons.delete_outline),
                            label: const Text('このテストを削除'),
                          ),
                        ],
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
