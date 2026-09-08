# auto_scoring_api.api.CriteriaApi

## Load the API package
```dart
import 'package:auto_scoring_api/api.dart';
```

All URIs are relative to *http://localhost*

Method | HTTP request | Description
------------- | ------------- | -------------
[**confirmCriteriaTestsTestIdCriteriaConfirmPost**](CriteriaApi.md#confirmcriteriateststestidcriteriaconfirmpost) | **POST** /tests/{test_id}/criteria/confirm | Confirm Criteria
[**estimateCriteriaTestsTestIdCriteriaEstimateGet**](CriteriaApi.md#estimatecriteriateststestidcriteriaestimateget) | **GET** /tests/{test_id}/criteria/estimate | Estimate Criteria
[**extractCriteriaTestsTestIdCriteriaExtractPost**](CriteriaApi.md#extractcriteriateststestidcriteriaextractpost) | **POST** /tests/{test_id}/criteria/extract | Extract Criteria
[**getCriteriaTestsTestIdCriteriaGet**](CriteriaApi.md#getcriteriateststestidcriteriaget) | **GET** /tests/{test_id}/criteria | Get Criteria
[**updateCriteriaTestsTestIdCriteriaPut**](CriteriaApi.md#updatecriteriateststestidcriteriaput) | **PUT** /tests/{test_id}/criteria | Update Criteria


# **confirmCriteriaTestsTestIdCriteriaConfirmPost**
> CriteriaResponse confirmCriteriaTestsTestIdCriteriaConfirmPost(testId, confirmCriteriaRequest)

Confirm Criteria

Sign off on every point value, and write the test's questions.  Refuses while any 配点 is 不明. That is the gate: `Question.points` is the maximum every grade for that question is computed against, so a value nobody read must be typed in by a person before it can reach the database -- never defaulted, never skipped (`ensure_confirmable`).

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getCriteriaApi();
final String testId = testId_example; // String | 
final ConfirmCriteriaRequest confirmCriteriaRequest = ; // ConfirmCriteriaRequest | 

try {
    final response = api.confirmCriteriaTestsTestIdCriteriaConfirmPost(testId, confirmCriteriaRequest);
    print(response);
} on DioException catch (e) {
    print('Exception when calling CriteriaApi->confirmCriteriaTestsTestIdCriteriaConfirmPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **testId** | **String**|  | 
 **confirmCriteriaRequest** | [**ConfirmCriteriaRequest**](ConfirmCriteriaRequest.md)|  | 

### Return type

[**CriteriaResponse**](CriteriaResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **estimateCriteriaTestsTestIdCriteriaEstimateGet**
> CriteriaEstimateResponse estimateCriteriaTestsTestIdCriteriaEstimateGet(testId)

Estimate Criteria

How many pages an extraction would send, and what that would cost.  Reads only the page count -- no rendering, no provider call, no charge. Takes the shared PDFium lock anyway: ``page_count`` opens the document, and this app serializes every PDF read for the reason `build_criteria_router` documents.

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getCriteriaApi();
final String testId = testId_example; // String | 

try {
    final response = api.estimateCriteriaTestsTestIdCriteriaEstimateGet(testId);
    print(response);
} on DioException catch (e) {
    print('Exception when calling CriteriaApi->estimateCriteriaTestsTestIdCriteriaEstimateGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **testId** | **String**|  | 

### Return type

[**CriteriaEstimateResponse**](CriteriaEstimateResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **extractCriteriaTestsTestIdCriteriaExtractPost**
> CriteriaResponse extractCriteriaTestsTestIdCriteriaExtractPost(testId)

Extract Criteria

Read the registered 採点基準PDF with the configured model.  Every page is rendered and sent as an image. That is not a fallback for a failed text extraction -- 6 of the 11 measured subjects have no text layer at all, and they are the subjects whose answers are formulae, so the image path is the only one that covers them (``adapters.criteria_extraction.source``).  The result is a **proposal**. It is stored as a DRAFT and nothing downstream reads it until a human confirms it.  Deliberately a **synchronous** handler, like ``/profile/analyze``: FastAPI runs those in its worker threadpool, so the per-test lock below and the minute-long provider call are held off the event loop. Written as ``async def`` with ``await to_thread(...)`` inside, the two blocking calls would move off the loop but ``with test_locks.for_test(...)`` would not -- a second extraction of the same test would then block the whole sidecar for as long as the first one takes to answer (code review of this Issue).

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getCriteriaApi();
final String testId = testId_example; // String | 

try {
    final response = api.extractCriteriaTestsTestIdCriteriaExtractPost(testId);
    print(response);
} on DioException catch (e) {
    print('Exception when calling CriteriaApi->extractCriteriaTestsTestIdCriteriaExtractPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **testId** | **String**|  | 

### Return type

[**CriteriaResponse**](CriteriaResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getCriteriaTestsTestIdCriteriaGet**
> CriteriaResponse getCriteriaTestsTestIdCriteriaGet(testId)

Get Criteria

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getCriteriaApi();
final String testId = testId_example; // String | 

try {
    final response = api.getCriteriaTestsTestIdCriteriaGet(testId);
    print(response);
} on DioException catch (e) {
    print('Exception when calling CriteriaApi->getCriteriaTestsTestIdCriteriaGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **testId** | **String**|  | 

### Return type

[**CriteriaResponse**](CriteriaResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **updateCriteriaTestsTestIdCriteriaPut**
> CriteriaResponse updateCriteriaTestsTestIdCriteriaPut(testId, updateCriteriaRequest)

Update Criteria

Save a reviewed (or entirely hand-entered) question set.  Creates the draft when there is none. That upsert is the escape hatch Issue #95 decision 8 asks for: a subject whose criteria PDF the model could not read at all must still be enterable, and requiring an extraction to succeed first would make the failure unrecoverable on exactly the documents that need the fallback.  Saving does not confirm. ``unreadable_pages`` and the extraction's own ``note`` are carried through untouched -- they describe what the extraction saw, and an edit does not change that.

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getCriteriaApi();
final String testId = testId_example; // String | 
final UpdateCriteriaRequest updateCriteriaRequest = ; // UpdateCriteriaRequest | 

try {
    final response = api.updateCriteriaTestsTestIdCriteriaPut(testId, updateCriteriaRequest);
    print(response);
} on DioException catch (e) {
    print('Exception when calling CriteriaApi->updateCriteriaTestsTestIdCriteriaPut: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **testId** | **String**|  | 
 **updateCriteriaRequest** | [**UpdateCriteriaRequest**](UpdateCriteriaRequest.md)|  | 

### Return type

[**CriteriaResponse**](CriteriaResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

