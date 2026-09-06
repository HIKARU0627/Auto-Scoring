import 'dart:typed_data';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';

Future<bool> _stubHealthCheck() async => true;

/// Default answer-intake operations: honestly report "not connected" rather
/// than faking success. Process supervision (spawning the sidecar and
/// handing `main.dart` a real [SidecarConnection]) is future work -- see
/// `docs/technology-stack.md` §1.2 -- so until then every real call surfaces
/// the same `unavailable` state [HomePage]'s health check already renders.
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
  });

  /// Replaced with `SidecarApiClient.isHealthy` when process supervision lands.
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
}
