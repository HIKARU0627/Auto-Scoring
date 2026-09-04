# auto_scoring_api.api.DependencyGraphApi

## Load the API package
```dart
import 'package:auto_scoring_api/api.dart';
```

All URIs are relative to *http://localhost*

Method | HTTP request | Description
------------- | ------------- | -------------
[**analyzeTestsTestIdDependencyGraphAnalyzePost**](DependencyGraphApi.md#analyzeteststestiddependencygraphanalyzepost) | **POST** /tests/{test_id}/dependency-graph/analyze | Analyze
[**confirmTestsTestIdDependencyGraphConfirmPost**](DependencyGraphApi.md#confirmteststestiddependencygraphconfirmpost) | **POST** /tests/{test_id}/dependency-graph/confirm | Confirm
[**getLatestTestsTestIdDependencyGraphGet**](DependencyGraphApi.md#getlatestteststestiddependencygraphget) | **GET** /tests/{test_id}/dependency-graph | Get Latest
[**listVersionsTestsTestIdDependencyGraphVersionsGet**](DependencyGraphApi.md#listversionsteststestiddependencygraphversionsget) | **GET** /tests/{test_id}/dependency-graph/versions | List Versions


# **analyzeTestsTestIdDependencyGraphAnalyzePost**
> DependencyGraphResponse analyzeTestsTestIdDependencyGraphAnalyzePost(testId, analyzeRequest)

Analyze

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getDependencyGraphApi();
final String testId = testId_example; // String | 
final AnalyzeRequest analyzeRequest = ; // AnalyzeRequest | 

try {
    final response = api.analyzeTestsTestIdDependencyGraphAnalyzePost(testId, analyzeRequest);
    print(response);
} on DioException catch (e) {
    print('Exception when calling DependencyGraphApi->analyzeTestsTestIdDependencyGraphAnalyzePost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **testId** | **String**|  | 
 **analyzeRequest** | [**AnalyzeRequest**](AnalyzeRequest.md)|  | 

### Return type

[**DependencyGraphResponse**](DependencyGraphResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **confirmTestsTestIdDependencyGraphConfirmPost**
> DependencyGraphResponse confirmTestsTestIdDependencyGraphConfirmPost(testId, confirmRequest)

Confirm

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getDependencyGraphApi();
final String testId = testId_example; // String | 
final ConfirmRequest confirmRequest = ; // ConfirmRequest | 

try {
    final response = api.confirmTestsTestIdDependencyGraphConfirmPost(testId, confirmRequest);
    print(response);
} on DioException catch (e) {
    print('Exception when calling DependencyGraphApi->confirmTestsTestIdDependencyGraphConfirmPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **testId** | **String**|  | 
 **confirmRequest** | [**ConfirmRequest**](ConfirmRequest.md)|  | 

### Return type

[**DependencyGraphResponse**](DependencyGraphResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getLatestTestsTestIdDependencyGraphGet**
> DependencyGraphResponse getLatestTestsTestIdDependencyGraphGet(testId)

Get Latest

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getDependencyGraphApi();
final String testId = testId_example; // String | 

try {
    final response = api.getLatestTestsTestIdDependencyGraphGet(testId);
    print(response);
} on DioException catch (e) {
    print('Exception when calling DependencyGraphApi->getLatestTestsTestIdDependencyGraphGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **testId** | **String**|  | 

### Return type

[**DependencyGraphResponse**](DependencyGraphResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **listVersionsTestsTestIdDependencyGraphVersionsGet**
> BuiltList<DependencyGraphResponse> listVersionsTestsTestIdDependencyGraphVersionsGet(testId)

List Versions

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getDependencyGraphApi();
final String testId = testId_example; // String | 

try {
    final response = api.listVersionsTestsTestIdDependencyGraphVersionsGet(testId);
    print(response);
} on DioException catch (e) {
    print('Exception when calling DependencyGraphApi->listVersionsTestsTestIdDependencyGraphVersionsGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **testId** | **String**|  | 

### Return type

[**BuiltList&lt;DependencyGraphResponse&gt;**](DependencyGraphResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

