# auto_scoring_api.api.DefaultApi

## Load the API package
```dart
import 'package:auto_scoring_api/api.dart';
```

All URIs are relative to *http://localhost*

Method | HTTP request | Description
------------- | ------------- | -------------
[**createSubmissionTestsTestIdSubmissionsPost**](DefaultApi.md#createsubmissionteststestidsubmissionspost) | **POST** /tests/{test_id}/submissions | Create Submission
[**getSubmissionSubmissionsSubmissionIdGet**](DefaultApi.md#getsubmissionsubmissionssubmissionidget) | **GET** /submissions/{submission_id} | Get Submission
[**gradingAvailabilityGradingAvailabilityGet**](DefaultApi.md#gradingavailabilitygradingavailabilityget) | **GET** /grading/availability | Grading Availability
[**healthzHealthzGet**](DefaultApi.md#healthzhealthzget) | **GET** /healthz | Healthz
[**listSubmissionsTestsTestIdSubmissionsGet**](DefaultApi.md#listsubmissionsteststestidsubmissionsget) | **GET** /tests/{test_id}/submissions | List Submissions
[**listTestsTestsGet**](DefaultApi.md#listteststestsget) | **GET** /tests | List Tests
[**ocrAvailabilityOcrAvailabilityGet**](DefaultApi.md#ocravailabilityocravailabilityget) | **GET** /ocr/availability | Ocr Availability
[**scoreScorePost**](DefaultApi.md#scorescorepost) | **POST** /score | Score


# **createSubmissionTestsTestIdSubmissionsPost**
> SubmissionResponse createSubmissionTestsTestIdSubmissionsPost(testId, file, studentLabel)

Create Submission

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getDefaultApi();
final String testId = testId_example; // String | 
final MultipartFile file = BINARY_DATA_HERE; // MultipartFile | 
final String studentLabel = studentLabel_example; // String | 

try {
    final response = api.createSubmissionTestsTestIdSubmissionsPost(testId, file, studentLabel);
    print(response);
} on DioException catch (e) {
    print('Exception when calling DefaultApi->createSubmissionTestsTestIdSubmissionsPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **testId** | **String**|  | 
 **file** | **MultipartFile**|  | 
 **studentLabel** | **String**|  | [optional] 

### Return type

[**SubmissionResponse**](SubmissionResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: multipart/form-data
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getSubmissionSubmissionsSubmissionIdGet**
> SubmissionResponse getSubmissionSubmissionsSubmissionIdGet(submissionId)

Get Submission

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getDefaultApi();
final String submissionId = submissionId_example; // String | 

try {
    final response = api.getSubmissionSubmissionsSubmissionIdGet(submissionId);
    print(response);
} on DioException catch (e) {
    print('Exception when calling DefaultApi->getSubmissionSubmissionsSubmissionIdGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **submissionId** | **String**|  | 

### Return type

[**SubmissionResponse**](SubmissionResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **gradingAvailabilityGradingAvailabilityGet**
> GradingAvailabilityResponse gradingAvailabilityGradingAvailabilityGet()

Grading Availability

Whether AI grading is configured on this host (Issue #97).  Behind the bearer token, unlike ``/healthz``: it reports on this installation's configuration, which is nobody's business but the app's -- and it is not a liveness probe, so nothing needs it before the handshake has been read.

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getDefaultApi();

try {
    final response = api.gradingAvailabilityGradingAvailabilityGet();
    print(response);
} on DioException catch (e) {
    print('Exception when calling DefaultApi->gradingAvailabilityGradingAvailabilityGet: $e\n');
}
```

### Parameters
This endpoint does not need any parameter.

### Return type

[**GradingAvailabilityResponse**](GradingAvailabilityResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **healthzHealthzGet**
> BuiltMap<String, String> healthzHealthzGet()

Healthz

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getDefaultApi();

try {
    final response = api.healthzHealthzGet();
    print(response);
} on DioException catch (e) {
    print('Exception when calling DefaultApi->healthzHealthzGet: $e\n');
}
```

### Parameters
This endpoint does not need any parameter.

### Return type

**BuiltMap&lt;String, String&gt;**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **listSubmissionsTestsTestIdSubmissionsGet**
> BuiltList<SubmissionResponse> listSubmissionsTestsTestIdSubmissionsGet(testId)

List Submissions

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getDefaultApi();
final String testId = testId_example; // String | 

try {
    final response = api.listSubmissionsTestsTestIdSubmissionsGet(testId);
    print(response);
} on DioException catch (e) {
    print('Exception when calling DefaultApi->listSubmissionsTestsTestIdSubmissionsGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **testId** | **String**|  | 

### Return type

[**BuiltList&lt;SubmissionResponse&gt;**](SubmissionResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **listTestsTestsGet**
> BuiltList<TestSummary> listTestsTestsGet()

List Tests

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getDefaultApi();

try {
    final response = api.listTestsTestsGet();
    print(response);
} on DioException catch (e) {
    print('Exception when calling DefaultApi->listTestsTestsGet: $e\n');
}
```

### Parameters
This endpoint does not need any parameter.

### Return type

[**BuiltList&lt;TestSummary&gt;**](TestSummary.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **ocrAvailabilityOcrAvailabilityGet**
> OcrAvailabilityResponse ocrAvailabilityOcrAvailabilityGet()

Ocr Availability

Whether OCR is configured on this host (Issue #114).  Behind the bearer token for the same reason as ``/grading/availability``: it reports on this installation's configuration, and it is not a liveness probe.

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getDefaultApi();

try {
    final response = api.ocrAvailabilityOcrAvailabilityGet();
    print(response);
} on DioException catch (e) {
    print('Exception when calling DefaultApi->ocrAvailabilityOcrAvailabilityGet: $e\n');
}
```

### Parameters
This endpoint does not need any parameter.

### Return type

[**OcrAvailabilityResponse**](OcrAvailabilityResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **scoreScorePost**
> ScoreResponse scoreScorePost(scoreRequest)

Score

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getDefaultApi();
final ScoreRequest scoreRequest = ; // ScoreRequest | 

try {
    final response = api.scoreScorePost(scoreRequest);
    print(response);
} on DioException catch (e) {
    print('Exception when calling DefaultApi->scoreScorePost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **scoreRequest** | [**ScoreRequest**](ScoreRequest.md)|  | 

### Return type

[**ScoreResponse**](ScoreResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

