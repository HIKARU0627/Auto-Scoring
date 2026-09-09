import 'package:test/test.dart';
import 'package:auto_scoring_api/auto_scoring_api.dart';

/// tests for CriteriaApi
void main() {
  final instance = AutoScoringApi().getCriteriaApi();

  group(CriteriaApi, () {
    // Confirm Criteria
    //
    // Sign off on every point value, and write the test's questions.  Refuses while any 配点 is 不明. That is the gate: `Question.points` is the maximum every grade for that question is computed against, so a value nobody read must be typed in by a person before it can reach the database -- never defaulted, never skipped (`ensure_confirmable`).
    //
    //Future<CriteriaResponse> confirmCriteriaTestsTestIdCriteriaConfirmPost(String testId, ConfirmCriteriaRequest confirmCriteriaRequest) async
    test('test confirmCriteriaTestsTestIdCriteriaConfirmPost', () async {
      // TODO
    });

    // Extract Criteria
    //
    // Read the registered 採点基準PDF with the configured model.  Every page is rendered and sent as an image. That is not a fallback for a failed text extraction -- 6 of the 11 measured subjects have no text layer at all, and they are the subjects whose answers are formulae, so the image path is the only one that covers them (``adapters.criteria_extraction.source``).  The result is a **proposal**. It is stored as a DRAFT and nothing downstream reads it until a human confirms it.
    //
    //Future<CriteriaResponse> extractCriteriaTestsTestIdCriteriaExtractPost(String testId) async
    test('test extractCriteriaTestsTestIdCriteriaExtractPost', () async {
      // TODO
    });

    // Get Criteria
    //
    //Future<CriteriaResponse> getCriteriaTestsTestIdCriteriaGet(String testId) async
    test('test getCriteriaTestsTestIdCriteriaGet', () async {
      // TODO
    });

    // Update Criteria
    //
    // Save a reviewed (or entirely hand-entered) question set.  Creates the draft when there is none. That upsert is the escape hatch Issue #95 decision 8 asks for: a subject whose criteria PDF the model could not read at all must still be enterable, and requiring an extraction to succeed first would make the failure unrecoverable on exactly the documents that need the fallback.  Saving does not confirm. ``unreadable_pages`` and the extraction's own ``note`` are carried through untouched -- they describe what the extraction saw, and an edit does not change that.
    //
    //Future<CriteriaResponse> updateCriteriaTestsTestIdCriteriaPut(String testId, UpdateCriteriaRequest updateCriteriaRequest) async
    test('test updateCriteriaTestsTestIdCriteriaPut', () async {
      // TODO
    });
  });
}
