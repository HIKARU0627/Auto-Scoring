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

Future<SubmissionResponse> _unavailableCreateSubmission({
  required String testId,
  required String filePath,
  String? studentLabel,
}) async => _unavailable();

/// Fetches every registered test available to import answers into
/// (simplified-design-spec.md §16.4).
typedef ListTests = Future<List<TestSummary>> Function();

/// Fetches every submission already imported for [testId].
typedef ListSubmissions =
    Future<List<SubmissionResponse>> Function(String testId);

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
    this.createSubmission = _unavailableCreateSubmission,
  });

  /// Replaced with `SidecarApiClient.isHealthy` when process supervision lands.
  final Future<bool> Function() healthCheck;

  final ListTests listTests;
  final ListSubmissions listSubmissions;
  final CreateSubmission createSubmission;
}
