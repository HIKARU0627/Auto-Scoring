import 'package:test/test.dart';
import 'package:auto_scoring_api/auto_scoring_api.dart';

/// tests for ExportApi
void main() {
  final instance = AutoScoringApi().getExportApi();

  group(ExportApi, () {
    // List Exports
    //
    //Future<BuiltList<ExportResponse>> listExportsSubmissionsSubmissionIdExportsGet(String submissionId) async
    test('test listExportsSubmissionsSubmissionIdExportsGet', () async {
      // TODO
    });

    // Request Export
    //
    //Future<ExportRequestResponse> requestExportSubmissionsSubmissionIdExportPost(String submissionId) async
    test('test requestExportSubmissionsSubmissionIdExportPost', () async {
      // TODO
    });
  });
}
