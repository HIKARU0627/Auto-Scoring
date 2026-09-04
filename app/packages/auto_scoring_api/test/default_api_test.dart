import 'package:test/test.dart';
import 'package:auto_scoring_api/auto_scoring_api.dart';

/// tests for DefaultApi
void main() {
  final instance = AutoScoringApi().getDefaultApi();

  group(DefaultApi, () {
    // Healthz
    //
    //Future<BuiltMap<String, String>> healthzHealthzGet() async
    test('test healthzHealthzGet', () async {
      // TODO
    });

    // Score
    //
    //Future<ScoreResponse> scoreScorePost(ScoreRequest scoreRequest) async
    test('test scoreScorePost', () async {
      // TODO
    });
  });
}
