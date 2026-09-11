# auto_scoring_api.api.AiUsageApi

## Load the API package
```dart
import 'package:auto_scoring_api/api.dart';
```

All URIs are relative to *http://localhost*

Method | HTTP request | Description
------------- | ------------- | -------------
[**getGradingCostGradingCostGet**](AiUsageApi.md#getgradingcostgradingcostget) | **GET** /grading-cost | Get Grading Cost
[**getMonthlyAiUsageAiUsageMonthlyGet**](AiUsageApi.md#getmonthlyaiusageaiusagemonthlyget) | **GET** /ai-usage/monthly | Get Monthly Ai Usage
[**getSubmissionAiUsageSubmissionsSubmissionIdAiUsageGet**](AiUsageApi.md#getsubmissionaiusagesubmissionssubmissionidaiusageget) | **GET** /submissions/{submission_id}/ai-usage | Get Submission Ai Usage
[**saveGradingCostGradingCostPut**](AiUsageApi.md#savegradingcostgradingcostput) | **PUT** /grading-cost | Save Grading Cost


# **getGradingCostGradingCostGet**
> GradingCostModel getGradingCostGradingCostGet()

Get Grading Cost

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getAiUsageApi();

try {
    final response = api.getGradingCostGradingCostGet();
    print(response);
} on DioException catch (e) {
    print('Exception when calling AiUsageApi->getGradingCostGradingCostGet: $e\n');
}
```

### Parameters
This endpoint does not need any parameter.

### Return type

[**GradingCostModel**](GradingCostModel.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getMonthlyAiUsageAiUsageMonthlyGet**
> MonthlyAiUsageResponse getMonthlyAiUsageAiUsageMonthlyGet()

Get Monthly Ai Usage

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getAiUsageApi();

try {
    final response = api.getMonthlyAiUsageAiUsageMonthlyGet();
    print(response);
} on DioException catch (e) {
    print('Exception when calling AiUsageApi->getMonthlyAiUsageAiUsageMonthlyGet: $e\n');
}
```

### Parameters
This endpoint does not need any parameter.

### Return type

[**MonthlyAiUsageResponse**](MonthlyAiUsageResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getSubmissionAiUsageSubmissionsSubmissionIdAiUsageGet**
> SubmissionAiUsageResponse getSubmissionAiUsageSubmissionsSubmissionIdAiUsageGet(submissionId)

Get Submission Ai Usage

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getAiUsageApi();
final String submissionId = submissionId_example; // String | 

try {
    final response = api.getSubmissionAiUsageSubmissionsSubmissionIdAiUsageGet(submissionId);
    print(response);
} on DioException catch (e) {
    print('Exception when calling AiUsageApi->getSubmissionAiUsageSubmissionsSubmissionIdAiUsageGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **submissionId** | **String**|  | 

### Return type

[**SubmissionAiUsageResponse**](SubmissionAiUsageResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **saveGradingCostGradingCostPut**
> GradingCostModel saveGradingCostGradingCostPut(gradingCostModel)

Save Grading Cost

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getAiUsageApi();
final GradingCostModel gradingCostModel = ; // GradingCostModel | 

try {
    final response = api.saveGradingCostGradingCostPut(gradingCostModel);
    print(response);
} on DioException catch (e) {
    print('Exception when calling AiUsageApi->saveGradingCostGradingCostPut: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **gradingCostModel** | [**GradingCostModel**](GradingCostModel.md)|  | 

### Return type

[**GradingCostModel**](GradingCostModel.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

