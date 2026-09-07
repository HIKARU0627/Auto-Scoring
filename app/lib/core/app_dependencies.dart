import 'dart:typed_data';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';

Future<bool> _stubHealthCheck() async => true;

/// Default answer-intake operations: honestly report "not connected" rather
/// than faking success.
///
/// These defaults are the *test* configuration now that process supervision
/// exists: a widget test constructs `AppDependencies()` and overrides only
/// the handful of calls it exercises. The running app never uses them --
/// `main.dart` builds [AppDependencies.fromClient] from the connection
/// [SidecarSupervisor] establishes (`docs/windows-distribution.md` §5).
Never _unavailable() => throw SidecarApiException(
  SidecarErrorKind.unavailable,
  'sidecar is not connected',
);

// Each wrapper is `async` on purpose, even though it just forwards to
// `_unavailable()`: a plain `=>` body would let `_unavailable()`'s `throw`
// escape *synchronously* from the call, before the function's Future is ever
// created. `AnswerIntakePage.initState()` calls `listTests()` directly (not
// inside a try/catch, expecting a Future it can hand to FutureBuilder), so a
// synchronous throw here would crash while the widget is still mounting
// instead of surfacing as the `snapshot.hasError` state FutureBuilder renders.
// `async` makes Dart capture that throw into the returned Future instead.
Future<List<TestSummary>> _unavailableListTests() async => _unavailable();

Future<List<SubmissionResponse>> _unavailableListSubmissions(
  String testId,
) async => _unavailable();

Future<SubmissionResponse> _unavailableGetSubmission(
  String submissionId,
) async => _unavailable();

Future<SubmissionResponse> _unavailableCreateSubmission({
  required String testId,
  required String filePath,
  String? studentLabel,
}) async => _unavailable();

Future<TestResponse> _unavailableCreateTest({
  required String name,
  String? subject,
  required String modelAnswerPath,
  required String manualPath,
}) async => _unavailable();

Future<TestResponse> _unavailableGetTest(String testId) async => _unavailable();

Future<List<TestResponse>> _unavailableListTestRegistrations() async =>
    _unavailable();

Future<ProfileResponse> _unavailableAnalyzeProfile(String testId) async =>
    _unavailable();

Future<ProfileResponse> _unavailableGetProfile(String testId) async =>
    _unavailable();

Future<ProfileResponse> _unavailableUpdateProfile(
  String testId,
  List<RegionModel> regions,
) async => _unavailable();

Future<ProfileResponse> _unavailableConfirmProfile(
  String testId, {
  required int revision,
}) async => _unavailable();

Future<CompleteRegistrationResponse> _unavailableCompleteRegistration(
  String testId,
) async => _unavailable();

Future<DependencyGraphResponse> _unavailableAnalyzeDependencyGraph(
  String testId, {
  List<QuestionTextOverride> overrides = const [],
}) async => _unavailable();

Future<DependencyGraphResponse> _unavailableGetDependencyGraph(
  String testId,
) async => _unavailable();

Future<DependencyGraphResponse> _unavailableConfirmDependencyGraph(
  String testId, {
  required int version,
  required List<DependencyEdgeModel> edges,
}) async => _unavailable();

Future<List<QuestionResponse>> _unavailableListQuestions(String testId) async =>
    _unavailable();

Future<Uint8List> _unavailableGetSourcePdf(String submissionId) async =>
    _unavailable();

Future<List<RecognitionResponse>> _unavailableListRecognitions(
  String submissionId,
  String questionId,
) async => _unavailable();

Future<List<GradeResultResponse>> _unavailableListGrades(
  String submissionId,
  String questionId,
) async => _unavailable();

Future<List<AnnotationResponse>> _unavailableListAnnotations(
  String submissionId,
  String questionId,
) async => _unavailable();

Future<List<JobResponse>> _unavailableListJobs(String submissionId) async =>
    _unavailable();

Future<List<ReviewResponse>> _unavailableListReviews(
  String submissionId,
  String questionId,
) async => _unavailable();

Future<ReviewActionResponse> _unavailableEditReview(
  String submissionId,
  String questionId, {
  required int expectedVersion,
  String? expectedAiGradeId,
  required int scoreAwarded,
  required int scoreMaximum,
  double confidence = 1.0,
  List<CriterionOutcomeRequest> criteria = const [],
  String? rationale,
  String? comment,
  String? recognizedText,
  List<AnnotationEditRequest>? annotations,
  String? note,
}) async => _unavailable();

Future<ReviewActionResponse> _unavailableRejectReview(
  String submissionId,
  String questionId, {
  required int expectedVersion,
  String? reason,
}) async => _unavailable();

Future<ReviewActionResponse> _unavailableRegradeReview(
  String submissionId,
  String questionId, {
  required int expectedVersion,
  String? reason,
}) async => _unavailable();

Future<ReviewActionResponse> _unavailableApproveReview(
  String submissionId,
  String questionId, {
  required int expectedVersion,
  String? expectedAiGradeId,
  String? note,
}) async => _unavailable();

Future<ReviewActionResponse> _unavailableUndoReview(
  String submissionId,
  String questionId, {
  required int expectedVersion,
}) async => _unavailable();

Future<ExportRequestResponse> _unavailableRequestExport(
  String submissionId,
) async => _unavailable();

Future<List<ExportResponse>> _unavailableListExports(
  String submissionId,
) async => _unavailable();

Future<JobResponse> _unavailableGetJob(String jobId) async => _unavailable();

Future<JobResponse> _unavailableRetryJob(String jobId) async => _unavailable();

/// Fetches every registered test available to import answers into
/// (simplified-design-spec.md §16.4).
typedef ListTests = Future<List<TestSummary>> Function();

/// Fetches every submission already imported for [testId].
typedef ListSubmissions =
    Future<List<SubmissionResponse>> Function(String testId);

/// One submission's current intake/processing state (添削レビュー画面のstate表示).
typedef GetSubmission =
    Future<SubmissionResponse> Function(String submissionId);

/// Uploads one answer PDF for [testId]. Re-uploading a failed submission's
/// exact bytes retries it in place; re-uploading identical bytes for a
/// submission that isn't errored throws [DuplicateSubmissionException]
/// (docs/answer-intake-and-preprocessing.md §2).
typedef CreateSubmission =
    Future<SubmissionResponse> Function({
      required String testId,
      required String filePath,
      String? studentLabel,
    });

/// Registers a new test's model-answer + marking-manual PDFs (テスト登録画面,
/// Issue #16). Creates a `draft` test; no profile exists yet.
typedef CreateTest =
    Future<TestResponse> Function({
      required String name,
      String? subject,
      required String modelAnswerPath,
      required String manualPath,
    });

/// One test's current registration state (テスト設定画面).
typedef GetTest = Future<TestResponse> Function(String testId);

/// Every test regardless of status -- how a `draft` registration is found
/// and reopened again after leaving テスト設定画面 or restarting the app.
typedef ListTestRegistrations = Future<List<TestResponse>> Function();

/// Generates DRAFT profile candidates from a test's two registration PDFs.
/// Safe to call again -- always overwrites whatever DRAFT profile was there.
typedef AnalyzeProfile = Future<ProfileResponse> Function(String testId);

/// The current (draft or confirmed) profile for a test.
typedef GetProfile = Future<ProfileResponse> Function(String testId);

/// Replaces a test's profile regions with a human-reviewed set (still
/// DRAFT -- not the confirm step).
typedef UpdateProfile =
    Future<ProfileResponse> Function(String testId, List<RegionModel> regions);

/// The human confirmation step over a test's current profile region set.
/// `revision` must match the profile currently on disk (the caller's own
/// last `getProfile`/`updateProfile`/`analyzeProfile` response), or another
/// client's edit landed in between and this is rejected as stale.
typedef ConfirmProfile =
    Future<ProfileResponse> Function(String testId, {required int revision});

/// The final registration gate: moves a test from `draft` to `ready` once
/// both the profile and the dependency graph are confirmed.
typedef CompleteRegistration =
    Future<CompleteRegistrationResponse> Function(String testId);

/// Generates a new dependency-graph candidate version for a test (Issue #26).
typedef AnalyzeDependencyGraph =
    Future<DependencyGraphResponse> Function(
      String testId, {
      List<QuestionTextOverride> overrides,
    });

/// The latest dependency-graph version for a test (draft or confirmed).
typedef GetDependencyGraph =
    Future<DependencyGraphResponse> Function(String testId);

/// The human confirmation step over one dependency-graph version of a test.
typedef ConfirmDependencyGraph =
    Future<DependencyGraphResponse> Function(
      String testId, {
      required int version,
      required List<DependencyEdgeModel> edges,
    });

/// Every `Question` for [testId] (its profile areas + rubric) -- the
/// 添削レビュー画面's Navigation Rail and Inspector (§16.5, Issue #21).
typedef ListQuestions = Future<List<QuestionResponse>> Function(String testId);

/// The original, unmodified answer PDF for one submission, for the `pdfrx`
/// viewer to render underneath the annotation overlay (§13.1).
typedef GetSourcePdf = Future<Uint8List> Function(String submissionId);

/// Every `RecognitionResult` recorded for one submission-question so far
/// (AI proposals and human corrections, oldest first).
typedef ListRecognitions =
    Future<List<RecognitionResponse>> Function(
      String submissionId,
      String questionId,
    );

/// Every `GradeResult` recorded for one submission-question so far, each with
/// its own score, Grading Confidence, rubric criteria, and rationale.
typedef ListGrades =
    Future<List<GradeResultResponse>> Function(
      String submissionId,
      String questionId,
    );

/// Every `Annotation` recorded for one submission-question, for the PDF
/// overlay.
typedef ListAnnotations =
    Future<List<AnnotationResponse>> Function(
      String submissionId,
      String questionId,
    );

/// Every `Job` (kind GRADING) ever created for one submission, across every
/// question -- the per-question job's own lifecycle (queued/running/blocked/
/// succeeded/failed/cancelled), used to tell "still processing" apart from
/// "this attempt is done" independent of what data has been persisted so far
/// (添削レビュー画面のpolling, Issue #21 P1 review).
typedef ListJobs = Future<List<JobResponse>> Function(String submissionId);

/// The full append-only operation history for one submission-question,
/// oldest first (Issue #22 §19). Its length is the ``expectedVersion`` the
/// next mutating review call for this submission-question must pass.
typedef ListReviews =
    Future<List<ReviewResponse>> Function(
      String submissionId,
      String questionId,
    );

/// A human's corrected score/comment (and, optionally, recognized text and
/// annotations) -- always confirms in the same step (Issue #22 "edit").
/// [expectedVersion] must be this question's current review-history length
/// (`ListReviews`'s result); a stale value throws [SidecarApiException] with
/// `SidecarErrorKind.conflict`, as does having no AI grade yet to correct,
/// or a stale [expectedAiGradeId] (Issue #22 P1 review) -- see
/// `SidecarApiClient.editReview`.
typedef EditReview =
    Future<ReviewActionResponse> Function(
      String submissionId,
      String questionId, {
      required int expectedVersion,
      String? expectedAiGradeId,
      required int scoreAwarded,
      required int scoreMaximum,
      double confidence,
      List<CriterionOutcomeRequest> criteria,
      String? rationale,
      String? comment,
      String? recognizedText,
      List<AnnotationEditRequest>? annotations,
      String? note,
    });

/// Records that the AI's current proposal is unusable (Issue #22 "reject").
typedef RejectReview =
    Future<ReviewActionResponse> Function(
      String submissionId,
      String questionId, {
      required int expectedVersion,
      String? reason,
    });

/// Queues a fresh AI attempt (Issue #22 "regrade").
typedef RegradeReview =
    Future<ReviewActionResponse> Function(
      String submissionId,
      String questionId, {
      required int expectedVersion,
      String? reason,
    });

/// Confirms the AI's current proposal as-is (Issue #22 "approve", the
/// confirm half of "承認して次へ"). See [EditReview] for [expectedAiGradeId].
typedef ApproveReview =
    Future<ReviewActionResponse> Function(
      String submissionId,
      String questionId, {
      required int expectedVersion,
      String? expectedAiGradeId,
      String? note,
    });

/// Reverts the currently-effective human review action as a new row (Ctrl+Z,
/// Issue #22 "Undo").
typedef UndoReview =
    Future<ReviewActionResponse> Function(
      String submissionId,
      String questionId, {
      required int expectedVersion,
    });

/// Requests the annotated-PDF export for [submissionId] (Issue #23,
/// simplified-design-spec.md §14). Throws [SidecarApiException] with
/// `SidecarErrorKind.conflict` if any question is not yet confirmed.
typedef RequestExport =
    Future<ExportRequestResponse> Function(String submissionId);

/// Every successful export recorded for [submissionId], oldest first
/// (Issue #23: 出力履歴・保存先表示).
typedef ListExports =
    Future<List<ExportResponse>> Function(String submissionId);

/// One `Job`'s current state, by id (Issue #23: exportジョブの進捗polling).
typedef GetJob = Future<JobResponse> Function(String jobId);

/// Requeues a `FAILED` job (Issue #23: 出力の再試行).
typedef RetryJob = Future<JobResponse> Function(String jobId);

/// Composition-root dependency container.
///
/// Features read their collaborators from here instead of constructing them,
/// so the dependency direction stays `features -> core -> api`. A richer DI
/// solution (Riverpod) arrives with the first real feature.
class AppDependencies {
  const AppDependencies({
    this.healthCheck = _stubHealthCheck,
    this.listTests = _unavailableListTests,
    this.listSubmissions = _unavailableListSubmissions,
    this.getSubmission = _unavailableGetSubmission,
    this.createSubmission = _unavailableCreateSubmission,
    this.createTest = _unavailableCreateTest,
    this.getTest = _unavailableGetTest,
    this.listTestRegistrations = _unavailableListTestRegistrations,
    this.analyzeProfile = _unavailableAnalyzeProfile,
    this.getProfile = _unavailableGetProfile,
    this.updateProfile = _unavailableUpdateProfile,
    this.confirmProfile = _unavailableConfirmProfile,
    this.completeRegistration = _unavailableCompleteRegistration,
    this.analyzeDependencyGraph = _unavailableAnalyzeDependencyGraph,
    this.getDependencyGraph = _unavailableGetDependencyGraph,
    this.confirmDependencyGraph = _unavailableConfirmDependencyGraph,
    this.listQuestions = _unavailableListQuestions,
    this.getSourcePdf = _unavailableGetSourcePdf,
    this.listRecognitions = _unavailableListRecognitions,
    this.listGrades = _unavailableListGrades,
    this.listAnnotations = _unavailableListAnnotations,
    this.listJobs = _unavailableListJobs,
    this.listReviews = _unavailableListReviews,
    this.editReview = _unavailableEditReview,
    this.rejectReview = _unavailableRejectReview,
    this.regradeReview = _unavailableRegradeReview,
    this.approveReview = _unavailableApproveReview,
    this.undoReview = _unavailableUndoReview,
    this.requestExport = _unavailableRequestExport,
    this.listExports = _unavailableListExports,
    this.getJob = _unavailableGetJob,
    this.retryJob = _unavailableRetryJob,
  });

  /// Wires every operation to a live sidecar.
  ///
  /// The composition root's real configuration: `main.dart` calls this once
  /// [SidecarSupervisor] reports [SidecarReady], with a [SidecarApiClient]
  /// built from that connection. Tear-off references (`client.listTests`
  /// rather than `() => client.listTests()`) so each field is the client's
  /// own method -- the extra `CancelToken?` those methods accept is an
  /// optional named parameter, which Dart's function subtyping allows a
  /// typedef without it to hold.
  AppDependencies.fromClient(SidecarApiClient client)
    : healthCheck = client.isHealthy,
      listTests = client.listTests,
      listSubmissions = client.listSubmissions,
      getSubmission = client.getSubmission,
      createSubmission = client.createSubmission,
      createTest = client.createTest,
      getTest = client.getTest,
      listTestRegistrations = client.listTestRegistrations,
      analyzeProfile = client.analyzeProfile,
      getProfile = client.getProfile,
      updateProfile = client.updateProfile,
      confirmProfile = client.confirmProfile,
      completeRegistration = client.completeRegistration,
      analyzeDependencyGraph = client.analyzeDependencyGraph,
      getDependencyGraph = client.getDependencyGraph,
      confirmDependencyGraph = client.confirmDependencyGraph,
      listQuestions = client.listQuestions,
      getSourcePdf = client.getSourcePdf,
      listRecognitions = client.listRecognitions,
      listGrades = client.listGrades,
      listAnnotations = client.listAnnotations,
      listJobs = client.listJobs,
      listReviews = client.listReviews,
      editReview = client.editReview,
      rejectReview = client.rejectReview,
      regradeReview = client.regradeReview,
      approveReview = client.approveReview,
      undoReview = client.undoReview,
      requestExport = client.requestExport,
      listExports = client.listExports,
      getJob = client.getJob,
      retryJob = client.retryJob;

  /// Whether the sidecar answers its health endpoint. In the running app this
  /// is `SidecarApiClient.isHealthy`; the default is a stub that reports
  /// healthy so widget tests need not stand one up.
  final Future<bool> Function() healthCheck;

  final ListTests listTests;
  final ListSubmissions listSubmissions;
  final GetSubmission getSubmission;
  final CreateSubmission createSubmission;
  final CreateTest createTest;
  final GetTest getTest;
  final ListTestRegistrations listTestRegistrations;
  final AnalyzeProfile analyzeProfile;
  final GetProfile getProfile;
  final UpdateProfile updateProfile;
  final ConfirmProfile confirmProfile;
  final CompleteRegistration completeRegistration;
  final AnalyzeDependencyGraph analyzeDependencyGraph;
  final GetDependencyGraph getDependencyGraph;
  final ConfirmDependencyGraph confirmDependencyGraph;
  final ListQuestions listQuestions;
  final GetSourcePdf getSourcePdf;
  final ListRecognitions listRecognitions;
  final ListGrades listGrades;
  final ListAnnotations listAnnotations;
  final ListJobs listJobs;
  final ListReviews listReviews;
  final EditReview editReview;
  final RejectReview rejectReview;
  final RegradeReview regradeReview;
  final ApproveReview approveReview;
  final UndoReview undoReview;
  final RequestExport requestExport;
  final ListExports listExports;
  final GetJob getJob;
  final RetryJob retryJob;
}
