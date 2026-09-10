/// Which already-registered tests an intake batch's answers could be routed
/// to, and clearing routings that no longer point at one of them.
///
/// Extracted from `features/intake/intake_page.dart` (Issue #126) into its
/// own file rather than folded into `core/intake_review.dart`: that file is
/// Issue #101's confirmation-step state, and answer *attribution* (which
/// registered test an answer belongs to) is a later, separate concern
/// (Issue #80) that reads it. Keeping the two apart gives a change to either
/// one a file of its own to land in, the same reasoning Issue #126 applies to
/// `test_settings_page.dart`.
library;

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/intake_review.dart';

/// The tests an answer could be routed to: [existingTests], narrowed to
/// [narrowedTestIds] when the reviewer has picked any.
///
/// Narrowing is the real cost control: a week whose answers are all one
/// subject narrows to one candidate, and then nothing is asked at all -- the
/// answer is already decided.
List<TestSummary> attributionCandidates({
  required List<TestSummary> existingTests,
  required Set<String> narrowedTestIds,
}) => narrowedTestIds.isEmpty
    ? existingTests
    : existingTests.where((test) => narrowedTestIds.contains(test.id)).toList();

/// Whether the reviewer has explicitly narrowed the batch to one test.
///
/// **Held as state, never inferred from the candidate count.** A count of one
/// can mean "the reviewer said so" or "only one test happens to be
/// registered" -- and the second is what every first-time user hits. Treating
/// them the same would assign every answer with nobody having chosen
/// anything. **A number does not carry an intention.**
///
/// [candidateCount] is not a second guess at intent: it confirms the test the
/// reviewer chose still exists. `narrowedTestIds` is a selection that can
/// outlive the list it points into -- the registered tests are re-read at the
/// start of every batch -- and without this check, routing against a chosen
/// test that has since been deleted throws (review round 4).
bool reviewerChoseOneTest({
  required Set<String> narrowedTestIds,
  required int candidateCount,
}) => narrowedTestIds.length == 1 && candidateCount == 1;

/// Clears any answer routed or proposed to a test that is no longer in
/// [allowedTestIds].
///
/// An answer already routed to a test the reviewer has just narrowed away has
/// to lose that routing: the dropdown it is shown in no longer offers that
/// value, and leaving it set would both crash the control and keep a
/// decision the reviewer has implicitly withdrawn.
IntakeReviewState dropRoutingOutsideCandidates(
  IntakeReviewState review,
  Set<String> allowedTestIds,
) {
  var next = review;
  for (final file in review.allFiles) {
    final routed = file.answerTestId;
    final proposed = file.proposedAnswerTestId;
    final routedIsStale = routed != null && !allowedTestIds.contains(routed);
    final proposedIsStale =
        proposed != null && !allowedTestIds.contains(proposed);
    if (routedIsStale || proposedIsStale) {
      next = next.withFile(
        file.relativePath,
        (current) => current.copyWith(
          clearAnswerTestId: routedIsStale,
          clearProposedAnswerTestId: proposedIsStale,
        ),
      );
    }
  }
  return next;
}
