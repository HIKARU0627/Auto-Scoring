import 'package:test/test.dart';
import 'package:auto_scoring_api/auto_scoring_api.dart';

/// tests for ErrorCatalogApi
void main() {
  final instance = AutoScoringApi().getErrorCatalogApi();

  group(ErrorCatalogApi, () {
    // Get Error Catalog
    //
    //Future<ErrorCatalogResponse> getErrorCatalogTestsTestIdErrorCatalogGet(String testId) async
    test('test getErrorCatalogTestsTestIdErrorCatalogGet', () async {
      // TODO
    });

    // Import Error Catalog
    //
    // Read the registered 添削資料 Excel into the persisted catalogue.  The three \"we have no catalogue\" states are refused with a 409 naming which one it is, and an unreadable file is recorded (and answered 422) rather than returned as an empty catalogue -- the distinction Issue #106 was written to preserve.
    //
    //Future<ErrorCatalogResponse> importErrorCatalogTestsTestIdErrorCatalogImportPost(String testId, ImportErrorCatalogRequest importErrorCatalogRequest) async
    test('test importErrorCatalogTestsTestIdErrorCatalogImportPost', () async {
      // TODO
    });

    // Save Error Catalog
    //
    // Save a reviewed row set, refused if it is based on a stale revision.
    //
    //Future<ErrorCatalogResponse> saveErrorCatalogTestsTestIdErrorCatalogPut(String testId, SaveErrorCatalogRequest saveErrorCatalogRequest) async
    test('test saveErrorCatalogTestsTestIdErrorCatalogPut', () async {
      // TODO
    });
  });
}
