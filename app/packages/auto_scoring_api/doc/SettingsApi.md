# auto_scoring_api.api.SettingsApi

## Load the API package
```dart
import 'package:auto_scoring_api/api.dart';
```

All URIs are relative to *http://localhost*

Method | HTTP request | Description
------------- | ------------- | -------------
[**clearTransportOrderSettingsTransportOrderDelete**](SettingsApi.md#cleartransportordersettingstransportorderdelete) | **DELETE** /settings/transport-order | Clear Transport Order
[**deleteApiKeySettingsApiKeysSlotIdDelete**](SettingsApi.md#deleteapikeysettingsapikeysslotiddelete) | **DELETE** /settings/api-keys/{slot_id} | Delete Api Key
[**readApiKeysSettingsApiKeysGet**](SettingsApi.md#readapikeyssettingsapikeysget) | **GET** /settings/api-keys | Read Api Keys
[**saveApiKeySettingsApiKeysSlotIdPut**](SettingsApi.md#saveapikeysettingsapikeysslotidput) | **PUT** /settings/api-keys/{slot_id} | Save Api Key
[**saveTransportOrderSettingsTransportOrderPut**](SettingsApi.md#savetransportordersettingstransportorderput) | **PUT** /settings/transport-order | Save Transport Order
[**verifySettingsApiKeysSlotIdVerifyPost**](SettingsApi.md#verifysettingsapikeysslotidverifypost) | **POST** /settings/api-keys/{slot_id}/verify | Verify


# **clearTransportOrderSettingsTransportOrderDelete**
> ApiKeySettingsResponse clearTransportOrderSettingsTransportOrderDelete()

Clear Transport Order

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getSettingsApi();

try {
    final response = api.clearTransportOrderSettingsTransportOrderDelete();
    print(response);
} on DioException catch (e) {
    print('Exception when calling SettingsApi->clearTransportOrderSettingsTransportOrderDelete: $e\n');
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

# **saveTransportOrderSettingsTransportOrderPut**
> ApiKeySettingsResponse saveTransportOrderSettingsTransportOrderPut(saveTransportOrderRequest)

Save Transport Order

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getSettingsApi();
final SaveTransportOrderRequest saveTransportOrderRequest = ; // SaveTransportOrderRequest | 

try {
    final response = api.saveTransportOrderSettingsTransportOrderPut(saveTransportOrderRequest);
    print(response);
} on DioException catch (e) {
    print('Exception when calling SettingsApi->saveTransportOrderSettingsTransportOrderPut: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **saveTransportOrderRequest** | [**SaveTransportOrderRequest**](SaveTransportOrderRequest.md)|  | 

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

