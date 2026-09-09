import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:pdfrx/pdfrx.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/app_dependencies.dart';
import 'package:auto_scoring_app/core/confidence_level.dart';
import 'package:auto_scoring_app/core/dependency_dag.dart';
import 'package:auto_scoring_app/core/design/app_status_tone.dart';
import 'package:auto_scoring_app/core/design/app_theme_context.dart';
import 'package:auto_scoring_app/core/design/design_tokens.dart';
import 'package:auto_scoring_app/core/grading_kickoff.dart';
import 'package:auto_scoring_app/core/material_read_ranges.dart';
import 'package:auto_scoring_app/core/pdf_review_geometry.dart';
import 'package:auto_scoring_app/core/question_status.dart';
import 'package:auto_scoring_app/core/submission_status.dart';
import 'package:auto_scoring_app/core/widgets/app_error_banner.dart';
import 'package:auto_scoring_app/features/pdf_review/dependency_dag_panel.dart';
import 'package:auto_scoring_app/features/pdf_review/export_dialog.dart';

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
class PdfReviewPage extends ConsumerStatefulWidget {
  const PdfReviewPage({
    super.key,
    required this.testId,
    required this.submissionId,
  });

  final String testId;
  final String submissionId;

  @override
  ConsumerState<PdfReviewPage> createState() => _PdfReviewPageState();
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

  /// Which job set this question's cached results were read under
  /// (`_PdfReviewPageState._jobsGeneration` at the moment the fetch that
  /// filled them started), or `-1` while nothing has been read yet.
  ///
  /// **This is what makes the cache expire.** Results are a function of the
  /// jobs that produced them, so the moment the job set changes, every
  /// question's cache is stale -- not only the one being looked at. See
  /// `_PdfReviewPageState._jobsGeneration`.
  int jobsGeneration = -1;

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

/// How close to the bottom of the Inspector counts as having reached it.
///
/// A hair rather than zero: scroll extents are doubles that a device pixel
/// ratio and a fractional viewport height leave a rounding error in, and a
/// reviewer who has visibly scrolled to the end must not be told they have
/// not (Issue #85).
const double _materialReadEpsilon = 1;

/// How much of a screenful 「続きを表示」 advances by. Less than one, so two
/// consecutive pages overlap and no row falls between them.
const double _materialPageOverlap = 0.9;

/// The two edges of a 判断材料 row, as suffixes on its marker's key.
const String _materialTop = '#top';
const String _materialBottom = '#bottom';

/// How much of a row may be missing before it still counts as covered, as a
/// fraction of that row's height. A rounding allowance, not a licence to skip
/// -- at a 2525px 根拠 this is under three pixels.

class _PdfReviewPageState extends ConsumerState<PdfReviewPage> {
  /// The sidecar operations this screen was opened against, captured once in
  /// [initState] -- never re-resolved from the provider mid-request. See
  /// [appDependenciesProvider] for why that rule exists.
  late final AppDependencies _dependencies;

  late final PdfViewerController _pdfController;
  final _noteController = TextEditingController();
  final _noteFocusNode = FocusNode(debugLabel: '修正コメント');

  /// The Inspector's own scroll position, so this screen can tell whether the
  /// 判断材料 has actually reached the reviewer's eyes and can take them to
  /// the rest of it (Issue #85).
  final _inspectorScrollController = ScrollController();

  /// Per 判断材料 row, **which parts of it have been on screen**, as merged
  /// fractions of that row's own height.
  ///
  /// A union of intervals rather than a pair of edges, and that is the whole
  /// design. Four earlier versions asked a scroll number, or a pair of edge
  /// markers, whether a row had been read, and neither can answer it:
  ///
  /// - `maxScrollExtent` and the material's own height are facts about the
  ///   current layout, so a relayout un-saw material that had been displayed
  ///   in full (レビュー1・2回目).
  /// - `extentAfter == 0` is evidence gathered about *the material that was
  ///   there when it was measured*, so reusing it after a poll replaced a row
  ///   above the fold marked material read that nobody had seen (レビュー3・
  ///   4回目).
  /// - "both edges have been on screen" says nothing about the middle. Drag
  ///   the scrollbar from the top of a 2525px 根拠 straight to the end and
  ///   both edges have been seen with the whole body skipped (レビュー5回目)
  ///   -- and a block taller than the viewport is exactly the 根拠本文, the
  ///   thing this gate exists for.
  ///
  /// **証拠は、それが証明する材料そのものに紐づいていなければならない。**
  /// Fractions rather than pixels so that a rewrap -- the same words at a
  /// different width -- does not un-cover what was covered: the *proportion*
  /// of a row that has been shown survives relayout, where a pixel range
  /// would not. Intervals are merged on the way in, so a row holds a handful
  /// at most.
  final Map<String, List<(double, double)>> _materialSeenRanges = {};

  /// Two markers per row -- one at each edge of its block
  /// ([_materialRowEdge]) -- to measure that row's extent against the
  /// viewport. Kept across rebuilds so a marker keeps its identity in the
  /// tree; keys are row ids, so this is bounded by the rows this session has
  /// actually fetched.
  final Map<String, GlobalKey> _materialRowKeys = {};

  /// The Inspector's scroll viewport, to measure the markers against.
  final GlobalKey _inspectorViewportKey = GlobalKey(
    debugLabel: 'review-inspector-viewport',
  );

  /// Whether the nearest unread 判断材料 is *above* the current view rather
  /// than below it.
  ///
  /// A poll can replace a row off the top of the panel while the reviewer is
  /// parked at the bottom, and then 「続きを表示」 has to go *up*. Sending it
  /// down there moved nothing, which is a button that does nothing
  /// (レビュー5回目 P2). Held as state because it is a fact about the last
  /// layout, and build must not go measuring render objects.
  bool _unreadIsAbove = false;

  /// Whether the markers have been measured for the material now on screen.
  ///
  /// Distinct from "nothing has been seen": before the first measurement the
  /// answer is *unknown*, and drawing 「この下にまだ判断材料があります」 over a
  /// panel that in fact fits -- for the one frame between building it and
  /// measuring it -- would be a flash of a false statement.
  bool _materialMeasured = false;

  bool _loadingShell = true;
  String? _shellError;
  SubmissionResponse? _submission;
  List<QuestionResponse> _questions = const [];
  Uint8List? _pdfBytes;
  int _questionIndex = 0;
  final Map<String, QuestionReviewState> _reviews = {};
  List<JobResponse> _jobs = const [];

  /// The test's latest 設問依存グラフ (Issue #26), or `null` if the fetch
  /// failed or none has been analyzed. Fetched once with the shell: a
  /// confirmed graph is immutable, so unlike the jobs it has no reason to be
  /// re-read on every poll tick.
  DependencyGraphResponse? _dependencyGraph;
  Timer? _pollTimer;

  /// Bumped every time [_refreshJobs] observes a **different** job set.
  ///
  /// This is the one place that answers "what does a change in processing
  /// invalidate?", and the answer is: every question's cached results, at
  /// once. [QuestionReviewState.jobsGeneration] records which job set an
  /// entry was read under, and [_loadReview] refuses to reuse an entry from
  /// an older one.
  ///
  /// **Why it has to be all of them, not the selected one.** The first two
  /// attempts at this fixed a narrower slice each time and left the next one
  /// open: refreshing the jobs without the grades they produce (review round
  /// 2), then refreshing the selected question's grades but not the other
  /// questions' (review round 3 -- open 問2, go back and start grading, and
  /// 問2 keeps the empty results it was opened with, because
  /// [_isAwaitingGrade] reads "terminal job, no grade" as "nothing to wait
  /// for" and lets the empty cache stand). Neither is a special case of
  /// 「AI採点を開始」: *any* path that changes the jobs -- a poll tick, a
  /// 再判定, a retry, a graph re-confirm -- has the same effect on every
  /// question, so the invalidation belongs where the change is noticed
  /// rather than at each caller.
  ///
  /// **The caches this screen owns, and why this is the only one that
  /// needs expiring.** `_questions` and `_pdfBytes` are properties of the
  /// test and the answer PDF, which processing never changes. `_submission`
  /// is re-read by every poll and every refresh, and grading does not move
  /// it anyway (`docs/home-dashboard.md` §3.1). `_dependencyGraph` is
  /// re-read from inside [_refreshJobs] itself when the jobs say it is
  /// superseded. `_jobs`/`_jobsLoaded`/`_gradingFailure` are written by the
  /// very calls that would invalidate them. That leaves [_reviews], which
  /// this stamp covers.
  int _jobsGeneration = 0;

  /// Whether [_refreshJobs] has ever come back successfully. `false` covers
  /// both "not fetched yet" and "the fetch failed", which [_jobs] cannot tell
  /// apart on its own -- it is an empty list in all three cases, including
  /// the genuine "no job was ever created". 「AI採点はまだ開始されていません」
  /// is a claim about the sidecar's state, so it must not be made off a list
  /// this screen never managed to read (Issue #80).
  bool _jobsLoaded = false;

  /// True while 「AI採点を開始」 is in flight (Issue #80), so the button is
  /// disabled rather than able to fire a second request on top of the first.
  bool _startingGrading = false;

  /// How the last 「AI採点を開始」 failed, or `null`. Carries both the text to
  /// show and whether pressing again could change anything
  /// ([GradingKickoffFailure]) -- keeping only the message is what let a 404
  /// leave the button live above its own 「答案が見つかりません」 (review
  /// round 1, P2-2).
  ///
  /// Deliberately *not* [_shellError]: the reviewer can still read the answer,
  /// the recognized text and the grades while grading refuses to start,
  /// exactly as a missing dependency graph does not become this screen's error
  /// state either (`docs/dependency-dag-progress-view.md` §1.7, §1.11).
  GradingKickoffFailure? _gradingFailure;

  @override
  void initState() {
    super.initState();
    _dependencies = ref.read(appDependenciesProvider);
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
    _inspectorScrollController.dispose();
    super.dispose();
  }

  void _handleNoteFocusChange() {
    _setStateIfMounted(() {});
  }

  /// `setState` that does nothing once this screen is gone. **Nothing in this
  /// State calls `setState` directly** -- `pdf_review_page_lint_test.dart`
  /// fails if a bare one comes back.
  ///
  /// **誰が中止の責任を持つか.** Two rules, and the second exists because the
  /// first keeps being broken:
  ///
  /// 1. *The function doing the `await` stops itself.* After every `await`
  ///    that a screen teardown could outlive, re-check [mounted] before
  ///    doing anything further. **An inner helper's own [mounted] check does
  ///    not stop its caller** -- `_refreshJobs` returning early because the
  ///    screen went away still hands control back to `_refreshJobsAndQuestion`,
  ///    which used to carry on into `_loadReview` and `setState` on a dead
  ///    State. That asymmetry is what made this easy to miss.
  /// 2. *And `setState` refuses anyway.* Rule 1 is a discipline, and this
  ///    codebase has broken it three times -- Issue #66 (`ref.read` after
  ///    dispose), Issue #64 ("leaving the screen mid-request"), and Issue #80
  ///    (「AI採点を開始」's response landing after the reviewer left). A missed
  ///    guard should cost a wasted fetch, not an unhandled exception, so the
  ///    one call that would actually throw is made a no-op instead.
  ///
  /// Rule 2 is a backstop, not a licence to skip rule 1: work done after
  /// teardown is still wasted work, and a `Timer` or a controller call is not
  /// covered by it ([_updatePolling] guards itself for exactly that reason).
  void _setStateIfMounted(VoidCallback fn) {
    if (!mounted) return;
    setState(fn);
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

  /// The state of one question, for **every** place on this screen that shows
  /// one: the 処理の進み方 panel, the Navigation Rail, and the Inspector's
  /// badge (Issue #84).
  ///
  /// Deliberately the only route to a question's state. The three used to
  /// derive their own -- the panel from `Job` + `Review`, the rail from
  /// whether this screen had fetched that question yet, the Inspector badge
  /// from the *答案's* state -- and drifted into saying different things
  /// about the same 問1: 承認済み in the panel, ⚠要確認 in the Inspector,
  /// an undifferentiated hourglass in the rail. Same inputs through one
  /// function is what makes that impossible rather than merely fixed.
  ///
  /// Note what is *not* folded in here: whether this screen has finished
  /// fetching that question, and whether that fetch failed. Those are facts
  /// about the Inspector's content, not about the question -- the Inspector
  /// shows a spinner and a retry banner for them -- and letting the rail
  /// paint them was how it came to answer a different question from the one
  /// the panel beside it was answering.
  QuestionStatus _questionStatus(QuestionResponse question) =>
      deriveQuestionStatus(
        job: _latestJobFor(question.id),
        review: _reviews[question.id]?.effectiveReview,
      );

  /// The words for [_questionStatus], with a blocked question naming the
  /// prerequisite it is waiting on -- the same string the DAG node prints,
  /// via the same `core` rule.
  String _questionStatusLabel(QuestionResponse question) =>
      _questionStatus(question).labelWaitingFor(_blockedOnNumber(question));

  /// The 設問番号 of the question [question]'s job is waiting on, or `null`
  /// when it is not blocked (or the prerequisite is not in this submission's
  /// own question list, which a graph fetched for the whole test can name).
  String? _blockedOnNumber(QuestionResponse question) {
    final blockedOn = _latestJobFor(question.id)?.blockedOnQuestionId;
    if (blockedOn == null) return null;
    for (final candidate in _questions) {
      if (candidate.id == blockedOn) return candidate.number;
    }
    return null;
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
    // A `Timer` is not covered by `_setStateIfMounted`: arming one here after
    // teardown would keep firing against a disposed State until it happened
    // to be cancelled (rule 1 in that method's doc).
    if (!mounted) return;
    final review = _currentReview;
    final question = _currentQuestion;
    final shouldPoll =
        review == null ||
        review.loading ||
        (question != null && _isAwaitingGrade(review, question.id)) ||
        _anyJobInFlight;
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

  /// Whether *any* question of this submission still has a job the queue
  /// could move on its own.
  ///
  /// Polling used to track only the selected question, which was enough when
  /// the screen showed nothing about the others. The 進捗 panel (Issue #64)
  /// shows all of them at once, and its whole point is watching an upstream
  /// question finish and release a downstream one -- neither of which need
  /// be the question the reviewer is sitting on. Without this the graph
  /// would freeze the moment the selected question was done, which is
  /// exactly when the rest of the submission is still working.
  bool get _anyJobInFlight =>
      _jobs.any((job) => !_terminalJobStates.contains(job.state));

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
      final submission = await _dependencies.getSubmission(widget.submissionId);
      if (!mounted) return;
      _setStateIfMounted(() => _submission = submission);
      // Silent: a background poll should not flash the loading spinner or
      // an error banner over content the reviewer is already looking at.
      await _refreshJobsAndQuestion(silent: true);
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

  /// "PDF出力" toolbar action (Issue #23): shows [ExportDialog], which owns
  /// the whole request/poll/retry flow itself -- this screen does not track
  /// export state beyond launching it.
  Future<void> _showExportDialog() async {
    await showExportDialog(context, submissionId: widget.submissionId);
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
      final submission = await _dependencies.getSubmission(widget.submissionId);
      if (!mounted) return;
      _setStateIfMounted(() => _submission = submission);
    } on SidecarApiException {
      // Fall through to refreshing the question data regardless.
    }
    await _refreshJobsAndQuestion(question: question);
  }

  /// Best-effort refresh of every job for this submission. A failure here
  /// must never block the submission/question refresh around it -- the Jobs
  /// API only ever informs [_updatePolling]/[_isAwaitingGrade]'s decision,
  /// it is never the sole source of anything the Inspector itself shows, so
  /// a stale (or, initially, empty) [_jobs] just means "treat this
  /// question's own job state as unknown" rather than surfacing an error.
  Future<void> _refreshJobs() async {
    try {
      final jobs = await _dependencies.listJobs(widget.submissionId);
      if (!mounted) return;
      final changed = _jobsFingerprint(jobs) != _jobsFingerprint(_jobs);
      _setStateIfMounted(() {
        _jobs = jobs;
        _jobsLoaded = true;
        // Only on a real change: an unchanged job set means every cached
        // result is still the result of exactly those jobs, and expiring
        // them anyway would re-fetch all four lists for every question the
        // reviewer visits after any refresh at all.
        if (changed) _jobsGeneration++;
      });
    } on SidecarApiException {
      // Keep the last-known jobs list -- retried on the next tick/refresh.
      return;
    }
    await _refetchDependencyGraphIfSuperseded();
  }

  /// What a job set has to say about the results it may have produced.
  ///
  /// `id` covers a job appearing or being re-issued under a new graph
  /// version, `state` covers it moving, and `usable` covers a `SUCCEEDED`
  /// job the queue judged untrustworthy (which is a different result for a
  /// reviewer than a usable one). Timestamps are deliberately left out: a
  /// `RUNNING` job whose `updated_at` ticks has not produced anything new.
  static String _jobsFingerprint(List<JobResponse> jobs) =>
      (jobs.map((j) => '${j.id}:${j.state}:${j.usable}').toList()..sort()).join(
        '|',
      );

  /// Re-reads this submission's jobs **and** everything that has to agree
  /// with them, then re-evaluates polling.
  ///
  /// Exists as one method rather than three lines copied to each call site
  /// because "refresh the jobs and forget what travels with them" is a
  /// mistake this screen has now made twice. Issue #64 refreshed the jobs
  /// without the dependency graph they run under, drawing one version's
  /// execution on another version's structure; 「AI採点を開始」 refreshed the
  /// jobs without the grades they produce, so a submission whose jobs came
  /// back already `succeeded` showed レビュー待ち in the diagram over an
  /// Inspector with nothing in it -- and, because
  /// [_isAwaitingGrade] reads "terminal job, no grade" as "nothing to wait
  /// for", polling stopped too, leaving it that way until a manual 更新
  /// (review round 2, P2).
  ///
  /// The graph half already lives inside [_refreshJobs]. The question half is
  /// here. **Anything else that must be re-read alongside a job belongs in
  /// this method**, once, for every caller -- that is the whole point of it
  /// existing.
  ///
  /// [question] defaults to whichever question is selected; [_refreshQuestion]
  /// passes the one an in-flight action was actually for, which may no longer
  /// be the selected one by the time it resolves. [silent] is for background
  /// polling, which must not flash a spinner or an error banner over content
  /// the reviewer is already reading.
  Future<void> _refreshJobsAndQuestion({
    QuestionResponse? question,
    bool silent = false,
  }) async {
    await _refreshJobs();
    // `_refreshJobs` stopping itself does not stop *this* function -- the
    // asymmetry that made review round 4's crash possible.
    if (!mounted) return;
    _updatePolling();
    final target = question ?? _currentQuestion;
    if (target == null) return;
    await _loadReview(target, forceReload: true, silent: silent);
  }

  /// 「AI採点を開始」 -- `POST /submissions/{id}/jobs` (Issue #80).
  ///
  /// Offered only while this submission has no jobs at all
  /// ([_buildStartGradingSection]). On success there is nothing to render
  /// specially: re-reading the jobs is enough, and the diagram, the rail and
  /// the Inspector all start showing real states through the same
  /// [_questionStatus] they already use.
  ///
  /// Idempotent server-side, so a double press cannot create a second set of
  /// jobs (`docs/job-queue.md`「起票のタイミング」).
  Future<void> _startGrading() async {
    _setStateIfMounted(() {
      _startingGrading = true;
      _gradingFailure = null;
    });
    try {
      await _dependencies.startGrading(widget.submissionId);
      // The reviewer can leave (or open another answer) while this request is
      // in flight; nothing below is worth doing for a screen that is gone
      // (review round 4).
      if (!mounted) return;
      // Not just the jobs: a fast (or already-existing) grading run can have
      // this submission's jobs back as `succeeded` by the time the POST
      // returns, and the empty grades fetched before the kickoff would then
      // sit there unrefreshed with polling switched off.
      await _refreshJobsAndQuestion();
    } on SidecarApiException catch (error) {
      if (!mounted) return;
      _setStateIfMounted(
        () => _gradingFailure = GradingKickoffFailure.of(error),
      );
    } finally {
      _setStateIfMounted(() => _startingGrading = false);
    }
  }

  /// Re-reads the dependency graph whenever what is on screen is no longer
  /// the structure this submission's jobs are running under.
  ///
  /// The graph is fetched once with the shell because a confirmed graph is
  /// immutable -- but the *test's* graph is not. Confirming a new version
  /// elsewhere (テスト設定画面) cancels this submission's incomplete jobs and
  /// re-issues them against the new version (`POST /dependency-graph/confirm`,
  /// Issue #26), so polling would keep showing the new jobs' states over the
  /// old version's edges and layers. With a dependency reversed, the arrows
  /// and the 「問n 待ち」 labels then contradict each other -- one version's
  /// execution drawn on another version's structure (review round 2, P2).
  ///
  /// The jobs are the authority on which version is in force: a `Job` only
  /// ever exists against a *confirmed* graph, so the newest
  /// `dependency_graph_version` any of them names is the version this screen
  /// ought to be drawing. Nothing to compare against (no job carries one)
  /// means there is nothing to go and fetch either.
  Future<void> _refetchDependencyGraphIfSuperseded() async {
    final newest = _jobs
        .map((job) => job.dependencyGraphVersion)
        .nonNulls
        .fold<int?>(null, (a, b) => a == null || b > a ? b : a);
    if (newest == null || !_dependencyGraphIsBehind(newest)) return;
    await _loadDependencyGraph();
  }

  /// Whether the cached graph is worth re-reading, given that the jobs are
  /// running under confirmed version [newestJobVersion].
  ///
  /// Asking "is this the current structure?" rather than the narrower "is
  /// there a newer version?" is what closes the two gaps review round 3
  /// found -- both were in this guard rather than in the comparison itself.
  bool _dependencyGraphIsBehind(int newestJobVersion) {
    final graph = _dependencyGraph;
    // Nothing cached: either the test had no graph, or the one fetch this
    // screen makes happened to fail. A job naming a version proves a
    // confirmed graph does exist, so this is worth another try -- otherwise
    // one transient error left the panel missing until the screen was
    // reopened, with polling and 更新 both unable to bring it back.
    if (graph == null) return true;
    // A confirmed graph at least as new as every job is the structure those
    // jobs ran under. Older means a newer version was confirmed elsewhere.
    // Not `!=`: the re-issue leaves the superseded jobs behind as CANCELLED
    // rows naming the old version, so "any job disagrees" would stay true
    // forever afterwards and refetch on every poll tick.
    if (graph.status == 'confirmed') return graph.version < newestJobVersion;
    // A draft is not a structure this screen draws at all -- the panel is
    // showing its notice instead. `confirm` does not bump the version
    // (`domain.dependency_graph.DependencyGraph.confirm`), so a job turning
    // up on the draft's *own* version is precisely the signal that this
    // draft has since been confirmed; requiring a strictly newer one missed
    // it and left the notice standing forever. A draft still ahead of every
    // job is the ordinary re-analyzed-after-registration case, where
    // re-reading would only return the same draft again.
    return graph.version <= newestJobVersion;
  }

  /// Best-effort fetch of the test's dependency graph, for the 進捗 panel
  /// (Issue #64). A 404 is the normal answer for a test whose graph was
  /// never analyzed, and the panel simply does not appear then -- the
  /// reviewer's actual work (認識文字・採点・承認) does not depend on it, so
  /// this must never turn into the screen's error state.
  Future<void> _loadDependencyGraph() async {
    try {
      final graph = await _dependencies.getDependencyGraph(widget.testId);
      if (!mounted) return;
      _setStateIfMounted(() => _dependencyGraph = graph);
    } on SidecarApiException {
      // No graph to draw; the panel stays hidden.
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
    _setStateIfMounted(() {
      _loadingShell = true;
      _shellError = null;
    });
    try {
      final submission = await _dependencies.getSubmission(widget.submissionId);
      final questions = await _dependencies.listQuestions(widget.testId);
      final pdfBytes = await _dependencies.getSourcePdf(widget.submissionId);
      final sorted = questions.toList()
        ..sort((a, b) {
          final byPage = a.page.compareTo(b.page);
          return byPage != 0
              ? byPage
              : _compareQuestionNumbers(a.number, b.number);
        });
      if (!mounted) return;
      _setStateIfMounted(() {
        _submission = submission;
        _questions = sorted;
        _pdfBytes = pdfBytes;
        _questionIndex = 0;
      });
      // Before the jobs, so that `_refreshJobs`' own staleness check has
      // something to compare against and does not fetch the same graph a
      // second time on startup.
      await _loadDependencyGraph();
      await _refreshJobs();
      if (!mounted) return;
      _updatePolling();
      unawaited(_ensureReviewLoaded());
    } on SidecarApiException catch (error) {
      if (!mounted) return;
      _setStateIfMounted(() => _shellError = error.message);
    } finally {
      _setStateIfMounted(() => _loadingShell = false);
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
    // Entered from several chains that each contain an `await` before this
    // point; the caller may already be gone.
    if (!mounted) return;
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
    // Read under an older job set, so it may be missing results those jobs
    // have since produced -- including for a question the reviewer opened
    // *before* grading was started and has not opened since
    // (`_jobsGeneration`).
    final readUnderOlderJobs =
        existing != null && existing.jobsGeneration != _jobsGeneration;
    if (existing != null &&
        !forceReload &&
        !resultsStillMissing &&
        !readUnderOlderJobs &&
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
    // Captured before the fetch, not after: if the job set changes while
    // these four lists are in flight, the result describes the *old* jobs
    // and must stay expired.
    final jobsGeneration = _jobsGeneration;
    if (silent) {
      _reviews[question.id] = review;
    } else {
      review.loading = true;
      review.error = null;
      _setStateIfMounted(() => _reviews[question.id] = review);
    }
    try {
      final recognitions = await _dependencies.listRecognitions(
        widget.submissionId,
        question.id,
      );
      final grades = await _dependencies.listGrades(
        widget.submissionId,
        question.id,
      );
      final annotations = await _dependencies.listAnnotations(
        widget.submissionId,
        question.id,
      );
      final reviews = await _dependencies.listReviews(
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
          : await _dependencies.listRecognitions(
              widget.submissionId,
              question.id,
            );
      if (!mounted || generation != review.fetchGeneration) return;
      _setStateIfMounted(() {
        review.recognitions = consistentRecognitions;
        review.grades = grades;
        review.annotations = annotations;
        review.reviews = reviews;
        review.loading = false;
        review.jobsGeneration = jobsGeneration;
        // A successful refresh -- silent or not -- means the Inspector no
        // longer needs to keep showing a fetch failure from before it (P2
        // review): the data it was retried for is here now.
        review.error = null;
      });
    } on SidecarApiException catch (error) {
      if (!mounted || silent || generation != review.fetchGeneration) return;
      _setStateIfMounted(() {
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
    _setStateIfMounted(() => _questionIndex = index);
    final question = _currentQuestion!;
    _noteController.text = _reviews[question.id]?.note ?? '';
    // Back to the top of the Inspector: the next question's 判断材料 starts at
    // its own beginning, not wherever the previous one was left scrolled to.
    // Whether it overflows is unknown until that panel has laid out, and the
    // notice must not be inherited from the question just left.
    //
    // Nothing about what has been *read* is reset here:
    // [_materialSeenRanges] is keyed by row, so coming back to a question already
    // read through does not ask the reviewer to read it again. Only the
    // *measurement* is invalidated -- the next question's markers have not
    // been placed yet.
    if (_inspectorScrollController.hasClients) {
      _inspectorScrollController.jumpTo(0);
    }
    _materialMeasured = false;
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

  /// [_selectQuestion] addressed by question id -- what the 進捗 panel has,
  /// since a DAG node knows nothing about this screen's list order.
  void _selectQuestionById(String questionId) {
    final index = _questions.indexWhere((q) => q.id == questionId);
    if (index >= 0) _selectQuestion(index);
  }

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

  /// Whether every row the Inspector is currently showing has been covered
  /// end to end ([_materialSeenRanges]).
  ///
  /// True immediately when the panel does not scroll at all -- every row is
  /// wholly inside the viewport on the first measurement -- which is the
  /// ordinary case at 1280x720 and the reason this gate costs a reviewer
  /// nothing there.
  bool get _materialFullyRead {
    final question = _currentQuestion;
    final review = _currentReview;
    if (question == null || review == null || !review.hasLoaded) return false;
    return _materialRowIds(question, review).every(_isRowCovered);
  }

  bool _isRowCovered(String id) =>
      materialRowIsCovered(_materialSeenRanges[id]);

  /// The rows the Inspector is showing for [question] right now, in the order
  /// they are drawn.
  ///
  /// Ids are enough to name them because the history is append-only: a
  /// `Recognition`, a `GradeResult` and an `Annotation` are written once and
  /// never edited, so a human correction, a re-grade and an Undo each arrive
  /// as *different rows* (`docs/review-edit-history.md`).
  List<String> _materialRowIds(
    QuestionResponse question,
    QuestionReviewState review,
  ) => [
    if (review.latestOcrRecognition case final row?) 'ocr:${row.id}',
    if (review.latestGradingRecognition case final row?) 'grading:${row.id}',
    if (review.effectiveHumanRecognition case final row?) 'human:${row.id}',
    if (review.latestAiGrade case final row?) 'grade:${row.id}',
    if (review.displayGrade case final row? when row.source_ == 'human')
      'human-grade:${row.id}',
    // 採点基準 has no row of its own -- its definition belongs to the
    // question -- but the 判定 beside each criterion comes from
    // `displayGrade`, so the block is tracked under whichever grade is
    // currently answering for it.
    if (question.rubric.isNotEmpty) 'rubric:${review.displayGrade?.id ?? '-'}',
    for (final annotation in _fallbackAnnotationsFor(question, review))
      'annotation:${annotation.id}',
  ];

  /// A zero-height marker at one edge of [id]'s block, [edge] being
  /// `_materialTop` or `_materialBottom`. The pair gives that row's extent,
  /// which [_recordMaterialSeen] intersects with the viewport.
  ///
  /// Markers rather than a wrapper around each block: a wrapper is a widget
  /// in the layout, and this screen has already been burnt by measuring
  /// something the measurement itself changed. A zero-height box cannot move
  /// what it is measuring.
  Widget _materialRowEdge(String id, String edge) => SizedBox.shrink(
    key: _materialRowKeys.putIfAbsent(
      '$id$edge',
      () => GlobalKey(debugLabel: 'material-row:$id$edge'),
    ),
  );

  /// The y of one of [id]'s markers in the viewport's coordinates, or `null`
  /// if it is not in the tree.
  double? _markerY(String id, String edge, RenderBox viewport) {
    final marker = _materialRowKeys['$id$edge']?.currentContext
        ?.findRenderObject();
    if (marker is! RenderBox || !marker.attached || !marker.hasSize) {
      return null;
    }
    return marker.localToGlobal(Offset.zero, ancestor: viewport).dy;
  }

  /// Records the part of each row that is inside the viewport right now, and
  /// which way the nearest unread material lies.
  ///
  /// Geometry rather than scroll offsets: the question is "has *this part of
  /// this row* been shown", and only the row's own position can answer it.
  /// Reads render objects, so it must run after layout -- every one of its
  /// three triggers does ([_buildInspector]).
  void _recordMaterialSeen() {
    final question = _currentQuestion;
    final review = _currentReview;
    // Not while the panel is showing a spinner or an error: those are not the
    // material, and marking them read would hand the reviewer an enabled 承認
    // for content they have not been shown yet.
    if (question == null || review == null || !review.hasLoaded) return;
    if (review.loading || review.error != null) return;
    final viewport = _inspectorViewportKey.currentContext?.findRenderObject();
    if (viewport is! RenderBox || !viewport.attached || !viewport.hasSize) {
      return;
    }
    final height = viewport.size.height;
    final updated = <String, List<(double, double)>>{};
    double? firstUnreadY;
    for (final id in _materialRowIds(question, review)) {
      final top = _markerY(id, _materialTop, viewport);
      final bottom = _markerY(id, _materialBottom, viewport);
      if (top == null || bottom == null) continue;
      final rowHeight = bottom - top;
      final visibleTop = math.max(top, 0.0);
      final visibleBottom = math.min(bottom, height);
      final existing = updated[id] ?? _materialSeenRanges[id] ?? const [];
      if (visibleBottom > visibleTop) {
        // A row shorter than a hair is covered the moment any of it shows.
        final merged = rowHeight <= _materialReadEpsilon
            ? const [(0.0, 1.0)]
            : mergeMaterialRange(
                existing,
                (visibleTop - top) / rowHeight,
                (visibleBottom - top) / rowHeight,
              );
        if (!sameMaterialRanges(existing, merged)) updated[id] = merged;
      }
      firstUnreadY ??= _firstGapY(updated[id] ?? existing, top, rowHeight);
    }
    final unreadIsAbove = firstUnreadY != null && firstUnreadY < 0;
    if (updated.isEmpty &&
        _materialMeasured &&
        unreadIsAbove == _unreadIsAbove) {
      return;
    }
    _setStateIfMounted(() {
      _materialMeasured = true;
      _unreadIsAbove = unreadIsAbove;
      _materialSeenRanges.addAll(updated);
    });
  }

  /// Where the first not-yet-covered part of a row sits in viewport
  /// coordinates, or `null` when the row is covered end to end.
  double? _firstGapY(
    List<(double, double)> ranges,
    double top,
    double rowHeight,
  ) {
    if (ranges.isNotEmpty &&
        ranges.first.$1 <= materialCoverEpsilon &&
        ranges.first.$2 >= 1 - materialCoverEpsilon) {
      return null;
    }
    final gapStart = ranges.isEmpty || ranges.first.$1 > materialCoverEpsilon
        ? 0.0
        : ranges.first.$2;
    return top + gapStart * rowHeight;
  }

  /// Brings the next screenful of unread 判断材料 into view.
  ///
  /// **One page at a time, not a jump** (レビュー4回目). Only what actually
  /// passes the viewport is recorded, so a jump would skip straight past
  /// everything in between -- the button would promise 「続きを表示」 and not
  /// deliver it. The overlap keeps a line of context and stops a row from
  /// falling exactly between two pages.
  ///
  /// **Towards the unread material, which is not always downwards**
  /// (レビュー5回目 P2). A poll can replace a row off the top of the panel
  /// while the reviewer is parked at the bottom; sending them further down
  /// there moves nothing at all, and a button that does nothing is a broken
  /// button.
  void _revealRestOfMaterial() {
    if (!_inspectorScrollController.hasClients) return;
    final position = _inspectorScrollController.position;
    final page = position.viewportDimension * _materialPageOverlap;
    _inspectorScrollController.animateTo(
      _unreadIsAbove
          ? math.max(position.pixels - page, position.minScrollExtent)
          : math.min(position.pixels + page, position.maxScrollExtent),
      duration: AppMotion.emphasis,
      curve: AppMotion.standard,
    );
  }

  /// Whether 承認 is being held back purely because the 判断材料 has not been
  /// shown to the end yet -- the one case that gets an explanation and a way
  /// out rather than a silently dead button.
  bool get _blockedOnUnreadMaterial {
    final review = _currentReview;
    if (!_canDecide) return false;
    if (review!.isConfirmed || review.latestAiGrade == null) return false;
    // Only once the markers have actually been measured for what is on
    // screen. Before that, "no row has been seen" is ignorance rather than a
    // fact, and the notice would flash over a panel that in fact fits.
    return _materialMeasured && !_materialFullyRead;
  }

  /// Whether "承認して次へ" may act: [_canDecide], and either the question is
  /// already confirmed (pure navigation -- an `edit` already confirmed it in
  /// the same step) or an AI grade exists to confirm (domain: `Review`
  /// requires `ai_grade_result_id` for `APPROVED`, P1 review) *and* the
  /// 判断材料 behind it has actually been on screen ([_materialFullyRead]).
  ///
  /// That last condition is the whole point of Issue #85. This app's premise
  /// is that AI grades and a person confirms; while 承認して次へ was reachable
  /// with 根拠 and 基準ごとの判定 below the fold, the fastest way through a
  /// stack of submissions was to press Enter without ever looking, and over
  /// dozens of them that is what a person will actually do. Refusing to
  /// confirm material the screen never showed is the only one of the three
  /// options in the Issue that removes that shortcut rather than labelling
  /// it; see `docs/pdf-review-overlay.md` §2.15.
  bool get _canApprove {
    final review = _currentReview;
    if (!_canDecide) return false;
    if (review!.isConfirmed) return true;
    return review.latestAiGrade != null && _materialFullyRead;
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
    _setStateIfMounted(() => review.actionInFlight = true);
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
      if (mounted) await _refreshQuestion(question);
      _setStateIfMounted(() => review.actionInFlight = false);
    }
    return succeeded;
  }

  Future<void> _approveAndNext() async {
    // Pressing Enter and having nothing happen is not an explanation. When
    // the only thing in the way is unread material, Enter means "show me the
    // rest" -- which is also the one way a keyboard-only reviewer can reach
    // it, since ↑/↓ are 設問移動 on this screen (Issue #85).
    if (_blockedOnUnreadMaterial) {
      _revealRestOfMaterial();
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            _unreadIsAbove
                ? '判断材料が画面外に残っていました。上に戻して表示したうえで承認できます。'
                : '判断材料が画面外に残っていました。表示したうえで、もう一度 Enter で承認できます。',
          ),
        ),
      );
      return;
    }
    if (!_canApprove) return;
    final review = _currentReview!;
    final question = _currentQuestion!;
    var proceed = true;
    if (!review.isConfirmed) {
      proceed = await _performReviewAction(
        question,
        review,
        () => _dependencies.approveReview(
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
      () => _dependencies.rejectReview(
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
      () => _dependencies.regradeReview(
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
      () => _dependencies.undoReview(
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
    // Captured *before* the dialog opens, not re-read from [review] after it
    // closes (Issue #22 P1 review, round 2): [review] is the same mutable
    // `QuestionReviewState` the background poll keeps updating in place, so
    // a regrade completing while the dialog is open would otherwise let the
    // eventual save submit *new* concurrency tokens (expectedVersion/
    // expectedAiGradeId) alongside the *old*, already-stale score/text the
    // dialog still shows -- silently landing this edit against an AI attempt
    // the reviewer never actually saw. Freezing both tokens here instead
    // makes that race surface as the same conflict a stale token always
    // would.
    final expectedVersion = review.expectedVersion;
    final expectedAiGradeId = review.latestAiGrade?.id;
    final currentGrade = review.displayGrade;
    // This dialog has no fields for rubric criteria or rationale -- an edit
    // through it is always score/comment/recognized-text only, so the new
    // human `GradeResult` it produces must carry the displayed grade's own
    // criteria/rationale forward unchanged, not silently drop them (Issue
    // #22 P2 review, round 3): `editReview` defaults `criteria`/`rationale`
    // to empty/`None` when omitted, and `edit_question` builds the new grade
    // from exactly what it is given -- a comment-only edit would otherwise
    // blank out every rubric criterion this question had already been
    // judged against, in the display and in a dependent question's grading
    // context alike.
    final carriedCriteria = [
      for (final criterion
          in currentGrade?.criteria ?? const <CriterionResultResponse>[])
        CriterionOutcomeRequest(
          (b) => b
            ..criterionId = criterion.criterionId
            ..outcome = criterion.outcome
            ..confidence = criterion.confidence,
        ),
    ];
    final carriedRationale = currentGrade?.rationale;
    // Captured now too, for the same reason as the two tokens above: an
    // existing effective human recognition (including one whose *text* is
    // an explicit, previously-saved empty string -- see [recognizedText]
    // below) must keep being treated as "there is something to preserve"
    // even if the background poll later updates [review] while this dialog
    // is still open.
    final currentHumanRecognition = review.effectiveHumanRecognition;
    final currentText =
        currentHumanRecognition?.text ??
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
              const SizedBox(height: AppSpacing.md),
              TextField(
                key: const Key('edit-dialog-score'),
                controller: scoreController,
                decoration: InputDecoration(
                  labelText: '点数 (0〜${question.points})',
                ),
                keyboardType: TextInputType.number,
              ),
              const SizedBox(height: AppSpacing.md),
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
    // `null` means "this edit does not touch the recognized text at all"
    // (`edit_question` then leaves the existing recognition alone) -- distinct
    // from an *explicit* clear, which must reach the server as an empty
    // string, not collapse into that same `null` (Issue #22 P2 review, round
    // 2): a reviewer who deletes AI-misread text to mark the answer as blank
    // needs that recorded as a human recognition reading `''`, or the screen
    // (correctly reporting the save as successful) would keep falling back
    // to display the very AI text they just deleted.
    //
    // [currentHumanRecognition] guards the case that check alone missed
    // (Issue #22 P2 review, round 3): once an *earlier* edit already saved
    // such an explicit empty correction, its `currentText` is itself `''`,
    // so leaving the field untouched on a later, unrelated edit (e.g.
    // changing only the score) would otherwise look identical to "nothing
    // was ever recognized" and wrongly send `null` -- silently reverting the
    // saved correction back to the AI's own text once that later edit's
    // *new* human grade fails to share any recognition's `created_at`. A
    // human recognition already being in effect -- whatever its text -- is
    // always something to keep re-asserting on this new edit; only "never
    // touched, and there is still nothing to say" stays `null`, so a
    // question with no recognition of any kind yet does not gain a spurious
    // empty human row on every score-only edit.
    final recognizedText =
        currentHumanRecognition == null && currentText.isEmpty && text.isEmpty
        ? null
        : text;
    await _performReviewAction(
      question,
      review,
      () => _dependencies.editReview(
        widget.submissionId,
        question.id,
        expectedVersion: expectedVersion,
        expectedAiGradeId: expectedAiGradeId,
        scoreAwarded: score,
        scoreMaximum: question.points,
        criteria: carriedCriteria,
        rationale: carriedRationale,
        comment: comment.isEmpty ? null : comment,
        recognizedText: recognizedText,
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
        title: Text(_appBarTitle(), overflow: TextOverflow.ellipsis),
        actions: [
          if (!_loadingShell) ...[
            _buildSubmissionStateChip(),
            const SizedBox(width: AppSpacing.md),
          ],
          IconButton(
            key: const Key('review-export-button'),
            tooltip: 'PDF出力',
            icon: const Icon(Icons.picture_as_pdf_outlined),
            onPressed: _loadingShell ? null : _showExportDialog,
          ),
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
        padding: AppSpacing.page,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.error_outline, size: AppIconSize.display),
            const SizedBox(height: AppSpacing.sm),
            Text(_shellError!, key: const Key('review-shell-error')),
            const SizedBox(height: AppSpacing.lg),
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
        // Navigation Rail is unaffected: it stays a vertical rail on the left
        // at every width (`NavigationRail` has no horizontal layout), labels
        // included (see [_buildNavigationRail]).
        final narrow = constraints.maxWidth < AppLayout.narrowBreakpoint;
        final rail = _buildNavigationRail();
        final inspector = _buildInspector(narrow: narrow);
        // The 進捗パネル band is charged to the PDF viewer, not to the whole
        // screen. It used to sit full-width above everything, which meant the
        // Inspector -- the only thing on this screen 承認 is a decision about
        // -- lost the band's height too, and at 1280x720 that pushed 根拠・
        // コメント・基準ごとの判定 below the fold while 承認して次へ stayed
        // visible (Issue #85). Beside the PDF the band also stops being a
        // 1280px-wide strip holding a ~480px diagram, which is what left the
        // nodes in the left three fifths of the window.
        //
        // At a narrow width the Inspector is stacked under the viewer and so
        // shares the pane, and the band's share shrinks with it. The narrow
        // (stacked) layout splits height by flex ratio, not a fixed pixel size
        // for the Inspector -- a fixed height plus the action bar could exceed
        // a short viewport's total height (a landscape phone, a short desktop
        // window) and overflow. Flexible shares always fit, and the Inspector
        // already scrolls internally if its content doesn't fit its share
        // (P2 review).
        final viewerPane = Column(
          children: [
            // 「AI採点を開始」 sits above the height budget, not inside it
            // (Issue #80). It is a call to action with a button in it, so it
            // takes its natural height and is never the thing that gets
            // squeezed -- and what the 進捗 band may take is a share of what
            // is left *after* it. Measuring the band against the whole pane
            // instead overflowed a short window by the notice's own height.
            ?_buildStartGradingSection(),
            Expanded(
              child: LayoutBuilder(
                builder: (context, remaining) => Column(
                  children: [
                    ?_buildDependencyDagDiagram(remaining),
                    Expanded(
                      // A flex share, with nothing in the Inspector that
                      // insists on a height of its own. It had briefly needed
                      // a floor, because 修正コメント欄 was pinned below the
                      // scrolling material and a share smaller than that band
                      // overflowed rather than shrinking. The field is back
                      // inside the scroll region (レビュー4回目 P2-2), so a
                      // share of any size fits again -- the panel just scrolls.
                      child: narrow
                          ? Column(
                              children: [
                                Expanded(flex: 3, child: _buildPdfViewer()),
                                Expanded(flex: 2, child: inspector),
                              ],
                            )
                          : _buildPdfViewer(),
                    ),
                  ],
                ),
              ),
            ),
          ],
        );
        return Column(
          children: [
            Expanded(
              child: Row(
                children: [
                  rail,
                  const VerticalDivider(width: AppLayout.hairline),
                  Expanded(child: viewerPane),
                  if (!narrow)
                    SizedBox(width: AppLayout.inspectorWidth, child: inspector),
                ],
              ),
            ),
            _buildActionBar(),
          ],
        );
      },
    );
  }

  /// The band above the rail: 「AI採点を開始」 when nothing has been queued
  /// for this submission yet, then the 設問依存DAG 進捗 panel (Issue #64).
  /// `null` when there is neither.
  /// 「この答案のAI採点はまだ開始されていません」+「AI採点を開始」, or `null`
  /// once any job exists (Issue #80, `docs/dependency-dag-progress-view.md`
  /// §1.11).
  ///
  /// **Only at zero jobs.** One job is proof the submission was already
  /// queued, and a button sitting there would read as "press to grade it
  /// again" -- which it is not (the call is idempotent and would do nothing).
  /// Re-running a question is 再判定 and `POST /jobs/{id}/retry`.
  ///
  /// Shown regardless of what the dependency graph looks like: the
  /// unconfirmed-graph notice below says only that the *diagram* cannot be
  /// drawn, never that grading has not started, and 409 is where the reviewer
  /// finds out that the graph is what is in the way.
  ///
  /// Not shown at all until the job list has actually been read once
  /// ([_jobsLoaded]) -- an empty [_jobs] because the fetch failed is not the
  /// same fact as an empty [_jobs] because nothing was ever queued, and only
  /// the second one may be said out loud.
  Widget? _buildStartGradingSection() {
    if (!_jobsLoaded || _jobs.isNotEmpty) return null;
    final failure = _gradingFailure;
    // A failure the sidecar already answered "there is no such submission" to
    // takes the button away entirely. Leaving it live -- directly above its
    // own 「答案が見つかりません」 -- invited the reviewer to re-send a request
    // whose answer cannot change, which is exactly what the intake screen was
    // already careful not to do (`core/grading_kickoff.dart`).
    final canStart = failure?.retryable ?? true;
    return Padding(
      padding: AppSpacing.banner,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Icon(
                Icons.play_circle_outline,
                size: AppIconSize.inline,
                color: AppStatusTone.neutral.color(context),
              ),
              const SizedBox(width: AppSpacing.xs),
              Expanded(
                child: Text(
                  'この答案のAI採点はまだ開始されていません',
                  key: const Key('review-grading-not-started'),
                  style: context.texts.bodyMedium,
                ),
              ),
              if (canStart) ...[
                const SizedBox(width: AppSpacing.sm),
                FilledButton.icon(
                  key: const Key('review-start-grading-button'),
                  onPressed: _startingGrading ? null : () => _startGrading(),
                  icon: const Icon(Icons.play_arrow),
                  label: const Text(startGradingLabel),
                ),
              ],
            ],
          ),
          if (failure != null) ...[
            const SizedBox(height: AppSpacing.sm),
            // `retryable: false` on the banner regardless: when a retry is
            // worth offering, the 「AI採点を開始」 button right above *is* it,
            // and a second one inside the banner would be two controls for one
            // action; when it is not, there is nothing to offer at all.
            AppErrorBanner(
              message: failure.message,
              messageKey: const Key('review-start-grading-error'),
              retryable: false,
            ),
          ],
        ],
      ),
    );
  }

  /// The 設問依存DAG 進捗 panel (Issue #64), or `null` when there is nothing
  /// truthful to draw.
  ///
  /// Only a **confirmed** graph is drawn. `POST /dependency-graph/analyze`
  /// always starts a new DRAFT version rather than touching the confirmed
  /// one, so re-analyzing a test after registration leaves the *latest*
  /// graph a draft that no job ever ran under -- and the sidecar only serves
  /// the latest version. Drawing it would show a dependency structure the
  /// running pipeline is not using. The notice says so rather than leaving
  /// the panel silently missing.
  Widget? _buildDependencyDagDiagram(BoxConstraints pane) {
    final graph = _dependencyGraph;
    if (graph == null) return null;
    if (graph.status != 'confirmed') {
      return Padding(
        padding: AppSpacing.banner,
        child: Text(
          '最新の依存関係グラフが未確定のため、処理の進み方は表示できません。',
          key: const Key('dag-unconfirmed-notice'),
          style: context.texts.bodySmall,
        ),
      );
    }
    final layout = _buildDependencyDagLayout(graph, pane.maxWidth);
    if (layout == null) return null;
    return DependencyDagPanel(
      layout: layout,
      maxCanvasHeight: pane.maxHeight * AppLayout.dagPanelMaxHeightFraction,
      selectedQuestionId: _currentQuestion?.id,
      onQuestionSelected: _selectQuestionById,
    );
  }

  /// Turns this screen's caches into the pure inputs `core` lays out.
  ///
  /// The review half of each node's state is whatever this screen happens to
  /// have fetched -- `_ensureReviewLoaded` only loads the question being
  /// looked at, so an unvisited question shows how far the *pipeline* got
  /// and gains the human decision once it is opened. Loading every
  /// question's review history on every poll tick would cost one request per
  /// question per three seconds to colour in decisions the reviewer has, by
  /// definition, not made yet.
  ///
  /// The rail and the Inspector make exactly the same trade-off, because
  /// they go through the same [_questionStatus] (Issue #84).
  DependencyDagLayout? _buildDependencyDagLayout(
    DependencyGraphResponse graph,
    double availableWidth,
  ) {
    final questions = <DagQuestion>[];
    final released = <String>{};
    for (final question in _questions) {
      final job = _latestJobFor(question.id);
      questions.add(
        DagQuestion(
          id: question.id,
          label: question.number,
          status: _questionStatus(question),
          blockedOnQuestionId: job?.blockedOnQuestionId,
        ),
      );
      if (releasesDependents(job)) released.add(question.id);
    }
    return buildDependencyDagLayout(
      questions: questions,
      edges: graph.edges.toList(),
      releasedQuestionIds: released,
      availableWidth: availableWidth,
    );
  }

  /// `NavigationRail` does not scroll its own destinations -- with enough
  /// questions it simply overflows once they no longer fit the available
  /// height. Wrapping it in `SingleChildScrollView` + `IntrinsicHeight`
  /// (the standard workaround for this widget) lets it size to its natural
  /// height and scroll the excess instead (P2 review), while still filling
  /// the full available height when destinations already fit.
  Widget _buildNavigationRail() {
    final rail = NavigationRail(
      key: const Key('review-question-rail'),
      selectedIndex: _questionIndex,
      onDestinationSelected: _selectQuestion,
      extended: false,
      // 設問番号 is shown at every width. Dropping the labels at narrow
      // widths bought 16px and cost the reviewer the one thing the rail is
      // indexed by: five destinations became five unlabelled icons, and with
      // the old undifferentiated hourglass, five *identical* unlabelled
      // icons (Issue #84).
      labelType: NavigationRailLabelType.all,
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

  /// The rail is the reviewer's map of the whole submission, so its icons say
  /// how far each question has got -- read from [_questionStatus], the same
  /// place the 処理の進み方 panel reads (Issue #84).
  ///
  /// It used to read `_reviews[question.id]` instead, which only this
  /// screen's *currently open* question ever has: every other question came
  /// out as one undifferentiated `hourglass_empty`, collapsing 要確認・
  /// 実行待ち・レビュー待ち into one picture while the panel directly above
  /// was drawing all three apart. Nothing new has to be fetched to fix that
  /// -- `_jobs` already covers the whole submission.
  ///
  /// The state's word rides along as a tooltip and as the semantics label:
  /// the rail is too narrow for a second line of text, and the icon alone
  /// would leave 「どういう意味の形か」 to be guessed (Issue #25).
  Widget _questionStatusIcon(QuestionResponse question) {
    final status = _questionStatus(question);
    final label = '問${question.number} ${_questionStatusLabel(question)}';
    return Tooltip(
      message: label,
      excludeFromSemantics: true,
      child: Semantics(
        label: label,
        child: Icon(status.icon, color: status.tone.color(context)),
      ),
    );
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
    // 「その行の末尾が画面に出たか」を測り直す契機は3つあり、**3つとも要る。**
    // 「材料が変わったか」は行のidだけで答えられるが、こちらは現在のレイアウト
    // についての問いなので、レイアウトが変わり得るたびに測り直すほかない。
    //
    // 1. 指が動かしたとき — `ScrollNotification`（下）。
    // 2. この画面が build されたとき — 直下の post-frame。最初のレイアウト、
    //    設問の切り替え、データの到着がここに入る。内容が収まってしまう
    //    ふつうのケースはスクロール通知を1度も出さないので、通知だけに
    //    頼ると「下端外に何も無い画面で承認が出せない」形で固まる。
    // 3. build を伴わずレイアウトだけ変わったとき —
    //    `ScrollMetricsNotification`（下）。進捗パネルを畳むのはそのパネル
    //    自身の `setState` なので、この画面は build されない。指も触れて
    //    いないので 1 も 2 も鳴らないまま、Inspector のビューポートだけが
    //    広がる（レビュー3回目 P2）。
    //
    // 2 と 3 が重なって鳴るのは無害である。`_recordMaterialSeen` は本当に
    // 変わったときしか `setState` しないので、余分な測り直しはそこで止まる。
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _recordMaterialSeen();
    });
    return Column(
      children: [
        Expanded(
          // The notice floats over the panel instead of taking a row in it.
          //
          // Inside the scrolling column it was part of the very thing it
          // described: at 700x720 the material overflows, the notice appears,
          // and widening to 1280x720 -- where the material fits on its own --
          // left the notice's own ~60px still hanging below the fold, so the
          // panel read as unread because the unread notice was in it. The
          // gate locked itself. Above the action bar it was the same loop
          // through the viewport instead of through the content. A `Stack` is
          // the only placement that costs neither (Issue #85, レビュー1回目 P2).
          child: Stack(
            children: [
              // Trigger 3.  Dispatched from a microtask rather than during
              // layout, so reacting with `setState` is safe here.
              NotificationListener<ScrollMetricsNotification>(
                onNotification: (_) {
                  _recordMaterialSeen();
                  return false;
                },
                // Trigger 1: the reviewer dragging, live.
                child: NotificationListener<ScrollNotification>(
                  onNotification: (_) {
                    _recordMaterialSeen();
                    return false;
                  },
                  // `KeyedSubtree` rather than putting the global key on the
                  // scroll view itself: `review-inspector` is the key the
                  // tests and the reveal action address it by, and a widget
                  // has room for one key.
                  child: KeyedSubtree(
                    key: _inspectorViewportKey,
                    child: SingleChildScrollView(
                      key: const Key('review-inspector'),
                      controller: _inspectorScrollController,
                      padding: AppSpacing.panel,
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          // Heading and state on one line rather than
                          // stacked: this panel is the only place the 判断材料
                          // lives, and every row it does not spend on a
                          // heading is a row of 根拠/コメント/基準ごとの判定
                          // that gets to stay on screen with the 承認 button
                          // (Issue #85). The badge is still the *question's*
                          // state, still reading `_questionStatus` like the
                          // rail and the panel do, and still adjacent to the
                          // 問N it belongs to (Issue #84) -- only the axis it
                          // is stacked on changed.
                          Row(
                            children: [
                              Expanded(
                                child: Text(
                                  '問${question.number}',
                                  style: context.texts.titleLarge,
                                ),
                              ),
                              _buildQuestionStateChip(question),
                            ],
                          ),
                          const SizedBox(height: AppSpacing.lg),
                          if (review == null || review.loading)
                            const Center(
                              key: Key('review-question-loading'),
                              child: Padding(
                                padding: AppSpacing.page,
                                child: CircularProgressIndicator(),
                              ),
                            )
                          else if (review.error != null)
                            _buildQuestionError(review.error!)
                          else ...[
                            _buildQuestionContent(question, review),
                            // 修正コメント欄はスクロールする側に戻した
                            // (レビュー4回目 P2-2)。1行から3行へ伸びる**可変高**
                            // なので、固定の帯として下端に留めると、3行入力した
                            // ときに帯を越えて桁あふれし、判断材料の領域が高さ0に
                            // なって「続きを表示」にすら届かなくなっていた ---
                            // 承認ゲートを原理的に満たせない画面である。
                            //
                            // 留める理由も無くなった。ゲートは「行ごとに末尾が
                            // 画面に出たか」で決まるようになり、スクロール量とは
                            // 無関係なので、メモ欄がスクロール領域の中にあっても
                            // 判定は1pxも変わらない。
                            const Divider(height: AppLayout.sectionDivider),
                            _buildNoteField(),
                          ],
                        ],
                      ),
                    ),
                  ),
                ),
              ),
              if (_blockedOnUnreadMaterial)
                Positioned(
                  left: 0,
                  right: 0,
                  bottom: 0,
                  child: _buildUnreadMaterialNotice(),
                ),
            ],
          ),
        ),
      ],
    );
  }

  /// The badge directly under the 問N heading. It says what *that question*
  /// is, and nothing else (Issue #84).
  ///
  /// What used to sit here was the **答案全体** の state. Both readings were
  /// individually correct, and that was the problem: two grains of state
  /// stood one above the other under a heading naming a single question, so
  /// the panel could say 問1 承認済み while this said ⚠要確認 -- and the
  /// 承認して次へ button sat under both. 答案 state has not been dropped, it
  /// moved to the AppBar next to the 答案's own name
  /// ([_buildSubmissionStateChip]).
  Widget _buildQuestionStateChip(QuestionResponse question) {
    final status = _questionStatus(question);
    final toneColor = status.tone.color(context);
    return Align(
      alignment: AlignmentDirectional.centerStart,
      child: Chip(
        key: const Key('review-question-state'),
        avatar: Icon(status.icon, size: AppIconSize.dense, color: toneColor),
        label: Text(_questionStatusLabel(question)),
        // 形・枠線・日本語ラベルの三重表現。DAGノードが状態のトーンで枠を
        // 描くのと同じ規則で、こちらだけ枠が無いと同じ状態が違う見え方に
        // なる (Issue #25 / #84)。
        side: BorderSide(
          color: status.tone == AppStatusTone.neutral
              ? context.colors.outlineVariant
              : toneColor,
        ),
      ),
    );
  }

  /// 答案1件ぶんの取込状態。AppBar に置いてあるのは、そこが**答案の名前**が
  /// 出ている唯一の場所だからである (Issue #84)。ラベルにも「答案:」を付けて、
  /// 位置と語の両方で対象を名指す -- 設問見出しの直下にあったときは、どちらも
  /// 無かった。
  Widget _buildSubmissionStateChip() {
    final visual = SubmissionStatusVisual.of(_submission?.state);
    return Row(
      key: const Key('review-submission-state'),
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(
          visual.icon,
          size: AppIconSize.dense,
          color: visual.tone.color(context),
        ),
        const SizedBox(width: AppSpacing.xs),
        Text('答案: ${visual.label}', style: context.textRoles.uiLabel),
      ],
    );
  }

  Widget _buildQuestionError(String message) {
    return AppErrorBanner(
      message: message,
      messageKey: const Key('review-question-error'),
      onRetry: () => _ensureReviewLoaded(forceReload: true),
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
        if (ocrRecognition != null)
          _materialRowEdge('ocr:${ocrRecognition.id}', _materialTop),
        Text('AI認識文字', style: context.texts.titleSmall),
        const SizedBox(height: AppSpacing.xs),
        if (ocrRecognition == null)
          const Text('未認識')
        else ...[
          Text(
            ocrRecognition.text,
            key: const Key('review-recognition-text'),
            style: context.textRoles.recognizedText,
          ),
          const SizedBox(height: AppSpacing.xs),
          _ConfidenceBadge(
            key: const Key('review-recognition-confidence'),
            label: 'OCR文字認識信頼度',
            confidence: ocrRecognition.confidence.toDouble(),
          ),
          _materialRowEdge('ocr:${ocrRecognition.id}', _materialBottom),
        ],
        // The AI grader's own reading is a *second*, distinct AI-sourced row
        // (docs/ai-grading-pipeline.md "AI graderが訂正した認識結果を保持する")
        // -- shown alongside OCR's, not merged into it, so a reviewer can
        // see whether/how the grader corrected what OCR read (P2 review).
        if (gradingRecognition != null) ...[
          const SizedBox(height: AppSpacing.sm),
          _materialRowEdge('grading:${gradingRecognition.id}', _materialTop),
          Text(
            '採点AIの認識結果',
            key: const Key('review-grading-recognition-label'),
            style: context.texts.labelLarge,
          ),
          Text(
            gradingRecognition.text,
            key: const Key('review-grading-recognition-text'),
            style: context.textRoles.recognizedText,
          ),
          const SizedBox(height: AppSpacing.xs),
          _ConfidenceBadge(
            key: const Key('review-grading-recognition-confidence'),
            label: '採点AI文字認識信頼度',
            confidence: gradingRecognition.confidence.toDouble(),
          ),
          _materialRowEdge('grading:${gradingRecognition.id}', _materialBottom),
        ],
        // A human correction never overwrites the AI's row (append-only
        // history, §19/§35-5) -- shown as its own, clearly-labeled entry
        // instead of silently replacing "AI認識文字" above, so a human's
        // confidence (always 1.0) is never mistaken for the AI's.
        if (humanRecognition != null) ...[
          const SizedBox(height: AppSpacing.sm),
          _materialRowEdge('human:${humanRecognition.id}', _materialTop),
          _ProvenanceLabel(
            key: const Key('review-human-recognition-label'),
            text: '人による修正',
          ),
          Text(
            humanRecognition.text,
            key: const Key('review-human-recognition-text'),
            style: context.textRoles.recognizedText,
          ),
          _materialRowEdge('human:${humanRecognition.id}', _materialBottom),
        ],
        const Divider(height: AppLayout.sectionDivider),
        if (aiGrade != null)
          _materialRowEdge('grade:${aiGrade.id}', _materialTop),
        Text('採点', style: context.texts.titleSmall),
        const SizedBox(height: AppSpacing.xs),
        if (aiGrade == null)
          const Text('未採点')
        else ...[
          Text(
            '${aiGrade.score.awarded} / ${aiGrade.score.maximum} 点',
            key: const Key('review-score'),
            style: context.textRoles.score,
          ),
          const SizedBox(height: AppSpacing.xs),
          _ConfidenceBadge(
            key: const Key('review-grading-confidence'),
            label: '採点信頼度',
            confidence: aiGrade.confidence.toDouble(),
          ),
          if (aiGrade.rationale case final rationale?
              when rationale.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.sm),
            Text('根拠', style: context.texts.labelLarge),
            Text(
              rationale,
              key: const Key('review-rationale'),
              style: context.textRoles.gradingComment,
            ),
          ],
          // AIの総評コメント (簡易設計書 §16.5「コメント」) -- 根拠 (この点数に
          // なった理由) とは別の欄として表示する。
          if (aiGrade.comment case final comment? when comment.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.sm),
            Text('コメント', style: context.texts.labelLarge),
            Text(
              comment,
              key: const Key('review-grade-comment'),
              style: context.textRoles.gradingComment,
            ),
          ],
          _materialRowEdge('grade:${aiGrade.id}', _materialBottom),
        ],
        if (humanGrade != null) ...[
          const SizedBox(height: AppSpacing.sm),
          _materialRowEdge('human-grade:${humanGrade.id}', _materialTop),
          _ProvenanceLabel(
            key: const Key('review-human-grade-label'),
            text: '人による確定',
          ),
          Text(
            '${humanGrade.score.awarded} / ${humanGrade.score.maximum} 点',
            key: const Key('review-human-score'),
            style: context.textRoles.score,
          ),
          _materialRowEdge('human-grade:${humanGrade.id}', _materialBottom),
        ],
        // The rubric's own definition (description + 配点) is shown
        // whenever the question has one, independent of whether AI/human
        // grading has happened yet -- outcomes below annotate it where a
        // grade has judged that criterion, but the definition itself must
        // never disappear just because grading hasn't reached it (P1
        // review).
        if (question.rubric.isNotEmpty) ...[
          const SizedBox(height: AppSpacing.sm),
          _materialRowEdge(
            'rubric:${review.displayGrade?.id ?? '-'}',
            _materialTop,
          ),
          Text('採点基準', style: context.texts.labelLarge),
          // One line per criterion, not a `ListTile` with the 判定 on a
          // second line under it: a dense tile costs 64px each, and a rubric
          // of four criteria alone was taller than the space the whole panel
          // had at 1280x720 (Issue #85). Icon *and* Japanese label are both
          // still there -- the 判定 must never be carried by colour alone
          // (Issue #25).
          for (final criterion in question.rubric)
            Padding(
              key: Key('rubric-criterion-${criterion.id}'),
              padding: const EdgeInsets.only(top: AppSpacing.xs),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(
                    _criterionIcon(
                      _criterionOutcomeFor(criterion.id, review.displayGrade),
                    ),
                    size: AppIconSize.dense,
                  ),
                  const SizedBox(width: AppSpacing.xs),
                  Expanded(
                    child: Text(
                      '${criterion.description}（${criterion.maxPoints}点）',
                      style: context.textRoles.questionText,
                    ),
                  ),
                  const SizedBox(width: AppSpacing.sm),
                  Text(
                    _criterionLabel(
                      _criterionOutcomeFor(criterion.id, review.displayGrade),
                    ),
                    style: context.texts.labelLarge,
                  ),
                ],
              ),
            ),
        ],
        _materialRowEdge(
          'rubric:${review.displayGrade?.id ?? '-'}',
          _materialBottom,
        ),
        if (fallbackAnnotations.isNotEmpty) ...[
          const Divider(height: AppLayout.sectionDivider),
          Text('設問コメント', style: context.texts.titleSmall),
          for (final annotation in fallbackAnnotations) ...[
            _materialRowEdge('annotation:${annotation.id}', _materialTop),
            ListTile(
              key: Key('fallback-annotation-${annotation.id}'),
              dense: true,
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.comment_outlined),
              title: Text(
                annotation.comment ?? annotation.anchorText ?? '',
                style: context.textRoles.gradingComment,
              ),
            ),
            _materialRowEdge('annotation:${annotation.id}', _materialBottom),
          ],
        ],
      ],
    );
  }

  /// 修正/却下/再判定 の理由欄。
  ///
  /// Pinned under the scrolling 判断材料 rather than sitting at the bottom of
  /// it (Issue #85). Two reasons, and they point the same way: it is an
  /// *input*, so it belongs next to the buttons that consume it rather than
  /// buried under the rubric; and keeping it out of the scroll region is what
  /// lets "scrolled to the end" mean "saw all of the 判断材料" exactly, which
  /// is the condition 承認 is gated on ([_materialFullyRead]).
  Widget _buildNoteField() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.lg,
        AppSpacing.sm,
        AppSpacing.lg,
        AppSpacing.lg,
      ),
      child: TextField(
        key: const Key('review-note-field'),
        controller: _noteController,
        focusNode: _noteFocusNode,
        // Starts at one line and grows to three as it is typed into: three
        // empty lines held open at the bottom of the panel are three lines of
        // 採点基準 that the 判断材料 above does not get.
        minLines: 1,
        maxLines: 3,
        decoration: const InputDecoration(
          isDense: true,
          labelText: '修正コメント',
          hintText: 'このセッション内でのみ保持されるメモです',
          border: OutlineInputBorder(),
        ),
        onChanged: _saveNote,
      ),
    );
  }

  Widget _buildActionBar() {
    return Material(
      elevation: AppElevation.raised,
      child: Padding(
        padding: AppSpacing.actionBar,
        child: _buildActionButtons(),
      ),
    );
  }

  /// Why 承認 is refused, and the way out of it (Issue #85).
  ///
  /// Icon plus a sentence plus a named action -- never a colour on its own
  /// (Issue #25) -- and it is present only while the gate is actually closed,
  /// so it reads as "there is more to look at", not as a permanent banner the
  /// eye learns to skip.
  ///
  /// Floated over the bottom edge of the panel by [_buildInspector] rather
  /// than laid out inside it, so that it takes neither a row of the material
  /// nor a slice of the viewport. It sits at the bottom because that is the
  /// direction it is pointing, and the only thing it ever covers is material
  /// the reviewer is about to scroll past anyway -- by the time they reach
  /// the end, the gate is open and the notice is gone.
  Widget _buildUnreadMaterialNotice() {
    return Material(
      // Opaque, and lifted: it is floating over the material, and text over
      // text is unreadable.
      elevation: AppElevation.raised,
      child: Padding(
        padding: AppSpacing.banner,
        child: Row(
          key: const Key('review-unread-material-notice'),
          children: [
            Icon(
              _unreadIsAbove ? Icons.arrow_upward : Icons.arrow_downward,
              size: AppIconSize.inline,
            ),
            const SizedBox(width: AppSpacing.xs),
            Expanded(
              child: Text(
                _unreadIsAbove
                    ? 'この上にまだ見ていない判断材料があります。表示すると承認できます。'
                    : 'この下にまだ判断材料があります。最後まで表示すると承認できます。',
                style: context.texts.bodySmall,
              ),
            ),
            const SizedBox(width: AppSpacing.sm),
            // Enter is bound page-wide to 承認して次へ, and a
            // `CallbackShortcuts` above this button would swallow it before
            // the button's own `ActivateIntent` ever ran -- so it is re-bound
            // here, closer to the focus, the same way the 進捗パネル re-binds
            // it for its nodes.
            Shortcuts(
              shortcuts: const <ShortcutActivator, Intent>{
                SingleActivator(LogicalKeyboardKey.enter): ActivateIntent(),
              },
              child: TextButton(
                key: const Key('review-reveal-material-button'),
                onPressed: _revealRestOfMaterial,
                child: const Text('続きを表示'),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildActionButtons() {
    return
    // Wraps onto a second line instead of scrolling horizontally at a
    // narrow desktop width (Issue #21 acceptance: desktopの標準/狭幅表示).
    //
    // It used to be a `reverse: true` horizontal scroll view, which starts
    // pinned to its *end*: at 700px the row's leading button, 元に戻す,
    // was scrolled off the left edge and rendered as 「戻す (Ctrl+Z)」 with
    // its icon gone. Undo is the only way back from a wrong 承認, so it is
    // the one label on this bar that must never be half-readable, and a
    // reviewer has no reason to suspect a bar with no visible scrollbar of
    // hiding a control (Issue #85). Wrapping keeps every button whole and
    // costs a second row only when they genuinely do not fit.
    Wrap(
      alignment: WrapAlignment.end,
      spacing: AppSpacing.md,
      runSpacing: AppSpacing.sm,
      children: [
        OutlinedButton.icon(
          key: const Key('review-undo-button'),
          onPressed: _canUndo ? _undo : null,
          icon: const Icon(Icons.undo),
          label: const Text('元に戻す (Ctrl+Z)'),
        ),
        OutlinedButton.icon(
          key: const Key('review-regrade-button'),
          onPressed: _canDecide ? _regrade : null,
          icon: const Icon(Icons.autorenew),
          label: const Text('再判定 (R)'),
        ),
        OutlinedButton.icon(
          key: const Key('review-edit-button'),
          onPressed: _canDecide ? _showEditDialog : null,
          icon: const Icon(Icons.edit_outlined),
          label: const Text('修正 (E)'),
        ),
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
        // A disabled button has to say why it is disabled, even when the
        // reason is also written above the material it guards -- the reviewer
        // may well be scrolled past the notice by then.
        Tooltip(
          message: _blockedOnUnreadMaterial
              ? '判断材料を末尾まで表示すると承認できます'
              : '承認して次の設問へ',
          child: FilledButton.icon(
            key: const Key('review-approve-button'),
            onPressed: _canApprove ? _approveAndNext : null,
            icon: const Icon(Icons.check),
            label: const Text('承認して次へ (Enter)'),
          ),
        ),
      ],
    );
  }
}

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
        const Icon(Icons.person, size: AppIconSize.inline),
        const SizedBox(width: AppSpacing.xs),
        Text(text, style: context.texts.labelLarge),
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
    // 低Confidence は「人間が見ないと決められない」の代表例なので、この画面で
    // 強調色を使ってよい数少ない場所。中/高は進行中と同じく無彩色に置く --
    // 全部に色を付ければ、どれも目立たなくなる。
    final tone = switch (level) {
      ConfidenceLevel.high => AppStatusTone.success,
      ConfidenceLevel.medium => AppStatusTone.neutral,
      ConfidenceLevel.low => AppStatusTone.attention,
    };
    final color = tone.color(context);
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
          Icon(icon, size: AppIconSize.dense, color: color),
          const SizedBox(width: AppSpacing.xs),
          Text(
            '$label: $percent% (${level.label})',
            style: context.texts.bodySmall?.copyWith(color: color),
          ),
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
    // 赤ペンの赤。`colorScheme.error` ではない -- 正解に付ける○はエラーでは
    // なく、これは答案の上に重ねる添削記号の色である (`AppStatusColors
    // .annotationMark`)。ライト/ダークで同じ値なのも意図的で、記号が乗るのは
    // テーマではなく常に白いPDFのページだから。
    final color = context.statusColors.annotationMark;
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
            const SizedBox(width: AppSpacing.xs),
            Text(label, style: TextStyle(color: color)),
          ],
        ],
      ),
    );
    if (tooltip == null || tooltip!.isEmpty) return child;
    return Tooltip(message: tooltip!, child: child);
  }
}
