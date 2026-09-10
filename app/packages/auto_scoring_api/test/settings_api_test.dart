import 'package:test/test.dart';
import 'package:auto_scoring_api/auto_scoring_api.dart';

/// tests for SettingsApi
void main() {
  final instance = AutoScoringApi().getSettingsApi();

  group(SettingsApi, () {
    // Delete Api Key
    //
    //Future<ApiKeySettingsResponse> deleteApiKeySettingsApiKeysSlotIdDelete(String slotId) async
    test('test deleteApiKeySettingsApiKeysSlotIdDelete', () async {
      // TODO
    });

    // Read Api Keys
    //
    //Future<ApiKeySettingsResponse> readApiKeysSettingsApiKeysGet() async
    test('test readApiKeysSettingsApiKeysGet', () async {
      // TODO
    });

    // Save Api Key
    //
    //Future<ApiKeySettingsResponse> saveApiKeySettingsApiKeysSlotIdPut(String slotId, SaveApiKeyRequest saveApiKeyRequest) async
    test('test saveApiKeySettingsApiKeysSlotIdPut', () async {
      // TODO
    });

    // Verify
    //
    //Future<VerifyApiKeyResponse> verifySettingsApiKeysSlotIdVerifyPost(String slotId) async
    test('test verifySettingsApiKeysSlotIdVerifyPost', () async {
      // TODO
    });
  });
}
