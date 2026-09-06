import 'package:test/test.dart';
import 'package:auto_scoring_api/auto_scoring_api.dart';

/// tests for ReviewApi
void main() {
  final instance = AutoScoringApi().getReviewApi();

  group(ReviewApi, () {
    // Get Source Pdf
    //
    //Future<Uint8List> getSourcePdfSubmissionsSubmissionIdSourcePdfGet(String submissionId) async
    test('test getSourcePdfSubmissionsSubmissionIdSourcePdfGet', () async {
      // TODO
    });

    // List Annotations
    //
    //Future<BuiltList<AnnotationResponse>> listAnnotationsSubmissionsSubmissionIdQuestionsQuestionIdAnnotationsGet(String submissionId, String questionId) async
    test(
        'test listAnnotationsSubmissionsSubmissionIdQuestionsQuestionIdAnnotationsGet',
        () async {
      // TODO
    });

    // List Grades
    //
    //Future<BuiltList<GradeResultResponse>> listGradesSubmissionsSubmissionIdQuestionsQuestionIdGradesGet(String submissionId, String questionId) async
    test('test listGradesSubmissionsSubmissionIdQuestionsQuestionIdGradesGet',
        () async {
      // TODO
    });

    // List Questions
    //
    //Future<BuiltList<QuestionResponse>> listQuestionsTestsTestIdQuestionsGet(String testId) async
    test('test listQuestionsTestsTestIdQuestionsGet', () async {
      // TODO
    });
  });
}
