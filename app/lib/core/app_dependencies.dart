import 'dart:typed_data';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';

Future<bool> _stubHealthCheck() async => true;

/// Default answer-intake operations: honestly report "not connected" rather
/// than faking success.
///
/// These defaults are what [appDependenciesProvider] serves when nothing has
/// overridden it -- a widget test builds an `AppDependencies()` carrying only
/// the handful of calls it exercises and installs it through the provider
/// (`test/app_harness.dart`), and the running app sits on these while the
/// sidecar is not reachable, with `main.dart` swapping in
/// [AppDependencies.fromClient] for the connection [SidecarSupervisor]
/// establishes (`docs/windows-distribution.md` §5).
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
  required String criteriaPath,
  List<({MaterialRole role, String path})> materials = const [],
}) async => _unavailable();

Future<List<TestMaterialResponse>> _unavailableAddMaterials(
  String testId, {
  required List<({MaterialRole role, String path})> materials,
}) async => _unavailable();

Future<List<TestMaterialResponse>> _unavailableListMaterials(
  String testId,
) async => _unavailable();

Future<void> _unavailableDeleteTest(String testId) async => _unavailable();

Future<IntakePlanResponse> _unavailablePlanIntake({
  required String templateId,
  required String rootName,
  required List<ScannedFileModel> files,
}) async => _unavailable();

Future<List<IntakeTemplateModel>> _unavailableListIntakeTemplates() async =>
    _unavailable();

Future<double?> _unavailableIntakeCost() async => _unavailable();

Future<double?> _unavailableSaveIntakeCost(double? unitCost) async =>
    _unavailable();

Future<List<IntakeTemplateModel>> _unavailableSaveIntakeTemplates(
  List<IntakeTemplateModel> templates,
) async => _unavailable();

Future<ClassificationAvailabilityResponse>
_unavailableClassificationAvailability() async => _unavailable();

Future<RoleProposalResponse> _unavailableClassifyMaterial({
  required String path,
}) async => _unavailable();

Future<AttributionProposalResponse> _unavailableAttributeAnswer({
  required String path,
  required List<({String id, String label})> candidates,
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

Future<CriteriaEstimateResponse> _unavailableEstimateCriteria(
  String testId,
) async => _unavailable();

Future<CriteriaResponse> _unavailableExtractCriteria(String testId) async =>
    _unavailable();

Future<CriteriaResponse> _unavailableGetCriteria(String testId) async =>
    _unavailable();

Future<CriteriaResponse> _unavailableUpdateCriteria(
  String testId,
  List<CriteriaQuestionModel> questions, {
  int? declaredTotalPoints,
}) async => _unavailable();

Future<CriteriaResponse> _unavailableConfirmCriteria(
  String testId, {
  required int revision,
}) async => _unavailable();

Future<AnswerLayoutResponse> _unavailableGetAnswerLayout(String testId) async =>
    _unavailable();

Future<AnswerLayoutResponse> _unavailableUploadAnswerLayout(
  String testId, {
  required String filePath,
}) async => _unavailable();

Future<Uint8List> _unavailableGetAnswerLayoutPdf(String testId) async =>
    _unavailable();

Future<ProfileResponse> _unavailableDetectAnswerAreas(String testId) async =>
    _unavailable();

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

Future<List<JobResponse>> _unavailableStartGrading(String submissionId) async =>
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

Future<GradingAvailabilityResponse> _unavailableGradingAvailability() async =>
    _unavailable();

Future<JobResponse> _unavailableGetJob(String jobId) async => _unavailable();

Future<JobResponse> _unavailableRetryJob(String jobId) async => _unavailable();

/// Fetches every registered test available to import answers into
/// (simplified-design-spec.md §16.4).
typedef ListTests = Future<List<TestSummary>> Function();

/// Whether this installation can AI-grade at all, and if not, why
/// (Issue #97). Asked once per sidecar connection by the composition
/// root, which puts the answer above every screen.
typedef GetGradingAvailability = Future<GradingAvailabilityResponse> Function();

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

/// Registers a new test from its 採点基準PDF plus any optional role-tagged
/// materials (Issue #101). Creates a `draft` test; no profile exists yet.
///
/// **No model-answer parameter.** That document does not exist in real
/// grading material (Issue #95 decision 1); one a reviewer happens to have is
/// passed in [materials] under [MaterialRole.reference].
typedef CreateTest =
    Future<TestResponse> Function({
      required String name,
      String? subject,
      required String criteriaPath,
      List<({MaterialRole role, String path})> materials,
    });

/// Attaches more materials to a test that already exists (Issue #101) -- the
/// weekly flow, where 添削資料 turn up after the test was registered.
typedef AddMaterials =
    Future<List<TestMaterialResponse>> Function(
      String testId, {
      required List<({MaterialRole role, String path})> materials,
    });

/// Which file became which role for one test.
typedef ListMaterials =
    Future<List<TestMaterialResponse>> Function(String testId);

/// Deletes a test and everything under it -- what the completion screen offers
/// when a batch went into the wrong one.
typedef DeleteTest = Future<void> Function(String testId);

/// Plans a scanned batch against a saved 取込の型. Sends no file bytes.
typedef PlanIntake =
    Future<IntakePlanResponse> Function({
      required String templateId,
      required String rootName,
      required List<ScannedFileModel> files,
    });

/// Every saved 取込の型 (設定画面).
typedef ListIntakeTemplates = Future<List<IntakeTemplateModel>> Function();

/// The per-call price the reviewer entered, or `null` for "not set".
typedef GetIntakeCost = Future<double?> Function();

/// Records the per-call price; `null` clears it.
typedef SaveIntakeCost = Future<double?> Function(double? unitCost);

/// Replaces the saved 取込の型 with the given list.
typedef SaveIntakeTemplates =
    Future<List<IntakeTemplateModel>> Function(
      List<IntakeTemplateModel> templates,
    );

/// Whether this host can classify at all, and if not, why.
typedef GetClassificationAvailability =
    Future<ClassificationAvailabilityResponse> Function();

/// Asks what one file is, from its first page. One file per call.
typedef ClassifyMaterial =
    Future<RoleProposalResponse> Function({required String path});

/// Asks which of the offered tests one answer belongs to.
///
/// Never called with fewer than two candidates: with one, the reviewer has
/// already decided and the sidecar refuses the call.
typedef AttributeAnswer =
    Future<AttributionProposalResponse> Function({
      required String path,
      required List<({String id, String label})> candidates,
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

/// 抽出が送るページ数と概算費用を、送る前に答える。
/// `unitCost` が `null` なら「見積もれません」であって 0 円ではない。
typedef EstimateCriteria =
    Future<CriteriaEstimateResponse> Function(String testId);

/// Reads a test's 配点と採点基準 out of its registered 採点基準PDF (Issue
/// #103). Always a proposal a human edits, never a value grading reads
/// directly.
typedef ExtractCriteria = Future<CriteriaResponse> Function(String testId);

/// The current (draft or confirmed) 配点と採点基準 for a test.
typedef GetCriteria = Future<CriteriaResponse> Function(String testId);

/// Saves a reviewed -- or entirely hand-entered -- question set (still
/// DRAFT). Creates the draft when there is none, which is what lets a
/// reviewer enter every 配点 by hand on a test whose extraction failed.
typedef UpdateCriteria =
    Future<CriteriaResponse> Function(
      String testId,
      List<CriteriaQuestionModel> questions, {
      int? declaredTotalPoints,
    });

/// The human sign-off over a test's 配点. `revision` must match the draft
/// currently on disk, the same staleness contract [ConfirmProfile] has.
/// Rejected (422) while any 配点 is still 不明.
typedef ConfirmCriteria =
    Future<CriteriaResponse> Function(String testId, {required int revision});

/// Whether a test has a reference answer sheet stored, and whether
/// answer-area detection can run on this machine (Issue #105).
typedef GetAnswerLayout = Future<AnswerLayoutResponse> Function(String testId);

/// Stores one student's answer sheet as a test's layout reference,
/// replacing any previous one.
typedef UploadAnswerLayout =
    Future<AnswerLayoutResponse> Function(
      String testId, {
      required String filePath,
    });

/// A test's stored answer sheet as PDF bytes, for the overlay editor.
typedef GetAnswerLayoutPdf = Future<Uint8List> Function(String testId);

/// Detects a test's answer areas on its stored answer sheet and saves them
/// as DRAFT profile regions. Safe to call again.
typedef DetectAnswerAreas = Future<ProfileResponse> Function(String testId);

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

/// Creates and queues one submission's per-question AI 採点 jobs, returning
/// every job it now has (Issue #80). Called automatically right after a
/// successful 取込 whose outcome was `ai_processed`, and from the 添削レビュー
/// screen for a submission that has no jobs at all -- see
/// `docs/job-queue.md`「起票のタイミング」for why both, and for how the
/// 409 (no confirmed dependency graph, or a concurrent creation) and 404
/// answers are meant to reach the reviewer.
typedef StartGrading = Future<List<JobResponse>> Function(String submissionId);

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

/// The [AppDependencies] every screen resolves its collaborators through.
///
/// Overridden twice, and only twice:
///
/// * by the composition root (`main.dart`), with [AppDependencies.fromClient]
///   for the connection [SidecarSupervisor] currently has -- and back to the
///   not-connected default whenever that connection goes away, so no screen
///   can keep calling a closed client;
/// * by widget tests (`test/app_harness.dart`), with an [AppDependencies]
///   carrying stand-ins for the handful of operations under test.
///
/// The default is the not-connected configuration below: every real call
/// throws `sidecar is not connected` rather than pretending to succeed.
///
/// **A screen reads this once, in `initState`, and holds the result** -- it
/// never resolves it again per call. Two reasons, and the first is a
/// correctness one:
///
/// * `ref` throws a `StateError` once a `ConsumerState` has been disposed. A
///   method that awaits between two calls -- `PdfReviewPage._loadShell`,
///   `TestSettingsPage._loadAll` -- would raise an *unhandled* async error, not
///   a [SidecarApiException] its `catch` would see, if the reviewer left the
///   screen mid-request (Issue #66 review, P2). Riverpod says as much in that
///   error: "save the provider state in a field of your State class".
/// * A request that started against one connection should finish against that
///   one, or not at all. When the value here is replaced the composition root
///   sends the router to `AppRoutes.starting` (`main.dart`), so a screen still
///   holding the old value is already on its way out.
///
/// A `ConsumerWidget` with no async gap (`HomePage`) may of course `watch` it
/// in `build` -- that is the point of a provider.
final appDependenciesProvider = Provider<AppDependencies>(
  (ref) => const AppDependencies(),
);

/// Composition-root dependency container.
///
/// Features read their collaborators from [appDependenciesProvider] instead of
/// constructing them or being handed them through constructors, so the
/// dependency direction stays `features -> core -> api` and no page has to
/// carry another page's dependencies to it.
class AppDependencies {
  const AppDependencies({
    this.healthCheck = _stubHealthCheck,
    this.gradingAvailability = _unavailableGradingAvailability,
    this.listTests = _unavailableListTests,
    this.listSubmissions = _unavailableListSubmissions,
    this.getSubmission = _unavailableGetSubmission,
    this.createSubmission = _unavailableCreateSubmission,
    this.createTest = _unavailableCreateTest,
    this.addMaterials = _unavailableAddMaterials,
    this.listMaterials = _unavailableListMaterials,
    this.deleteTest = _unavailableDeleteTest,
    this.planIntake = _unavailablePlanIntake,
    this.listIntakeTemplates = _unavailableListIntakeTemplates,
    this.intakeCost = _unavailableIntakeCost,
    this.saveIntakeCost = _unavailableSaveIntakeCost,
    this.saveIntakeTemplates = _unavailableSaveIntakeTemplates,
    this.classificationAvailability = _unavailableClassificationAvailability,
    this.classifyMaterial = _unavailableClassifyMaterial,
    this.attributeAnswer = _unavailableAttributeAnswer,
    this.getTest = _unavailableGetTest,
    this.listTestRegistrations = _unavailableListTestRegistrations,
    this.analyzeProfile = _unavailableAnalyzeProfile,
    this.getProfile = _unavailableGetProfile,
    this.updateProfile = _unavailableUpdateProfile,
    this.confirmProfile = _unavailableConfirmProfile,
    this.estimateCriteria = _unavailableEstimateCriteria,
    this.extractCriteria = _unavailableExtractCriteria,
    this.getCriteria = _unavailableGetCriteria,
    this.updateCriteria = _unavailableUpdateCriteria,
    this.confirmCriteria = _unavailableConfirmCriteria,
    this.getAnswerLayout = _unavailableGetAnswerLayout,
    this.uploadAnswerLayout = _unavailableUploadAnswerLayout,
    this.getAnswerLayoutPdf = _unavailableGetAnswerLayoutPdf,
    this.detectAnswerAreas = _unavailableDetectAnswerAreas,
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
    this.startGrading = _unavailableStartGrading,
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
      gradingAvailability = client.gradingAvailability,
      listTests = client.listTests,
      listSubmissions = client.listSubmissions,
      getSubmission = client.getSubmission,
      createSubmission = client.createSubmission,
      createTest = client.createTest,
      addMaterials = client.addMaterials,
      listMaterials = client.listMaterials,
      deleteTest = client.deleteTest,
      planIntake = client.planIntake,
      listIntakeTemplates = client.listIntakeTemplates,
      intakeCost = client.intakeCost,
      saveIntakeCost = client.saveIntakeCost,
      saveIntakeTemplates = client.saveIntakeTemplates,
      classificationAvailability = client.classificationAvailability,
      classifyMaterial = client.classifyMaterial,
      attributeAnswer = client.attributeAnswer,
      getTest = client.getTest,
      listTestRegistrations = client.listTestRegistrations,
      analyzeProfile = client.analyzeProfile,
      getProfile = client.getProfile,
      updateProfile = client.updateProfile,
      confirmProfile = client.confirmProfile,
      estimateCriteria = client.estimateCriteria,
      extractCriteria = client.extractCriteria,
      getCriteria = client.getCriteria,
      updateCriteria = client.updateCriteria,
      confirmCriteria = client.confirmCriteria,
      getAnswerLayout = client.getAnswerLayout,
      uploadAnswerLayout = client.uploadAnswerLayout,
      getAnswerLayoutPdf = client.getAnswerLayoutPdf,
      detectAnswerAreas = client.detectAnswerAreas,
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
      startGrading = client.startGrading,
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

  final GetGradingAvailability gradingAvailability;
  final ListTests listTests;
  final ListSubmissions listSubmissions;
  final GetSubmission getSubmission;
  final CreateSubmission createSubmission;
  final CreateTest createTest;
  final AddMaterials addMaterials;
  final ListMaterials listMaterials;
  final DeleteTest deleteTest;
  final PlanIntake planIntake;
  final ListIntakeTemplates listIntakeTemplates;
  final GetIntakeCost intakeCost;
  final SaveIntakeCost saveIntakeCost;
  final SaveIntakeTemplates saveIntakeTemplates;
  final GetClassificationAvailability classificationAvailability;
  final ClassifyMaterial classifyMaterial;
  final AttributeAnswer attributeAnswer;
  final GetTest getTest;
  final ListTestRegistrations listTestRegistrations;
  final AnalyzeProfile analyzeProfile;
  final GetProfile getProfile;
  final UpdateProfile updateProfile;
  final ConfirmProfile confirmProfile;
  final EstimateCriteria estimateCriteria;
  final ExtractCriteria extractCriteria;
  final GetCriteria getCriteria;
  final UpdateCriteria updateCriteria;
  final ConfirmCriteria confirmCriteria;
  final GetAnswerLayout getAnswerLayout;
  final UploadAnswerLayout uploadAnswerLayout;
  final GetAnswerLayoutPdf getAnswerLayoutPdf;
  final DetectAnswerAreas detectAnswerAreas;
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
  final StartGrading startGrading;
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
