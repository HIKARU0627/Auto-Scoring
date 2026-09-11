import 'package:test/test.dart';
import 'package:auto_scoring_api/auto_scoring_api.dart';

/// tests for AiUsageApi
void main() {
  final instance = AutoScoringApi().getAiUsageApi();

  group(AiUsageApi, () {
    // Get Grading Cost
    //
    //Future<GradingCostModel> getGradingCostGradingCostGet() async
    test('test getGradingCostGradingCostGet', () async {
      // TODO
    });

    // Get Monthly Ai Usage
    //
    //Future<MonthlyAiUsageResponse> getMonthlyAiUsageAiUsageMonthlyGet() async
    test('test getMonthlyAiUsageAiUsageMonthlyGet', () async {
      // TODO
    });

    // Get Submission Ai Usage
    //
    //Future<SubmissionAiUsageResponse> getSubmissionAiUsageSubmissionsSubmissionIdAiUsageGet(String submissionId) async
    test('test getSubmissionAiUsageSubmissionsSubmissionIdAiUsageGet',
        () async {
      // TODO
    });

    // Save Grading Cost
    //
    //Future<GradingCostModel> saveGradingCostGradingCostPut(GradingCostModel gradingCostModel) async
    test('test saveGradingCostGradingCostPut', () async {
      // TODO
    });
  });
}
