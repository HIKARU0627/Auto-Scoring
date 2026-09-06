import 'package:test/test.dart';
import 'package:auto_scoring_api/auto_scoring_api.dart';

/// tests for DependencyGraphApi
void main() {
  final instance = AutoScoringApi().getDependencyGraphApi();

  group(DependencyGraphApi, () {
    // Analyze
    //
    //Future<DependencyGraphResponse> analyzeTestsTestIdDependencyGraphAnalyzePost(String testId, AnalyzeRequest analyzeRequest) async
    test('test analyzeTestsTestIdDependencyGraphAnalyzePost', () async {
      // TODO
    });

    // Confirm
    //
    //Future<DependencyGraphResponse> confirmTestsTestIdDependencyGraphConfirmPost(String testId, ConfirmRequest confirmRequest) async
    test('test confirmTestsTestIdDependencyGraphConfirmPost', () async {
      // TODO
    });

    // Get Latest
    //
    //Future<DependencyGraphResponse> getLatestTestsTestIdDependencyGraphGet(String testId) async
    test('test getLatestTestsTestIdDependencyGraphGet', () async {
      // TODO
    });

    // List Versions
    //
    //Future<BuiltList<DependencyGraphResponse>> listVersionsTestsTestIdDependencyGraphVersionsGet(String testId) async
    test('test listVersionsTestsTestIdDependencyGraphVersionsGet', () async {
      // TODO
    });
  });
}
