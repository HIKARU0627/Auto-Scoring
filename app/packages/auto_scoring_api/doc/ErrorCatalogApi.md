# auto_scoring_api.api.ErrorCatalogApi

## Load the API package
```dart
import 'package:auto_scoring_api/api.dart';
```

All URIs are relative to *http://localhost*

Method | HTTP request | Description
------------- | ------------- | -------------
[**getErrorCatalogTestsTestIdErrorCatalogGet**](ErrorCatalogApi.md#geterrorcatalogteststestiderrorcatalogget) | **GET** /tests/{test_id}/error-catalog | Get Error Catalog
[**importErrorCatalogTestsTestIdErrorCatalogImportPost**](ErrorCatalogApi.md#importerrorcatalogteststestiderrorcatalogimportpost) | **POST** /tests/{test_id}/error-catalog/import | Import Error Catalog
[**saveErrorCatalogTestsTestIdErrorCatalogPut**](ErrorCatalogApi.md#saveerrorcatalogteststestiderrorcatalogput) | **PUT** /tests/{test_id}/error-catalog | Save Error Catalog


# **getErrorCatalogTestsTestIdErrorCatalogGet**
> ErrorCatalogResponse getErrorCatalogTestsTestIdErrorCatalogGet(testId)

Get Error Catalog

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getErrorCatalogApi();
final String testId = testId_example; // String | 

try {
    final response = api.getErrorCatalogTestsTestIdErrorCatalogGet(testId);
    print(response);
} on DioException catch (e) {
    print('Exception when calling ErrorCatalogApi->getErrorCatalogTestsTestIdErrorCatalogGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **testId** | **String**|  | 

### Return type

[**ErrorCatalogResponse**](ErrorCatalogResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **importErrorCatalogTestsTestIdErrorCatalogImportPost**
> ErrorCatalogResponse importErrorCatalogTestsTestIdErrorCatalogImportPost(testId, importErrorCatalogRequest)

Import Error Catalog

Read the registered 添削資料 Excel into the persisted catalogue.  The three \"we have no catalogue\" states are refused with a 409 naming which one it is, and an unreadable file is recorded (and answered 422) rather than returned as an empty catalogue -- the distinction Issue #106 was written to preserve.

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getErrorCatalogApi();
final String testId = testId_example; // String | 
final ImportErrorCatalogRequest importErrorCatalogRequest = ; // ImportErrorCatalogRequest | 

try {
    final response = api.importErrorCatalogTestsTestIdErrorCatalogImportPost(testId, importErrorCatalogRequest);
    print(response);
} on DioException catch (e) {
    print('Exception when calling ErrorCatalogApi->importErrorCatalogTestsTestIdErrorCatalogImportPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **testId** | **String**|  | 
 **importErrorCatalogRequest** | [**ImportErrorCatalogRequest**](ImportErrorCatalogRequest.md)|  | 

### Return type

[**ErrorCatalogResponse**](ErrorCatalogResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **saveErrorCatalogTestsTestIdErrorCatalogPut**
> ErrorCatalogResponse saveErrorCatalogTestsTestIdErrorCatalogPut(testId, saveErrorCatalogRequest)

Save Error Catalog

Save a reviewed row set, refused if it is based on a stale revision.

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getErrorCatalogApi();
final String testId = testId_example; // String | 
final SaveErrorCatalogRequest saveErrorCatalogRequest = ; // SaveErrorCatalogRequest | 

try {
    final response = api.saveErrorCatalogTestsTestIdErrorCatalogPut(testId, saveErrorCatalogRequest);
    print(response);
} on DioException catch (e) {
    print('Exception when calling ErrorCatalogApi->saveErrorCatalogTestsTestIdErrorCatalogPut: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **testId** | **String**|  | 
 **saveErrorCatalogRequest** | [**SaveErrorCatalogRequest**](SaveErrorCatalogRequest.md)|  | 

### Return type

[**ErrorCatalogResponse**](ErrorCatalogResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

