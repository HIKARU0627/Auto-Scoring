import 'package:test/test.dart';
import 'package:auto_scoring_api/auto_scoring_api.dart';

/// tests for RecognitionsApi
void main() {
  final instance = AutoScoringApi().getRecognitionsApi();

  group(RecognitionsApi, () {
    // Create Manual Recognition
    //
    //Future<RecognitionResponse> createManualRecognitionSubmissionsSubmissionIdQuestionsQuestionIdRecognitionsPost(String submissionId, String questionId, ManualRecognitionRequest manualRecognitionRequest) async
    test(
        'test createManualRecognitionSubmissionsSubmissionIdQuestionsQuestionIdRecognitionsPost',
        () async {
      // TODO
    });

    // Get Answer Image
    //
    //Future<JsonObject> getAnswerImageSubmissionsSubmissionIdQuestionsQuestionIdAnswerImageGet(String submissionId, String questionId) async
    test(
        'test getAnswerImageSubmissionsSubmissionIdQuestionsQuestionIdAnswerImageGet',
        () async {
      // TODO
    });

    // List Recognitions
    //
    //Future<BuiltList<RecognitionResponse>> listRecognitionsSubmissionsSubmissionIdQuestionsQuestionIdRecognitionsGet(String submissionId, String questionId) async
    test(
        'test listRecognitionsSubmissionsSubmissionIdQuestionsQuestionIdRecognitionsGet',
        () async {
      // TODO
    });
  });
}
