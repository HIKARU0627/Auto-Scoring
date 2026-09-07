import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:pdfrx/pdfrx.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/app_dependencies.dart';
import 'package:auto_scoring_app/core/confidence_level.dart';
import 'package:auto_scoring_app/core/pdf_review_geometry.dart';

/// 添削レビュー画面 (simplified-design-specification.md §16.5, Issue #21 + #22).
///
/// Shows the original answer PDF with AI recognition/score/rubric/confidence
/// and annotations for the selected question side by side: Navigation Rail
/// (設問一覧) + `pdfrx` PDF viewer with a widget overlay for annotations that
/// carry a target Bounding Box + Inspector (認識文字/点数/根拠/採点基準/
/// confidence) + a bottom action bar. The original PDF is never edited --
/// annotations are drawn as widgets on top of it (§13.1).
///
/// Edit/reject/regrade/approve-and-next and Ctrl+Z undo (Issue #22) each
/// persist an append-only `Review` row through the sidecar
/// (`AppDependencies.editReview`/`rejectReview`/`regradeReview`/
/// `approveReview`/`undoReview`) and re-fetch this question's full state
/// afterwards -- nothing about a reviewer's decision lives only in this
/// screen's memory any more (that was Issue #21's own, explicit "対象外").
/// Generating the final corrected PDF is still a later issue's job. See
/// `docs/pdf-review-overlay.md` (Issue #21) and
/// `docs/review-edit-history.md` (Issue #22) for the full list of
/// decisions/open questions this screen relies on.
///
/// `features` may depend on `core` and `api` (see `AGENTS.md` "Architecture").
class PdfReviewPage extends StatefulWidget {
  const PdfReviewPage({
    super.key,
    required this.dependencies,
    required this.testId,
    required this.submissionId,
  });

  final AppDependencies dependencies;
  final String testId;
  final String submissionId;

  @override
  State<PdfReviewPage> createState() => _PdfReviewPageState();
}

/// The last element of [reviews] that is neither an ``undone`` row nor the
/// specific row an ``undone`` row names, or `null` if every row has been
/// undone (or there are none) -- the server-side twin of
/// `domain.review_workflow.effective_latest_review` (Issue #22). See that
/// function's docstring: Redo is out of scope for Issue #22, so a plain
/// exclusion set is sufficient here too.
ReviewResponse? _effectiveLatestReview(List<ReviewResponse>? reviews) {
  if (reviews == null) return null;
  final excluded = <String>{};
  for (final review in reviews) {
    if (review.action == 'undone') {
      excluded.add(review.id);
      final target = review.undoneReviewId;
      if (target != null) excluded.add(target);
    }
  }
  for (var i = reviews.length - 1; i >= 0; i--) {
    if (!excluded.contains(reviews[i].id)) return reviews[i];
  }
  return null;
}

/// Everything fetched (or being fetched) for one question, including its
/// full append-only review history (Issue #22). Persisting a reviewer's
/// edit/reject/regrade/approve/undo decision happens through
/// `AppDependencies`' review methods -- this only caches the server's own
/// state, it never invents any of its own.
class QuestionReviewState {
  List<RecognitionResponse>? recognitions;
  List<GradeResultResponse>? grades;
  List<AnnotationResponse>? annotations;
  List<ReviewResponse>? reviews;
  String? error;
  bool loading = false;

  /// Shared free-text input for whichever action the reviewer next takes
  /// (edit's note, reject's/regrade's reason) -- backed by `_noteController`
  /// in `_PdfReviewPageState`, cleared per question the same way that
  /// controller already is.
  String note = '';

  /// Set for the duration of one edit/reject/regrade/approve/undo call for
  /// this question, so the action bar can disable itself and a second click
  /// (or a duplicate keyboard shortcut trigger) can't fire an overlapping
  /// request with the same `expectedVersion` (`_performReviewAction`).
  bool actionInFlight = false;

  /// Bumped at the start of every `_ensureReviewLoaded` call for this
  /// question; a call only applies its result if it is still the most
  /// recently issued one by the time its fetch resolves. Without this, a
  /// slower, superseded fetch (e.g. two overlapping poll ticks, or a manual
  /// refresh racing the background poll) completing after a newer one could
  /// overwrite fresher data with stale data (P2 review).
  int fetchGeneration = 0;

  bool get hasLoaded =>
      recognitions != null &&
      grades != null &&
      annotations != null &&
      reviews != null;

  /// The `Review` row currently in effect for this question (Issue #22),
  /// or `null` if none exists yet or every one has been undone.
  ReviewResponse? get effectiveReview => _effectiveLatestReview(reviews);

  /// The version token the *next* edit/reject/regrade/approve/undo call for
  /// this question must pass as `expectedVersion` -- this pair's review
  /// history length so far.
  int get expectedVersion => reviews?.length ?? 0;

  /// Whether this question's grade is currently confirmed (`approved`/
  /// `modified`, and not since undone) -- gates whether "承認して次へ" still
  /// needs to record a fresh confirmation or may just navigate.
  bool get isConfirmed {
    final action = effectiveReview?.action;
    return action == 'approved' || action == 'modified';
  }

  /// The OCR pipeline's own reading (Issue #19), or `null` if none exists
  /// yet. Kept separate from [latestGradingRecognition] and
  /// [effectiveHumanRecognition]: a multimodal grader may correct the OCR
  /// text it was given, and that correction is persisted as a *second*,
  /// distinct AI-sourced row rather than replacing this one (append-only
  /// history, docs/ai-grading-pipeline.md "AI graderが訂正した認識結果を
  /// 保持する") -- so a reviewer can compare what OCR read against what the
  /// grader actually used, not just see whichever happens to be more recent.
  RecognitionResponse? get latestOcrRecognition =>
      _latestWhere(recognitions, (r) => r.stage == 'ocr');

  /// The AI grader's own (possibly OCR-correcting) reading, or `null` if
  /// grading hasn't produced one yet. See [latestOcrRecognition].
  RecognitionResponse? get latestGradingRecognition =>
      _latestWhere(recognitions, (r) => r.stage == 'grading');

  /// The latest AI-proposed grade, or `null` if none exists yet.
  GradeResultResponse? get latestAiGrade =>
      _latestWhere(grades, (g) => g.source_ == 'ai');

  /// The latest human-confirmed/corrected grade, or `null` if a human has
  /// never graded this question yet.
  GradeResultResponse? get latestHumanGrade =>
      _latestWhere(grades, (g) => g.source_ == 'human');

  /// The most authoritative grade to show where only one value fits (e.g.
  /// the `score` annotation on the PDF overlay), derived from
  /// [effectiveReview] rather than simply "the latest human grade by
  /// timestamp" (Issue #22 P1: Undo must actually revert what is
  /// *displayed*, not just add a new history row alongside an unaffected
  /// display). `Review.MODIFIED` -> its own `humanGradeResultId`;
  /// `Review.APPROVED` -> its own `aiGradeResultId`; anything else
  /// (`rejected`/`regrade_requested`, or nothing reviewed yet) -> the latest
  /// AI proposal, so a fresh AI attempt after a regrade request still shows
  /// up automatically once it lands.
  GradeResultResponse? get displayGrade {
    final review = effectiveReview;
    switch (review?.action) {
      case 'modified':
        return _gradeById(review!.humanGradeResultId) ?? latestAiGrade;
      case 'approved':
        return _gradeById(review!.aiGradeResultId) ?? latestAiGrade;
      default:
        return latestAiGrade;
    }
  }

  GradeResultResponse? _gradeById(String? id) {
    if (id == null) return null;
    return _latestWhere(grades, (g) => g.id == id);
  }

  /// The recognized text currently in effect, given [effectiveReview] --
  /// the same undo-aware resolution [displayGrade] already gives the score
  /// (Issue #22 P1 review): once Undo reverts a `modified` review, the human
  /// [RecognitionResponse] it introduced must stop being treated as the
  /// authoritative reading the Inspector/edit dialog show, even though its
  /// row is still there (append-only). A `modified` review in effect shows
  /// the human recognition sharing its own human grade's `createdAt`
  /// (`edit_question` persists both from the same clock read, the same
  /// signal [annotationsForDisplayedAttempt] already relies on) -- `null` if
  /// that edit did not touch the recognized text at all, so callers fall
  /// back through [latestGradingRecognition]/[latestOcrRecognition] exactly
  /// as if no human correction had ever happened.
  RecognitionResponse? get effectiveHumanRecognition {
    final review = effectiveReview;
    if (review?.action != 'modified') return null;
    final humanGrade = _gradeById(review!.humanGradeResultId);
    if (humanGrade == null) return null;
    return _latestWhere(
      recognitions,
      (r) => r.stage == 'human' && r.createdAt == humanGrade.createdAt,
    );
  }

  /// Only the annotations belonging to [displayGrade]'s own grading attempt,
  /// not every attempt this question has ever had. `Annotation` carries no
  /// explicit link to the `GradeResult` it was produced alongside
  /// (`GradingJobProcessor.process` persists both from the exact same clock
  /// read, in the exact same transaction, but records neither row's id on
  /// the other) -- a re-submitted question (Issue #18: a new confirmed
  /// dependency-graph version) creates a new Job, and therefore a new grade
  /// *and* a new set of annotations, without ever removing the old ones
  /// (append-only history). Matching on that shared `created_at` is the
  /// only signal available to tell attempts apart without a schema change
  /// (P1 review) -- without it, every past attempt's marks stayed overlaid
  /// on top of whatever score `displayGrade`/the Inspector currently show.
  /// It also correctly hides every AI annotation once a human's own grade
  /// supersedes the AI's (a human grade never shares its `created_at` with
  /// an AI-authored annotation), which is exactly the "stale mark next to a
  /// corrected score" case this exists to prevent.
  List<AnnotationResponse> get annotationsForDisplayedAttempt {
    final grade = displayGrade;
    if (grade == null) return const [];
    return (annotations ?? const <AnnotationResponse>[])
        .where((a) => a.createdAt == grade.createdAt)
        .toList();
  }

  /// Only the recognitions ([RecognitionResponse]s) that could belong to
  /// [displayGrade]'s own grading attempt, for resolving a text-anchored
  /// annotation's Bounding Box against the *right* OCR result.
  ///
  /// Unlike [annotationsForDisplayedAttempt], this cannot match on an exact
  /// shared `created_at`: `RecognitionJobProcessor.process` commits the
  /// OCR-stage `RecognitionResult` in its *own*, earlier transaction, before
  /// the grading half even calls the `AIProvider` (see `_isAwaitingGrade`),
  /// so an attempt's own OCR recognition always predates its grade. A
  /// re-graded question's history holds one such OCR recognition per
  /// attempt (each `Job` gets its own, deterministically-`id`'d row), and
  /// naively searching every one of them for an `anchor_text` match could
  /// pick a *different* (stale, or not-yet-displayed) attempt's box for the
  /// same text at a different position (P2 review). Bounding by "created no
  /// later than [displayGrade]" keeps only recognitions [displayGrade]'s own
  /// attempt could actually have produced -- any recognition from a job
  /// created *after* it (a newer, not-yet-graded re-submission that simply
  /// finished its OCR half first) is excluded, leaving exactly the
  /// currently-displayed attempt's own OCR result as the latest match.
  List<RecognitionResponse> get recognitionsForDisplayedAttempt {
    final all = recognitions ?? const <RecognitionResponse>[];
    final grade = displayGrade;
    if (grade == null) return all;
    return all.where((r) => !r.createdAt.isAfter(grade.createdAt)).toList();
  }
}

/// The last element of [items] matching [test], or `null` if none does.
/// `items` is oldest-first (server history order), so scanning from the end
/// finds the most recent match without a full sort.
T? _latestWhere<T>(List<T>? items, bool Function(T) test) {
  if (items == null) return null;
  for (var i = items.length - 1; i >= 0; i--) {
    if (test(items[i])) return items[i];
  }
  return null;
}

/// Splits [value] into alternating runs of ASCII digits and non-digits,
/// e.g. `"1a"` -> `["1", "a"]`, `"問10"` -> `["問", "10"]`. The building
/// block for [_compareQuestionNumbers]'s natural-sort key.
List<String> _tokenizeForNaturalSort(String value) {
  final tokens = <String>[];
  final buffer = StringBuffer();
  bool? previousWasDigit;
  for (final unit in value.codeUnits) {
    final isDigit = unit >= 0x30 && unit <= 0x39; // '0'..'9'
    if (previousWasDigit != null && isDigit != previousWasDigit) {
      tokens.add(buffer.toString());
      buffer.clear();
    }
    buffer.writeCharCode(unit);
    previousWasDigit = isDigit;
  }
  if (buffer.isNotEmpty) tokens.add(buffer.toString());
  return tokens;
}

/// Orders question numbers the way a reviewer expects: naturally (1, 2,
/// ..., 10), not lexicographically (which would put "10" before "2"), and
/// with a single, transitive rule for labels that mix digits and letters
/// (e.g. sub-questions like "1a") -- `Question.number` accepts any non-empty
/// string (P2 review), so a comparator that only special-cases pure-integer
/// labels and otherwise falls back to raw string comparison is not a total
/// order (it can report `2 < 10`, `10 < "1a"`, and `"1a" < 2` all at once,
/// since "10" vs "1a" and "1a" vs "2" each take the *other* branch of that
/// special case). Comparing token-by-token with one fixed rule throughout
/// (equal-type tokens compare within their type; a numeric token always
/// sorts before a non-numeric one at the same position) avoids that: every
/// pairwise comparison normalizes both sides identically, which is what
/// makes the result transitive.
int _compareQuestionNumbers(String a, String b) {
  final tokensA = _tokenizeForNaturalSort(a);
  final tokensB = _tokenizeForNaturalSort(b);
  final sharedLength = tokensA.length < tokensB.length
      ? tokensA.length
      : tokensB.length;
  for (var i = 0; i < sharedLength; i++) {
    final numA = int.tryParse(tokensA[i]);
    final numB = int.tryParse(tokensB[i]);
    if (numA != null && numB != null) {
      final comparison = numA.compareTo(numB);
      if (comparison != 0) return comparison;
      continue;
    }
    if (numA != null) return -1;
    if (numB != null) return 1;
    final comparison = tokensA[i].compareTo(tokensB[i]);
    if (comparison != 0) return comparison;
  }
  return tokensA.length.compareTo(tokensB.length);
}

class _PdfReviewPageState extends State<PdfReviewPage> {
  late final PdfViewerController _pdfController;
  final _noteController = TextEditingController();
  final _noteFocusNode = FocusNode(debugLabel: '修正コメント');

  bool _loadingShell = true;
  String? _shellError;
  SubmissionResponse? _submission;
  List<QuestionResponse> _questions = const [];
  Uint8List? _pdfBytes;
  int _questionIndex = 0;
  final Map<String, QuestionReviewState> _reviews = {};
  List<JobResponse> _jobs = const [];
  Timer? _pollTimer;

  @override
  void initState() {
    super.initState();
    _pdfController = PdfViewerController();
    // Rebuilds so the keyboard bindings in build() can drop out while the
    // note field has focus (see _shortcutBindings) -- FocusNode changes do
    // not trigger a rebuild on their own.
    _noteFocusNode.addListener(_handleNoteFocusChange);
    _loadShell();
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    _noteFocusNode.removeListener(_handleNoteFocusChange);
    _noteController.dispose();
    _noteFocusNode.dispose();
    super.dispose();
  }

  void _handleNoteFocusChange() {
    if (mounted) setState(() {});
  }

  /// `Job.state` values that will never change again on their own -- once a
  /// question's job reaches one of these, nothing still running server-side
  /// could still produce a grade for it (mirrors
  /// `auto_scoring.domain.models.JobState`; a `FAILED` job can still be
  /// auto-retried back to `QUEUED` by the backend's own retry policy, but
  /// that is exactly the "not obviously still running" case the manual
  /// refresh button exists for, same as every other terminal state here).
  static const _terminalJobStates = {'succeeded', 'failed', 'cancelled'};

  /// The most recently created `Job` for [questionId], or `null` if none has
  /// been created yet (Issue #18: jobs are created only via an explicit
  /// `POST .../jobs`, never automatically, and a re-submission under a new
  /// confirmed dependency-graph version creates a second one for the same
  /// question).
  JobResponse? _latestJobFor(String questionId) {
    JobResponse? latest;
    for (final job in _jobs) {
      if (job.questionId != questionId) continue;
      if (latest == null || job.createdAt.isAfter(latest.createdAt)) {
        latest = job;
      }
    }
    return latest;
  }

  /// Whether [questionId]'s AI processing might still produce (or replace)
  /// a grade -- polling must keep running, and a cached "loaded" result
  /// must stay provisional (not treated as final), while this is true.
  ///
  /// Not simply "no grade exists yet": `GradingJobProcessor.process`
  /// commits the OCR half's `RecognitionResult` in its own transaction
  /// *before* ever calling the `AIProvider` for the grading half
  /// (`jobs/grading_processor.py`) -- so a job can already be `RUNNING`,
  /// still waiting on that provider call, with only its OCR recognition
  /// visible so far. Stopping as soon as *any* AI output (including just
  /// that recognition) exists would let the screen decide "done" while a
  /// grade is still on its way, leaving 承認 permanently disabled until a
  /// manual refresh (P1 review).
  ///
  /// Nor is "*a* grade exists" enough on its own (P2 review): a question can
  /// be re-submitted under a newer confirmed dependency-graph version
  /// (Issue #18), which creates a *new* `Job` for it while the append-only
  /// history still has the previous attempt's `GradeResult`. If that new
  /// job is `QUEUED`/`RUNNING`/`BLOCKED`, the cached `latestAiGrade` belongs
  /// to a superseded attempt, not the one currently in flight -- treating
  /// it as final would leave the reviewer looking at a stale score/
  /// annotations even after the new attempt finishes, until a manual
  /// refresh.
  ///
  /// So this keeps polling while either: no job is known for [questionId]
  /// and no grade exists yet either (nothing to go on but "keep checking");
  /// the latest known job is not yet in a [_terminalJobStates] state (a
  /// newer attempt might still be running, whether or not an older grade
  /// happens to be cached); or the latest job *is* terminal but the cached
  /// grade still predates it (`grade.createdAt` no later than
  /// `job.createdAt` -- the grade was written strictly after the job that
  /// produced it was created, so this means the grades list has not caught
  /// up with that attempt's result yet and needs one more refetch).
  bool _isAwaitingGrade(QuestionReviewState review, String questionId) {
    final job = _latestJobFor(questionId);
    if (job == null) return review.latestAiGrade == null;
    if (!_terminalJobStates.contains(job.state)) return true;
    final grade = review.latestAiGrade;
    return grade == null ? false : !grade.createdAt.isAfter(job.createdAt);
  }

  /// Starts polling while the *currently selected* question is still
  /// [_isAwaitingGrade], and stops once it is not. Safe to call repeatedly
  /// -- it only (re)starts the timer when the desired state actually
  /// changes.
  ///
  /// Deliberately not keyed on `_submission.state`: intake moves a
  /// submission through `unprocessed`/`ai_processing` to `ai_processed`
  /// synchronously, before any per-question recognition/grading job even
  /// exists (`adapters/submission_intake.py`) -- by the time a reviewer
  /// opens this page the submission is essentially always already past
  /// those two states, so gating polling on them means the real
  /// queued/running window is never actually observed and an
  /// initially-empty question stays cached until a manual refresh (P1
  /// review). Whether *this* question's own job/grade has actually finished
  /// is the one signal that tracks its real progress.
  void _updatePolling() {
    final review = _currentReview;
    final question = _currentQuestion;
    final shouldPoll =
        review == null ||
        review.loading ||
        (question != null && _isAwaitingGrade(review, question.id));
    if (shouldPoll == (_pollTimer != null)) return;
    if (shouldPoll) {
      _pollTimer = Timer.periodic(
        const Duration(seconds: 3),
        (_) => _pollWhileProcessing(),
      );
    } else {
      _pollTimer?.cancel();
      _pollTimer = null;
    }
  }

  /// Set for the duration of one [_pollWhileProcessing] run -- a refresh
  /// occasionally takes longer than the 3-second tick interval (e.g. a slow
  /// request), and without this a new tick firing mid-refresh would start a
  /// second, overlapping fetch on top of it (P2 review). The per-question
  /// generation counter in `_ensureReviewLoaded` also guards the data
  /// itself, but skipping the overlapping tick here avoids the redundant
  /// request entirely.
  bool _pollInFlight = false;

  Future<void> _pollWhileProcessing() async {
    if (_pollInFlight) return;
    _pollInFlight = true;
    try {
      final submission = await widget.dependencies.getSubmission(
        widget.submissionId,
      );
      if (!mounted) return;
      setState(() => _submission = submission);
      await _refreshJobs();
      _updatePolling();
      // Silent: a background poll should not flash the loading spinner or
      // an error banner over content the reviewer is already looking at.
      await _ensureReviewLoaded(forceReload: true, silent: true);
    } on SidecarApiException {
      // Transient poll failure -- retried on the next tick rather than
      // surfaced as an error banner.
    } finally {
      _pollInFlight = false;
    }
  }

  /// Manual "更新" action (P1 review: a submission stuck in
  /// unprocessed/ai_processing must be refreshable without relying solely
  /// on the background poll) -- refreshes the *currently selected* question.
  /// See [_refreshQuestion] for the version [_performReviewAction] uses,
  /// which refreshes whichever question the action was actually for.
  Future<void> _refreshCurrentQuestion() async {
    final question = _currentQuestion;
    if (question == null) return;
    await _refreshQuestion(question);
  }

  /// Refreshes [question]'s own recognitions/grades/annotations/reviews
  /// (plus the submission's own state chip and the job list) regardless of
  /// which question is currently selected -- [_performReviewAction] passes
  /// the question an edit/reject/regrade/approve/undo call actually acted
  /// on, which may no longer be [_currentQuestion] by the time the request
  /// resolves if the reviewer navigated away while it was in flight (P2
  /// review): refreshing "the current question" in that case would update
  /// the wrong question's cache and leave the acted-upon one stale. Best-
  /// effort on the submission refetch -- a failure there still lets the
  /// question data refresh below, since that is the part a reviewer
  /// watching a stuck "処理中" state actually wants.
  Future<void> _refreshQuestion(QuestionResponse question) async {
    try {
      final submission = await widget.dependencies.getSubmission(
        widget.submissionId,
      );
      if (!mounted) return;
      setState(() => _submission = submission);
    } on SidecarApiException {
      // Fall through to refreshing the question data regardless.
    }
    await _refreshJobs();
    _updatePolling();
    await _loadReview(question, forceReload: true);
  }

  /// Best-effort refresh of every job for this submission. A failure here
  /// must never block the submission/question refresh around it -- the Jobs
  /// API only ever informs [_updatePolling]/[_isAwaitingGrade]'s decision,
  /// it is never the sole source of anything the Inspector itself shows, so
  /// a stale (or, initially, empty) [_jobs] just means "treat this
  /// question's own job state as unknown" rather than surfacing an error.
  Future<void> _refreshJobs() async {
    try {
      final jobs = await widget.dependencies.listJobs(widget.submissionId);
      if (!mounted) return;
      setState(() => _jobs = jobs);
    } on SidecarApiException {
      // Keep the last-known jobs list -- retried on the next tick/refresh.
    }
  }

  QuestionResponse? get _currentQuestion =>
      _questionIndex >= 0 && _questionIndex < _questions.length
      ? _questions[_questionIndex]
      : null;

  QuestionReviewState? get _currentReview {
    final question = _currentQuestion;
    if (question == null) return null;
    return _reviews[question.id];
  }

  Future<void> _loadShell() async {
    setState(() {
      _loadingShell = true;
      _shellError = null;
    });
    try {
      final submission = await widget.dependencies.getSubmission(
        widget.submissionId,
      );
      final questions = await widget.dependencies.listQuestions(widget.testId);
      final pdfBytes = await widget.dependencies.getSourcePdf(
        widget.submissionId,
      );
      final sorted = questions.toList()
        ..sort((a, b) {
          final byPage = a.page.compareTo(b.page);
          return byPage != 0
              ? byPage
              : _compareQuestionNumbers(a.number, b.number);
        });
      if (!mounted) return;
      setState(() {
        _submission = submission;
        _questions = sorted;
        _pdfBytes = pdfBytes;
        _questionIndex = 0;
      });
      await _refreshJobs();
      _updatePolling();
      unawaited(_ensureReviewLoaded());
    } on SidecarApiException catch (error) {
      if (!mounted) return;
      setState(() => _shellError = error.message);
    } finally {
      if (mounted) setState(() => _loadingShell = false);
    }
  }

  /// [_loadReview] for the *currently selected* question. See that method
  /// for [forceReload]/[silent].
  Future<void> _ensureReviewLoaded({
    bool forceReload = false,
    bool silent = false,
  }) async {
    final question = _currentQuestion;
    if (question == null) return;
    await _loadReview(question, forceReload: forceReload, silent: silent);
  }

  /// Fetches (or refreshes) [question]'s recognitions/grades/annotations --
  /// not necessarily the currently selected one: [_refreshQuestion] passes
  /// whichever question an in-flight review action was actually for, which
  /// may differ from [_currentQuestion] by the time that action resolves
  /// (P2 review). [silent] skips flipping [QuestionReviewState.loading]/
  /// clearing its error and skips surfacing a fetch failure -- used by the
  /// background poll below so a transient hiccup or the routine "still
  /// nothing yet" tick doesn't flash the spinner or an error banner over
  /// content the reviewer is already looking at.
  Future<void> _loadReview(
    QuestionResponse question, {
    bool forceReload = false,
    bool silent = false,
  }) async {
    final existing = _reviews[question.id];
    if (silent && existing != null && existing.loading) {
      // A visible fetch (initial load, manual refresh, or a question
      // switch) is already in flight for this question -- let it finish
      // undisturbed instead of bumping fetchGeneration out from under it.
      // Silent fetches never set `loading` themselves, so this can only be
      // true because of a visible one; superseding it here would otherwise
      // leave `loading` stuck true forever if this silent poll then fails
      // (its failure handler intentionally never touches `loading`/`error`,
      // see below) (P2 review).
      return;
    }
    // A cached result with no grade yet is not necessarily final -- this
    // question's own job may simply still be running (see
    // `_isAwaitingGrade`), independent of the submission's own state -- so
    // it must not block a later refetch just because `hasLoaded` happens to
    // be true. Recomputed from the *current* cache each call (not a stored
    // flag) so it also self-corrects if this question was last fetched from
    // a different question's perspective (e.g. a stale entry that was never
    // revisited) (P1 review).
    final resultsStillMissing =
        existing != null && _isAwaitingGrade(existing, question.id);
    if (existing != null &&
        !forceReload &&
        !resultsStillMissing &&
        !existing.loading &&
        existing.error == null &&
        existing.hasLoaded) {
      return;
    }
    // Guards against a slower, superseded fetch for this same question
    // overwriting a newer one's result -- e.g. two poll ticks 3 seconds
    // apart where the first is still in flight when the second starts, or
    // a manual refresh racing the background poll (P2 review).
    final review = existing ?? QuestionReviewState();
    final generation = ++review.fetchGeneration;
    if (silent) {
      _reviews[question.id] = review;
    } else {
      review.loading = true;
      review.error = null;
      setState(() => _reviews[question.id] = review);
    }
    try {
      final recognitions = await widget.dependencies.listRecognitions(
        widget.submissionId,
        question.id,
      );
      final grades = await widget.dependencies.listGrades(
        widget.submissionId,
        question.id,
      );
      final annotations = await widget.dependencies.listAnnotations(
        widget.submissionId,
        question.id,
      );
      final reviews = await widget.dependencies.listReviews(
        widget.submissionId,
        question.id,
      );
      // `GradingJobProcessor.process` commits the grading-stage recognition
      // atomically with the grade (and its annotations) it accompanies --
      // both written from the exact same clock read, same as
      // `QuestionReviewState.annotationsForDisplayedAttempt` relies on --
      // but strictly *after*, and separately from, the OCR-stage
      // recognition's own earlier commit. If that atomic commit lands
      // between the `listRecognitions` and `listGrades` calls above,
      // `recognitions` is a snapshot from just before it: it is missing the
      // grading-stage recognition the grade we just fetched was written
      // alongside, even though that grade itself already reflects the new
      // attempt. Left uncorrected, 採点AIの認識結果 stays missing until a
      // manual refresh, because a grade already exists and (per
      // `_isAwaitingGrade`) that alone can stop polling (P2 review).
      // Detected by checking whether the latest AI grade has a matching
      // recognition (identical `created_at`, by construction); if not, one
      // more fetch picks up a consistent snapshot.
      final latestAiGrade = _latestWhere(grades, (g) => g.source_ == 'ai');
      final consistentRecognitions =
          latestAiGrade == null ||
              recognitions.any((r) => r.createdAt == latestAiGrade.createdAt)
          ? recognitions
          : await widget.dependencies.listRecognitions(
              widget.submissionId,
              question.id,
            );
      if (!mounted || generation != review.fetchGeneration) return;
      setState(() {
        review.recognitions = consistentRecognitions;
        review.grades = grades;
        review.annotations = annotations;
        review.reviews = reviews;
        review.loading = false;
        // A successful refresh -- silent or not -- means the Inspector no
        // longer needs to keep showing a fetch failure from before it (P2
        // review): the data it was retried for is here now.
        review.error = null;
      });
    } on SidecarApiException catch (error) {
      if (!mounted || silent || generation != review.fetchGeneration) return;
      setState(() {
        review.error = error.message;
        review.loading = false;
      });
    } finally {
      if (mounted) _updatePolling();
    }
  }

  void _selectQuestion(int index) {
    if (index < 0 || index >= _questions.length || index == _questionIndex) {
      return;
    }
    final previousPage = _currentQuestion?.page;
    setState(() => _questionIndex = index);
    final question = _currentQuestion!;
    _noteController.text = _reviews[question.id]?.note ?? '';
    // Only move the viewer when the target question is on a different page --
    // staying on the same page keeps whatever zoom/scroll the reviewer set
    // (Issue #21 acceptance: "Question/Submission移動、zoom/scrollを保った
    // page表示").
    if (previousPage != question.page && _pdfController.isReady) {
      unawaited(_pdfController.goToPage(pageNumber: question.page));
    }
    // Re-evaluate immediately against the newly-selected question's own
    // (possibly already-loaded) cache, rather than waiting for
    // _ensureReviewLoaded below to eventually finish -- it may not do
    // anything at all if this question already has data.
    _updatePolling();
    unawaited(_ensureReviewLoaded());
  }

  void _moveQuestion(int delta) => _selectQuestion(_questionIndex + delta);

  /// Whether the current question's data is fully loaded and free of a
  /// fetch error -- approving/rejecting data the reviewer cannot actually
  /// see yet (still loading, or the last fetch failed) would let them
  /// unknowingly confirm content they never reviewed. Also false while a
  /// review action for this question is already in flight, so a second
  /// click (or a duplicate keyboard trigger) can't fire an overlapping
  /// request (Issue #22).
  bool get _canDecide {
    final review = _currentReview;
    return review != null &&
        !review.loading &&
        !review.actionInFlight &&
        review.error == null &&
        review.hasLoaded;
  }

  /// Whether "承認して次へ" may act: [_canDecide], and either the question is
  /// already confirmed (pure navigation -- an `edit` already confirmed it in
  /// the same step) or an AI grade exists to confirm (domain: `Review`
  /// requires `ai_grade_result_id` for `APPROVED`, P1 review).
  bool get _canApprove {
    final review = _currentReview;
    if (!_canDecide) return false;
    return review!.isConfirmed || review.latestAiGrade != null;
  }

  /// Whether Ctrl+Z has something to revert.
  bool get _canUndo {
    final review = _currentReview;
    return _canDecide && review!.effectiveReview != null;
  }

  String? _reasonFromNote(QuestionReviewState review) =>
      review.note.trim().isEmpty ? null : review.note.trim();

  /// Runs one edit/reject/regrade/approve/undo call for [question],
  /// disabling [review]'s action bar for its duration and always resyncing
  /// [question]'s full state (recognitions/grades/annotations/reviews, and
  /// the submission's own state chip) afterwards -- on success *and* on
  /// failure, since a `SidecarErrorKind.conflict` means another request
  /// already changed what's on the server (Issue #22 acceptance: "同時/重複
  /// requestが履歴を二重作成せず…"). Takes [question]/[review] as explicit
  /// captured-before-the-await parameters, not read fresh from
  /// [_currentQuestion]/[_currentReview]: navigation stays enabled while an
  /// action is in flight (only [question]'s own action bar disables), so the
  /// reviewer may already have selected a different question by the time
  /// [action] resolves -- refreshing "whichever question is current then"
  /// would update the wrong question's cache and leave [question] stale (P2
  /// review). Returns whether [action] completed without error, so a caller
  /// like [_approveAndNext] knows whether it is safe to also navigate.
  Future<bool> _performReviewAction(
    QuestionResponse question,
    QuestionReviewState review,
    Future<void> Function() action,
  ) async {
    if (review.actionInFlight) return false;
    setState(() => review.actionInFlight = true);
    var succeeded = false;
    try {
      await action();
      succeeded = true;
    } on SidecarApiException catch (error) {
      if (!mounted) return false;
      final message = error.kind == SidecarErrorKind.conflict
          ? '他の操作と競合しました。最新の状態に更新します。(${error.message})'
          : error.message;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(message)));
    } finally {
      await _refreshQuestion(question);
      if (mounted) setState(() => review.actionInFlight = false);
    }
    return succeeded;
  }

  Future<void> _approveAndNext() async {
    if (!_canApprove) return;
    final review = _currentReview!;
    final question = _currentQuestion!;
    var proceed = true;
    if (!review.isConfirmed) {
      proceed = await _performReviewAction(
        question,
        review,
        () => widget.dependencies.approveReview(
          widget.submissionId,
          question.id,
          expectedVersion: review.expectedVersion,
          expectedAiGradeId: review.latestAiGrade?.id,
          note: _reasonFromNote(review),
        ),
      );
    }
    if (!mounted || !proceed) return;
    // Only auto-advance if the reviewer hasn't already navigated away from
    // [question] while the approve request above was in flight (P2 review)
    // -- otherwise this would advance from wherever they've since selected
    // instead, and [question] itself would never be the one advanced past.
    if (_currentQuestion?.id != question.id) return;
    if (_questionIndex < _questions.length - 1) {
      _moveQuestion(1);
    } else {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('最後の設問です')));
    }
  }

  Future<void> _reject() async {
    if (!_canDecide) return;
    final review = _currentReview!;
    final question = _currentQuestion!;
    await _performReviewAction(
      question,
      review,
      () => widget.dependencies.rejectReview(
        widget.submissionId,
        question.id,
        expectedVersion: review.expectedVersion,
        reason: _reasonFromNote(review),
      ),
    );
  }

  Future<void> _regrade() async {
    if (!_canDecide) return;
    final review = _currentReview!;
    final question = _currentQuestion!;
    await _performReviewAction(
      question,
      review,
      () => widget.dependencies.regradeReview(
        widget.submissionId,
        question.id,
        expectedVersion: review.expectedVersion,
        reason: _reasonFromNote(review),
      ),
    );
  }

  Future<void> _undo() async {
    if (!_canUndo) return;
    final review = _currentReview!;
    final question = _currentQuestion!;
    await _performReviewAction(
      question,
      review,
      () => widget.dependencies.undoReview(
        widget.submissionId,
        question.id,
        expectedVersion: review.expectedVersion,
      ),
    );
  }

  /// Opens the "修正" dialog (score/comment/recognized text), prefilled from
  /// [QuestionReviewState.displayGrade] -- Issue #22's "edit" use case.
  /// Always confirms in the same step (`ReviewAction.MODIFIED`), matching
  /// `adapters.review_actions.edit_question`'s own docstring. Annotation
  /// editing (moving/deleting a mark) is out of scope for Issue #22 -- see
  /// `docs/review-edit-history.md` "Annotationの修正範囲".
  Future<void> _showEditDialog() async {
    if (!_canDecide) return;
    final review = _currentReview!;
    final question = _currentQuestion!;
    final currentGrade = review.displayGrade;
    final currentText =
        review.effectiveHumanRecognition?.text ??
        review.latestGradingRecognition?.text ??
        review.latestOcrRecognition?.text ??
        '';
    final scoreController = TextEditingController(
      text: (currentGrade?.score.awarded ?? 0).toString(),
    );
    final commentController = TextEditingController(
      text: currentGrade?.comment ?? '',
    );
    final textController = TextEditingController(text: currentText);
    final saved = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text('問${question.number} を修正'),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              TextField(
                key: const Key('edit-dialog-text'),
                controller: textController,
                decoration: const InputDecoration(labelText: '認識文字'),
                maxLines: 3,
              ),
              const SizedBox(height: 12),
              TextField(
                key: const Key('edit-dialog-score'),
                controller: scoreController,
                decoration: InputDecoration(
                  labelText: '点数 (0〜${question.points})',
                ),
                keyboardType: TextInputType.number,
              ),
              const SizedBox(height: 12),
              TextField(
                key: const Key('edit-dialog-comment'),
                controller: commentController,
                decoration: const InputDecoration(labelText: 'コメント'),
                maxLines: 2,
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text('キャンセル'),
          ),
          FilledButton(
            key: const Key('edit-dialog-save'),
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: const Text('保存'),
          ),
        ],
      ),
    );
    if (saved != true || !mounted) return;
    final score = int.tryParse(scoreController.text.trim());
    if (score == null || score < 0 || score > question.points) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('点数は0〜${question.points}の整数で入力してください')),
      );
      return;
    }
    final text = textController.text.trim();
    final comment = commentController.text.trim();
    await _performReviewAction(
      question,
      review,
      () => widget.dependencies.editReview(
        widget.submissionId,
        question.id,
        expectedVersion: review.expectedVersion,
        expectedAiGradeId: review.latestAiGrade?.id,
        scoreAwarded: score,
        scoreMaximum: question.points,
        comment: comment.isEmpty ? null : comment,
        recognizedText: text.isEmpty ? null : text,
        note: _reasonFromNote(review),
      ),
    );
  }

  void _saveNote(String value) {
    final question = _currentQuestion;
    if (question == null) return;
    final review = _reviews.putIfAbsent(question.id, QuestionReviewState.new);
    review.note = value;
  }

  /// Empty while the note field has focus, so plain (unmodified) keys the
  /// reviewer types into it -- including "x"/"e"/"r" and Enter for a newline
  /// -- reach the text field instead of triggering 却下/修正/再判定/承認して
  /// 次へ. `CallbackShortcuts` swallows any matching key regardless of what
  /// its callback does, so the binding itself must be absent, not merely a
  /// no-op, while typing (P1 review).
  ///
  /// Key assignments per docs/business-rules-and-evaluation-data.md §2 (16):
  /// Enter=承認して次へ, E=修正, X=却下, R=再判定, ↑/↓=設問移動, Ctrl+Z=Undo.
  Map<ShortcutActivator, VoidCallback> get _shortcutBindings {
    if (_noteFocusNode.hasFocus) return const {};
    return {
      LogicalKeySet(LogicalKeyboardKey.arrowDown): () => _moveQuestion(1),
      LogicalKeySet(LogicalKeyboardKey.arrowUp): () => _moveQuestion(-1),
      LogicalKeySet(LogicalKeyboardKey.enter): () =>
          unawaited(_approveAndNext()),
      LogicalKeySet(LogicalKeyboardKey.keyX): () => unawaited(_reject()),
      LogicalKeySet(LogicalKeyboardKey.keyE): () =>
          unawaited(_showEditDialog()),
      LogicalKeySet(LogicalKeyboardKey.keyR): () => unawaited(_regrade()),
      LogicalKeySet(LogicalKeyboardKey.control, LogicalKeyboardKey.keyZ): () =>
          unawaited(_undo()),
    };
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(_appBarTitle()),
        actions: [
          IconButton(
            key: const Key('review-refresh-button'),
            tooltip: '更新',
            icon: const Icon(Icons.refresh),
            onPressed: _loadingShell ? null : _refreshCurrentQuestion,
          ),
        ],
      ),
      body: _loadingShell
          ? const Center(
              key: Key('review-loading'),
              child: CircularProgressIndicator(),
            )
          : _shellError != null
          ? _buildShellError()
          : _questions.isEmpty
          ? const Center(
              key: Key('review-empty-shell'),
              child: Text('この設問構成にはまだ設問がありません'),
            )
          : CallbackShortcuts(
              bindings: _shortcutBindings,
              child: Focus(autofocus: true, child: _buildReviewBody(context)),
            ),
    );
  }

  String _appBarTitle() {
    final label = _submission?.studentLabel ?? widget.submissionId;
    return '添削レビュー - $label';
  }

  Widget _buildShellError() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.error_outline, size: 40),
            const SizedBox(height: 8),
            Text(_shellError!, key: const Key('review-shell-error')),
            const SizedBox(height: 16),
            FilledButton(onPressed: _loadShell, child: const Text('再試行')),
          ],
        ),
      ),
    );
  }

  Widget _buildReviewBody(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        // Below this width the Inspector moves under the PDF viewer instead
        // of beside it (Issue #21 acceptance: desktopの標準/狭幅表示). The
        // Navigation Rail itself always stays a vertical rail on the left --
        // it only switches to icon-only labels -- since `NavigationRail`
        // does not support a horizontal layout.
        final narrow = constraints.maxWidth < 900;
        final rail = _buildNavigationRail(narrow: narrow);
        final inspector = _buildInspector(narrow: narrow);
        // The narrow (stacked) layout splits height by flex ratio, not a
        // fixed pixel size for the Inspector -- a fixed height plus the
        // action bar could exceed a short viewport's total height (a
        // landscape phone, a short desktop window) and overflow. Flexible
        // shares always fit, and the Inspector already scrolls internally
        // if its content doesn't fit its share (P2 review).
        final viewerAndInspector = narrow
            ? Column(
                children: [
                  Expanded(flex: 3, child: _buildPdfViewer()),
                  Expanded(flex: 2, child: inspector),
                ],
              )
            : Row(
                children: [
                  Expanded(child: _buildPdfViewer()),
                  SizedBox(width: 360, child: inspector),
                ],
              );
        return Column(
          children: [
            Expanded(
              child: Row(
                children: [
                  rail,
                  const VerticalDivider(width: 1),
                  Expanded(child: viewerAndInspector),
                ],
              ),
            ),
            _buildActionBar(),
          ],
        );
      },
    );
  }

  /// `NavigationRail` does not scroll its own destinations -- with enough
  /// questions it simply overflows once they no longer fit the available
  /// height. Wrapping it in `SingleChildScrollView` + `IntrinsicHeight`
  /// (the standard workaround for this widget) lets it size to its natural
  /// height and scroll the excess instead (P2 review), while still filling
  /// the full available height when destinations already fit.
  Widget _buildNavigationRail({required bool narrow}) {
    final rail = NavigationRail(
      key: const Key('review-question-rail'),
      selectedIndex: _questionIndex,
      onDestinationSelected: _selectQuestion,
      extended: false,
      labelType: narrow
          ? NavigationRailLabelType.none
          : NavigationRailLabelType.all,
      destinations: [
        for (final question in _questions)
          NavigationRailDestination(
            icon: _questionStatusIcon(question),
            label: Text('問${question.number}'),
          ),
      ],
    );
    return LayoutBuilder(
      builder: (context, constraints) => SingleChildScrollView(
        child: ConstrainedBox(
          constraints: BoxConstraints(minHeight: constraints.maxHeight),
          child: IntrinsicHeight(child: rail),
        ),
      ),
    );
  }

  Icon _questionStatusIcon(QuestionResponse question) {
    final review = _reviews[question.id];
    if (review == null || review.loading) {
      return const Icon(Icons.hourglass_empty);
    }
    if (review.error != null) return const Icon(Icons.error_outline);
    return switch (review.effectiveReview?.action) {
      'approved' || 'modified' => const Icon(Icons.check_circle),
      'rejected' => const Icon(Icons.cancel_outlined),
      'regrade_requested' => const Icon(Icons.autorenew),
      _ => const Icon(Icons.radio_button_unchecked),
    };
  }

  Widget _buildPdfViewer() {
    final bytes = _pdfBytes;
    final question = _currentQuestion;
    if (bytes == null || question == null) {
      return const SizedBox.shrink();
    }
    return Semantics(
      label: '答案PDF 問${question.number} ページ${question.page}',
      child: PdfViewer.data(
        bytes,
        sourceName: widget.submissionId,
        controller: _pdfController,
        initialPageNumber: question.page,
        params: PdfViewerParams(
          pageOverlaysBuilder: (context, pageRect, page) =>
              _buildAnnotationOverlay(page.pageNumber, pageRect.size),
        ),
      ),
    );
  }

  /// Only the *currently selected* question's annotations, never a
  /// previously-visited one that happens to share this page -- rendering
  /// every question ever loaded for this page would make the overlay depend
  /// on navigation history (which questions were visited, and in what
  /// order) instead of on what is actually selected right now.
  List<Widget> _buildAnnotationOverlay(int pageNumber, Size pageSize) {
    final question = _currentQuestion;
    if (question == null || question.page != pageNumber) return const [];
    final review = _reviews[question.id];
    if (review == null) return const [];
    final widgets = <Widget>[];
    for (final annotation in review.annotationsForDisplayedAttempt) {
      final resolved = resolveAnnotationRect(
        annotation: annotation,
        questionAnswerArea: question.answerArea,
        questionScoreArea: question.scoreArea,
        recognitions: review.recognitionsForDisplayedAttempt,
      );
      if (resolved == null) continue;
      final rect = normalizedRectToLocal(resolved, pageSize);
      widgets.add(
        Positioned(
          key: Key('annotation-${annotation.id}'),
          left: rect.left,
          top: rect.top,
          width: rect.width,
          height: rect.height,
          child: _AnnotationMark(
            annotation: annotation,
            displayGrade: review.displayGrade,
          ),
        ),
      );
    }
    return widgets;
  }

  /// The annotations [_buildAnnotationOverlay] could not place anywhere on
  /// the page (§12.4) -- shown in the Inspector's "設問コメント" section
  /// instead of being silently dropped.
  List<AnnotationResponse> _fallbackAnnotationsFor(
    QuestionResponse question,
    QuestionReviewState review,
  ) => review.annotationsForDisplayedAttempt
      .where(
        (a) =>
            resolveAnnotationRect(
              annotation: a,
              questionAnswerArea: question.answerArea,
              questionScoreArea: question.scoreArea,
              recognitions: review.recognitionsForDisplayedAttempt,
            ) ==
            null,
      )
      .toList();

  Widget _buildInspector({required bool narrow}) {
    final question = _currentQuestion;
    final review = _currentReview;
    if (question == null) {
      return const SizedBox.shrink();
    }
    return SingleChildScrollView(
      key: const Key('review-inspector'),
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            '問${question.number}',
            style: Theme.of(context).textTheme.titleLarge,
          ),
          const SizedBox(height: 8),
          _buildSubmissionStateChip(),
          const SizedBox(height: 16),
          if (review == null || review.loading)
            const Center(
              key: Key('review-question-loading'),
              child: Padding(
                padding: EdgeInsets.all(24),
                child: CircularProgressIndicator(),
              ),
            )
          else if (review.error != null)
            _buildQuestionError(review.error!)
          else
            _buildQuestionContent(question, review),
        ],
      ),
    );
  }

  Widget _buildSubmissionStateChip() {
    final state = _submission?.state ?? 'unprocessed';
    final (icon, label) = _submissionStateVisual(state);
    return Chip(
      key: const Key('review-submission-state'),
      avatar: Icon(icon, size: 18),
      label: Text(label),
    );
  }

  Widget _buildQuestionError(String message) {
    return Card(
      color: Theme.of(context).colorScheme.errorContainer,
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(message, key: const Key('review-question-error')),
            TextButton(
              onPressed: () => _ensureReviewLoaded(forceReload: true),
              child: const Text('再試行'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildQuestionContent(
    QuestionResponse question,
    QuestionReviewState review,
  ) {
    final ocrRecognition = review.latestOcrRecognition;
    final gradingRecognition = review.latestGradingRecognition;
    // The *effective* human recognition/grade (Issue #22 P1 review), not
    // simply "the latest human row by timestamp": once Undo reverts a
    // `modified` review, its own `RecognitionResponse`/`GradeResultResponse`
    // rows are still there (append-only) but no longer the ones in effect --
    // see `QuestionReviewState.effectiveHumanRecognition`/`displayGrade`.
    final humanRecognition = review.effectiveHumanRecognition;
    final aiGrade = review.latestAiGrade;
    final displayGrade = review.displayGrade;
    final humanGrade = displayGrade?.source_ == 'human' ? displayGrade : null;
    final fallbackAnnotations = _fallbackAnnotationsFor(question, review);
    // A question can have no AI recognition/grade yet but still carry a
    // fallback annotation (e.g. a human-entered comment) or a rubric
    // definition -- the empty state below must not swallow either, or a
    // comment routed to this fallback area (§12.4), or the question's own
    // marking scheme, would silently disappear for an otherwise-unprocessed
    // question.
    final isEmpty =
        ocrRecognition == null &&
        gradingRecognition == null &&
        humanRecognition == null &&
        aiGrade == null &&
        humanGrade == null &&
        fallbackAnnotations.isEmpty &&
        question.rubric.isEmpty;
    if (isEmpty) {
      return const Text('まだAI結果がありません', key: Key('review-question-empty'));
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('AI認識文字', style: Theme.of(context).textTheme.titleSmall),
        const SizedBox(height: 4),
        if (ocrRecognition == null)
          const Text('未認識')
        else ...[
          Text(ocrRecognition.text, key: const Key('review-recognition-text')),
          const SizedBox(height: 4),
          _ConfidenceBadge(
            key: const Key('review-recognition-confidence'),
            label: 'OCR文字認識信頼度',
            confidence: ocrRecognition.confidence.toDouble(),
          ),
        ],
        // The AI grader's own reading is a *second*, distinct AI-sourced row
        // (docs/ai-grading-pipeline.md "AI graderが訂正した認識結果を保持する")
        // -- shown alongside OCR's, not merged into it, so a reviewer can
        // see whether/how the grader corrected what OCR read (P2 review).
        if (gradingRecognition != null) ...[
          const SizedBox(height: 8),
          Text(
            '採点AIの認識結果',
            key: const Key('review-grading-recognition-label'),
            style: Theme.of(context).textTheme.labelLarge,
          ),
          Text(
            gradingRecognition.text,
            key: const Key('review-grading-recognition-text'),
          ),
          const SizedBox(height: 4),
          _ConfidenceBadge(
            key: const Key('review-grading-recognition-confidence'),
            label: '採点AI文字認識信頼度',
            confidence: gradingRecognition.confidence.toDouble(),
          ),
        ],
        // A human correction never overwrites the AI's row (append-only
        // history, §19/§35-5) -- shown as its own, clearly-labeled entry
        // instead of silently replacing "AI認識文字" above, so a human's
        // confidence (always 1.0) is never mistaken for the AI's.
        if (humanRecognition != null) ...[
          const SizedBox(height: 8),
          _ProvenanceLabel(
            key: const Key('review-human-recognition-label'),
            text: '人による修正',
          ),
          Text(
            humanRecognition.text,
            key: const Key('review-human-recognition-text'),
          ),
        ],
        const Divider(height: 24),
        Text('採点', style: Theme.of(context).textTheme.titleSmall),
        const SizedBox(height: 4),
        if (aiGrade == null)
          const Text('未採点')
        else ...[
          Text(
            '${aiGrade.score.awarded} / ${aiGrade.score.maximum} 点',
            key: const Key('review-score'),
            style: Theme.of(context).textTheme.headlineSmall,
          ),
          const SizedBox(height: 4),
          _ConfidenceBadge(
            key: const Key('review-grading-confidence'),
            label: '採点信頼度',
            confidence: aiGrade.confidence.toDouble(),
          ),
          if (aiGrade.rationale case final rationale?
              when rationale.isNotEmpty) ...[
            const SizedBox(height: 8),
            Text('根拠', style: Theme.of(context).textTheme.labelLarge),
            Text(rationale, key: const Key('review-rationale')),
          ],
          // AIの総評コメント (簡易設計書 §16.5「コメント」) -- 根拠 (この点数に
          // なった理由) とは別の欄として表示する。
          if (aiGrade.comment case final comment? when comment.isNotEmpty) ...[
            const SizedBox(height: 8),
            Text('コメント', style: Theme.of(context).textTheme.labelLarge),
            Text(comment, key: const Key('review-grade-comment')),
          ],
        ],
        if (humanGrade != null) ...[
          const SizedBox(height: 8),
          _ProvenanceLabel(
            key: const Key('review-human-grade-label'),
            text: '人による確定',
          ),
          Text(
            '${humanGrade.score.awarded} / ${humanGrade.score.maximum} 点',
            key: const Key('review-human-score'),
            style: Theme.of(context).textTheme.headlineSmall,
          ),
        ],
        // The rubric's own definition (description + 配点) is shown
        // whenever the question has one, independent of whether AI/human
        // grading has happened yet -- outcomes below annotate it where a
        // grade has judged that criterion, but the definition itself must
        // never disappear just because grading hasn't reached it (P1
        // review).
        if (question.rubric.isNotEmpty) ...[
          const SizedBox(height: 8),
          Text('採点基準', style: Theme.of(context).textTheme.labelLarge),
          for (final criterion in question.rubric)
            ListTile(
              key: Key('rubric-criterion-${criterion.id}'),
              dense: true,
              contentPadding: EdgeInsets.zero,
              leading: Icon(
                _criterionIcon(
                  _criterionOutcomeFor(criterion.id, review.displayGrade),
                ),
              ),
              title: Text('${criterion.description}（${criterion.maxPoints}点）'),
              subtitle: Text(
                _criterionLabel(
                  _criterionOutcomeFor(criterion.id, review.displayGrade),
                ),
              ),
            ),
        ],
        if (fallbackAnnotations.isNotEmpty) ...[
          const Divider(height: 24),
          Text('設問コメント', style: Theme.of(context).textTheme.titleSmall),
          for (final annotation in fallbackAnnotations)
            ListTile(
              key: Key('fallback-annotation-${annotation.id}'),
              dense: true,
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.comment_outlined),
              title: Text(annotation.comment ?? annotation.anchorText ?? ''),
            ),
        ],
        const Divider(height: 24),
        Text('修正コメント', style: Theme.of(context).textTheme.titleSmall),
        TextField(
          key: const Key('review-note-field'),
          controller: _noteController,
          focusNode: _noteFocusNode,
          maxLines: 3,
          decoration: const InputDecoration(
            hintText: 'このセッション内でのみ保持されるメモです',
            border: OutlineInputBorder(),
          ),
          onChanged: _saveNote,
        ),
      ],
    );
  }

  Widget _buildActionBar() {
    return Material(
      elevation: 4,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        // Scrolls horizontally instead of overflowing at a narrow desktop
        // width (Issue #21 acceptance: desktopの標準/狭幅表示) -- every
        // button stays reachable by keyboard focus traversal regardless.
        child: SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          reverse: true,
          child: Row(
            mainAxisAlignment: MainAxisAlignment.end,
            children: [
              OutlinedButton.icon(
                key: const Key('review-undo-button'),
                onPressed: _canUndo ? _undo : null,
                icon: const Icon(Icons.undo),
                label: const Text('元に戻す (Ctrl+Z)'),
              ),
              const SizedBox(width: 12),
              OutlinedButton.icon(
                key: const Key('review-regrade-button'),
                onPressed: _canDecide ? _regrade : null,
                icon: const Icon(Icons.autorenew),
                label: const Text('再判定 (R)'),
              ),
              const SizedBox(width: 12),
              OutlinedButton.icon(
                key: const Key('review-edit-button'),
                onPressed: _canDecide ? _showEditDialog : null,
                icon: const Icon(Icons.edit_outlined),
                label: const Text('修正 (E)'),
              ),
              const SizedBox(width: 12),
              OutlinedButton.icon(
                key: const Key('review-reject-button'),
                // Disabled while the question's data is still loading (or
                // failed to load) -- rejecting content the reviewer cannot
                // actually see yet would silently confirm a decision made
                // on nothing (P2 review).
                onPressed: _canDecide ? _reject : null,
                icon: const Icon(Icons.close),
                label: const Text('却下 (X)'),
              ),
              const SizedBox(width: 12),
              FilledButton.icon(
                key: const Key('review-approve-button'),
                onPressed: _canApprove ? _approveAndNext : null,
                icon: const Icon(Icons.check),
                label: const Text('承認して次へ (Enter)'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

(IconData, String) _submissionStateVisual(String state) => switch (state) {
  'unprocessed' => (Icons.hourglass_empty, '未処理'),
  'ai_processing' => (Icons.autorenew, 'AI処理中'),
  'ai_processed' => (Icons.check_circle_outline, 'AI処理済み'),
  'needs_review' => (Icons.warning_amber, '要確認'),
  'reviewed' => (Icons.verified_outlined, '確認済み'),
  'exported' => (Icons.file_download_done, '出力済み'),
  'error' => (Icons.error_outline, 'エラー'),
  _ => (Icons.help_outline, state),
};

/// The outcome a grade recorded for [criterionId], or `null` if [grade] is
/// `null` or never judged that criterion (e.g. grading hasn't reached this
/// question yet, or a partial/failed AI run only scored some criteria).
String? _criterionOutcomeFor(String criterionId, GradeResultResponse? grade) {
  if (grade == null) return null;
  for (final result in grade.criteria) {
    if (result.criterionId == criterionId) return result.outcome;
  }
  return null;
}

IconData _criterionIcon(String? outcome) => switch (outcome) {
  'pass' => Icons.check_circle_outline,
  'partial' => Icons.remove_circle_outline,
  'fail' => Icons.cancel_outlined,
  null => Icons.hourglass_empty,
  _ => Icons.help_outline,
};

String _criterionLabel(String? outcome) => switch (outcome) {
  'pass' => '合格',
  'partial' => '部分合格',
  'fail' => '不合格',
  null => '未評価',
  _ => outcome,
};

/// A small "who produced this" marker (e.g. "人による修正") shown next to a
/// human-sourced recognition/grade, so it is never confused with the AI's
/// own proposal above it (P1 review: source must stay distinguishable).
class _ProvenanceLabel extends StatelessWidget {
  const _ProvenanceLabel({super.key, required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        const Icon(Icons.person, size: 16),
        const SizedBox(width: 4),
        Text(text, style: Theme.of(context).textTheme.labelLarge),
      ],
    );
  }
}

/// Numeric confidence + a textual level label + a distinct icon, so
/// Recognition/Grading Confidence is never distinguished by color alone
/// (Issue #21 acceptance criteria).
class _ConfidenceBadge extends StatelessWidget {
  const _ConfidenceBadge({
    super.key,
    required this.label,
    required this.confidence,
  });

  final String label;
  final double confidence;

  @override
  Widget build(BuildContext context) {
    final level = ConfidenceLevel.of(confidence);
    final icon = switch (level) {
      ConfidenceLevel.high => Icons.check_circle,
      ConfidenceLevel.medium => Icons.info_outline,
      ConfidenceLevel.low => Icons.warning_amber,
    };
    final percent = (confidence * 100).round();
    return Semantics(
      label: '$label $percent% ${level.label}',
      // Without this, the child Text's own auto-generated semantics label
      // merges with this one (joined by a newline) instead of being
      // replaced by it, and a screen reader would announce both.
      excludeSemantics: true,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 18),
          const SizedBox(width: 4),
          Text('$label: $percent% (${level.label})'),
        ],
      ),
    );
  }
}

/// One annotation mark drawn on the PDF overlay -- shape/text always differ
/// by kind, not just color, so the mark is legible without relying on color
/// (Issue #21 acceptance criteria).
class _AnnotationMark extends StatelessWidget {
  const _AnnotationMark({required this.annotation, required this.displayGrade});

  final AnnotationResponse annotation;

  /// The most authoritative grade to source the `score` mark's number from
  /// (human overrides AI once one exists -- see
  /// [QuestionReviewState.displayGrade]).
  final GradeResultResponse? displayGrade;

  @override
  Widget build(BuildContext context) {
    final content = switch (annotation.kind) {
      'circle' => const _ShapeMark(icon: Icons.panorama_fisheye, label: '○'),
      'cross' => const _ShapeMark(icon: Icons.close, label: '×'),
      'triangle' => const _ShapeMark(icon: Icons.change_history, label: '△'),
      'score' => _ShapeMark(
        icon: Icons.grade_outlined,
        label: displayGrade == null ? '―' : '${displayGrade!.score.awarded}',
      ),
      // The comment text can be long -- shown as a hover tooltip, not
      // squeezed inline next to the icon like the other kinds' short labels.
      'comment' => _ShapeMark(icon: Icons.comment, tooltip: annotation.comment),
      'underline' => const _ShapeMark(
        icon: Icons.format_underlined,
        label: '_',
      ),
      'box' => const _ShapeMark(icon: Icons.crop_square, label: '囲'),
      _ => _ShapeMark(icon: Icons.push_pin_outlined, label: annotation.kind),
    };
    return Semantics(
      label: '添削記号 ${annotation.kind} ${annotation.comment ?? ''}',
      excludeSemantics: true,
      child: content,
    );
  }
}

class _ShapeMark extends StatelessWidget {
  const _ShapeMark({required this.icon, this.label = '', this.tooltip});

  final IconData icon;
  final String label;
  final String? tooltip;

  @override
  Widget build(BuildContext context) {
    final color = Theme.of(context).colorScheme.error;
    // The icon alone already distinguishes most kinds by shape (not just
    // color); `label` additionally carries information the icon can't
    // (e.g. the actual awarded score number for `score`), so it is shown
    // alongside rather than dropped.
    final child = FittedBox(
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, color: color),
          if (label.isNotEmpty) ...[
            const SizedBox(width: 2),
            Text(label, style: TextStyle(color: color)),
          ],
        ],
      ),
    );
    if (tooltip == null || tooltip!.isEmpty) return child;
    return Tooltip(message: tooltip!, child: child);
  }
}
