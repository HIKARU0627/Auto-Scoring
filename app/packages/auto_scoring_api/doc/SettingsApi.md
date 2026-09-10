# auto_scoring_api.api.SettingsApi

## Load the API package
```dart
import 'package:auto_scoring_api/api.dart';
```

All URIs are relative to *http://localhost*

Method | HTTP request | Description
------------- | ------------- | -------------
[**deleteApiKeySettingsApiKeysSlotIdDelete**](SettingsApi.md#deleteapikeysettingsapikeysslotiddelete) | **DELETE** /settings/api-keys/{slot_id} | Delete Api Key
[**readApiKeysSettingsApiKeysGet**](SettingsApi.md#readapikeyssettingsapikeysget) | **GET** /settings/api-keys | Read Api Keys
[**saveApiKeySettingsApiKeysSlotIdPut**](SettingsApi.md#saveapikeysettingsapikeysslotidput) | **PUT** /settings/api-keys/{slot_id} | Save Api Key
[**verifySettingsApiKeysSlotIdVerifyPost**](SettingsApi.md#verifysettingsapikeysslotidverifypost) | **POST** /settings/api-keys/{slot_id}/verify | Verify


# **deleteApiKeySettingsApiKeysSlotIdDelete**
> ApiKeySettingsResponse deleteApiKeySettingsApiKeysSlotIdDelete(slotId)

Delete Api Key

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getSettingsApi();
final String slotId = slotId_example; // String | 

try {
    final response = api.deleteApiKeySettingsApiKeysSlotIdDelete(slotId);
    print(response);
} on DioException catch (e) {
    print('Exception when calling SettingsApi->deleteApiKeySettingsApiKeysSlotIdDelete: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **slotId** | **String**|  | 

### Return type

[**ApiKeySettingsResponse**](ApiKeySettingsResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **readApiKeysSettingsApiKeysGet**
> ApiKeySettingsResponse readApiKeysSettingsApiKeysGet()

Read Api Keys

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getSettingsApi();

try {
    final response = api.readApiKeysSettingsApiKeysGet();
    print(response);
} on DioException catch (e) {
    print('Exception when calling SettingsApi->readApiKeysSettingsApiKeysGet: $e\n');
}
```

### Parameters
This endpoint does not need any parameter.

### Return type

[**ApiKeySettingsResponse**](ApiKeySettingsResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **saveApiKeySettingsApiKeysSlotIdPut**
> ApiKeySettingsResponse saveApiKeySettingsApiKeysSlotIdPut(slotId, saveApiKeyRequest)

Save Api Key

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getSettingsApi();
final String slotId = slotId_example; // String | 
final SaveApiKeyRequest saveApiKeyRequest = ; // SaveApiKeyRequest | 

try {
    final response = api.saveApiKeySettingsApiKeysSlotIdPut(slotId, saveApiKeyRequest);
    print(response);
} on DioException catch (e) {
    print('Exception when calling SettingsApi->saveApiKeySettingsApiKeysSlotIdPut: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **slotId** | **String**|  | 
 **saveApiKeyRequest** | [**SaveApiKeyRequest**](SaveApiKeyRequest.md)|  | 

### Return type

[**ApiKeySettingsResponse**](ApiKeySettingsResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **verifySettingsApiKeysSlotIdVerifyPost**
> VerifyApiKeyResponse verifySettingsApiKeysSlotIdVerifyPost(slotId)

Verify

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getSettingsApi();
final String slotId = slotId_example; // String | 

try {
    final response = api.verifySettingsApiKeysSlotIdVerifyPost(slotId);
    print(response);
} on DioException catch (e) {
    print('Exception when calling SettingsApi->verifySettingsApiKeysSlotIdVerifyPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **slotId** | **String**|  | 

### Return type

[**VerifyApiKeyResponse**](VerifyApiKeyResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

